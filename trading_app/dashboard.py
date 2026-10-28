"""
FASE 5 - Dashboard dell'app di trading.

Come si apre (dalla cartella trading_app):
    streamlit run dashboard.py
Si apre da sola nel browser all'indirizzo http://localhost:8501
(visibile SOLO dal tuo computer, vedi .streamlit/config.toml).

Mostra:
  - stato dell'app (attiva/bloccata) e pulsante STOP DI EMERGENZA
  - posizioni aperte con guadagni/perdite (dal vivo da TWS, se è aperto)
  - andamento del conto rispetto all'ETF MSCI World
  - registro delle operazioni e degli eventi di rischio
  - risultati dell'ultimo backtest
"""

import asyncio

import altair as alt
import pandas as pd
import streamlit as st

from src.broker.ibkr import BrokerIBKR
from src.config import CARTELLA_PROGETTO, carica_config
from src.dashboard.dati import (confronto_benchmark, leggi_csv, metriche_confronto,
                                tabella_posizioni, ultime_righe, variazione_giornaliera)
from src.dati import crea_fornitore
from src.esecuzione.memoria import Registro, StoricoValori
from src.rischio import StatoRischio
from src.rischio.emergenza import FILE_REGISTRO, attiva_stop_emergenza, sblocca

st.set_page_config(page_title="Termometro ETF · demo", page_icon="🌡️", layout="wide")
config = carica_config()
BENCHMARK = config["etf_benchmark"]
GRUPPO_DI = {az: g for g, lista in config["azioni"].items() for az in lista}


# =====================================================================
#  Lettura dei dati
# =====================================================================
def _assicura_event_loop():
    """Streamlit lavora in un "thread" secondario: la libreria IBKR ha bisogno di un suo event loop."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _collega_broker() -> BrokerIBKR:
    _assicura_event_loop()
    return BrokerIBKR(config, client_id=config["broker"]["client_id_dashboard"])


@st.cache_data(ttl=60, show_spinner="Leggo il conto da TWS...")
def leggi_da_tws() -> dict:
    """Legge conto, posizioni e stop dal vivo. Ricorda il risultato per 60 secondi."""
    try:
        broker = _collega_broker()
    except Exception as e:
        return {"errore": str(e)}
    try:
        return {"account": broker.account, "conto": broker.conto(),
                "portafoglio": broker.portafoglio(), "stop": broker.stop_attivi()}
    finally:
        broker.disconnetti()


@st.cache_data(ttl=3600, show_spinner="Scarico i prezzi dell'ETF di riferimento...")
def prezzi_benchmark(inizio: str) -> pd.Series:
    try:
        prezzi = crea_fornitore(config, con_cache=False).scarica([BENCHMARK], inizio=inizio)
        return prezzi[BENCHMARK]
    except Exception:
        return pd.Series(dtype=float)


def grafico_confronto(confronto: pd.DataFrame) -> alt.Chart:
    """Grafico a linee con l'asse verticale che NON parte da zero (così si vedono bene i movimenti)."""
    lungo = confronto.rename_axis("Data").reset_index().melt("Data", var_name="Portafoglio", value_name="Valore")
    colori = alt.Scale(domain=list(confronto.columns), range=["#1f6feb", "#8c8c8c"][: confronto.shape[1]])
    return alt.Chart(lungo).mark_line(strokeWidth=2).encode(
        x=alt.X("Data:T", title=None),
        y=alt.Y("Valore:Q", title="Valore ($)", scale=alt.Scale(zero=False), axis=alt.Axis(format=",.0f")),
        color=alt.Color("Portafoglio:N", scale=colori, legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("Data:T", format="%d/%m/%Y"), "Portafoglio:N", alt.Tooltip("Valore:Q", format=",.0f")],
    ).properties(height=380)


def intestazioni_leggibili(tabella: pd.DataFrame) -> pd.DataFrame:
    """'prezzo_riferimento' -> 'Prezzo riferimento'"""
    return tabella.rename(columns=lambda c: c.replace("_", " ").capitalize())


def dollari(valore) -> str:
    """Formatta un importo in dollari all'italiana: 12.345 $"""
    return "—" if valore is None or pd.isna(valore) else f"{valore:,.0f} $".replace(",", ".")


# =====================================================================
#  Barra laterale: stato, STOP DI EMERGENZA, sblocco
# =====================================================================
stato = StatoRischio.carica(config)

with st.sidebar:
    st.header("🌡️ Termometro ETF")
    st.caption("Conto **DEMO** Interactive Brokers")

    if stato.bloccato:
        st.error(f"**App BLOCCATA** ({stato.tipo})\n\n{stato.motivo}\n\ndal {stato.quando}")
    else:
        st.success("**App ATTIVA**: nessun blocco")

    dal_vivo = st.toggle("Leggi i dati dal vivo da TWS", value=True,
                         help="Se TWS non è aperto, la dashboard mostra solo i dati salvati nei file.")
    if st.button("🔄 Aggiorna", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.subheader("🛑 Stop di emergenza")
    st.caption("Cancella tutti gli ordini, vende TUTTE le posizioni del conto demo e blocca l'app.")
    conferma = st.checkbox("Confermo: voglio chiudere tutto")
    if st.button("🛑 STOP DI EMERGENZA", type="primary", disabled=not conferma, use_container_width=True):
        try:
            broker = _collega_broker()
        except Exception as e:
            broker = None
            st.warning(f"Broker non raggiungibile: {e}")
        try:
            attiva_stop_emergenza(config, broker, motivo="pulsante della dashboard")
        finally:
            if broker is not None:
                broker.disconnetti()
        st.cache_data.clear()
        if broker is None:
            st.error("App BLOCCATA, ma le posizioni NON sono state chiuse: fallo a mano da TWS.")
        else:
            st.error("App BLOCCATA e ordini di chiusura inviati. Controlla in TWS.")

    if stato.bloccato:
        st.divider()
        st.subheader("🔓 Sblocca")
        st.caption("Prima chiediti PERCHÉ si è fermata e se il motivo è risolto.")
        parola = st.text_input("Scrivi SBLOCCA per confermare")
        if st.button("Sblocca l'app", disabled=parola.strip().upper() != "SBLOCCA", use_container_width=True):
            sblocca(config)
            st.rerun()


# =====================================================================
#  Riepilogo in alto
# =====================================================================
st.title("Il tuo conto demo")

vivo = leggi_da_tws() if dal_vivo else {"errore": "lettura dal vivo disattivata"}
storico = StoricoValori(config).leggi()

if "errore" in vivo:
    if dal_vivo:
        st.warning(f"TWS non raggiungibile, mostro solo i dati salvati. ({vivo['errore']})")
    valore = storico.iloc[-1] if len(storico) else None
    cassa = None
    portafoglio, stop = [], {}
else:
    st.caption(f"Collegato al conto demo **{vivo['account']}** · dati di TWS aggiornati ogni minuto")
    valore, cassa = vivo["conto"]["valore_totale"], vivo["conto"]["cassa"]
    portafoglio, stop = vivo["portafoglio"], vivo["stop"]

oggi = variazione_giornaliera(storico)
dall_inizio = (valore / storico.iloc[0] - 1) if valore is not None and len(storico) else None
c1, c2, c3, c4 = st.columns(4)
c1.metric("Valore del conto", dollari(valore), f"{oggi:+.2%} ieri sera" if oggi is not None else None)
c2.metric("Dall'inizio", f"{dall_inizio:+.2%}" if dall_inizio is not None else "—",
          help="Rispetto al valore del primo controllo giornaliero salvato.")
c3.metric("Cassa", dollari(cassa))
c4.metric("Posizioni aperte", len(portafoglio) if "errore" not in vivo else "—")


# =====================================================================
#  Schede
# =====================================================================
scheda_pos, scheda_andamento, scheda_registro, scheda_bt = st.tabs(
    ["📊 Posizioni", f"📈 Andamento vs {BENCHMARK}", "📒 Registro", "🧪 Backtest"])

with scheda_pos:
    if "errore" in vivo:
        st.info("Le posizioni si vedono dal vivo con TWS aperto. Intanto trovi lo storico nella scheda Registro.")
    elif not portafoglio:
        st.info("Nessuna posizione aperta.")
    else:
        tabella = tabella_posizioni(portafoglio, stop, GRUPPO_DI, valore)
        st.dataframe(
            tabella, hide_index=True, use_container_width=True,
            column_config={
                "Prezzo medio": st.column_config.NumberColumn(format="$%.2f"),
                "Prezzo attuale": st.column_config.NumberColumn(format="$%.2f"),
                "Valore": st.column_config.NumberColumn(format="$%.0f"),
                "Peso": st.column_config.ProgressColumn(
                    format="percent", min_value=0.0, max_value=config["rischio"]["max_per_azione_pct"] / 100 * 1.5,
                    help=f"Limite: {config['rischio']['max_per_azione_pct']}% del conto"),
                "Guadagno $": st.column_config.NumberColumn(format="$%.0f"),
                "Guadagno %": st.column_config.NumberColumn(format="percent"),
            })
        totale = tabella["Guadagno $"].sum(min_count=1)
        if pd.notna(totale):
            st.caption(f"Guadagno/perdita non ancora realizzato sulle posizioni aperte: **{dollari(totale)}**")
        if (tabella["Stop loss"] != "✅ attivo").any():
            st.warning("Alcune posizioni non hanno uno stop loss completo: il prossimo controllo giornaliero lo rimetterà.")

with scheda_andamento:
    if len(storico) < 2:
        st.info("Il grafico comparirà dopo almeno due controlli giornalieri con --esegui "
                "(il valore del conto viene salvato ogni sera).")
    else:
        confronto = confronto_benchmark(storico, prezzi_benchmark(str(storico.index[0].date())), f"Compra e tieni {BENCHMARK}")
        if confronto.shape[1] < 2:
            st.warning(f"Non riesco a scaricare i prezzi di {BENCHMARK}: mostro solo il conto.")
        st.altair_chart(grafico_confronto(confronto), use_container_width=True)
        metriche = metriche_confronto(confronto)
        if not metriche.empty:
            st.dataframe(metriche.map(lambda v: f"{v:+.1%}" if pd.notna(v) else "—"), use_container_width=True)
        st.caption("Stesso capitale di partenza per entrambi: la linea grigia è quanto avresti con il semplice "
                   f"compra e tieni dell'ETF {BENCHMARK}.")

with scheda_registro:
    registro = Registro(config)
    st.subheader("Ordini inviati")
    operazioni = leggi_csv(registro.file_operazioni)
    if operazioni.empty:
        st.info("Ancora nessun ordine.")
    else:
        st.dataframe(intestazioni_leggibili(operazioni.iloc[::-1]), hide_index=True, use_container_width=True)
    st.subheader("Esecuzioni (prezzi effettivi)")
    esecuzioni = leggi_csv(registro.file_esecuzioni)
    if esecuzioni.empty:
        st.info("Ancora nessuna esecuzione registrata.")
    else:
        st.dataframe(intestazioni_leggibili(esecuzioni.iloc[::-1]), hide_index=True, use_container_width=True)
    st.subheader("Eventi di rischio")
    eventi = ultime_righe(FILE_REGISTRO, 30)
    st.code("\n".join(eventi) if eventi else "Nessun evento: nessuno stop, blocco o sblocco finora.", language=None)

with scheda_bt:
    cartella = CARTELLA_PROGETTO / config["backtest"]["cartella_risultati"]
    grafico = cartella / "backtest_grafico.png"
    if grafico.exists():
        st.image(str(grafico), use_container_width=True)
        st.caption("Ricorda: le azioni in lista sono state scelte oggi, quindi il backtest è più ottimista della realtà.")
    else:
        st.info("Nessun backtest trovato. Lancialo con: python -m scripts.fase2_backtest")
