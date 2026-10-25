# App di trading "termometro ETF"

Gli ETF globali e settoriali fanno da "termometro" del mercato: se un'area o un settore
è in trend positivo, l'app compra le azioni più forti di quell'area; se il trend gira, riduce o chiude.

> ⚠️ Solo conto **demo** (paper trading) finché non si decide diversamente. Niente consigli finanziari: è un progetto per imparare.

## Stato delle fasi
- [x] **Fase 1** – struttura del progetto e download dati
- [ ] Fase 2 – strategia e backtest
- [ ] Fase 3 – gestione del rischio
- [ ] Fase 4 – collegamento al conto demo Interactive Brokers
- [ ] Fase 5 – dashboard Streamlit

## Struttura delle cartelle
```
trading_app/
├── config/config.yaml      ← TUTTI i parametri (ETF, azioni, medie mobili, rischio, costi)
├── src/
│   ├── config.py           ← legge config.yaml
│   └── dati/
│       ├── base.py         ← il "contratto" che ogni fonte dati deve rispettare
│       ├── yahoo.py        ← fonte dati Yahoo Finance (yfinance)
│       └── cache.py        ← salva i dati su disco per non riscaricarli
├── scripts/fase1_scarica_dati.py   ← script di prova della Fase 1
├── tests/                  ← test automatici
├── data/cache/             ← qui finiscono i prezzi scaricati (creata in automatico)
└── logs/                   ← registri (fasi successive)
```

## Installazione (una volta sola)
Serve Python 3.10 o più recente. Apri il terminale nella cartella `trading_app` e scrivi:
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
