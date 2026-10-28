"""
Pacchetto "dati": tutto ciò che riguarda il recupero dei prezzi di mercato.

Uso tipico:
    from src.dati import crea_fornitore
    fornitore = crea_fornitore(config)
    prezzi = fornitore.scarica(["SPY", "QQQ"], inizio="2015-01-01")
"""

from .base import FornitoreDati
from .cache import FornitoreConCache
from .yahoo import FornitoreYahoo


def crea_fornitore(config: dict, con_cache: bool = True) -> FornitoreDati:
    """
    "Fabbrica" del fornitore dati: legge dal config quale usare.
    Per aggiungere un nuovo fornitore in futuro basta scrivere una nuova classe
    e aggiungerla qui: il resto dell'app non cambia.
    """
    nome = config["dati"]["fornitore"]
    if nome == "yfinance":
        fornitore = FornitoreYahoo()
    else:
        raise ValueError(f"Fornitore dati sconosciuto: {nome}")

    if not con_cache:
        return fornitore

    # Avvolgiamo il fornitore con la cache su disco
    return FornitoreConCache(
        fornitore,
        cartella=config["dati"]["cartella_cache"],
        validita_ore=config["dati"]["validita_cache_ore"],
    )
