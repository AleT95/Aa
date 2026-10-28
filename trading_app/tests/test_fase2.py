"""
Test automatici della Fase 2. Usano prezzi INVENTATI (non di mercato) costruiti
apposta per controllare che la logica faccia quello che deve.
Si lanciano con:  python -m unittest discover tests
"""

import copy
import unittest

import numpy as np
import pandas as pd

from src.backtest import Backtest, calcola_metriche
from src.backtest.costi import ModelloCosti
from src.backtest.motore import compra_e_tieni
from src.config import carica_config
from src.strategia.indicatori import trend_positivo


def config_di_prova():
    """Config ridotto: 2 settori, 3 azioni ciascuno, filtro globale sul 'mondo'."""
    config = copy.deepcopy(carica_config())
    config["etf_aree"] = {"mondo": "MONDO"}
    config["etf_settori"] = {"tech": "ETF_T", "salute": "ETF_S"}
    config["azioni"] = {"tech": ["T1", "T2", "T3"], "salute": ["S1", "S2", "S3"]}
    config["strategia"]["azioni_per_settore"] = 2
    return config


def prezzi_sali_scendi(giorni_salita=500, giorni_discesa=250):
    """Tutto sale per un po' (a velocità diverse), poi tutto scende."""
    date = pd.bdate_range("2015-01-01", periods=giorni_salita + giorni_discesa)
    rng = np.random.default_rng(42)
    velocita = {"MONDO": 0.0004, "ETF_T": 0.0006, "ETF_S": 0.0005,
                "T1": 0.0010, "T2": 0.0007, "T3": 0.0003, "S1": 0.0002, "S2": 0.0008, "S3": 0.0006}
    dati = {}
    for t, v in velocita.items():
        passi = np.r_[np.full(giorni_salita, v), np.full(giorni_discesa, -2 * v)]
        rumore = rng.normal(0, 0.002, len(date))
        dati[t] = 100 * np.exp(np.cumsum(passi + rumore))
    return pd.DataFrame(dati, index=date)


class TestIndicatori(unittest.TestCase):

    def test_trend_salita_e_discesa(self):
        su = pd.DataFrame({"X": np.linspace(100, 200, 400)})
        giu = pd.DataFrame({"X": np.linspace(200, 100, 400)})
        self.assertTrue(trend_positivo(su, 50, 200, [3, 6])["X"].iloc[-1])
        self.assertFalse(trend_positivo(giu, 50, 200, [3, 6])["X"].iloc[-1])

    def test_dati_insufficienti_non_comprano(self):
        corti = pd.DataFrame({"X": np.linspace(100, 200, 100)})   # meno di 200 giorni
        self.assertFalse(trend_positivo(corti, 50, 200, [3, 6])["X"].any())


class TestCosti(unittest.TestCase):

    def test_commissione_minimo_e_massimo(self):
        costi = ModelloCosti(carica_config())
        self.assertEqual(costi.commissione(10, 100), 1.0)          # 10 x 0,005 = 0,05 -> minimo 1 $
        self.assertAlmostEqual(costi.commissione(1000, 100), 5.0)  # 1000 x 0,005 = 5 $
        self.assertAlmostEqual(costi.commissione(10, 1), 0.10)     # tetto: 1% di 10 $
        self.assertGreater(costi.prezzo_esecuzione(100, True), 100)
        self.assertLess(costi.prezzo_esecuzione(100, False), 100)


class TestBacktest(unittest.TestCase):

    def setUp(self):
        self.config = config_di_prova()
        self.prezzi = prezzi_sali_scendi()
        self.bt = Backtest(self.config, self.prezzi)
        self.valori = self.bt.esegui()
        self.op = self.bt.registro_operazioni()

    def test_compra_le_piu_forti(self):
        acquistati = set(self.op.loc[self.op["operazione"] == "ACQUISTO", "titolo"])
        self.assertIn("T1", acquistati)       # la più veloce del tech
        self.assertIn("S2", acquistati)       # la più veloce della salute
        self.assertNotIn("T3", acquistati)    # la più lenta del tech non entra nella top 2

    def test_in_discesa_vende_tutto(self):
        self.assertEqual(self.bt.posizioni, {})
        motivi = self.op.loc[self.op["operazione"] == "VENDITA", "motivo"]
        self.assertTrue(motivi.str.contains("trend negativo").any())

    def test_mai_oltre_il_peso_massimo_al_momento_dell_acquisto(self):
        acquisti = self.op[self.op["operazione"] == "ACQUISTO"]
        for _, riga in acquisti.iterrows():
            valore_giorno = self.valori[pd.Timestamp(riga["data"])]
            self.assertLessEqual(riga["quantita"] * riga["prezzo"], valore_giorno * 0.05 + 1e-6)

    def test_cassa_mai_negativa_e_valori_validi(self):
        self.assertGreaterEqual(self.bt.cassa, 0)
        self.assertFalse(self.valori.isna().any())

    def test_metriche(self):
        m = calcola_metriche(self.valori)
        self.assertLessEqual(m["Massimo drawdown"], 0)
        self.assertAlmostEqual(m["Capitale finale"], self.valori.iloc[-1])


class TestCompraETieni(unittest.TestCase):

    def test_senza_costi_segue_il_prezzo(self):
        config = carica_config()
        config["costi"].update(commissione_per_azione=0, commissione_minima=0, slippage_pct=0)
        prezzi = pd.Series([100.0, 110.0, 121.0], index=pd.bdate_range("2020-01-01", periods=3))
        valori = compra_e_tieni(prezzi, 10_000, ModelloCosti(config), "BH")
        self.assertAlmostEqual(valori.iloc[-1], 12_100)


if __name__ == "__main__":
    unittest.main()
