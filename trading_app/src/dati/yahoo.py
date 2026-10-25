"""
Fornitore dati basato su Yahoo Finance (libreria yfinance, gratuita).
"""

import logging

import pandas as pd
import yfinance as yf

from .base import FornitoreDati

log = logging.getLogger(__name__)


class FornitoreYahoo(FornitoreDati):

    def scarica(self, tickers: list[str], inizio: str, fine: str | None = None) -> pd.DataFrame:
        log.info("Scarico da Yahoo Finance %d ticker dal %s...", len(tickers), inizio)

        # auto_adjust=True -> i prezzi sono già corretti per dividendi e split
        grezzi = yf.download(
            tickers,
            start=inizio,
            end=fine,
            auto_adjust=True,
            progress=False,
            group_by="column",
        )
        if grezzi is None or grezzi.empty:
            raise RuntimeError("Yahoo Finance non ha restituito dati. Controlla la connessione internet.")

        # Teniamo solo la colonna "Close" (chiusura)
        chiusure = grezzi["Close"]
        if isinstance(chiusure, pd.Series):          # caso di un solo ticker
            chiusure = chiusure.to_frame(name=tickers[0])

        chiusure.index = pd.to_datetime(chiusure.index).tz_localize(None)
        chiusure = chiusure.sort_index()

        # Segnaliamo i ticker che non sono arrivati (es. nome sbagliato o delistato)
        vuoti = [t for t in tickers if t not in chiusure.columns or chiusure[t].dropna().empty]
        if vuoti:
            log.warning("Nessun dato per: %s (controlla il nome del ticker)", vuoti)
            chiusure = chiusure.drop(columns=[t for t in vuoti if t in chiusure.columns])

        return chiusure
