"""
FASE 2 - Backtest della strategia "termometro ETF".

Come si lancia (dalla cartella trading_app):
    python -m scripts.fase2_backtest

Risultati salvati nella cartella "risultati":
    - backtest_grafico.png        andamento strategia vs compra e tieni MSCI World
    - backtest_operazioni.csv     tutte le compravendite con data, prezzo e motivo
    - backtest_valori.csv         valore del portafoglio giorno per giorno
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

    # --- 2. Simulazione ------------------------------------------------
    bt = Backtest(config, prezzi)
    strategia = bt.esegui()

    benchmark = config["etf_benchmark"]
    riferimento = compra_e_tieni(
        prezzi.loc[strategia.index, benchmark], bt.capitale_iniziale, ModelloCosti(config),
        nome=f"Compra e tieni {benchmark}",
    )

    # --- 3. Pagelle ----------------------------------------------------
    rf = config["backtest"]["tasso_senza_rischio_pct"]
    m_strat = calcola_metriche(strategia, rf)
    m_rif = calcola_metriche(riferimento, rf)

    operazioni = bt.registro_operazioni()
    vendite = operazioni[operazioni["operazione"] == "VENDITA"] if len(operazioni) else operazioni
    vincenti = (vendite["utile"] > 0).mean() if len(vendite) else float("nan")
    commissioni = operazioni["commissione"].sum() if len(operazioni) else 0.0

    stampa_report(strategia, m_strat, m_rif, riferimento.name, len(operazioni), vincenti, commissioni)

    # --- 4. Salvataggio ------------------------------------------------
    cartella = CARTELLA_PROGETTO / config["backtest"]["cartella_risultati"]
    cartella.mkdir(exist_ok=True)
    operazioni.to_csv(cartella / "backtest_operazioni.csv", index=False)
    pd.concat([strategia, riferimento], axis=1).to_csv(cartella / "backtest_valori.csv")
    disegna_grafico(strategia, riferimento, cartella / "backtest_grafico.png")
    print(f" File salvati nella cartella: {cartella}\n")


def stampa_report(valori, m_strat, m_rif, nome_rif, n_operazioni, vincenti, commissioni):
    formato = {
        "Capitale finale": lambda v: f"{v:,.0f} $".replace(",", "."),
        "Sharpe ratio": lambda v: f"{v:.2f}",
    }
    print("\n" + "=" * 66)
    print(f" BACKTEST  {valori.index[0].date()}  ->  {valori.index[-1].date()}")
    print("=" * 66)
    print(f" {'':<26}{'Strategia':>18}{nome_rif:>22}")
    for chiave in m_strat:
        f = formato.get(chiave, lambda v: f"{v:+.1%}" if chiave != "Volatilità annua" else f"{v:.1%}")
        print(f" {chiave:<26}{f(m_strat[chiave]):>18}{f(m_rif[chiave]):>22}")
    print("-" * 66)
    print(f" {'Numero di operazioni':<26}{n_operazioni:>18}{1:>22}")
    print(f" {'Vendite in guadagno':<26}{vincenti:>18.0%}{'-':>22}")
    print(f" {'Commissioni pagate':<26}{commissioni:>16,.0f} ${'-':>22}".replace(",", "."))
    print("=" * 66)
    print(" ATTENZIONE: i risultati passati NON garantiscono quelli futuri.")
    print(" Le azioni in lista sono state scelte OGGI: il backtest è quindi troppo")
    print(" ottimista (\"errore del sopravvissuto\"), vedi README.\n")


def disegna_grafico(strategia, riferimento, file):
    fig, (alto, basso) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                      gridspec_kw={"height_ratios": [3, 1]})
    for serie, colore in [(strategia, "#1f6feb"), (riferimento, "#8c8c8c")]:
        alto.plot(serie.index, serie.values, label=serie.name, color=colore, linewidth=1.6)
        basso.plot(serie.index, serie_drawdown(serie).values * 100, color=colore, linewidth=1.2)
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
