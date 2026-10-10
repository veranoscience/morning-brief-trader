"""Calcule les indicateurs de risque d'un trader et contrôle ses limites.

Les chiffres du brief viennent TOUJOURS de ce script, jamais d'un calcul fait
« de tête » par le modèle : c'est ce qui rend le brief fiable et auditable.

    python scripts/compute_risk.py --trader T01
    python scripts/compute_risk.py --trader all --date 2026-10-09

Sortie : JSON sur la sortie standard.
Variable d'environnement : DATABASE_URL (rôle en lecture seule suffit).
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date

import pandas as pd

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://brief_reader:lecture_seule@localhost:5432/trading")

SEUIL_ALERTE = 0.80      # au-delà de 80 % d'une limite : ALERTE
SEUIL_MOUVEMENT = 0.03   # variation journalière notable : |rendement| >= 3 %


def statut(utilisation: float) -> str:
    if utilisation > 1.0:
        return "DEPASSEMENT"
    if utilisation >= SEUIL_ALERTE:
        return "ALERTE"
    return "OK"


def evaluer(positions: pd.DataFrame, prix_jour: pd.Series, prix_veille: pd.Series,
            limites: pd.DataFrame) -> dict:
    """Calcul pur (sans base de données), testable unitairement.

    positions : colonnes ticker, quantite, prix_moyen, secteur
    prix_jour / prix_veille : Series indexées par ticker
    limites   : colonnes type_limite, perimetre, valeur_limite
    """
    pos = positions.copy()
    pos["cours"] = pos["ticker"].map(prix_jour).astype(float)
    pos["cours_veille"] = pos["ticker"].map(prix_veille).astype(float)
    pos["quantite"] = pos["quantite"].astype(float)
    pos["prix_moyen"] = pos["prix_moyen"].astype(float)
    pos["valeur_marche"] = pos["quantite"] * pos["cours"]
    pos["pnl_jour"] = pos["quantite"] * (pos["cours"] - pos["cours_veille"])
    pos["pnl_latent"] = pos["quantite"] * (pos["cours"] - pos["prix_moyen"])
    pos["variation_pct"] = pos["cours"] / pos["cours_veille"] - 1

    brute = float(pos["valeur_marche"].abs().sum())
    nette = float(pos["valeur_marche"].sum())
    pnl_jour = float(pos["pnl_jour"].sum())
    par_secteur = pos.groupby("secteur")["valeur_marche"].sum()
    pos["poids_pct"] = pos["valeur_marche"].abs() / brute * 100 if brute else 0.0

    controles = []
    for lim in limites.itertuples(index=False):
        valeur_limite = float(lim.valeur_limite)
        if lim.type_limite == "exposition_brute":
            mesure, libelle = brute, "Exposition brute"
        elif lim.type_limite == "exposition_secteur":
            mesure = abs(float(par_secteur.get(lim.perimetre, 0.0)))
            libelle = f"Exposition secteur {lim.perimetre}"
        elif lim.type_limite == "concentration":
            ligne = pos.loc[pos["poids_pct"].idxmax()]
            mesure, libelle = float(ligne["poids_pct"]), f"Concentration (max : {ligne['ticker']})"
        elif lim.type_limite == "perte_journaliere":
            mesure, libelle = max(0.0, -pnl_jour), "Perte du jour"
        else:
            continue
        utilisation = mesure / valeur_limite if valeur_limite else 0.0
        controles.append({
            "limite": libelle,
            "type": lim.type_limite,
            "mesure": round(mesure, 2),
            "valeur_limite": valeur_limite,
            "utilisation_pct": round(utilisation * 100, 1),
            "statut": statut(utilisation),
        })

    ordre = {"DEPASSEMENT": 0, "ALERTE": 1, "OK": 2}
    controles.sort(key=lambda c: (ordre[c["statut"]], -c["utilisation_pct"]))

    mouvements = pos[pos["variation_pct"].abs() >= SEUIL_MOUVEMENT] \
        .sort_values("variation_pct")[["ticker", "variation_pct", "pnl_jour"]]

    arrondi = lambda x: round(float(x), 2)  # noqa: E731
    return {
        "synthese": {
            "exposition_brute": arrondi(brute),
            "exposition_nette": arrondi(nette),
            "pnl_jour": arrondi(pnl_jour),
            "pnl_latent": arrondi(pos["pnl_latent"].sum()),
            "nb_depassements": sum(c["statut"] == "DEPASSEMENT" for c in controles),
            "nb_alertes": sum(c["statut"] == "ALERTE" for c in controles),
        },
        "controles_limites": controles,
        "mouvements_notables": [
            {"ticker": m.ticker, "variation_pct": round(m.variation_pct * 100, 2),
             "pnl_jour": arrondi(m.pnl_jour)} for m in mouvements.itertuples(index=False)],
        "positions": [
            {"ticker": r.ticker, "secteur": r.secteur, "quantite": r.quantite,
             "cours": r.cours, "valeur_marche": arrondi(r.valeur_marche),
             "poids_pct": round(float(r.poids_pct), 1), "pnl_jour": arrondi(r.pnl_jour),
             "pnl_latent": arrondi(r.pnl_latent)}
            for r in pos.sort_values("valeur_marche", key=abs, ascending=False).itertuples(index=False)],
        "exposition_par_secteur": {k: arrondi(v) for k, v in par_secteur.sort_values().items()},
    }


def charger_et_evaluer(trader_id: str, jour: date | None) -> dict:
    import psycopg

    with psycopg.connect(DB_URL) as conn:
        def lire(sql: str, params: tuple = ()) -> pd.DataFrame:
            cur = conn.execute(sql, params)
            return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])

        trader = lire("SELECT * FROM traders WHERE trader_id = %s", (trader_id,))
        if trader.empty:
            raise SystemExit(f"Trader inconnu : {trader_id}")
        dates = lire("SELECT DISTINCT date_cours FROM cours ORDER BY date_cours")["date_cours"].tolist()
        jour = jour or dates[-1]
        anterieures = [d for d in dates if d < jour]
        if jour not in dates or not anterieures:
            raise SystemExit(f"Pas de cours pour le {jour} ou la séance précédente")
        veille = anterieures[-1]
        cours = lire("SELECT ticker, date_cours, cloture, source FROM cours WHERE date_cours IN (%s, %s)",
                     (jour, veille))
        positions = lire("""SELECT p.ticker, p.quantite, p.prix_moyen, i.secteur
                            FROM positions p JOIN instruments i USING (ticker)
                            WHERE p.trader_id = %s""", (trader_id,))
        limites = lire("SELECT type_limite, perimetre, valeur_limite FROM limites WHERE trader_id = %s",
                       (trader_id,))

    prix = cours.pivot(index="ticker", columns="date_cours", values="cloture")
    resultat = evaluer(positions, prix[jour], prix[veille], limites)
    return {
        "trader": {"id": trader_id, "nom": trader.at[0, "nom"], "desk": trader.at[0, "desk"]},
        "date": str(jour),
        "seance_precedente": str(veille),
        "source_cours": sorted(cours["source"].unique().tolist()),
        **resultat,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--trader", required=True, help="identifiant (ex. T01) ou 'all'")
    p.add_argument("--date", type=date.fromisoformat, default=None, help="AAAA-MM-JJ (défaut : dernière séance)")
    args = p.parse_args()

    if args.trader == "all":
        import psycopg
        with psycopg.connect(DB_URL) as conn:
            ids = [r[0] for r in conn.execute("SELECT trader_id FROM traders ORDER BY trader_id")]
        sortie = [charger_et_evaluer(t, args.date) for t in ids]
    else:
        sortie = charger_et_evaluer(args.trader, args.date)
    print(json.dumps(sortie, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
