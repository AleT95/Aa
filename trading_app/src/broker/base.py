"""
Il "contratto" che ogni broker deve rispettare (come per i dati nella Fase 1).

Oggi c'è solo Interactive Brokers, ma il resto dell'app parla con questa
interfaccia: così nei test usiamo un broker finto e, un domani, potremmo
cambiare broker senza riscrivere la logica.
"""

from abc import ABC, abstractmethod


class Broker(ABC):

    @abstractmethod
    def conto(self) -> dict:
        """{'valore_totale': ..., 'cassa': ...} in dollari."""

    @abstractmethod
    def posizioni(self) -> dict[str, dict]:
        """{ticker: {'quantita': int, 'prezzo_medio': float}} delle azioni in portafoglio."""

    @abstractmethod
    def stop_attivi(self) -> dict[str, int]:
        """{ticker: quantità coperta} degli ordini di stop loss in attesa presso il broker."""

    @abstractmethod
    def compra(self, ticker: str, quantita: int, stop: dict, motivo: str) -> str:
        """
        Ordine di acquisto "a mercato" con stop loss ATTACCATO: lo stop si attiva
        da solo appena l'acquisto viene eseguito.
        stop = {'tipo': 'fisso'|'trailing', 'percentuale': 8, 'livello': 92.0}
        Restituisce l'identificativo dell'ordine.
        """

    @abstractmethod
    def vendi(self, ticker: str, quantita: int, motivo: str) -> str:
        """Ordine di vendita a mercato. Prima di vendere bisogna cancellare lo stop del titolo!"""

    @abstractmethod
    def metti_stop(self, ticker: str, quantita: int, stop: dict) -> str:
        """Piazza uno stop loss su una posizione già esistente."""

    @abstractmethod
    def cancella_stop(self, ticker: str):
        """Cancella gli stop loss in attesa di un titolo."""

    @abstractmethod
    def chiudi_tutto(self, motivo: str) -> list[dict]:
        """
        STOP DI EMERGENZA: cancella TUTTI gli ordini e vende TUTTE le posizioni.
        Restituisce [{'titolo', 'quantita', 'id'}] degli ordini di chiusura inviati.
        """

    @abstractmethod
    def esecuzioni(self) -> list[dict]:
        """Ordini eseguiti di recente: [{'id', 'data', 'titolo', 'operazione', 'quantita', 'prezzo', 'commissione'}]."""

    @abstractmethod
    def disconnetti(self):
        """Chiude il collegamento."""
