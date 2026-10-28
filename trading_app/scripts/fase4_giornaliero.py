"""
FASE 4 - Il controllo giornaliero sul conto DEMO di Interactive Brokers.

Prima di lanciarlo: TWS deve essere aperto e collegato al conto DEMO (vedi README).

Come si lancia (dalla cartella trading_app):
    python -m scripts.fase4_giornaliero            PROVA: mostra gli ordini, NON li invia
    python -m scripts.fase4_giornaliero --esegui   invia davvero gli ordini al conto demo

Va lanciato una volta al giorno, dopo la chiusura della borsa americana
(dopo le 22:00 ora italiana). Per farlo in automatico: avvia_giornaliero.bat
"""

import argparse
import logging

import pandas as pd

from src.broker.ibkr import BrokerIBKR, ErroreSicurezza
from src.config import CARTELLA_PROGETTO, carica_config, tutti_i_ticker
from src.dati import crea_fornitore
from src.esecuzione import CicloGiornaliero


def main():
    parser = argparse.ArgumentParser(description="Controllo giornaliero sul conto demo")
    parser.add_argument("--esegui", action="store_true", help="invia davvero gli ordini al conto DEMO")
    args = parser.parse_args()

    (CARTELLA_PROGETTO / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(CARTELLA_PROGETTO / "logs" / "giornaliero.log", encoding="utf-8")],
    )
    config = carica_config()

    # Prezzi aggiornati (forza=True: niente cache, vogliamo l'ultima chiusura)
    anni = 2      # per medie mobili e momentum bastano 2 anni di storia
    inizio = (pd.Timestamp.today() - pd.DateOffset(years=anni)).strftime("%Y-%m-%d")
    prezzi = crea_fornitore(config).scarica(tutti_i_ticker(config), inizio=inizio, forza=True)

    broker = BrokerIBKR(config)
    try:
        ciclo = CicloGiornaliero(config, broker, prezzi, esegui=args.esegui)
        ciclo.esegui_ciclo()
    finally:
        broker.disconnetti()

    stampa_ordini(ciclo.ordini, args.esegui)


def stampa_ordini(ordini, eseguiti):
    if not ordini:
        return
    print("\n" + "=" * 100)
    print(" ORDINI " + ("INVIATI AL CONTO DEMO" if eseguiti else "CHE VERREBBERO INVIATI (modalità prova)"))
    print("=" * 100)
    print(f" {'Operazione':<11}{'Titolo':<8}{'Quantità':>9}{'Prezzo rif.':>13}   Motivo")
    for o in ordini:
        print(f" {o['operazione']:<11}{o['titolo']:<8}{o['quantita']:>9}{o['prezzo']:>13.2f}   {o['motivo']}")
    print("=" * 100)
    if not eseguiti:
        print(" Per inviarli davvero al conto DEMO: python -m scripts.fase4_giornaliero --esegui")
    print()


if __name__ == "__main__":
    try:
        main()
    except (ConnectionError, ErroreSicurezza) as errore:
        print(f"\n⛔ {errore}\n")
        raise SystemExit(1)
