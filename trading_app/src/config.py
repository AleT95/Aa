"""
Caricamento della configurazione.

Legge il file config/config.yaml e lo restituisce come un dizionario Python
(una struttura "chiave -> valore", tipo una rubrica).
Tutti gli altri moduli prendono i parametri da qui, così nessun numero
è "scritto a mano" dentro il codice.
"""

from pathlib import Path

import yaml

# Cartella principale del progetto (quella che contiene config/, src/, data/...)
CARTELLA_PROGETTO = Path(__file__).resolve().parent.parent
FILE_CONFIG_PREDEFINITO = CARTELLA_PROGETTO / "config" / "config.yaml"


def carica_config(percorso: str | Path | None = None) -> dict:
    """Legge il file YAML e controlla che le sezioni principali ci siano."""
    percorso = Path(percorso) if percorso else FILE_CONFIG_PREDEFINITO
    with open(percorso, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Controllo di sicurezza: se manca una sezione, meglio accorgersene subito
    sezioni_obbligatorie = ["dati", "etf_aree", "etf_settori", "azioni", "strategia", "rischio", "costi", "broker"]
    mancanti = [s for s in sezioni_obbligatorie if s not in config]
    if mancanti:
        raise ValueError(f"Nel file di configurazione mancano le sezioni: {mancanti}")

    # Paracadute: il broker deve restare in modalità demo
    if config["broker"].get("modalita") != "paper":
        raise ValueError("Per sicurezza è ammessa solo la modalità 'paper' (conto demo).")

    return config


def tutti_i_ticker(config: dict) -> list[str]:
    """Restituisce la lista (senza doppioni) di tutti i ticker da scaricare: ETF + azioni."""
    ticker = [config["etf_benchmark"]]
    ticker += list(config["etf_aree"].values())
    ticker += list(config["etf_settori"].values())
    for lista in config["azioni"].values():
        ticker += lista
    # dict.fromkeys toglie i doppioni mantenendo l'ordine
    return list(dict.fromkeys(ticker))
