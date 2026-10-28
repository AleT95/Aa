"""
FASE 4 - Prova di collegamento a Interactive Brokers (SOLO LETTURA: non invia ordini).

Come si lancia (dalla cartella trading_app), con TWS aperto sul conto DEMO:
    python -m scripts.fase4_test_connessione
"""

from src.broker.ibkr import BrokerIBKR, ErroreSicurezza
from src.config import carica_config


def main():
    config = carica_config()
    print("\nMi collego a TWS...")
    broker = BrokerIBKR(config)
    try:
        conto = broker.conto()
        posizioni = broker.posizioni()
        stop = broker.stop_attivi()
        print(f"✅ Collegato al conto DEMO {broker.account}")
        print(f"   Valore del conto: {conto['valore_totale']:,.0f} $   Cassa: {conto['cassa']:,.0f} $")
        if posizioni:
            print(f"\n   {'Titolo':<8}{'Quantità':>9}{'Prezzo medio':>14}{'Coperto da stop':>17}")
            for t, p in posizioni.items():
                print(f"   {t:<8}{p['quantita']:>9}{p['prezzo_medio']:>14.2f}{stop.get(t, 0):>17}")
        else:
            print("   Nessuna posizione aperta.")
    finally:
        broker.disconnetti()
    print("\nTutto ok: il collegamento funziona.\n")


if __name__ == "__main__":
    try:
        main()
    except (ConnectionError, ErroreSicurezza) as errore:
        print(f"\n⛔ {errore}\n")
        raise SystemExit(1)
