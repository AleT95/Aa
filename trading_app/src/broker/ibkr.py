"""
Collegamento a Interactive Brokers tramite TWS (o IB Gateway) e la libreria ib_async.

DUE SICUREZZE per restare sul conto DEMO:
  1. Porta: accettiamo solo 7497 (TWS demo) e 4002 (IB Gateway demo).
     Le porte del conto reale (7496 e 4001) vengono rifiutate prima ancora di collegarsi.
  2. Numero di conto: i conti demo di IBKR iniziano con "D" (es. DU1234567).
     Se il conto collegato non è demo, ci scolleghiamo subito e l'app si ferma.

L'app lavora in dollari. Se il tuo conto è in euro, i valori vengono convertiti
con il cambio che fornisce IBKR stesso.
"""

import logging

from ib_async import IB, MarketOrder, Order, Stock, StopOrder
from ib_async.order import OrderStatus

from .base import Broker

log = logging.getLogger(__name__)

PORTE_DEMO = {7497, 4002}
ETICHETTA = "termometro"          # compare negli ordini su TWS, per riconoscere quelli dell'app


class ErroreSicurezza(RuntimeError):
    """Qualcosa non torna con la modalità demo: meglio fermarsi."""


class BrokerIBKR(Broker):

    def __init__(self, config: dict, ib: IB | None = None):
        b = config["broker"]
        if b["modalita"] != "paper":
            raise ErroreSicurezza("È ammessa solo la modalità 'paper' (conto demo).")
        if b["porta"] not in PORTE_DEMO:
            raise ErroreSicurezza(f"La porta {b['porta']} non è una porta del conto demo (ammesse: {sorted(PORTE_DEMO)}).")

        self.ib = ib or IB()
        try:
            self.ib.connect(b["host"], b["porta"], clientId=b["client_id"], timeout=b["timeout_secondi"])
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            raise ConnectionError(
                "Non riesco a collegarmi a TWS. Controlla che: 1) TWS sia aperto e collegato al conto DEMO; "
                "2) in TWS sia attiva l'API (Configurazione > API > Impostazioni: 'Enable ActiveX and Socket Clients'); "
                f"3) la porta in TWS sia {b['porta']}."
            ) from e

        conti = self.ib.managedAccounts()
        if not conti or not all(c.startswith("D") for c in conti):
            self.ib.disconnect()
            raise ErroreSicurezza(f"Il conto collegato ({conti}) NON è un conto demo. Mi sono scollegato per sicurezza.")
        self.account = conti[0]
        self._contratti: dict[str, Stock] = {}
        log.info("Collegato a IBKR, conto demo %s", self.account)

    # ------------------------------------------------------------------
    #  Lettura del conto
    # ------------------------------------------------------------------
    def _cambio_usd(self) -> float:
        """Quante unità della valuta del conto vale 1 dollaro (1 se il conto è in dollari)."""
        for v in self.ib.accountValues(self.account):
            if v.tag == "ExchangeRate" and v.currency == "USD":
                return float(v.value)
        log.warning("Cambio USD non trovato: suppongo che il conto sia in dollari.")
        return 1.0

    def conto(self) -> dict:
        valori = {v.tag: float(v.value) for v in self.ib.accountSummary(self.account)
                  if v.tag in ("NetLiquidation", "TotalCashValue")}
        cambio = self._cambio_usd()
        return {"valore_totale": valori["NetLiquidation"] / cambio, "cassa": valori["TotalCashValue"] / cambio}

    def posizioni(self) -> dict[str, dict]:
        return {
            p.contract.symbol: {"quantita": int(p.position), "prezzo_medio": float(p.avgCost)}
            for p in self.ib.positions(self.account)
            if p.contract.secType == "STK" and p.position != 0
        }

    def _ordini_stop_aperti(self, ticker: str | None = None):
        for t in self.ib.openTrades():
            o = t.order
            if (o.action == "SELL" and o.orderType in ("STP", "TRAIL")
                    and t.orderStatus.status in OrderStatus.ActiveStates | {"PreSubmitted", "Submitted"}
                    and (ticker is None or t.contract.symbol == ticker)):
                yield t

    def stop_attivi(self) -> dict[str, int]:
        coperti: dict[str, int] = {}
        for t in self._ordini_stop_aperti():
            coperti[t.contract.symbol] = coperti.get(t.contract.symbol, 0) + int(t.order.totalQuantity)
        return coperti

    # ------------------------------------------------------------------
    #  Ordini
    # ------------------------------------------------------------------
    def _contratto(self, ticker: str) -> Stock:
        if ticker not in self._contratti:
            contratto = Stock(ticker, "SMART", "USD")
            self.ib.qualifyContracts(contratto)
            self._contratti[ticker] = contratto
        return self._contratti[ticker]

    def _ordine_stop(self, quantita: int, stop: dict) -> Order:
        if stop["tipo"] == "trailing":
            ordine = Order(action="SELL", orderType="TRAIL", totalQuantity=quantita,
                           trailingPercent=stop["percentuale"])
        else:
            ordine = StopOrder("SELL", quantita, round(stop["livello"], 2))
        ordine.tif = "GTC"            # resta valido finché non scatta o lo cancelliamo
        ordine.account = self.account
        ordine.orderRef = ETICHETTA
        return ordine

    def compra(self, ticker: str, quantita: int, stop: dict, motivo: str) -> str:
        contratto = self._contratto(ticker)
        padre = MarketOrder("BUY", quantita, tif="DAY", account=self.account, orderRef=ETICHETTA)
        padre.orderId = self.ib.client.getReqId()
        padre.transmit = False                          # parte solo insieme al suo stop
        figlio = self._ordine_stop(quantita, stop)
        figlio.parentId = padre.orderId                 # lo stop si attiva quando l'acquisto è eseguito
        figlio.transmit = True
        self.ib.placeOrder(contratto, padre)
        self.ib.placeOrder(contratto, figlio)
        self.ib.sleep(1)
        log.info("ACQUISTO %s x%d inviato (%s)", ticker, quantita, motivo)
        return str(padre.orderId)

    def vendi(self, ticker: str, quantita: int, motivo: str) -> str:
        ordine = MarketOrder("SELL", quantita, tif="DAY", account=self.account, orderRef=ETICHETTA)
        trade = self.ib.placeOrder(self._contratto(ticker), ordine)
        self.ib.sleep(1)
        log.info("VENDITA %s x%d inviata (%s)", ticker, quantita, motivo)
        return str(trade.order.orderId)

    def metti_stop(self, ticker: str, quantita: int, stop: dict) -> str:
        trade = self.ib.placeOrder(self._contratto(ticker), self._ordine_stop(quantita, stop))
        self.ib.sleep(1)
        return str(trade.order.orderId)

    def cancella_stop(self, ticker: str):
        for t in list(self._ordini_stop_aperti(ticker)):
            self.ib.cancelOrder(t.order)
        self.ib.sleep(1)

    def chiudi_tutto(self, motivo: str) -> list[dict]:
        """Cancella TUTTI gli ordini aperti, poi vende (o ricompra, se allo scoperto) tutte le posizioni."""
        self.ib.reqGlobalCancel()
        self.ib.sleep(2)
        chiuse = []
        for ticker, p in self.posizioni().items():
            azione = "SELL" if p["quantita"] > 0 else "BUY"
            ordine = MarketOrder(azione, abs(p["quantita"]), tif="DAY", account=self.account, orderRef=ETICHETTA)
            trade = self.ib.placeOrder(self._contratto(ticker), ordine)
            chiuse.append({"titolo": ticker, "quantita": abs(p["quantita"]), "id": str(trade.order.orderId)})
        self.ib.sleep(2)
        log.warning("CHIUDI TUTTO (%s): %d ordini di chiusura inviati", motivo, len(chiuse))
        return chiuse

    def esecuzioni(self) -> list[dict]:
        risultato = []
        for f in self.ib.reqExecutions():
            e = f.execution
            risultato.append({
                "id": e.execId, "data": f.time.isoformat(timespec="seconds"), "titolo": f.contract.symbol,
                "operazione": "ACQUISTO" if e.side == "BOT" else "VENDITA", "quantita": int(e.shares),
                "prezzo": float(e.price), "commissione": float(f.commissionReport.commission or 0),
            })
        return risultato

    def disconnetti(self):
        if self.ib.isConnected():
            self.ib.disconnect()
