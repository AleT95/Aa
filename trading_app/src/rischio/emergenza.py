"""
STOP DI EMERGENZA e controlli di sicurezza per l'app "dal vivo".

- attiva_stop_emergenza(): blocca l'app e (dalla Fase 4) chiude tutte le posizioni sul broker.
- puo_operare(): da chiamare PRIMA di qualsiasi ordine: se l'app è bloccata, non si fa nulla.
- sblocca(): l'unico modo per far ripartire l'app dopo un blocco. Lo decidi solo tu.

Ogni evento viene scritto anche nel registro logs/rischio.log.
"""

from datetime import datetime

from ..config import CARTELLA_PROGETTO
from .stato import EMERGENZA, StatoRischio

FILE_REGISTRO = CARTELLA_PROGETTO / "logs" / "rischio.log"


def scrivi_registro(messaggio: str):
    FILE_REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    with open(FILE_REGISTRO, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} | {messaggio}\n")


def attiva_stop_emergenza(config: dict, broker=None, motivo: str = "comando manuale") -> StatoRischio:
    """
    1. Segna l'app come bloccata (EMERGENZA) nel file di stato: non partiranno altri ordini.
    2. Se c'è un broker collegato, cancella gli ordini in attesa e vende tutto.
    Il blocco viene salvato PRIMA di toccare il broker: anche se la chiusura
    fallisse a metà, l'app resterebbe comunque ferma.
    """
    stato = StatoRischio.carica(config)
    stato.blocca(EMERGENZA, motivo)
    stato.salva(config)
    scrivi_registro(f"STOP DI EMERGENZA attivato: {motivo}")

    if broker is not None:
        broker.chiudi_tutto(motivo=f"STOP DI EMERGENZA: {motivo}")
        scrivi_registro("STOP DI EMERGENZA: richiesta di chiusura di tutte le posizioni inviata al broker")
    return stato


def blocca_per_limite(config: dict, tipo: str, motivo: str) -> StatoRischio:
    """Usato dall'app quando supera un limite di perdita giornaliero o mensile."""
    stato = StatoRischio.carica(config)
    stato.blocca(tipo, motivo)
    stato.salva(config)
    scrivi_registro(f"BLOCCO {tipo}: {motivo}")
    return stato


def puo_operare(config: dict) -> tuple[bool, str]:
    """True se l'app può inviare ordini; altrimenti False e il motivo."""
    stato = StatoRischio.carica(config)
    return (not stato.bloccato), stato.descrizione()


def sblocca(config: dict) -> StatoRischio:
    stato = StatoRischio.carica(config)
    precedente = stato.descrizione()
    stato.sblocca()
    stato.salva(config)
    scrivi_registro(f"SBLOCCO manuale (era: {precedente})")
    return stato
