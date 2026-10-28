"""
Il motore del backtest: rivive il passato giorno per giorno, come se l'app
fosse stata accesa 10 anni fa.

Regola d'oro contro i "trucchi" involontari:
la decisione si prende con i prezzi di chiusura di IERI e si esegue alla
chiusura di OGGI. Così non usiamo mai informazioni che quel giorno non avremmo avuto.
(Nella realtà l'app controllerà dopo la chiusura e l'ordine partirà il giorno dopo.)
"""

import math
from dataclasses import dataclass

import pandas as pd

from ..strategia import StrategiaTermometro
from .costi import ModelloCosti


@dataclass
class Posizione:
    gruppo: str
    quantita: int
    prezzo_carico: float      # prezzo medio pagato (costi inclusi)
    data_acquisto: pd.Timestamp


class Backtest:

    def __init__(self, config: dict, prezzi: pd.DataFrame):
        # ffill: se un giorno manca il prezzo di un titolo usiamo l'ultimo noto
        # (prima della quotazione il prezzo resta vuoto, quindi il titolo non viene comprato)
        self.prezzi = prezzi.ffill()
        self.config = config
        self.strategia = StrategiaTermometro(config, self.prezzi)
        self.costi = ModelloCosti(config)
        self.capitale_iniziale = float(config["rischio"]["capitale_iniziale"])
        self.peso_max = config["rischio"]["max_per_azione_pct"] / 100
        self.ribilanciamento = config["strategia"]["ribilanciamento"]

        # Stato del portafoglio durante la simulazione
        self.cassa = self.capitale_iniziale
        self.posizioni: dict[str, Posizione] = {}
        self.operazioni: list[dict] = []   # il registro di ogni compravendita
        self.valori: dict = {}             # valore del portafoglio giorno per giorno

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
            self.posizioni[ticker] = Posizione(gruppo, quantita, (quantita * prezzo_eff + commissione) / quantita, giorno)
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

        for ieri, oggi in zip(giorni[:-1], giorni[1:]):
            self._giornata(ieri, oggi)
            self.valori[oggi] = self._valore_totale(oggi)

        return pd.Series(self.valori, name="Strategia")

    def _giornata(self, ieri, oggi):
        st = self.strategia

        # 1) VENDITE PER TREND NEGATIVO: il termometro del gruppo (o del mondo) è diventato freddo
        for ticker, pos in list(self.posizioni.items()):
            if not st.gruppo_positivo(pos.gruppo, ieri):
                etf = st.etf_globale if not st.mercato_ok(ieri) else st.etf_gruppo[pos.gruppo]
                self._vendi(oggi, ticker, f"{etf} in trend negativo")

        # 2) RIBILANCIAMENTO: si rifà la classifica (una volta al mese o a settimana)
        ribilancia = self._e_giorno_di_ribilanciamento(ieri, oggi)
        obiettivo = st.portafoglio_obiettivo(ieri)
        if ribilancia:
            for ticker in list(self.posizioni):
                if ticker not in obiettivo:
                    self._vendi(oggi, ticker, "uscito dalla classifica delle migliori del settore")
        else:
            # Fuori dal ribilanciamento entriamo solo nei gruppi appena "accesi" (senza posizioni)
            gruppi_con_posizioni = {p.gruppo for p in self.posizioni.values()}
            obiettivo = {t: v for t, v in obiettivo.items() if v[0] not in gruppi_con_posizioni}

        # 3) LIMITE PER TITOLO: nessuna azione può superare il peso massimo (es. 5%)
        totale = self._valore_totale(oggi)
        if ribilancia:
            for ticker, pos in list(self.posizioni.items()):
                eccesso = pos.quantita * self.prezzi.at[oggi, ticker] - totale * self.peso_max
                if eccesso > 0:
                    quante = math.ceil(eccesso / self.prezzi.at[oggi, ticker])
                    self._vendi(oggi, ticker, f"riduzione al {self.peso_max:.0%} del capitale", quante)

        # 4) ACQUISTI: ogni nuova azione riceve il peso massimo consentito
        for ticker, (gruppo, motivo) in obiettivo.items():
            if ticker not in self.posizioni:
                self._compra(oggi, ticker, gruppo, totale * self.peso_max, motivo)

    # ------------------------------------------------------------------
    def registro_operazioni(self) -> pd.DataFrame:
        return pd.DataFrame(self.operazioni)


def compra_e_tieni(prezzi: pd.Series, capitale: float, costi: ModelloCosti, nome: str) -> pd.Series:
    """Il confronto onesto: compro l'ETF il primo giorno con tutto il capitale e non lo tocco più."""
    prezzi = prezzi.ffill().dropna()
    prezzo_eff = costi.prezzo_esecuzione(prezzi.iloc[0], acquisto=True)
    quantita = math.floor(capitale / prezzo_eff)
    while quantita > 0 and quantita * prezzo_eff + costi.commissione(quantita, prezzo_eff) > capitale:
        quantita -= 1
    cassa = capitale - quantita * prezzo_eff - costi.commissione(quantita, prezzo_eff)
    return (cassa + quantita * prezzi).rename(nome)
