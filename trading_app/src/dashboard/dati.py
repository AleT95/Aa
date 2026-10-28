"""
Preparazione dei dati per la dashboard.

Qui c'è solo "cucina": leggere file, fare conti, preparare tabelle.
La parte grafica sta in dashboard.py. Tenerle separate permette di
testare i conti senza dover aprire il browser.
"""

from pathlib import Path

import pandas as pd

from ..backtest import calcola_metriche


def leggi_csv(file: Path) -> pd.DataFrame:
    """Legge un registro CSV; se non esiste ancora restituisce una tabella vuota."""
    if not Path(file).exists():
        return pd.DataFrame()
    return pd.read_csv(file)


def ultime_righe(file: Path, quante: int = 20) -> list[str]:
    """Le ultime righe di un file di testo (es. logs/rischio.log), dalla più recente."""
    if not Path(file).exists():
        return []
    righe = Path(file).read_text(encoding="utf-8").splitlines()
    return list(reversed(righe[-quante:]))


def variazione_giornaliera(storico: pd.Series) -> float | None:
    """Variazione del conto rispetto alla sera prima (es. -0.012 = -1,2%)."""
    if len(storico) < 2:
        return None
    return storico.iloc[-1] / storico.iloc[-2] - 1


def confronto_benchmark(storico: pd.Series, prezzi_benchmark: pd.Series, nome_benchmark: str) -> pd.DataFrame:
    """
    Mette sullo stesso grafico il conto e l'ETF di riferimento, facendoli partire
    dallo STESSO valore: è come chiedersi "se il primo giorno avessi messo gli stessi
    soldi nell'ETF, quanto avrei oggi?".
    """
    if storico.empty:
        return pd.DataFrame()
    confronto = pd.DataFrame({"Conto demo": storico})
    if prezzi_benchmark.dropna().empty:          # prezzi dell'ETF non disponibili (es. niente internet)
        return confronto
    bench = prezzi_benchmark.reindex(storico.index, method="ffill").dropna()
    if not bench.empty:
        confronto[nome_benchmark] = bench / bench.iloc[0] * storico.loc[bench.index[0]]
    return confronto.dropna()


def metriche_confronto(confronto: pd.DataFrame) -> pd.DataFrame:
    """Rendimento, drawdown ecc. per ogni colonna del confronto (servono almeno 2 giorni)."""
    if len(confronto) < 2:
        return pd.DataFrame()
    righe = {nome: calcola_metriche(confronto[nome]) for nome in confronto.columns}
    tabella = pd.DataFrame(righe)
    return tabella.drop(index=["Capitale finale"], errors="ignore")


def tabella_posizioni(portafoglio: list[dict], stop: dict, gruppo_di: dict, valore_totale: float) -> pd.DataFrame:
    """La tabella delle posizioni aperte, pronta da mostrare."""
    righe = []
    for p in portafoglio:
        prezzo = p.get("prezzo_attuale")
        valore = p.get("valore") if p.get("valore") is not None else (
            p["quantita"] * prezzo if prezzo else None)
        guadagno_pct = (prezzo / p["prezzo_medio"] - 1) if prezzo and p["prezzo_medio"] else None
        coperto = stop.get(p["titolo"], 0)
        righe.append({
            "Titolo": p["titolo"],
            "Settore": gruppo_di.get(p["titolo"], "fuori strategia"),
            "Quantità": p["quantita"],
            "Prezzo medio": p["prezzo_medio"],
            "Prezzo attuale": prezzo,
            "Valore": valore,
            "Peso": (valore / valore_totale) if valore and valore_totale else None,
            "Guadagno $": p.get("guadagno"),
            "Guadagno %": guadagno_pct,
            "Stop loss": "✅ attivo" if coperto >= p["quantita"] else ("⚠️ parziale" if coperto else "❌ assente"),
        })
    tabella = pd.DataFrame(righe)
    if not tabella.empty:
        tabella = tabella.sort_values("Valore", ascending=False, na_position="last").reset_index(drop=True)
    return tabella
