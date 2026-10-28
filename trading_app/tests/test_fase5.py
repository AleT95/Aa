"""
Test automatici della Fase 5 (dashboard). Nessun TWS e dati INVENTATI.
Si lanciano con:  python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
import yaml
from streamlit.testing.v1 import AppTest

import src.config
from src.config import CARTELLA_PROGETTO, carica_config
from src.dashboard.dati import confronto_benchmark, metriche_confronto, tabella_posizioni, variazione_giornaliera
from src.rischio import StatoRischio, emergenza


class TestDatiDashboard(unittest.TestCase):

    def test_confronto_parte_dallo_stesso_valore(self):
        date = pd.bdate_range("2026-01-05", periods=3)
        storico = pd.Series([100_000.0, 101_000.0, 99_000.0], index=date)
        etf = pd.Series([50.0, 55.0, 60.0], index=date)
        confronto = confronto_benchmark(storico, etf, "URTH")
        self.assertEqual(confronto.iloc[0]["URTH"], 100_000)
        self.assertAlmostEqual(confronto.iloc[-1]["URTH"], 120_000)
        self.assertIn("Rendimento totale", metriche_confronto(confronto).index)

    def test_confronto_senza_prezzi_etf_mostra_solo_il_conto(self):
        storico = pd.Series([100.0, 101.0], index=pd.bdate_range("2026-01-05", periods=2))
        confronto = confronto_benchmark(storico, pd.Series(dtype=float), "URTH")
        self.assertEqual(list(confronto.columns), ["Conto demo"])

    def test_variazione_giornaliera(self):
        storico = pd.Series([100.0, 98.0], index=pd.bdate_range("2026-01-05", periods=2))
        self.assertAlmostEqual(variazione_giornaliera(storico), -0.02)
        self.assertIsNone(variazione_giornaliera(storico.iloc[:1]))

    def test_tabella_posizioni(self):
        portafoglio = [
            {"titolo": "AAPL", "quantita": 10, "prezzo_medio": 100, "prezzo_attuale": 110, "valore": 1100, "guadagno": 100},
            {"titolo": "TSLA", "quantita": 5, "prezzo_medio": 200, "prezzo_attuale": 180, "valore": 900, "guadagno": -100},
        ]
        t = tabella_posizioni(portafoglio, {"AAPL": 10}, {"AAPL": "tecnologia"}, 20_000)
        aapl, tsla = t.iloc[0], t.iloc[1]
        self.assertAlmostEqual(aapl["Guadagno %"], 0.10)
        self.assertAlmostEqual(aapl["Peso"], 0.055)
        self.assertEqual(aapl["Stop loss"], "✅ attivo")
        self.assertEqual(tsla["Settore"], "fuori strategia")
        self.assertEqual(tsla["Stop loss"], "❌ assente")


class TestAppDashboard(unittest.TestCase):
    """Apre davvero la dashboard (senza browser) e simula i clic."""

    def setUp(self):
        self.cartella = tempfile.TemporaryDirectory()
        self.addCleanup(self.cartella.cleanup)
        c = Path(self.cartella.name)
        config = carica_config()
        config["rischio"]["file_stato"] = str(c / "stato.json")
        config["esecuzione"].update(
            file_memoria=str(c / "memoria.json"), file_storico_valori=str(c / "storico.csv"),
            file_registro=str(c / "operazioni.csv"), file_esecuzioni=str(c / "esecuzioni.csv"))
        config["backtest"]["cartella_risultati"] = str(c / "risultati")
        config["broker"]["timeout_secondi"] = 2
        file_config = c / "config.yaml"
        file_config.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
        self.config = config
        for patch in (mock.patch.object(src.config, "FILE_CONFIG_PREDEFINITO", file_config),
                      mock.patch.object(emergenza, "FILE_REGISTRO", c / "rischio.log")):
            patch.start()
            self.addCleanup(patch.stop)

    def apri(self):
        app = AppTest.from_file(str(CARTELLA_PROGETTO / "dashboard.py"), default_timeout=30)
        app.run()
        self.assertFalse(app.exception, app.exception)
        return app

    def test_si_apre_senza_tws_e_senza_dati(self):
        app = self.apri()
        self.assertTrue(any("TWS non raggiungibile" in w.value for w in app.warning))
        self.assertTrue(any("ATTIVA" in s.value for s in app.sidebar.success))

    def test_pulsante_emergenza_serve_la_conferma_e_poi_blocca(self):
        app = self.apri()
        pulsante = next(b for b in app.sidebar.button if "STOP" in b.label)
        self.assertTrue(pulsante.disabled)                     # senza conferma non si preme
        app.sidebar.checkbox[0].check().run()
        next(b for b in app.sidebar.button if "STOP" in b.label).click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(StatoRischio.carica(self.config).tipo, "emergenza")

    def test_sblocco_dalla_dashboard(self):
        stato = StatoRischio()
        stato.blocca("giornaliero", "test")
        stato.salva(self.config)
        app = self.apri()
        self.assertTrue(any("BLOCCATA" in e.value for e in app.sidebar.error))
        app.sidebar.text_input[0].input("SBLOCCA").run()
        next(b for b in app.sidebar.button if "Sblocca" in b.label).click().run()
        self.assertFalse(StatoRischio.carica(self.config).bloccato)


if __name__ == "__main__":
    unittest.main()
