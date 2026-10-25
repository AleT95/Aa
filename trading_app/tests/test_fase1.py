"""
Test automatici della Fase 1 (non servono internet né Yahoo).
Si lanciano con:  python -m unittest discover tests
"""

import tempfile
import unittest

import pandas as pd

from src.config import carica_config, tutti_i_ticker
from src.dati.base import FornitoreDati
from src.dati.cache import FornitoreConCache


class FornitoreDiProva(FornitoreDati):
    """Finge di scaricare: restituisce prezzi costanti e conta le chiamate."""

    def __init__(self):
        self.chiamate = 0

    def scarica(self, tickers, inizio, fine=None):
        self.chiamate += 1
        date = pd.bdate_range(inizio, periods=10)
        return pd.DataFrame({t: 100.0 for t in tickers}, index=date)


class TestFase1(unittest.TestCase):

    def test_config_si_carica(self):
        config = carica_config()
        tickers = tutti_i_ticker(config)
        self.assertIn("SPY", tickers)
        self.assertEqual(len(tickers), len(set(tickers)))   # niente doppioni

    def test_cache_evita_il_secondo_download(self):
        with tempfile.TemporaryDirectory() as cartella:
            finto = FornitoreDiProva()
            fornitore = FornitoreConCache(finto, cartella=cartella, validita_ore=1)
            primo = fornitore.scarica(["SPY", "QQQ"], inizio="2020-01-01")
            secondo = fornitore.scarica(["SPY"], inizio="2020-01-01")
            self.assertEqual(finto.chiamate, 1)              # la seconda volta legge dal disco
            self.assertEqual(list(secondo.columns), ["SPY"])
            self.assertEqual(len(primo), len(secondo))


if __name__ == "__main__":
    unittest.main()
