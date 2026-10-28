"""
Backtest della strategia "termometro ETF" (Fase 2, con i freni della Fase 3).

Come si lancia (dalla cartella trading_app):
    python -m scripts.fase2_backtest

Confronta tre portafogli:
    - la strategia CON la gestione del rischio (stop loss e limiti di perdita)
    - la stessa strategia SENZA freni (per vedere cosa cambiano)
    - il semplice compra e tieni dell'ETF MSCI World

Risultati salvati nella cartella "risultati":
    - backtest_grafico.png        andamento dei portafogli e cadute (drawdown)
    - backtest_operazioni.csv     tutte le compravendite con data, prezzo e motivo
    - backtest_eventi_rischio.csv stop loss scattati, blocchi e ripartenze
    - backtest_valori.csv         valore dei portafogli giorno per giorno
"""

import logging

import matplotlib
matplotlib.use("Agg")                    # disegna il grafico su file, senza aprire finestre
import matplotlib.pyplot as plt
import pandas as pd

from src.backtest import Backtest, calcola_metriche
from src.backtest.costi import ModelloCosti
from src.backtest.metriche import serie_drawdown
from src.backtest.motore import compra_e_tieni
from src.config import CARTELLA_PROGETTO, carica_config, tutti_i_ticker
from src.dati import crea_fornitore


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    config = carica_config()

    # --- 1. Dati -------------------------------------------------------
    anni = config["dati"]["anni_storico"]
    inizio = (pd.Timestamp.today() - pd.DateOffset(years=anni)).strftime("%Y-%m-%d")
    prezzi = crea_fornitore(config).scarica(tutti_i_ticker(config), inizio=inizio)

    # --- 2. Simulazioni ------------------------------------------------
    bt = Backtest(config, prezzi, rischio_attivo=True)
    con_freni = bt.esegui().rename("Con freni")
    senza_freni = Backtest(config, prezzi, rischio_attivo=False).esegui().rename("Senza freni")

    benchmark = config["etf_benchmark"]
    riferimento = compra_e_tieni(
        prezzi.loc[con_freni.index, benchmark], bt.capitale_iniziale, ModelloCosti(config),
        nome=f"Compra e tieni {benchmark}",
    )
    portafogli = [con_freni, senza_freni, riferimento]

    # --- 3. Pagelle ----------------------------------------------------
    rf = config["backtest"]["tasso_senza_rischio_pct"]
    metriche = [calcola_metriche(p, rf) for p in portafogli]
    operazioni = bt.registro_operazioni()
    eventi = bt.registro_eventi()
    stampa_report(con_freni, portafogli, metriche, operazioni, eventi)

    # --- 4. Salvataggio ------------------------------------------------
    cartella = CARTELLA_PROGETTO / config["backtest"]["cartella_risultati"]
    cartella.mkdir(exist_ok=True)
    operazioni.to_csv(cartella / "backtest_operazioni.csv", index=False)
    eventi.to_csv(cartella / "backtest_eventi_rischio.csv", index=False)
    pd.concat(portafogli, axis=1).to_csv(cartella / "backtest_valori.csv")
    disegna_grafico(portafogli, cartella / "backtest_grafico.png")
    print(f" File salvati nella cartella: {cartella}\n")


def stampa_report(valori, portafogli, metriche, operazioni, eventi):
    def formatta(chiave, v):
        if chiave == "Capitale finale":
            return f"{v:,.0f} $".replace(",", ".")
        if chiave == "Sharpe ratio":
            return f"{v:.2f}"
        if chiave == "Volatilità annua":
            return f"{v:.1%}"
        return f"{v:+.1%}"

    larghezza = 26 + 20 * len(portafogli)
    print("\n" + "=" * larghezza)
    print(f" BACKTEST  {valori.index[0].date()}  ->  {valori.index[-1].date()}")
    print("=" * larghezza)
    print(" " + " " * 25 + "".join(f"{p.name:>20}" for p in portafogli))
    for chiave in metriche[0]:
        print(f" {chiave:<25}" + "".join(f"{formatta(chiave, m[chiave]):>20}" for m in metriche))
    print("-" * larghezza)

    vendite = operazioni[operazioni["operazione"] == "VENDITA"] if len(operazioni) else operazioni
    vincenti = f"{(vendite['utile'] > 0).mean():.0%}" if len(vendite) else "-"
    commissioni = operazioni["commissione"].sum() if len(operazioni) else 0.0
    conta = eventi["evento"].value_counts() if len(eventi) else {}
    righe = {
        "Numero di operazioni": len(operazioni),
        "Vendite in guadagno": vincenti,
        "Commissioni pagate": f"{commissioni:,.0f} $".replace(",", "."),
        "Stop loss scattati": conta.get("STOP LOSS", 0),
        "Blocchi giornalieri": conta.get("BLOCCO GIORNALIERO", 0),
        "Blocchi mensili": conta.get("BLOCCO MENSILE", 0),
    }
    print(" (dettagli della strategia con freni)")
    for chiave, valore in righe.items():
        print(f" {chiave:<25}{valore:>20}")
    print("=" * larghezza)
    print(" ATTENZIONE: i risultati passati NON garantiscono quelli futuri.")
    print(" Le azioni in lista sono state scelte OGGI: il backtest è quindi troppo")
    print(" ottimista (\"errore del sopravvissuto\"), vedi README.\n")


def disegna_grafico(portafogli, file):
    colori = ["#1f6feb", "#e8a33d", "#8c8c8c"]
    fig, (alto, basso) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                      gridspec_kw={"height_ratios": [3, 1]})
    for serie, colore in zip(portafogli, colori):
        alto.plot(serie.index, serie.values, label=serie.name, color=colore, linewidth=1.5)
        basso.plot(serie.index, serie_drawdown(serie).values * 100, color=colore, linewidth=1.1)
    alto.set_title("Strategia termometro ETF vs compra e tieni")
    alto.set_ylabel("Valore del portafoglio ($)")
    alto.legend(loc="upper left")
    alto.grid(alpha=0.3)
    basso.set_ylabel("Drawdown (%)")
    basso.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(file, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
