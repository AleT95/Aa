"""
Costi di trading: commissioni del broker e slippage.

Lo slippage è la differenza tra il prezzo che "vedi" e quello a cui compri davvero:
nella realtà compri un po' più caro e vendi un po' più a buon mercato.
Ignorarlo farebbe sembrare la strategia migliore di quanto sia.
"""


class ModelloCosti:

    def __init__(self, config: dict):
        c = config["costi"]
        self.per_azione = c["commissione_per_azione"]
        self.minima = c["commissione_minima"]
        self.max_pct = c["commissione_max_pct"] / 100
        self.slippage = c["slippage_pct"] / 100

    def prezzo_esecuzione(self, prezzo: float, acquisto: bool) -> float:
        """Prezzo effettivo: un po' più alto se compri, un po' più basso se vendi."""
        return prezzo * (1 + self.slippage) if acquisto else prezzo * (1 - self.slippage)

    def commissione(self, quantita: int, prezzo: float) -> float:
        """Commissione stile Interactive Brokers "Fixed": tot $ per azione, con un minimo e un massimo."""
        lorda = max(self.minima, quantita * self.per_azione)
        return min(lorda, quantita * prezzo * self.max_pct)
