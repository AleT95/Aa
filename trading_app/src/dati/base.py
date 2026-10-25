"""
Il "contratto" che ogni fornitore di dati deve rispettare.

Pensala come una presa elettrica standard: yfinance, Interactive Brokers o
qualsiasi altra fonte devono avere la stessa "spina" (stesso metodo `scarica`
con lo stesso formato di risultato). Così possiamo cambiare fonte senza
riscrivere la strategia.
"""

from abc import ABC, abstractmethod

import pandas as pd


class FornitoreDati(ABC):
    """Classe base astratta: non si usa direttamente, si "eredita"."""

    @abstractmethod
    def scarica(self, tickers: list[str], inizio: str, fine: str | None = None) -> pd.DataFrame:
        """
        Deve restituire una tabella (DataFrame) di prezzi di CHIUSURA RETTIFICATI
        (cioè corretti per dividendi e frazionamenti):
            - righe   = date (indice di tipo data)
            - colonne = ticker
        Esempio:
                         SPY     QQQ
            2015-01-02  180.1   95.3
            2015-01-05  177.0   94.0
        """
        raise NotImplementedError
