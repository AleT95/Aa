"""
La strategia "termometro ETF".

Idea in parole semplici:
  1. Guardo l'ETF di ogni settore/area (il "termometro").
  2. Se il termometro dice "caldo" (trend positivo), compro le azioni più forti
     di quel settore, cioè quelle con il momentum più alto.
  3. Se il termometro diventa "freddo", vendo le azioni di quel settore.
  4. Filtro globale (opzionale): se anche l'ETF del mondo è "freddo", vendo tutto.

Questa classe NON compra e non vende: si limita a DIRE cosa fare in un certo giorno.
Il backtest (e più avanti il broker) eseguirà le sue indicazioni. Separare le due
cose ci permette di usare la stessa strategia sia nel backtest sia dal vivo.
"""

import pandas as pd

from ..config import etf_del_gruppo
from .indicatori import media_mobile, momentum, trend_positivo


class StrategiaTermometro:

    def __init__(self, config: dict, prezzi: pd.DataFrame):
        s = config["strategia"]
        self.azioni_per_gruppo = s["azioni_per_settore"]
        self.gruppi = config["azioni"]                       # {gruppo: [azioni]}
        self.etf_gruppo = {g: etf_del_gruppo(config, g) for g in self.gruppi}

        filtro = s.get("filtro_globale") or "nessuno"
        self.etf_globale = None if filtro == "nessuno" else config["etf_aree"][filtro]

        # Calcoliamo tutti gli indicatori UNA volta sola, per tutti i giorni
        self.trend = trend_positivo(prezzi, s["media_mobile_breve"], s["media_mobile_lunga"], s["momentum_mesi"])
        self.momentum = momentum(prezzi, s["momentum_mesi"])
        self.sopra_mm_lunga = prezzi > media_mobile(prezzi, s["media_mobile_lunga"])

        # Primo giorno in cui tutti gli indicatori sono "pronti" (servono 200 giorni + 6 mesi di storia)
        giorni_minimi = max(s["media_mobile_lunga"], max(s["momentum_mesi"]) * 21)
        self.primo_giorno_utile = prezzi.index[min(giorni_minimi, len(prezzi) - 1)]

    # ------------------------------------------------------------------
    def mercato_ok(self, giorno) -> bool:
        """Il filtro globale: True se il mondo è in trend positivo (o se il filtro è spento)."""
        if self.etf_globale is None:
            return True
        return bool(self.trend.at[giorno, self.etf_globale])

    def gruppo_positivo(self, gruppo: str, giorno) -> bool:
        """True se il termometro del gruppo segna "caldo" E il mercato globale è ok."""
        return self.mercato_ok(giorno) and bool(self.trend.at[giorno, self.etf_gruppo[gruppo]])

    def migliori_azioni(self, gruppo: str, giorno) -> list[str]:
        """
        Le azioni più forti del gruppo in quel giorno.
        Per essere scelta, un'azione deve avere essa stessa momentum positivo e
        prezzo sopra la media mobile lunga (non compriamo un titolo in caduta
        solo perché il suo settore va bene).
        """
        candidati = {}
        for azione in self.gruppi[gruppo]:
            if azione not in self.momentum.columns:
                continue                                      # nessun dato per questo titolo
            mom = self.momentum.at[giorno, azione]
            if pd.notna(mom) and mom > 0 and self.sopra_mm_lunga.at[giorno, azione]:
                candidati[azione] = mom
        classifica = sorted(candidati, key=candidati.get, reverse=True)
        return classifica[: self.azioni_per_gruppo]

    def portafoglio_obiettivo(self, giorno) -> dict[str, tuple[str, str]]:
        """
        Cosa vorremmo avere in portafoglio in quel giorno.
        Restituisce {azione: (gruppo, motivo)}.
        """
        obiettivo = {}
        for gruppo in self.gruppi:
            if not self.gruppo_positivo(gruppo, giorno):
                continue
            etf = self.etf_gruppo[gruppo]
            for pos, azione in enumerate(self.migliori_azioni(gruppo, giorno), start=1):
                mom = self.momentum.at[giorno, azione]
                obiettivo[azione] = (gruppo, f"{etf} in trend positivo; {azione} n.{pos} per momentum ({mom:+.0%})")
        return obiettivo
