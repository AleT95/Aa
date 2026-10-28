# App di trading "termometro ETF"

Gli ETF globali e settoriali fanno da "termometro" del mercato: se un'area o un settore
è in trend positivo, l'app compra le azioni più forti di quell'area; se il trend gira, riduce o chiude.

> ⚠️ Solo conto **demo** (paper trading) finché non si decide diversamente. Niente consigli finanziari: è un progetto per imparare.

## Stato delle fasi
- [x] **Fase 1** – struttura del progetto e download dati
- [x] **Fase 2** – strategia e backtest
- [x] **Fase 3** – gestione del rischio
- [ ] Fase 4 – collegamento al conto demo Interactive Brokers
- [ ] Fase 5 – dashboard Streamlit

## Struttura delle cartelle
```
trading_app/
├── config/config.yaml      ← TUTTI i parametri (ETF, azioni, medie mobili, rischio, costi)
├── src/
│   ├── config.py           ← legge config.yaml
│   ├── dati/
│   │   ├── base.py         ← il "contratto" che ogni fonte dati deve rispettare
│   │   ├── yahoo.py        ← fonte dati Yahoo Finance (yfinance)
│   │   └── cache.py        ← salva i dati su disco per non riscaricarli
│   ├── strategia/
│   │   ├── indicatori.py   ← medie mobili, momentum, "trend positivo"
│   │   └── termometro.py   ← le regole: quali azioni tenere e perché
│   ├── backtest/
│   │   ├── motore.py       ← simula il passato giorno per giorno
│   │   ├── costi.py        ← commissioni e slippage
│   │   └── metriche.py     ← rendimento, drawdown, Sharpe...
│   └── rischio/
│       ├── gestore.py      ← 5% per titolo, stop loss, limiti di perdita
│       ├── stato.py        ← ricorda su file se l'app è bloccata
│       └── emergenza.py    ← STOP DI EMERGENZA e sblocco
├── scripts/
│   ├── fase1_scarica_dati.py   ← prova della Fase 1
│   ├── fase2_backtest.py       ← il backtest completo (con e senza freni)
│   └── rischio.py              ← comandi: stato / stop (emergenza) / sblocca
├── risultati/              ← grafico e registro operazioni del backtest (creata in automatico)
├── tests/                  ← test automatici
├── data/cache/             ← qui finiscono i prezzi scaricati (creata in automatico)
└── logs/                   ← registri (fasi successive)
```

## Installazione (una volta sola)
Serve Python 3.10 o più recente. **Non mettere la cartella dentro OneDrive** (es. Desktop sincronizzato): usa per esempio `C:\progetti\trading_app`.
Apri il terminale nella cartella `trading_app` e scrivi:
```bash
python -m venv .venv                 # crea un "ambiente virtuale" (una scatola isolata per le librerie)
# Windows:   .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt      # installa le librerie
```

## Test della Fase 1
```bash
python -m unittest discover tests        # test automatici (non serve internet)
python -m scripts.fase1_scarica_dati     # scarica ~12 anni di prezzi e stampa un riepilogo
python -m scripts.fase1_scarica_dati --forza   # come sopra, ma ignora la cache
```
Il primo download dura qualche decina di secondi; i successivi (entro 12 ore) sono istantanei grazie alla cache.

## Test della Fase 2 (backtest)
```bash
python -m scripts.fase2_backtest
```
Stampa la tabella strategia vs compra e tieni MSCI World (URTH) e salva in `risultati/`:
- `backtest_grafico.png`: andamento del capitale e drawdown;
- `backtest_operazioni.csv`: ogni compravendita con data, titolo, prezzo e **motivo** (si apre con Excel);
- `backtest_valori.csv`: valore del portafoglio giorno per giorno.

### Le regole della strategia
1. **Ogni giorno** (dopo la chiusura) per ogni settore/area si guarda il suo ETF: è "in trend positivo"
   se il prezzo è sopra la media a 50 e a 200 giorni **e** il momentum (media dei rendimenti a 3 e 6 mesi) è positivo.
2. **Filtro globale**: se l'ETF mondo (URTH) non è in trend positivo, si vende tutto.
3. Se il termometro di un settore diventa negativo, si vendono subito le sue azioni.
4. **Una volta al mese** si rifà la classifica: per ogni settore positivo si tengono le 4 azioni
   con il momentum più alto (che siano anche sopra la propria media a 200 giorni).
5. Ogni azione nuova riceve il **5% del capitale**, e ogni mese le posizioni cresciute oltre il 5% vengono ridotte.
6. La decisione usa i prezzi di ieri e l'esecuzione avviene alla chiusura di oggi, con commissioni e slippage.

Più i freni della Fase 3, descritti sotto.

### ⚠️ Come leggere i risultati senza farsi illudere
- **Errore del sopravvissuto**: le azioni della lista (NVDA, LLY, META…) le abbiamo scelte *oggi*, sapendo
  già che sono andate bene. Nel 2015 nessuno sapeva quali sarebbero diventate le vincenti, quindi il
  backtest risulta **più bello della realtà**. Il confronto più onesto è con il drawdown e lo Sharpe, più che con il rendimento.
- **Troppo ritocco = autoinganno**: se cambi i parametri finché il risultato è stupendo, hai solo
  "imparato a memoria" il passato. Cambiali poco e con un motivo.

## Fase 3: gestione del rischio (i "freni")
| Freno | Cosa fa | Dove si cambia |
|---|---|---|
| Limite per titolo | mai più del 5% del capitale su una sola azione | `max_per_azione_pct` |
| Stop loss | vende se il titolo scende dell'8% (dal prezzo pagato o dal massimo raggiunto) | `stop_loss_pct`, `stop_loss_tipo` |
| Attesa dopo lo stop | il titolo appena fermato non si ricompra per 20 giorni | `giorni_attesa_dopo_stop` |
| Limite giornaliero | se il portafoglio perde il 3% in un giorno → **blocco** | `perdita_max_giornaliera_pct` |
| Limite mensile | se perde il 10% dall'inizio del mese → **blocco** | `perdita_max_mensile_pct` |
| Al blocco | vende tutto (oppure smette solo di comprare) | `chiudi_posizioni_al_blocco` |

Il blocco viene salvato in `data/stato_rischio.json`: anche se spegni il PC, l'app **non riparte da sola**.
Nel backtest simuliamo che tu la sblocchi dopo un giorno di pausa (blocco giornaliero) o il mese dopo (blocco mensile).

### Comandi di sicurezza
```bash
python -m scripts.rischio stato        # l'app è attiva o bloccata?
python -m scripts.rischio stop         # 🛑 STOP DI EMERGENZA (chiede conferma: scrivi SI)
python -m scripts.rischio stop --si    # 🛑 senza conferma, per quando hai fretta
python -m scripts.rischio sblocca      # riparte (chiede di scrivere SBLOCCA)
```
Ogni stop e sblocco viene annotato in `logs/rischio.log`.
Finché il broker non è collegato (Fase 4), lo stop blocca l'app ma non ha posizioni da vendere;
dalla Fase 4 venderà tutto anche sul conto demo. Nella Fase 5 avrà anche il suo pulsante rosso nella dashboard.
