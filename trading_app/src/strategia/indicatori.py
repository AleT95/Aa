"""
Indicatori tecnici: i "sensori" del termometro.

Tutte le funzioni lavorano su una tabella di prezzi (righe = giorni, colonne = ticker)
e restituiscono una tabella della stessa forma, così calcoliamo tutto in un colpo
per tutti i titoli e tutti i giorni.
"""

import pandas as pd

GIORNI_DI_BORSA_AL_MESE = 21


def media_mobile(prezzi: pd.DataFrame, giorni: int) -> pd.DataFrame:
    """Media dei prezzi degli ultimi `giorni` giorni (es. 50 o 200)."""
    return prezzi.rolling(giorni).mean()


def momentum(prezzi: pd.DataFrame, mesi: list[int]) -> pd.DataFrame:
    """
    Quanto è salito (o sceso) il prezzo negli ultimi N mesi, in percentuale.
    Con più periodi (es. 3 e 6 mesi) facciamo la media: 0.10 = +10%.
    """
    rendimenti = [prezzi / prezzi.shift(m * GIORNI_DI_BORSA_AL_MESE) - 1 for m in mesi]
    return sum(rendimenti) / len(rendimenti)


def trend_positivo(prezzi: pd.DataFrame, mm_breve: int, mm_lunga: int, mesi: list[int]) -> pd.DataFrame:
    """
    True dove il trend è positivo, cioè quando valgono TUTTE e tre:
      1. prezzo sopra la media mobile breve (es. 50 giorni)
      2. prezzo sopra la media mobile lunga (es. 200 giorni)
      3. momentum positivo
    Dove mancano dati (es. titolo appena quotato) il risultato è False: nel dubbio, non si compra.
    """
    return (
        (prezzi > media_mobile(prezzi, mm_breve))
        & (prezzi > media_mobile(prezzi, mm_lunga))
        & (momentum(prezzi, mesi) > 0)
    )
