"""
Il controllo giornaliero: quello che l'app fa ogni sera, dopo la chiusura dei mercati.

Segue le STESSE regole del backtest, nello stesso ordine:
  0. L'app è bloccata (limite o emergenza)? Allora non fa niente.
  1. Il conto ha superato un limite di perdita? Allora si blocca (e vende tutto).
  2. Qualche stop loss è scattato durante il giorno? Lo annota e mette il titolo "in castigo".
  3. Vende i titoli dei settori con il termometro "freddo".
  4. Il primo giorno del mese: rifà la classifica e riduce chi supera il 5%.
  5. Compra i titoli nuovi, ognuno con il suo stop loss attaccato.
  6. Controlla che ogni posizione abbia il suo stop loss presso il broker.

Gli ordini sono "a mercato" e vengono eseguiti all'apertura del giorno dopo.

MODALITÀ PROVA (predefinita): calcola e mostra gli ordini, ma NON li invia.
Per inviarli davvero al conto demo serve esegui=True.
"""

import logging
import math
from datetime import datetime

import pandas as pd

from ..broker import Broker
from ..rischio import GestoreRischio
from ..rischio.emergenza import blocca_per_limite, puo_operare, scrivi_registro
from ..strategia import StrategiaTermometro
from .memoria import Memoria, Registro, StoricoValori

log = logging.getLogger(__name__)


class CicloGiornaliero:

    def __init__(self, config: dict, broker: Broker, prezzi: pd.DataFrame, esegui: bool = False):
        self.config = config
        self.broker = broker
        self.esegui = esegui
        self.prezzi = prezzi.ffill()
        self.oggi = self.prezzi.index[-1]                 # ultima chiusura disponibile
        self.n_oggi = len(self.prezzi.index) - 1
        self.strategia = StrategiaTermometro(config, self.prezzi)
        self.rischio = GestoreRischio(config)
        self.memoria = Memoria.carica(config)
        self.storico = StoricoValori(config)
        self.registro = Registro(config)
        self.margine = config["esecuzione"]["margine_prezzo_pct"] / 100
        self.gruppo_di = {az: g for g, lista in config["azioni"].items() for az in lista}

        self.ordini: list[dict] = []      # gli ordini decisi oggi (inviati solo se esegui=True)
        self.messaggi: list[str] = []     # il "diario" della serata, da mostrare a schermo

    # ------------------------------------------------------------------
    def _msg(self, testo: str):
        self.messaggi.append(testo)
        log.info(testo)

    def _prezzo(self, ticker: str) -> float:
        return float(self.prezzi.at[self.oggi, ticker])

    def _stop(self, prezzo_base: float) -> dict:
        r = self.rischio
        return {"tipo": "trailing" if r.trailing else "fisso", "percentuale": r.stop_pct * 100,
                "livello": prezzo_base * (1 - r.stop_pct)}

    def _ordine(self, operazione: str, ticker: str, quantita: int, motivo: str, posizione_attuale: int = 0):
        """Registra l'ordine e, solo se esegui=True, lo invia davvero al broker."""
        prezzo = self._prezzo(ticker)
        id_ordine = "(prova)"
        if self.esegui:
            if operazione == "ACQUISTO":
                id_ordine = self.broker.compra(ticker, quantita, self._stop(prezzo), motivo)
            else:
                # PRIMA si cancella lo stop, altrimenti stop + vendita venderebbero due volte
                self.broker.cancella_stop(ticker)
                id_ordine = self.broker.vendi(ticker, quantita, motivo)
                rimaste = posizione_attuale - quantita
                if rimaste > 0:                      # vendita parziale: rimetto lo stop sul resto
                    self.broker.metti_stop(ticker, rimaste, self._stop(prezzo))
            self.registro.scrivi_operazione({
                "data_ora": datetime.now().isoformat(timespec="seconds"), "titolo": ticker,
                "operazione": operazione, "quantita": quantita, "prezzo_riferimento": round(prezzo, 2),
                "motivo": motivo, "id_ordine": id_ordine,
            })
        self.ordini.append({"operazione": operazione, "titolo": ticker, "quantita": quantita,
                            "prezzo": round(prezzo, 2), "motivo": motivo})

    # ------------------------------------------------------------------
    def esegui_ciclo(self):
        self._msg(f"Controllo del {self.oggi.date()} — modalità {'ESECUZIONE (conto demo)' if self.esegui else 'PROVA (nessun ordine inviato)'}")

        # Le esecuzioni di oggi (prezzi veri degli ordini) finiscono nel registro
        if self.esegui:
            nuove = self.registro.aggiorna_esecuzioni(self.broker.esecuzioni())
            if nuove:
                self._msg(f"Registrate {nuove} esecuzioni nuove in {self.registro.file_esecuzioni.name}")

        # 0) App bloccata?
        ok, descrizione = puo_operare(self.config)
        if not ok:
            self._msg(f"App {descrizione}. Nessun ordine. Per ripartire: python -m scripts.rischio sblocca")
            return

        conto = self.broker.conto()
        tutte = self.broker.posizioni()
        posizioni = {t: p for t, p in tutte.items() if t in self.gruppo_di}
        estranee = sorted(set(tutte) - set(posizioni))
        if estranee:
            self._msg(f"Titoli nel conto che non fanno parte della strategia (non li tocco): {estranee}")
        self._msg(f"Valore del conto: {conto['valore_totale']:,.0f} $ — cassa: {conto['cassa']:,.0f} $ — posizioni: {len(posizioni)}")

        # 1) Limiti di perdita
        if self._limiti_superati(conto["valore_totale"], posizioni):
            return

        # 2) Stop loss scattati da ieri a oggi
        self._rileva_stop(posizioni)

        # 3-5) Decisioni della strategia
        vendute = self._vendite_e_ribilanciamento(posizioni, conto)
        self._acquisti(posizioni, conto, vendute)

        # 6) Ogni posizione rimasta deve avere il suo stop loss presso il broker
        self._controlla_stop_presenti(posizioni, vendute)

        if self.esegui:
            self.memoria.posizioni_ieri = {t: p["quantita"] for t, p in posizioni.items()}
            self.memoria.vendite_inviate = sorted(t for t, q in vendute.items() if q >= posizioni[t]["quantita"])
            self.memoria.salva(self.config)
            self.storico.aggiungi(self.oggi, conto["valore_totale"])
        if not self.ordini:
            self._msg("Nessun ordine da inviare oggi: tutto in ordine.")

    # ------------------------------------------------------------------
    def _limiti_superati(self, valore: float, posizioni: dict) -> bool:
        """Rilegge lo storico del conto e verifica i limiti di perdita giornaliera e mensile."""
        verifica = GestoreRischio(self.config)
        for giorno, v in self.storico.leggi().items():
            if giorno < self.oggi:
                verifica.controlla_limiti(giorno, v)
        superato = verifica.controlla_limiti(self.oggi, valore)
        if not superato:
            return False

        tipo, motivo = superato
        self._msg(f"⛔ LIMITE SUPERATO ({tipo}): {motivo}")
        chiudi = self.config["rischio"]["chiudi_posizioni_al_blocco"]
        for ticker, p in posizioni.items():
            if chiudi:
                self.ordini.append({"operazione": "VENDITA", "titolo": ticker, "quantita": p["quantita"],
                                    "prezzo": round(self._prezzo(ticker), 2), "motivo": f"BLOCCO {tipo}: {motivo}"})
        if self.esegui:
            blocca_per_limite(self.config, tipo, motivo)
            self.storico.aggiungi(self.oggi, valore)
            if chiudi:
                for chiusa in self.broker.chiudi_tutto(f"BLOCCO {tipo}: {motivo}"):
                    self.registro.scrivi_operazione({
                        "data_ora": datetime.now().isoformat(timespec="seconds"), "titolo": chiusa["titolo"],
                        "operazione": "VENDITA", "quantita": chiusa["quantita"], "prezzo_riferimento": "",
                        "motivo": f"BLOCCO {tipo}: {motivo}", "id_ordine": chiusa["id"],
                    })
        self._msg("L'app è ora BLOCCATA. Per ripartire: python -m scripts.rischio sblocca")
        return True

    def _rileva_stop(self, posizioni: dict):
        """Un titolo che c'era ieri, che oggi non c'è più e che NON abbiamo venduto noi = stop loss scattato."""
        for ticker in self.memoria.posizioni_ieri:
            if ticker not in posizioni and ticker not in self.memoria.vendite_inviate:
                self._msg(f"STOP LOSS scattato su {ticker}: non lo ricompro per {self.rischio.giorni_attesa} giorni di borsa")
                self.memoria.stop_recenti[ticker] = str(self.oggi.date())
                if self.esegui:
                    self.registro.scrivi_operazione({
                        "data_ora": datetime.now().isoformat(timespec="seconds"), "titolo": ticker,
                        "operazione": "VENDITA", "quantita": self.memoria.posizioni_ieri[ticker],
                        "prezzo_riferimento": "", "motivo": "STOP LOSS eseguito dal broker", "id_ordine": "",
                    })
                    scrivi_registro(f"STOP LOSS scattato su {ticker}")
        # Ricarico gli stop recenti nel gestore, contando i giorni di borsa trascorsi
        for ticker, data in self.memoria.stop_recenti.items():
            n = int(self.prezzi.index.searchsorted(pd.Timestamp(data)))
            self.rischio.registra_stop(ticker, n)
        # ...e dimentico quelli il cui "castigo" è finito
        self.memoria.stop_recenti = {t: d for t, d in self.memoria.stop_recenti.items()
                                     if self.rischio.in_attesa(t, self.n_oggi)}

    def _vendite_e_ribilanciamento(self, posizioni: dict, conto: dict) -> dict[str, int]:
        """Restituisce {titolo: quantità venduta}."""
        st = self.strategia
        vendute: dict[str, int] = {}

        # 3) Trend negativo: si vende tutto il titolo
        for ticker, p in posizioni.items():
            gruppo = self.gruppo_di[ticker]
            if not st.gruppo_positivo(gruppo, self.oggi):
                etf = st.etf_globale if not st.mercato_ok(self.oggi) else st.etf_gruppo[gruppo]
                self._ordine("VENDITA", ticker, p["quantita"], f"{etf} in trend negativo", p["quantita"])
                vendute[ticker] = p["quantita"]

        # 4) Ribilanciamento: una volta al mese
        mese = self.oggi.strftime("%Y-%m")
        self.ribilancia = self.memoria.ultimo_ribilanciamento != mese
        if not self.ribilancia:
            return vendute
        self._msg("Primo controllo del mese: rifaccio la classifica delle azioni.")
        if self.esegui:
            self.memoria.ultimo_ribilanciamento = mese

        obiettivo = st.portafoglio_obiettivo(self.oggi, escludi=self._in_attesa())
        massimo = self.rischio.importo_massimo(conto["valore_totale"])
        for ticker, p in posizioni.items():
            if ticker in vendute:
                continue
            if ticker not in obiettivo:
                self._ordine("VENDITA", ticker, p["quantita"],
                             "uscito dalla classifica delle migliori del settore", p["quantita"])
                vendute[ticker] = p["quantita"]
                continue
            eccesso = p["quantita"] * self._prezzo(ticker) - massimo
            if eccesso > 0:
                quante = min(math.ceil(eccesso / self._prezzo(ticker)), p["quantita"])
                self._ordine("VENDITA", ticker, quante,
                             f"riduzione al {self.rischio.peso_max:.0%} del capitale", p["quantita"])
                vendute[ticker] = quante
        return vendute

    def _in_attesa(self) -> set[str]:
        return {t for t in self.gruppo_di if self.rischio.in_attesa(t, self.n_oggi)}

    def _acquisti(self, posizioni: dict, conto: dict, vendute: dict):
        obiettivo = self.strategia.portafoglio_obiettivo(self.oggi, escludi=self._in_attesa())
        rimaste = {t for t in posizioni if vendute.get(t, 0) < posizioni[t]["quantita"]}
        if not self.ribilancia:
            # Fuori dal ribilanciamento entriamo solo nei gruppi appena "accesi" (senza posizioni)
            gruppi_con_posizioni = {self.gruppo_di[t] for t in rimaste}
            obiettivo = {t: v for t, v in obiettivo.items() if v[0] not in gruppi_con_posizioni}

        massimo = self.rischio.importo_massimo(conto["valore_totale"])
        incasso = sum(q * self._prezzo(t) for t, q in vendute.items())
        budget = conto["cassa"] + incasso
        for ticker, (_, motivo) in obiettivo.items():
            if ticker in posizioni:
                continue
            prezzo_prudente = self._prezzo(ticker) * (1 + self.margine)
            quantita = math.floor(min(massimo, budget) / prezzo_prudente)
            if quantita <= 0:
                self._msg(f"Niente soldi sufficienti per comprare {ticker}")
                continue
            self._ordine("ACQUISTO", ticker, quantita, motivo)
            budget -= quantita * prezzo_prudente

    def _controlla_stop_presenti(self, posizioni: dict, vendute: dict):
        coperti = self.broker.stop_attivi()
        for ticker, p in posizioni.items():
            if ticker in vendute:
                continue                            # già gestito (venduto o stop rimesso sul resto)
            if coperti.get(ticker, 0) < p["quantita"]:
                self._msg(f"{ticker} non ha uno stop loss completo presso il broker: lo (ri)metto")
                if self.esegui:
                    self.broker.cancella_stop(ticker)
                    base = p["prezzo_medio"] if not self.rischio.trailing else self._prezzo(ticker)
                    self.broker.metti_stop(ticker, p["quantita"], self._stop(base))
