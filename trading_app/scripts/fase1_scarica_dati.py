"""
FASE 1 - Test: scarica i dati di tutti gli ETF e le azioni del config
e stampa un piccolo riepilogo.

Come si lancia (dalla cartella trading_app):
    python -m scripts.fase1_scarica_dati
    python -m scripts.fase1_scarica_dati --forza     # ignora la cache e riscarica
"""

import argparse
import logging

import pandas as pd

from src.config import carica_config, tutti_i_ticker
from src.dati import crea_fornitore


def main():
    parser = argparse.ArgumentParser(description="Scarica i dati di mercato")
    parser.add_argument("--forza", action="store_true", help="riscarica ignorando la cache")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    config = carica_config()
    tickers = tutti_i_ticker(config)
    anni = config["dati"]["anni_storico"]
    inizio = (pd.Timestamp.today() - pd.DateOffset(years=anni)).strftime("%Y-%m-%d")

    fornitore = crea_fornitore(config)
    prezzi = fornitore.scarica(tickers, inizio=inizio, forza=args.forza)

    # --- Riepilogo ---------------------------------------------------
    print("\n" + "=" * 62)
    print(f" Ticker richiesti: {len(tickers)}   ricevuti: {prezzi.shape[1]}")
    print(f" Periodo: {prezzi.index.min().date()} -> {prezzi.index.max().date()}"
          f"  ({len(prezzi)} giorni di borsa)")
    print("=" * 62)
    print(f" {'Ticker':<8}{'Primo giorno':<14}{'Ultimo prezzo':>14}{'Rend. totale':>14}")
    for t in prezzi.columns:
        serie = prezzi[t].dropna()
        rend = (serie.iloc[-1] / serie.iloc[0] - 1) * 100
        print(f" {t:<8}{str(serie.index[0].date()):<14}{serie.iloc[-1]:>14.2f}{rend:>13.0f}%")
    print("=" * 62)
    print(" Nota: un 'primo giorno' recente vuol dire che il titolo è quotato da poco.\n")


if __name__ == "__main__":
    main()
