"""
Il motore del backtest: rivive il passato giorno per giorno, come se l'app
fosse stata accesa 10 anni fa.

Regola d'oro contro i "trucchi" involontari:
la decisione si prende con i prezzi di chiusura di IERI e si esegue alla
chiusura di OGGI. Così non usiamo mai informazioni che quel giorno non avremmo avuto.
(Nella realtà l'app controllerà dopo la chiusura e l'ordine partirà il giorno dopo.)

Eccezione: lo stop loss. Nella realtà è un ordine che "aspetta" già dal broker e
scatta da solo durante la giornata, quindi lo controlliamo sul prezzo di OGGI.
"""

import math
from dataclasses import dataclass

import pandas as pd

from ..rischio import GestoreRischio, StatoRischio
from ..rischio.stato import MENSILE
from ..strategia import StrategiaTermometro
from .costi import ModelloCosti


@dataclass
class Posizione:
    gruppo: str
    quantita: int
    prezzo_carico: float      # prezzo medio pagato (costi inclusi)
    data_acquisto: pd.Timestamp
    prezzo_massimo: float     # chiusura più alta da quando la teniamo (per lo stop "trailing")


class Backtest:

    def __init__(self, config: dict, prezzi: pd.DataFrame, rischio_attivo: bool = True):
        # ffill: se un giorno manca il prezzo di un titolo usiamo l'ultimo noto
        # (prima della quotazione il prezzo resta vuoto, quindi il titolo non viene comprato)
        self.prezzi = prezzi.ffill()
        self.config = config
        self.strategia = StrategiaTermometro(config, self.prezzi)
        self.costi = ModelloCosti(config)
        self.rischio = GestoreRischio(config, attivo=rischio_attivo)
        self.capitale_iniziale = float(config["rischio"]["capitale_iniziale"])
        self.ribilanciamento = config["strategia"]["ribilanciamento"]

        # Stato del portafoglio durante la simulazione
        self.cassa = self.capitale_iniziale
        self.posizioni: dict[str, Posizione] = {}
        self.operazioni: list[dict] = []   # il registro di ogni compravendita
        self.eventi: list[dict] = []       # il registro dei "freni": stop loss, blocchi, ripartenze
        self.valori: dict = {}             # valore del portafoglio giorno per giorno

        # Blocco: nel backtest lo stato vive in memoria (non tocca il file dell'app vera)
        self.stato = StatoRischio()
        self._da_chiudere = False
        self._giorno_blocco = None         # (n. giorno, data) in cui è scattato il blocco

    # ------------------------------------------------------------------
    #  Operazioni elementari
    # ------------------------------------------------------------------
    def _valore_totale(self, giorno) -> float:
        investito = sum(p.quantita * self.prezzi.at[giorno, t] for t, p in self.posizioni.items())
        return self.cassa + investito

    def _compra(self, giorno, ticker: str, gruppo: str, importo: float, motivo: str):
        prezzo = self.prezzi.at[giorno, ticker]
        if pd.isna(prezzo):
            return
        prezzo_eff = self.costi.prezzo_esecuzione(prezzo, acquisto=True)
        quantita = math.floor(min(importo, self.cassa) / prezzo_eff)
        # Togliamo un'azione se la commissione non ci sta nella cassa
        while quantita > 0 and quantita * prezzo_eff + self.costi.commissione(quantita, prezzo_eff) > self.cassa:
            quantita -= 1
        if quantita <= 0:
            return
        commissione = self.costi.commissione(quantita, prezzo_eff)
        self.cassa -= quantita * prezzo_eff + commissione

        pos = self.posizioni.get(ticker)
        if pos:   # aggiunta a una posizione esistente: ricalcolo il prezzo medio
            costo_tot = pos.quantita * pos.prezzo_carico + quantita * prezzo_eff + commissione
            pos.quantita += quantita
            pos.prezzo_carico = costo_tot / pos.quantita
        else:
            carico = (quantita * prezzo_eff + commissione) / quantita
            self.posizioni[ticker] = Posizione(gruppo, quantita, carico, giorno, prezzo)
        self._registra(giorno, "ACQUISTO", ticker, quantita, prezzo_eff, commissione, motivo)

    def _vendi(self, giorno, ticker: str, motivo: str, quantita: int | None = None):
        pos = self.posizioni[ticker]
        quantita = pos.quantita if quantita is None else min(quantita, pos.quantita)
        if quantita <= 0:
            return
        prezzo_eff = self.costi.prezzo_esecuzione(self.prezzi.at[giorno, ticker], acquisto=False)
        commissione = self.costi.commissione(quantita, prezzo_eff)
        self.cassa += quantita * prezzo_eff - commissione
        utile = quantita * (prezzo_eff - pos.prezzo_carico) - commissione
        pos.quantita -= quantita
        if pos.quantita == 0:
            del self.posizioni[ticker]
        self._registra(giorno, "VENDITA", ticker, quantita, prezzo_eff, commissione, motivo, utile)

    def _registra(self, giorno, tipo, ticker, quantita, prezzo, commissione, motivo, utile=None):
        self.operazioni.append({
            "data": giorno.date(), "operazione": tipo, "titolo": ticker, "quantita": quantita,
            "prezzo": round(prezzo, 2), "commissione": round(commissione, 2),
            "utile": None if utile is None else round(utile, 2), "motivo": motivo,
        })

    def _evento(self, giorno, tipo: str, dettaglio: str):
        self.eventi.append({"data": giorno.date(), "evento": tipo, "dettaglio": dettaglio})

    def _e_giorno_di_ribilanciamento(self, ieri, oggi) -> bool:
        if self.ribilanciamento == "settimanale":
            return oggi.isocalendar()[:2] != ieri.isocalendar()[:2]
        return oggi.month != ieri.month   # mensile: primo giorno di borsa del mese

    # ------------------------------------------------------------------
    #  La simulazione
    # ------------------------------------------------------------------
    def esegui(self) -> pd.Series:
        """Esegue il backtest e restituisce il valore del portafoglio giorno per giorno."""
        giorni = self.prezzi.index[self.prezzi.index >= self.strategia.primo_giorno_utile]
        self.valori[giorni[0]] = self.cassa
        self.rischio.controlla_limiti(giorni[0], self.cassa)

        for n, (ieri, oggi) in enumerate(zip(giorni[:-1], giorni[1:]), start=1):
            self._giornata(n, ieri, oggi)
            valore = self._valore_totale(oggi)
            self.valori[oggi] = valore
            self._fine_giornata(n, oggi, valore)

        return pd.Series(self.valori, name="Strategia")

    def _giornata(self, n, ieri, oggi):
        st = self.strategia

        # 0) BLOCCO: chiusura delle posizioni decisa ieri sera, oppure ripartenza
        if self.stato.bloccato:
            if self._da_chiudere:
                for ticker in list(self.posizioni):
                    self._vendi(oggi, ticker, f"BLOCCO {self.stato.tipo}: chiusura di tutte le posizioni")
                self._da_chiudere = False
            elif self._puo_ripartire(n, oggi):
                self._evento(oggi, "RIPARTENZA", f"fine del blocco {self.stato.tipo}")
                self.stato.sblocca()

        # 1) STOP LOSS: il titolo è sceso sotto il suo livello di stop
        for ticker, pos in list(self.posizioni.items()):
            prezzo = self.prezzi.at[oggi, ticker]
            if self.rischio.stop_scattato(prezzo, pos.prezzo_carico, pos.prezzo_massimo):
                livello = self.rischio.livello_stop(pos.prezzo_carico, pos.prezzo_massimo)
                self._vendi(oggi, ticker, f"STOP LOSS: prezzo {prezzo:.2f} sotto lo stop {livello:.2f}")
                self.rischio.registra_stop(ticker, n)
                self._evento(oggi, "STOP LOSS", ticker)

        # 2) VENDITE PER TREND NEGATIVO: il termometro del gruppo (o del mondo) è diventato freddo
        for ticker, pos in list(self.posizioni.items()):
            if not st.gruppo_positivo(pos.gruppo, ieri):
                etf = st.etf_globale if not st.mercato_ok(ieri) else st.etf_gruppo[pos.gruppo]
                self._vendi(oggi, ticker, f"{etf} in trend negativo")

        # Da bloccati si può solo vendere: niente ribilanciamento né acquisti
        if self.stato.bloccato:
            return

        # 3) RIBILANCIAMENTO: si rifà la classifica (una volta al mese o a settimana)
        ribilancia = self._e_giorno_di_ribilanciamento(ieri, oggi)
        in_attesa = {t for t in self.prezzi.columns if self.rischio.in_attesa(t, n)}
        obiettivo = st.portafoglio_obiettivo(ieri, escludi=in_attesa)
        if ribilancia:
            for ticker in list(self.posizioni):
                if ticker not in obiettivo:
                    self._vendi(oggi, ticker, "uscito dalla classifica delle migliori del settore")
        else:
            # Fuori dal ribilanciamento entriamo solo nei gruppi appena "accesi" (senza posizioni)
            gruppi_con_posizioni = {p.gruppo for p in self.posizioni.values()}
            obiettivo = {t: v for t, v in obiettivo.items() if v[0] not in gruppi_con_posizioni}

        # 4) LIMITE PER TITOLO: nessuna azione può superare il peso massimo (es. 5%)
        totale = self._valore_totale(oggi)
        massimo = self.rischio.importo_massimo(totale)
        if ribilancia:
            for ticker, pos in list(self.posizioni.items()):
                eccesso = pos.quantita * self.prezzi.at[oggi, ticker] - massimo
                if eccesso > 0:
                    quante = math.ceil(eccesso / self.prezzi.at[oggi, ticker])
                    self._vendi(oggi, ticker, f"riduzione al {self.rischio.peso_max:.0%} del capitale", quante)

        # 5) ACQUISTI: ogni nuova azione riceve il peso massimo consentito
        for ticker, (gruppo, motivo) in obiettivo.items():
            if ticker not in self.posizioni:
                self._compra(oggi, ticker, gruppo, massimo, motivo)

    def _fine_giornata(self, n, oggi, valore):
        """Controlli della sera: aggiorno i massimi per lo stop trailing e verifico i limiti di perdita."""
        for ticker, pos in self.posizioni.items():
            pos.prezzo_massimo = max(pos.prezzo_massimo, self.prezzi.at[oggi, ticker])

        superato = self.rischio.controlla_limiti(oggi, valore)
        if superato and not self.stato.bloccato:
            tipo, motivo = superato
            self.stato.blocca(tipo, motivo, quando=oggi.to_pydatetime())
            self._da_chiudere = self.rischio.chiudi_al_blocco and bool(self.posizioni)
            self._giorno_blocco = (n, oggi)
            self._evento(oggi, f"BLOCCO {tipo.upper()}", motivo)

    def _puo_ripartire(self, n, oggi) -> bool:
        """
        Nella realtà sei TU a sbloccare l'app. Nel backtest simuliamo che tu lo faccia:
          - blocco giornaliero: si riparte dopo un giorno intero di pausa
          - blocco mensile: si riparte il mese successivo
        """
        n_blocco, giorno_blocco = self._giorno_blocco
        if n - n_blocco < 2:
            return False
        if self.stato.tipo == MENSILE:
            return (oggi.year, oggi.month) != (giorno_blocco.year, giorno_blocco.month)
        return True

    # ------------------------------------------------------------------
    def registro_operazioni(self) -> pd.DataFrame:
        return pd.DataFrame(self.operazioni)

    def registro_eventi(self) -> pd.DataFrame:
        return pd.DataFrame(self.eventi, columns=["data", "evento", "dettaglio"])


def compra_e_tieni(prezzi: pd.Series, capitale: float, costi: ModelloCosti, nome: str) -> pd.Series:
    """Il confronto onesto: compro l'ETF il primo giorno con tutto il capitale e non lo tocco più."""
    prezzi = prezzi.ffill().dropna()
    prezzo_eff = costi.prezzo_esecuzione(prezzi.iloc[0], acquisto=True)
    quantita = math.floor(capitale / prezzo_eff)
    while quantita > 0 and quantita * prezzo_eff + costi.commissione(quantita, prezzo_eff) > capitale:
        quantita -= 1
    cassa = capitale - quantita * prezzo_eff - costi.commissione(quantita, prezzo_eff)
    return (cassa + quantita * prezzi).rename(nome)
