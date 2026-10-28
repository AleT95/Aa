"""
Comandi di sicurezza dell'app.

Come si usano (dalla cartella trading_app):
    python -m scripts.rischio stato        mostra se l'app è attiva o bloccata
    python -m scripts.rischio stop         🛑 STOP DI EMERGENZA: blocca tutto e chiude le posizioni
    python -m scripts.rischio stop --si    come sopra, senza domanda di conferma
    python -m scripts.rischio sblocca      fa ripartire l'app dopo un blocco
"""

import argparse

from src.config import carica_config
from src.rischio.emergenza import attiva_stop_emergenza, puo_operare, sblocca


def collega_broker(config):
    """Il collegamento a Interactive Brokers arriverà nella Fase 4: per ora non c'è."""
    return None


def main():
    parser = argparse.ArgumentParser(description="Comandi di sicurezza dell'app di trading")
    parser.add_argument("comando", choices=["stato", "stop", "sblocca"])
    parser.add_argument("--si", action="store_true", help="salta la domanda di conferma (solo per 'stop')")
    args = parser.parse_args()
    config = carica_config()

    if args.comando == "stato":
        _, descrizione = puo_operare(config)
        print(f"\nApp {descrizione}\n")

    elif args.comando == "stop":
        if not args.si and input("\n🛑 Confermi lo STOP DI EMERGENZA? Scrivi SI: ").strip().upper() != "SI":
            print("Annullato: non ho fatto nulla.")
            return
        broker = collega_broker(config)
        stato = attiva_stop_emergenza(config, broker)
        print(f"\nApp {stato.descrizione()}")
        if broker is None:
            print("Nessun broker collegato (arriverà nella Fase 4): l'app è bloccata e non invierà ordini.")
        print("Per ripartire: python -m scripts.rischio sblocca\n")

    elif args.comando == "sblocca":
        ok, descrizione = puo_operare(config)
        if ok:
            print("\nL'app è già attiva, non c'è niente da sbloccare.\n")
            return
        print(f"\nStato attuale: {descrizione}")
        print("Prima di sbloccare, chiediti PERCHÉ si è fermata e se il motivo è risolto.")
        if input("Per sbloccare scrivi SBLOCCA: ").strip().upper() != "SBLOCCA":
            print("Annullato: l'app resta bloccata.")
            return
        sblocca(config)
        print("App sbloccata: dal prossimo controllo giornaliero tornerà a operare.\n")


if __name__ == "__main__":
    main()
