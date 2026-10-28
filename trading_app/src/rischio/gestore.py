"""
Il gestore del rischio: l'"ufficiale di sicurezza" dell'app.

Non decide COSA comprare (quello lo fa la strategia), ma QUANTO e QUANDO fermarsi:
  1. Limite per titolo: mai più del 5% del capitale su una singola azione.
  2. Stop loss: se un titolo scende troppo, si vende (fisso o "trailing").
  3. Attesa dopo uno stop: il titolo appena venduto in perdita non si ricompra subito.
  4. Limiti di perdita giornaliera e mensile: se superati, l'app si blocca.

Le stesse regole valgono nel backtest e (dalla Fase 4) nel trading sul conto demo.
"""

from .stato import GIORNALIERO, MENSILE


class GestoreRischio:

    def __init__(self, config: dict, attivo: bool = True):
        r = config["rischio"]
        self.attivo = attivo                 # False = solo limite per titolo (utile per confronti)
        self.peso_max = r["max_per_azione_pct"] / 100
        self.stop_pct = r["stop_loss_pct"] / 100
        self.trailing = r["stop_loss_tipo"] == "trailing"
        self.giorni_attesa = r["giorni_attesa_dopo_stop"]
        self.lim_giorno = r["perdita_max_giornaliera_pct"] / 100
        self.lim_mese = r["perdita_max_mensile_pct"] / 100
        self.chiudi_al_blocco = r["chiudi_posizioni_al_blocco"]
        if r["stop_loss_tipo"] not in ("fisso", "trailing"):
            raise ValueError("stop_loss_tipo deve essere 'fisso' o 'trailing'")

        self._stop_recenti: dict[str, int] = {}   # titolo -> n. del giorno in cui è scattato lo stop
        self._valore_ieri: float | None = None
        self._valore_inizio_mese: float | None = None
        self._mese: tuple | None = None

    # ------------------------------------------------------------------
    #  1. Quanto investire in un titolo
    # ------------------------------------------------------------------
    def importo_massimo(self, valore_portafoglio: float) -> float:
        return valore_portafoglio * self.peso_max

    # ------------------------------------------------------------------
    #  2. Stop loss
    # ------------------------------------------------------------------
    def livello_stop(self, prezzo_carico: float, prezzo_massimo: float) -> float:
        """
        Il prezzo sotto il quale si vende.
        - fisso:    8% sotto il prezzo pagato (es. pagato 100 -> stop a 92, per sempre)
        - trailing: 8% sotto il prezzo più alto raggiunto (es. sale a 150 -> lo stop sale a 138).
                    Lo stop "insegue" il prezzo verso l'alto e protegge i guadagni.
        """
        base = max(prezzo_carico, prezzo_massimo) if self.trailing else prezzo_carico
        return base * (1 - self.stop_pct)

    def stop_scattato(self, prezzo: float, prezzo_carico: float, prezzo_massimo: float) -> bool:
        return self.attivo and prezzo <= self.livello_stop(prezzo_carico, prezzo_massimo)

    # ------------------------------------------------------------------
    #  3. Attesa dopo uno stop
    # ------------------------------------------------------------------
    def registra_stop(self, ticker: str, n_giorno: int):
        self._stop_recenti[ticker] = n_giorno

    def in_attesa(self, ticker: str, n_giorno: int) -> bool:
        """True se il titolo è stato fermato da uno stop da meno di N giorni."""
        ultimo = self._stop_recenti.get(ticker)
        return self.attivo and ultimo is not None and n_giorno - ultimo < self.giorni_attesa

    # ------------------------------------------------------------------
    #  4. Limiti di perdita
    # ------------------------------------------------------------------
    def controlla_limiti(self, giorno, valore: float) -> tuple[str, str] | None:
        """
        Da chiamare ogni sera con il valore del portafoglio.
        Restituisce (tipo_blocco, motivo) se un limite è stato superato, altrimenti None.
        """
        if self._valore_ieri is None:                       # primo giorno: solo memorizzo
            self._valore_ieri = self._valore_inizio_mese = valore
            self._mese = (giorno.year, giorno.month)
            return None

        if (giorno.year, giorno.month) != self._mese:       # nuovo mese: nuovo punto di partenza
            self._mese = (giorno.year, giorno.month)
            self._valore_inizio_mese = self._valore_ieri

        var_giorno = valore / self._valore_ieri - 1
        var_mese = valore / self._valore_inizio_mese - 1
        self._valore_ieri = valore

        if not self.attivo:
            return None
        if var_mese <= -self.lim_mese:
            return MENSILE, f"perdita dall'inizio del mese {var_mese:.1%} (limite -{self.lim_mese:.0%})"
        if var_giorno <= -self.lim_giorno:
            return GIORNALIERO, f"perdita giornaliera {var_giorno:.1%} (limite -{self.lim_giorno:.0%})"
        return None
