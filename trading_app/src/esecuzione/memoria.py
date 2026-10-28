"""
La memoria dell'app tra un giorno e l'altro, salvata su file.

L'app viene accesa una volta al giorno e poi si spegne: per sapere cosa è
successo nel frattempo (es. uno stop loss scattato durante la giornata)
deve ricordarsi com'era la situazione la sera prima.
"""

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from ..config import CARTELLA_PROGETTO


def _percorso(config: dict, chiave: str) -> Path:
    return CARTELLA_PROGETTO / config["esecuzione"][chiave]


@dataclass
class Memoria:
    posizioni_ieri: dict = field(default_factory=dict)      # {titolo: quantità} di ieri sera
    vendite_inviate: list = field(default_factory=list)     # titoli che IERI abbiamo deciso di vendere
    stop_recenti: dict = field(default_factory=dict)        # {titolo: "AAAA-MM-GG"} stop loss scattati
    ultimo_ribilanciamento: str | None = None               # "AAAA-MM" dell'ultimo ribilanciamento

    @classmethod
    def carica(cls, config: dict) -> "Memoria":
        file = _percorso(config, "file_memoria")
        if not file.exists():
            return cls()
        return cls(**json.loads(file.read_text(encoding="utf-8")))

    def salva(self, config: dict):
        file = _percorso(config, "file_memoria")
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")


class StoricoValori:
    """Il valore del conto ogni sera: serve per i limiti di perdita giornaliera e mensile."""

    def __init__(self, config: dict):
        self.file = _percorso(config, "file_storico_valori")

    def leggi(self) -> pd.Series:
        if not self.file.exists():
            return pd.Series(dtype=float)
        dati = pd.read_csv(self.file, index_col="data", parse_dates=True)
        return dati["valore"]

    def aggiungi(self, giorno: pd.Timestamp, valore: float):
        storico = self.leggi()
        storico.loc[pd.Timestamp(giorno)] = round(valore, 2)       # se il giorno c'è già, lo sovrascrive
        self.file.parent.mkdir(parents=True, exist_ok=True)
        storico.sort_index().rename("valore").to_csv(self.file, index_label="data")


class Registro:
    """
    Il REGISTRO delle operazioni (file CSV, si apre con Excel):
      - operazioni.csv: ogni ordine inviato, con data, titolo, prezzo di riferimento e MOTIVO
      - esecuzioni.csv: il prezzo a cui il broker ha davvero eseguito gli ordini
    """

    COLONNE_OPERAZIONI = ["data_ora", "titolo", "operazione", "quantita", "prezzo_riferimento", "motivo", "id_ordine"]
    COLONNE_ESECUZIONI = ["id", "data", "titolo", "operazione", "quantita", "prezzo", "commissione"]

    def __init__(self, config: dict):
        self.file_operazioni = _percorso(config, "file_registro")
        self.file_esecuzioni = _percorso(config, "file_esecuzioni")

    @staticmethod
    def _aggiungi_righe(file: Path, colonne: list[str], righe: list[dict]):
        if not righe:
            return
        file.parent.mkdir(parents=True, exist_ok=True)
        nuovo = not file.exists()
        with open(file, "a", newline="", encoding="utf-8") as f:
            scrittore = csv.DictWriter(f, fieldnames=colonne)
            if nuovo:
                scrittore.writeheader()
            scrittore.writerows(righe)

    def scrivi_operazione(self, riga: dict):
        self._aggiungi_righe(self.file_operazioni, self.COLONNE_OPERAZIONI, [riga])

    def aggiorna_esecuzioni(self, esecuzioni: list[dict]) -> int:
        """Aggiunge le esecuzioni nuove (senza doppioni). Restituisce quante ne ha aggiunte."""
        gia_presenti = set()
        if self.file_esecuzioni.exists():
            with open(self.file_esecuzioni, encoding="utf-8") as f:
                gia_presenti = {r["id"] for r in csv.DictReader(f)}
        nuove = [e for e in esecuzioni if e["id"] not in gia_presenti]
        self._aggiungi_righe(self.file_esecuzioni, self.COLONNE_ESECUZIONI, nuove)
        return len(nuove)
