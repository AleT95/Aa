"""
Test automatici della Fase 4. Usano un BROKER FINTO (nessun collegamento a IBKR)
e prezzi INVENTATI, per controllare che il controllo giornaliero prenda le
decisioni giuste e le invii nell'ordine giusto.
Si lanciano con:  python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from src.broker.base import Broker
from src.broker.ibkr import BrokerIBKR, ErroreSicurezza
from src.esecuzione import CicloGiornaliero
from src.esecuzione.memoria import Memoria, StoricoValori
from src.rischio import StatoRischio, emergenza
from src.rischio.stato import GIORNALIERO
from tests.test_fase2 import config_di_prova, prezzi_sali_scendi


class BrokerFinto(Broker):
    """Finge di essere IBKR: tiene in memoria conto e posizioni e annota ogni chiamata."""

    def __init__(self, valore=100_000, cassa=100_000, posizioni=None, stop=None):
        self._conto = {"valore_totale": valore, "cassa": cassa}
        self._posizioni = posizioni or {}
        self._stop = stop or {}
        self.chiamate = []

    def conto(self): return self._conto
    def posizioni(self): return self._posizioni
    def stop_attivi(self): return self._stop
    def esecuzioni(self): return []
    def disconnetti(self): pass

    def compra(self, ticker, quantita, stop, motivo):
        self.chiamate.append(("compra", ticker, quantita, stop["tipo"]))
        return "1"

    def vendi(self, ticker, quantita, motivo):
        self.chiamate.append(("vendi", ticker, quantita))
        return "2"

    def metti_stop(self, ticker, quantita, stop):
        self.chiamate.append(("metti_stop", ticker, quantita))
        return "3"

    def cancella_stop(self, ticker):
        self.chiamate.append(("cancella_stop", ticker))

    def chiudi_tutto(self, motivo):
        self.chiamate.append(("chiudi_tutto",))
        return [{"titolo": t, "quantita": p["quantita"], "id": "9"} for t, p in self._posizioni.items()]


class BaseTest(unittest.TestCase):

    def setUp(self):
        self.cartella = tempfile.TemporaryDirectory()
        self.addCleanup(self.cartella.cleanup)
        c = Path(self.cartella.name)
        self.config = config_di_prova()
        self.config["rischio"]["file_stato"] = str(c / "stato.json")
        self.config["esecuzione"].update(
            file_memoria=str(c / "memoria.json"), file_storico_valori=str(c / "storico.csv"),
            file_registro=str(c / "operazioni.csv"), file_esecuzioni=str(c / "esecuzioni.csv"))
        registro = mock.patch.object(emergenza, "FILE_REGISTRO", c / "rischio.log")
        registro.start()
        self.addCleanup(registro.stop)
        self.in_salita = prezzi_sali_scendi(giorni_salita=500, giorni_discesa=0)
        self.in_discesa = prezzi_sali_scendi(giorni_salita=500, giorni_discesa=250)

    def ciclo(self, broker, prezzi, esegui=True):
        c = CicloGiornaliero(self.config, broker, prezzi, esegui=esegui)
        c.esegui_ciclo()
        return c


class TestCicloGiornaliero(BaseTest):

    def test_modalita_prova_non_invia_nulla(self):
        broker = BrokerFinto()
        c = self.ciclo(broker, self.in_salita, esegui=False)
        self.assertTrue(c.ordini)                       # ha deciso qualcosa...
        self.assertEqual(broker.chiamate, [])           # ...ma non ha inviato niente
        self.assertFalse(Path(self.config["esecuzione"]["file_registro"]).exists())

    def test_acquisti_con_stop_e_max_5_percento(self):
        broker = BrokerFinto()
        c = self.ciclo(broker, self.in_salita)
        acquisti = [x for x in broker.chiamate if x[0] == "compra"]
        comprati = {x[1] for x in acquisti}
        self.assertEqual(len(comprati & {"T1", "T2", "T3"}), 2)         # 2 titoli per settore
        self.assertEqual(len(comprati & {"S1", "S2", "S3"}), 2)
        self.assertTrue({"T1", "S2"} <= comprati)                      # le più forti ci sono sempre
        for _, ticker, quantita, tipo_stop in acquisti:
            self.assertEqual(tipo_stop, "trailing")
            self.assertLessEqual(quantita * c._prezzo(ticker), 5_000)
        registro = pd.read_csv(self.config["esecuzione"]["file_registro"])
        self.assertEqual(len(registro), 4)
        self.assertTrue(registro["motivo"].str.contains("trend positivo").all())

    def test_trend_negativo_cancella_lo_stop_prima_di_vendere(self):
        broker = BrokerFinto(posizioni={"T1": {"quantita": 10, "prezzo_medio": 100}}, stop={"T1": 10})
        self.ciclo(broker, self.in_discesa)
        self.assertEqual(broker.chiamate[:2], [("cancella_stop", "T1"), ("vendi", "T1", 10)])
        self.assertNotIn("compra", [x[0] for x in broker.chiamate])

    def test_app_bloccata_non_fa_nulla(self):
        stato = StatoRischio()
        stato.blocca("emergenza", "test")
        stato.salva(self.config)
        broker = BrokerFinto()
        c = self.ciclo(broker, self.in_salita)
        self.assertEqual(broker.chiamate, [])
        self.assertEqual(c.ordini, [])

    def test_limite_giornaliero_blocca_e_chiude_tutto(self):
        ieri = self.in_salita.index[-2]
        StoricoValori(self.config).aggiungi(ieri, 100_000)
        broker = BrokerFinto(valore=95_000, posizioni={"T1": {"quantita": 10, "prezzo_medio": 100}})
        self.ciclo(broker, self.in_salita)
        self.assertEqual(broker.chiamate, [("chiudi_tutto",)])
        self.assertEqual(StatoRischio.carica(self.config).tipo, GIORNALIERO)

    def test_stop_scattato_viene_rilevato_e_il_titolo_non_si_ricompra(self):
        Memoria(posizioni_ieri={"T1": 10}, vendite_inviate=[]).salva(self.config)
        broker = BrokerFinto()                          # T1 non c'è più: lo stop è scattato
        self.ciclo(broker, self.in_salita)
        comprati = {x[1] for x in broker.chiamate if x[0] == "compra"}
        self.assertNotIn("T1", comprati)
        self.assertIn("T3", comprati)                   # al suo posto entra la terza del settore
        self.assertIn("T1", Memoria.carica(self.config).stop_recenti)

    def test_rimette_lo_stop_mancante(self):
        mese = self.in_salita.index[-1].strftime("%Y-%m")
        Memoria(posizioni_ieri={"T1": 10}, ultimo_ribilanciamento=mese).salva(self.config)
        broker = BrokerFinto(posizioni={"T1": {"quantita": 10, "prezzo_medio": 100}}, stop={})
        self.ciclo(broker, self.in_salita)
        self.assertIn(("metti_stop", "T1", 10), broker.chiamate)

    def test_titoli_estranei_non_vengono_toccati(self):
        broker = BrokerFinto(posizioni={"TSLA": {"quantita": 5, "prezzo_medio": 200}})
        self.ciclo(broker, self.in_discesa)
        self.assertNotIn("TSLA", [x[1] for x in broker.chiamate if len(x) > 1])


class TestSicurezzaIBKR(unittest.TestCase):

    def setUp(self):
        self.config = config_di_prova()

    def test_porta_del_conto_reale_rifiutata_senza_collegarsi(self):
        self.config["broker"]["porta"] = 7496
        ib = mock.Mock()
        with self.assertRaises(ErroreSicurezza):
            BrokerIBKR(self.config, ib=ib)
        ib.connect.assert_not_called()

    def test_conto_reale_rifiutato_e_scollegato(self):
        ib = mock.Mock()
        ib.managedAccounts.return_value = ["U1234567"]
        with self.assertRaises(ErroreSicurezza):
            BrokerIBKR(self.config, ib=ib)
        ib.disconnect.assert_called_once()

    def test_conto_demo_accettato(self):
        ib = mock.Mock()
        ib.managedAccounts.return_value = ["DU1234567"]
        self.assertEqual(BrokerIBKR(self.config, ib=ib).account, "DU1234567")


if __name__ == "__main__":
    unittest.main()
