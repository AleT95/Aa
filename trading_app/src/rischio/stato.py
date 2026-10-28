"""
Lo "stato" del rischio salvato su file: la memoria dei freni.

Se l'app si blocca (limite di perdita superato o STOP DI EMERGENZA) lo scrive
in un file. Così, anche se spegni e riaccendi il computer, l'app ricorda di
essere bloccata e NON riparte da sola: per sbloccarla serve un tuo comando esplicito.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from ..config import CARTELLA_PROGETTO

# Tipi di blocco possibili
GIORNALIERO = "giornaliero"
MENSILE = "mensile"
EMERGENZA = "emergenza"


@dataclass
class StatoRischio:
    bloccato: bool = False
    tipo: str | None = None          # giornaliero | mensile | emergenza
    motivo: str | None = None
    quando: str | None = None        # data e ora del blocco

    def blocca(self, tipo: str, motivo: str, quando: datetime | None = None):
        # Un'emergenza non viene mai "declassata" da un blocco meno grave
        if self.bloccato and self.tipo == EMERGENZA:
            return
        self.bloccato, self.tipo, self.motivo = True, tipo, motivo
        self.quando = (quando or datetime.now()).isoformat(timespec="seconds")

    def sblocca(self):
        self.bloccato, self.tipo, self.motivo, self.quando = False, None, None, None

    def descrizione(self) -> str:
        if not self.bloccato:
            return "ATTIVA: nessun blocco in corso."
        return f"BLOCCATA ({self.tipo}) dal {self.quando}: {self.motivo}"

    # --- Salvataggio su file (usato dall'app dal vivo, non dal backtest) ---
    @staticmethod
    def percorso(config: dict) -> Path:
        return CARTELLA_PROGETTO / config["rischio"]["file_stato"]

    @classmethod
    def carica(cls, config: dict) -> "StatoRischio":
        file = cls.percorso(config)
        if not file.exists():
            return cls()
        return cls(**json.loads(file.read_text(encoding="utf-8")))

    def salva(self, config: dict):
        file = self.percorso(config)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
