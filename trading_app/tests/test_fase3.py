"""
Test automatici della Fase 3 (gestione del rischio). Prezzi INVENTATI, costruiti
apposta per far scattare i freni e controllare che funzionino.
Si lanciano con:  python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from src.backtest import Backtest
from src.config import carica_config
from src.rischio import GestoreRischio, StatoRischio
from src.rischio import emergenza
from src.rischio.stato import EMERGENZA, GIORNALIERO, MENSILE
from tests.test_fase2 import config_di_prova, prezzi_sali_scendi


class TestStopLoss(unittest.TestCase):

    def test_stop_fisso_e_trailing(self):
        config = carica_config()
        config["rischio"]["stop_loss_pct"] = 10
        config["rischio"]["stop_loss_tipo"] = "fisso"
        fisso = GestoreRischio(config)
        self.assertAlmostEqual(fisso.livello_stop(100, 150), 90)      # resta legato al prezzo pagato
        config["rischio"]["stop_loss_tipo"] = "trailing"
        trailing = GestoreRischio(config)
        self.assertAlmostEqual(trailing.livello_stop(100, 150), 135)  # insegue il massimo
        self.assertTrue(trailing.stop_scattato(134, 100, 150))
        self.assertFalse(trailing.stop_scattato(136, 100, 150))

    def test_attesa_dopo_lo_stop(self):
        g = GestoreRischio(carica_config())                            # 20 giorni di attesa
        g.registra_stop("AAPL", n_giorno=100)
        self.assertTrue(g.in_attesa("AAPL", 119))
        self.assertFalse(g.in_attesa("AAPL", 120))
        self.assertFalse(g.in_attesa("MSFT", 101))

    def test_spento_non_frena(self):
        g = GestoreRischio(carica_config(), attivo=False)
        self.assertFalse(g.stop_scattato(1, 100, 100))


class TestLimitiPerdita(unittest.TestCase):

    def test_limite_giornaliero(self):
        g = GestoreRischio(carica_config())                            # limite -3%
        g.controlla_limiti(pd.Timestamp("2024-03-01"), 100_000)
        self.assertIsNone(g.controlla_limiti(pd.Timestamp("2024-03-04"), 98_000))   # -2%: ok
        tipo, _ = g.controlla_limiti(pd.Timestamp("2024-03-05"), 94_000)            # -4%: blocco
        self.assertEqual(tipo, GIORNALIERO)

    def test_limite_mensile_e_nuovo_mese(self):
        g = GestoreRischio(carica_config())                            # limite -10%
        g.controlla_limiti(pd.Timestamp("2024-03-29"), 100_000)
        valore = 100_000
        risultato = None
        for giorno in pd.bdate_range("2024-04-01", periods=6):          # -2% al giorno
            valore *= 0.98
            risultato = g.controlla_limiti(giorno, valore) or risultato
        self.assertEqual(risultato[0], MENSILE)
        # A maggio si riparte da zero: un -2% non deve bloccare
        self.assertIsNone(g.controlla_limiti(pd.Timestamp("2024-05-01"), valore * 0.98))


class TestStatoEEmergenza(unittest.TestCase):

    def setUp(self):
        self.cartella = tempfile.TemporaryDirectory()
        self.config = carica_config()
        self.config["rischio"]["file_stato"] = str(Path(self.cartella.name) / "stato.json")
        registro = mock.patch.object(emergenza, "FILE_REGISTRO", Path(self.cartella.name) / "rischio.log")
        registro.start()
        self.addCleanup(registro.stop)
        self.addCleanup(self.cartella.cleanup)

    def test_stop_di_emergenza_chiude_tutto_e_resta_bloccato(self):
        broker = mock.Mock()
        emergenza.attiva_stop_emergenza(self.config, broker)
        broker.chiudi_tutto.assert_called_once()
        ok, descrizione = emergenza.puo_operare(self.config)
        self.assertFalse(ok)
        self.assertIn("emergenza", descrizione)
        # Il blocco sopravvive al "riavvio": lo rileggo dal file
        self.assertEqual(StatoRischio.carica(self.config).tipo, EMERGENZA)

    def test_emergenza_non_viene_declassata(self):
        emergenza.attiva_stop_emergenza(self.config)
        emergenza.blocca_per_limite(self.config, GIORNALIERO, "test")
        self.assertEqual(StatoRischio.carica(self.config).tipo, EMERGENZA)

    def test_sblocco_manuale(self):
        emergenza.attiva_stop_emergenza(self.config)
        emergenza.sblocca(self.config)
        self.assertTrue(emergenza.puo_operare(self.config)[0])
        self.assertIn("SBLOCCO", (Path(self.cartella.name) / "rischio.log").read_text(encoding="utf-8"))


class TestFreniNelBacktest(unittest.TestCase):

    def test_stop_loss_su_un_titolo_che_crolla(self):
        config = config_di_prova()
        prezzi = prezzi_sali_scendi()
        prezzi.iloc[420:, prezzi.columns.get_loc("T1")] *= 0.75        # T1 crolla del 25% in un giorno
        bt = Backtest(config, prezzi)
        bt.esegui()
        op, ev = bt.registro_operazioni(), bt.registro_eventi()

        stop = ev[(ev["evento"] == "STOP LOSS") & (ev["dettaglio"] == "T1")]
        self.assertFalse(stop.empty)
        giorno_stop = pd.Timestamp(stop["data"].iloc[0])
        # Nei 20 giorni di borsa successivi T1 non viene ricomprato
        fine_attesa = prezzi.index[prezzi.index.get_loc(giorno_stop) + 19]
        riacquisti = op[(op["titolo"] == "T1") & (op["operazione"] == "ACQUISTO")
                        & (pd.to_datetime(op["data"]) > giorno_stop)
                        & (pd.to_datetime(op["data"]) <= fine_attesa)]
        self.assertTrue(riacquisti.empty)

    def test_crollo_generale_blocca_e_poi_riparte(self):
        config = config_di_prova()
        config["rischio"]["max_per_azione_pct"] = 25                   # 4 titoli = tutto investito
        prezzi = prezzi_sali_scendi(giorni_salita=700, giorni_discesa=1)
        prezzi.iloc[450:] *= 0.94                                      # tutti -6% in un giorno
        bt = Backtest(config, prezzi)
        bt.esegui()
        op, ev = bt.registro_operazioni(), bt.registro_eventi()

        blocchi = ev[ev["evento"] == "BLOCCO GIORNALIERO"]
        self.assertEqual(len(blocchi), 1)
        giorno_blocco = pd.Timestamp(blocchi["data"].iloc[0])
        self.assertEqual(giorno_blocco, prezzi.index[450])
        # Il giorno dopo: si vende tutto e non si compra niente
        giorno_dopo = prezzi.index[451].date()
        del_giorno_dopo = op[op["data"] == giorno_dopo]
        self.assertTrue((del_giorno_dopo["operazione"] == "VENDITA").all())
        self.assertTrue(del_giorno_dopo["motivo"].str.contains("BLOCCO").all())
        # E poi l'app riparte
        self.assertIn("RIPARTENZA", set(ev["evento"]))

    def test_senza_freni_niente_blocchi(self):
        config = config_di_prova()
        config["rischio"]["max_per_azione_pct"] = 25
        prezzi = prezzi_sali_scendi(giorni_salita=700, giorni_discesa=1)
        prezzi.iloc[450:] *= 0.94
        bt = Backtest(config, prezzi, rischio_attivo=False)
        bt.esegui()
        self.assertTrue(bt.registro_eventi().empty)


if __name__ == "__main__":
    unittest.main()
