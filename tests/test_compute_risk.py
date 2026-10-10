"""Tests unitaires du calcul de risque (sans base de données).

    pytest -q
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from compute_risk import evaluer, statut  # noqa: E402


@pytest.fixture
def portefeuille():
    positions = pd.DataFrame({
        "ticker": ["AAA", "BBB", "HEDGE"],
        "quantite": [1000, 500, -200],
        "prix_moyen": [100.0, 200.0, 50.0],
        "secteur": ["Technologie", "Technologie", "Indice"],
    })
    veille = pd.Series({"AAA": 100.0, "BBB": 200.0, "HEDGE": 50.0})
    jour = pd.Series({"AAA": 90.0, "BBB": 210.0, "HEDGE": 49.0})
    limites = pd.DataFrame({
        "type_limite": ["exposition_brute", "exposition_secteur", "concentration", "perte_journaliere"],
        "perimetre": [None, "Technologie", None, None],
        "valeur_limite": [250_000, 150_000, 60, 4_000],
    })
    return positions, jour, veille, limites


def test_pnl_et_expositions(portefeuille):
    r = evaluer(*portefeuille)
    s = r["synthese"]
    # AAA : 1000 x -10 = -10 000 ; BBB : 500 x +10 = +5 000 ; HEDGE short : -200 x -1 = +200
    assert s["pnl_jour"] == pytest.approx(-4_800)
    # Brute = 90 000 + 105 000 + 9 800
    assert s["exposition_brute"] == pytest.approx(204_800)
    assert s["exposition_nette"] == pytest.approx(185_200)


def test_controles_limites(portefeuille):
    r = evaluer(*portefeuille)
    par_type = {c["type"]: c for c in r["controles_limites"]}
    assert par_type["perte_journaliere"]["statut"] == "DEPASSEMENT"   # 4 800 > 4 000
    assert par_type["exposition_secteur"]["statut"] == "DEPASSEMENT"  # 195 000 > 150 000
    assert par_type["exposition_brute"]["statut"] == "ALERTE"         # 81,9 %
    assert par_type["concentration"]["statut"] == "ALERTE"            # BBB = 51,3 % de 60 %
    # dépassements listés en premier
    assert r["controles_limites"][0]["statut"] == "DEPASSEMENT"


def test_mouvements_notables(portefeuille):
    r = evaluer(*portefeuille)
    tickers = [m["ticker"] for m in r["mouvements_notables"]]
    assert tickers == ["AAA", "BBB"]   # -10 % et +5 % ; HEDGE (-2 %) sous le seuil de 3 %


@pytest.mark.parametrize("u,attendu", [(0.5, "OK"), (0.8, "ALERTE"), (1.0, "ALERTE"), (1.01, "DEPASSEMENT")])
def test_statut(u, attendu):
    assert statut(u) == attendu
