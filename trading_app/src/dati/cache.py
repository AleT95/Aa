"""
Cache su disco: salva i prezzi scaricati in un file, così le volte successive
li leggiamo dal computer invece di riscaricarli (più veloce e non "stressiamo"
Yahoo con troppe richieste).
"""

import logging
import time
from pathlib import Path

import pandas as pd

from ..config import CARTELLA_PROGETTO
from .base import FornitoreDati

log = logging.getLogger(__name__)


class FornitoreConCache(FornitoreDati):
    """Avvolge un altro fornitore e aggiunge la cache (schema "decoratore")."""

    def __init__(self, fornitore: FornitoreDati, cartella: str, validita_ore: float):
        self.fornitore = fornitore
        self.cartella = CARTELLA_PROGETTO / cartella
        self.cartella.mkdir(parents=True, exist_ok=True)
        self.validita_secondi = validita_ore * 3600
        self.file = self.cartella / "prezzi.csv"

    def _cache_valida(self) -> bool:
        if not self.file.exists():
            return False
        eta = time.time() - self.file.stat().st_mtime
        return eta < self.validita_secondi

    def scarica(self, tickers: list[str], inizio: str, fine: str | None = None,
                forza: bool = False) -> pd.DataFrame:
        """forza=True ignora la cache e riscarica tutto."""
        if not forza and self._cache_valida():
            dati = pd.read_csv(self.file, index_col=0, parse_dates=True)
            copre_ticker = all(t in dati.columns for t in tickers)
            copre_date = dati.index.min() <= pd.Timestamp(inizio) + pd.Timedelta(days=7)
            if copre_ticker and copre_date:
                log.info("Uso i dati in cache (%s)", self.file)
                return self._ritaglia(dati, tickers, inizio, fine)

        dati = self.fornitore.scarica(tickers, inizio, fine)
        dati.to_csv(self.file)
        log.info("Dati salvati in cache: %s", self.file)
        return dati

    @staticmethod
    def _ritaglia(dati: pd.DataFrame, tickers: list[str], inizio: str, fine: str | None) -> pd.DataFrame:
        dati = dati.loc[dati.index >= pd.Timestamp(inizio), tickers]
        if fine:
            dati = dati.loc[dati.index < pd.Timestamp(fine)]
        return dati
