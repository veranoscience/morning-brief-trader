"""Remplit la base "trading" : traders, instruments, limites, cours, positions.

Remet tout à zéro à chaque lancement (sauf le schéma). Données fictives et reproductibles.

    python scripts/seed.py                       # cours réels si possible, sinon simulation
    python scripts/seed.py --offline             # simulation uniquement
    python scripts/seed.py --scenario krach_tech # choc sur la tech la dernière séance

Variable d'environnement : ADMIN_DATABASE_URL (rôle avec droits d'écriture).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import psycopg

sys.path.insert(0, str(Path(__file__).parent))
from prices import appliquer_choc, obtenir_cours  # noqa: E402

ADMIN_URL = os.environ.get(
    "ADMIN_DATABASE_URL", "postgresql://trader_admin:admin@localhost:5432/trading")

TRADERS = [
    ("T01", "Léa Martin", "Actions US — Tech"),
    ("T02", "Marc Dubois", "Actions US — Financières & Énergie"),
]

INSTRUMENTS = [
    ("AAPL", "Apple", "Action", "Technologie"),
    ("MSFT", "Microsoft", "Action", "Technologie"),
    ("NVDA", "NVIDIA", "Action", "Technologie"),
    ("AMZN", "Amazon", "Action", "Consommation discrétionnaire"),
    ("SPY", "SPDR S&P 500 ETF", "ETF", "Indice"),
    ("JPM", "JPMorgan Chase", "Action", "Financières"),
    ("GS", "Goldman Sachs", "Action", "Financières"),
    ("XOM", "Exxon Mobil", "Action", "Énergie"),
    ("CVX", "Chevron", "Action", "Énergie"),
    ("JNJ", "Johnson & Johnson", "Action", "Santé"),
]

# Montant cible de chaque position en USD (négatif = vente à découvert / couverture)
NOTIONNELS = {
    "T01": {"AAPL": 1_200_000, "MSFT": 1_000_000, "NVDA": 1_500_000,
            "AMZN": 800_000, "SPY": -600_000},
    "T02": {"JPM": 1_000_000, "GS": 900_000, "XOM": 1_100_000,
            "CVX": 700_000, "JNJ": 500_000},
}

LIMITES = [
    # trader, type, périmètre, valeur
    ("T01", "exposition_brute", None, 6_000_000),
    ("T01", "exposition_secteur", "Technologie", 4_500_000),
    ("T01", "concentration", None, 30),          # %
    ("T01", "perte_journaliere", None, 120_000),
    ("T02", "exposition_brute", None, 5_000_000),
    ("T02", "exposition_secteur", "Énergie", 1_600_000),
    ("T02", "concentration", None, 30),
    ("T02", "perte_journaliere", None, 100_000),
]

SCENARIOS = {
    "normal": {},
    # Séance de forte baisse sur la tech (en %)
    "krach_tech": {"NVDA": -9.0, "AAPL": -6.5, "MSFT": -6.0, "AMZN": -5.0, "SPY": -3.0},
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", choices=SCENARIOS, default="normal")
    p.add_argument("--offline", action="store_true", help="forcer les cours simulés")
    args = p.parse_args()

    tickers = [i[0] for i in INSTRUMENTS]
    cours = obtenir_cours(tickers, hors_ligne=args.offline)
    cours = appliquer_choc(cours, SCENARIOS[args.scenario])

    dates = sorted(cours["date_cours"].unique())
    veille, entree = dates[-2], dates[max(0, len(dates) - 21)]
    prix = cours.set_index(["ticker", "date_cours"])["cloture"]
    rng = np.random.default_rng(7)

    with psycopg.connect(ADMIN_URL) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE positions, limites, cours, instruments, traders RESTART IDENTITY CASCADE")
        cur.executemany("INSERT INTO traders VALUES (%s, %s, %s)", TRADERS)
        cur.executemany(
            "INSERT INTO instruments (ticker, nom, classe_actif, secteur) VALUES (%s, %s, %s, %s)",
            INSTRUMENTS)
        cur.executemany(
            "INSERT INTO cours VALUES (%s, %s, %s, %s)",
            cours[["ticker", "date_cours", "cloture", "source"]].itertuples(index=False, name=None))
        cur.executemany(
            "INSERT INTO limites (trader_id, type_limite, perimetre, valeur_limite) VALUES (%s, %s, %s, %s)",
            LIMITES)
        for trader, lignes in NOTIONNELS.items():
            for ticker, notionnel in lignes.items():
                quantite = round(notionnel / float(prix[(ticker, veille)]))
                prix_moyen = round(float(prix[(ticker, entree)]) * (1 + rng.uniform(-0.02, 0.02)), 2)
                cur.execute(
                    "INSERT INTO positions (trader_id, ticker, quantite, prix_moyen, ouverte_le) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (trader, ticker, quantite, prix_moyen, entree))

    sources = ", ".join(sorted(cours["source"].unique()))
    print(f"Base remplie — scénario '{args.scenario}', {len(dates)} séances "
          f"jusqu'au {dates[-1]}, source des cours : {sources}")


if __name__ == "__main__":
    main()
