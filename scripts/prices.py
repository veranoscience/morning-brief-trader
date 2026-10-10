"""Récupération des cours de clôture : yfinance (réel) ou simulation (hors ligne).

Utilisé par seed.py. Peut aussi être lancé seul pour tester :
    python scripts/prices.py --offline
"""
from __future__ import annotations

import argparse
from datetime import date

import numpy as np
import pandas as pd

# Prix de référence approximatifs, utilisés uniquement en mode simulation.
PRIX_REFERENCE = {
    "AAPL": 230.0, "MSFT": 440.0, "NVDA": 130.0, "AMZN": 190.0, "SPY": 570.0,
    "JPM": 220.0, "GS": 520.0, "XOM": 115.0, "CVX": 155.0, "JNJ": 160.0,
}

# Volatilité journalière approximative par ticker (simulation).
VOL_JOUR = {
    "AAPL": 0.015, "MSFT": 0.014, "NVDA": 0.030, "AMZN": 0.018, "SPY": 0.009,
    "JPM": 0.013, "GS": 0.016, "XOM": 0.014, "CVX": 0.014, "JNJ": 0.010,
}


def simuler_cours(tickers: list[str], nb_jours: int = 30, fin: date | None = None,
                  graine: int = 42) -> pd.DataFrame:
    """Marche aléatoire log-normale sur des jours ouvrés. Reproductible (graine fixe)."""
    rng = np.random.default_rng(graine)
    fin = pd.Timestamp(fin or date.today())
    if fin.weekday() >= 5:                       # samedi/dimanche -> vendredi
        fin -= pd.tseries.offsets.BDay(1)
    dates = pd.bdate_range(end=fin, periods=nb_jours)
    lignes = []
    for t in tickers:
        rendements = rng.normal(0.0003, VOL_JOUR.get(t, 0.015), nb_jours)
        rendements[0] = 0.0
        serie = PRIX_REFERENCE.get(t, 100.0) * np.exp(np.cumsum(rendements))
        for d, p in zip(dates, serie):
            lignes.append({"ticker": t, "date_cours": d.date(),
                           "cloture": round(float(p), 2), "source": "simulation"})
    return pd.DataFrame(lignes)


def telecharger_cours(tickers: list[str], periode: str = "3mo") -> pd.DataFrame:
    """Cours réels via yfinance. Lève une exception si rien n'est récupéré."""
    import yfinance as yf

    brut = yf.download(tickers, period=periode, interval="1d",
                       auto_adjust=True, progress=False, group_by="column")
    if brut is None or brut.empty:
        raise RuntimeError("yfinance n'a renvoyé aucune donnée")
    clotures = brut["Close"].dropna(how="all")
    lignes = []
    for t in tickers:
        if t not in clotures:
            continue
        for d, p in clotures[t].dropna().items():
            lignes.append({"ticker": t, "date_cours": d.date(),
                           "cloture": round(float(p), 2), "source": "yfinance"})
    if not lignes:
        raise RuntimeError("aucun cours exploitable")
    return pd.DataFrame(lignes)


def obtenir_cours(tickers: list[str], hors_ligne: bool = False) -> pd.DataFrame:
    """Essaie yfinance, bascule sur la simulation en cas d'échec."""
    if not hors_ligne:
        try:
            return telecharger_cours(tickers)
        except Exception as e:  # réseau coupé, ticker inconnu, quota...
            print(f"[prix] yfinance indisponible ({e}) -> simulation")
    return simuler_cours(tickers)


def appliquer_choc(cours: pd.DataFrame, chocs: dict[str, float]) -> pd.DataFrame:
    """Applique un choc (en %) sur la DERNIÈRE clôture des tickers indiqués."""
    cours = cours.copy()
    derniere = cours["date_cours"].max()
    for t, pct in chocs.items():
        masque = (cours["ticker"] == t) & (cours["date_cours"] == derniere)
        veille = cours[(cours["ticker"] == t) & (cours["date_cours"] < derniere)] \
            .sort_values("date_cours")["cloture"].iloc[-1]
        cours.loc[masque, "cloture"] = round(float(veille) * (1 + pct / 100), 2)
        cours.loc[masque, "source"] = cours.loc[masque, "source"] + "+choc"
    return cours


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Tester la récupération des cours")
    p.add_argument("--offline", action="store_true", help="forcer la simulation")
    args = p.parse_args()
    df = obtenir_cours(list(PRIX_REFERENCE), hors_ligne=args.offline)
    print(df.sort_values(["ticker", "date_cours"]).groupby("ticker").tail(2).to_string(index=False))
