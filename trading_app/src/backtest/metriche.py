"""
Le "pagelle" della strategia.

- Rendimento totale: quanto è cresciuto il capitale dall'inizio alla fine.
- Rendimento annuo (CAGR): lo stesso, ma "spalmato" su ogni anno (interesse composto).
- Massimo drawdown: la peggior caduta da un massimo a un minimo successivo.
  È la misura del "mal di pancia": -30% vuol dire che a un certo punto hai visto
  sparire quasi un terzo dei soldi rispetto al punto più alto.
- Volatilità: quanto "balla" il valore del portafoglio in un anno.
- Sharpe ratio: rendimento in più rispetto a un investimento sicuro, diviso per la volatilità.
  In pratica: quanto guadagno per ogni unità di rischio. Sopra 1 è buono, sotto 0,5 è debole.
"""

import numpy as np
import pandas as pd

GIORNI_DI_BORSA_ANNO = 252


def calcola_metriche(valori: pd.Series, tasso_senza_rischio_pct: float = 0.0) -> dict:
    valori = valori.dropna()
    rendimenti = valori.pct_change().dropna()
    anni = (valori.index[-1] - valori.index[0]).days / 365.25

    rendimento_totale = valori.iloc[-1] / valori.iloc[0] - 1
    cagr = (1 + rendimento_totale) ** (1 / anni) - 1 if anni > 0 else np.nan

    picchi = valori.cummax()
    drawdown = valori / picchi - 1

    volatilita = rendimenti.std() * np.sqrt(GIORNI_DI_BORSA_ANNO)
    extra = rendimenti - (tasso_senza_rischio_pct / 100) / GIORNI_DI_BORSA_ANNO
    sharpe = extra.mean() / rendimenti.std() * np.sqrt(GIORNI_DI_BORSA_ANNO) if rendimenti.std() > 0 else np.nan

    return {
        "Capitale finale": valori.iloc[-1],
        "Rendimento totale": rendimento_totale,
        "Rendimento annuo (CAGR)": cagr,
        "Massimo drawdown": drawdown.min(),
        "Volatilità annua": volatilita,
        "Sharpe ratio": sharpe,
    }


def serie_drawdown(valori: pd.Series) -> pd.Series:
    return valori / valori.cummax() - 1
