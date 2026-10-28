# App di trading "termometro ETF"

Gli ETF globali e settoriali fanno da "termometro" del mercato: se un'area o un settore
è in trend positivo, l'app compra le azioni più forti di quell'area; se il trend gira, riduce o chiude.

> ⚠️ Solo conto **demo** (paper trading) finché non si decide diversamente. Niente consigli finanziari: è un progetto per imparare.

## Stato delle fasi
- [x] **Fase 1** – struttura del progetto e download dati
- [x] **Fase 2** – strategia e backtest
- [x] **Fase 3** – gestione del rischio
- [x] **Fase 4** – collegamento al conto demo Interactive Brokers
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
│   ├── rischio/
│   │   ├── gestore.py      ← 5% per titolo, stop loss, limiti di perdita
│   │   ├── stato.py        ← ricorda su file se l'app è bloccata
│   │   └── emergenza.py    ← STOP DI EMERGENZA e sblocco
│   ├── broker/
│   │   ├── base.py         ← il "contratto" di un broker
│   │   └── ibkr.py         ← Interactive Brokers (SOLO conto demo, con doppio controllo)
│   └── esecuzione/
│       ├── giornaliero.py  ← il controllo della sera: decide e invia gli ordini
│       └── memoria.py      ← memoria tra un giorno e l'altro + REGISTRO operazioni
├── scripts/
│   ├── fase1_scarica_dati.py   ← prova della Fase 1
│   ├── fase2_backtest.py       ← il backtest completo (con e senza freni)
│   ├── rischio.py              ← comandi: stato / stop (emergenza) / sblocca
│   ├── fase4_test_connessione.py  ← prova il collegamento a IBKR (solo lettura)
│   └── fase4_giornaliero.py       ← il controllo giornaliero sul conto demo
├── avvia_giornaliero.bat   ← avvio automatico su Windows
├── risultati/              ← grafico e registro operazioni del backtest (creata in automatico)
├── tests/                  ← test automatici
├── data/cache/             ← qui finiscono i prezzi scaricati (creata in automatico)
└── logs/                   ← registro operazioni, esecuzioni, rischio e diario giornaliero
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
Con TWS aperto, lo stop cancella tutti gli ordini e vende tutte le posizioni del conto demo.
Se TWS è chiuso, l'app si blocca comunque, ma le posizioni vanno chiuse a mano da TWS.

## Fase 4: collegamento al conto DEMO di Interactive Brokers

### 1. Prepara IBKR (una volta sola)
1. Crea un account su interactivebrokers.com (anche senza versare soldi puoi avere il conto demo
   "Paper Trading"; il numero del conto demo inizia con **DU**).
2. Scarica e installa **TWS** (Trader Workstation).
3. Apri TWS e fai login scegliendo **Paper Trading** (non "Live"!).
4. In TWS: **File → Impostazioni globali → API → Impostazioni**:
   - spunta **Enable ActiveX and Socket Clients**
   - **togli** la spunta a **Read-Only API** (altrimenti l'app non può inviare ordini)
   - **Socket port: 7497**
   - in "Trusted IPs" lascia solo **127.0.0.1** (il tuo computer)
5. Sempre nelle impostazioni, in **Blocco e uscita**: imposta il **riavvio automatico** invece della disconnessione
   giornaliera, così TWS resta acceso.

### 2. Prova, in quest'ordine
```bash
python -m scripts.fase4_test_connessione       # 1) collegamento: mostra conto e posizioni (non tocca niente)
python -m scripts.fase4_giornaliero            # 2) PROVA: mostra gli ordini che invierebbe
python -m scripts.fase4_giornaliero --esegui   # 3) invia davvero gli ordini al conto DEMO
```
Senza `--esegui` l'app **non invia mai** ordini: guarda prima cosa farebbe.

### 3. Le sicurezze
- Accetta solo le porte demo (7497 TWS, 4002 IB Gateway): con le porte del conto reale si rifiuta di partire.
- Controlla il numero di conto: se non inizia con "D" (demo), si scollega subito.
- Ogni acquisto parte con il suo **stop loss attaccato**, che resta in TWS anche se l'app è spenta.
- Prima di vendere un titolo cancella il suo stop (altrimenti venderebbe due volte).
- I titoli nel conto che non fanno parte della strategia **non vengono toccati**
  (tranne con lo STOP DI EMERGENZA, che chiude tutto).

### 4. Come funziona la serata
Dopo la chiusura (dopo le 22:00 italiane) l'app: controlla se è bloccata → limiti di perdita → stop loss
scattati durante il giorno → vendite per trend negativo → (primo giorno del mese) classifica → acquisti.
Gli ordini sono "a mercato" e vengono eseguiti **all'apertura del giorno dopo**.

**Registro** (si aprono con Excel):
- `logs/operazioni.csv`: ogni ordine con data, titolo, prezzo di riferimento e **motivo**;
- `logs/esecuzioni.csv`: il prezzo a cui il broker li ha davvero eseguiti (aggiornato la sera dopo);
- `logs/giornaliero.log`: il diario di ogni controllo; `logs/rischio.log`: stop, blocchi e sblocchi.

### 5. Avvio automatico ogni sera (Windows)
1. Cerca **Utilità di pianificazione** nel menu Start → **Crea attività di base**.
2. Nome: "Trading demo" → Attivazione: **Giornalmente**, ore **22:30**.
3. Azione: **Avvio programma** → scegli il file `avvia_giornaliero.bat` nella cartella del progetto.
4. Il computer deve essere acceso e TWS aperto a quell'ora (nei weekend l'app non trova
   prezzi nuovi e non fa nulla di nuovo).

> 💱 Se il conto demo è in **euro**, l'app converte i valori in dollari con il cambio di IBKR.
> Comprando azioni americane con euro, IBKR "presta" i dollari: sul demo va bene; sul conto vero
> bisognerà convertire prima la valuta.
