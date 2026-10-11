"""Tests unitaires du contrôle de cohérence des briefs (sans base de données).

    pytest -q
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from check_brief import NOM_BRIEF, controler, lire_nombre  # noqa: E402
from compute_risk import evaluer  # noqa: E402

PICTOS = {"DEPASSEMENT": "🔴 DÉPASSEMENT", "ALERTE": "🟠 ALERTE", "OK": "🟢 OK"}


def usd(x: float, signe: bool = False) -> str:
    texte = f"{abs(round(x)):,}".replace(",", " ") + " USD"
    return ("−" if x < 0 else "+" if signe else "") + texte


def pct(x: float) -> str:
    return f"{x:.1f}".replace(".", ",") + " %"


def rediger(r: dict) -> str:
    """Brief conforme au modèle de la skill risk-brief, à partir du calcul."""
    s = r["synthese"]
    mesure = lambda c: pct(c["mesure"]) if c["type"] == "concentration" else usd(c["mesure"])  # noqa: E731
    priorite = [f"- 🔴 **{c['limite']}** : {mesure(c)} — **{pct(c['utilisation_pct'])} d'utilisation**."
                for c in r["controles_limites"] if c["statut"] == "DEPASSEMENT"]
    limites = [f"| {c['limite']} | {mesure(c)} | {c['valeur_limite']:g} | {pct(c['utilisation_pct'])} "
               f"| {PICTOS[c['statut']]} |" for c in r["controles_limites"]]
    return "\n".join([
        "# Morning Brief — Test (Desk)",
        "",
        "## 🚨 À traiter en priorité",
        *(priorite or ["Aucun dépassement de limite."]),
        "",
        "## Synthèse",
        "| P&L du jour | P&L latent | Exposition brute | Exposition nette |",
        "|---|---|---|---|",
        f"| **{usd(s['pnl_jour'], True)}** | {usd(s['pnl_latent'], True)} "
        f"| {usd(s['exposition_brute'])} | {usd(s['exposition_nette'])} |",
        "",
        "## Contrôle des limites",
        "| Limite | Mesure | Limite | Utilisation | Statut |",
        "|---|---|---|---|---|",
        *limites,
        "",
        "## Points d'attention",
        "- Le portefeuille pèse 204 800 USD brut.",
    ])


@pytest.fixture
def reference():
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
    return evaluer(positions, jour, veille, limites)


def ecarts(markdown: str, reference: dict) -> list[str]:
    return [r["element"] for r in controler(markdown, reference) if not r["ok"]]


def test_brief_correct_passe(reference):
    resultats = controler(rediger(reference), reference)
    # 4 éléments de synthèse + 3 par limite + 1 par dépassement (perte du jour, secteur)
    assert len(resultats) == 4 + 3 * 4 + 2
    assert all(r["ok"] for r in resultats)


def test_chiffre_modifie_echoue(reference):
    brief = rediger(reference)
    assert "**−4 800 USD**" in brief
    assert ecarts(brief.replace("**−4 800 USD**", "**−4 300 USD**"), reference) == ["P&L du jour"]


def test_tolerance_d_arrondi(reference):
    brief = rediger(reference)
    # 195 000 USD de mesure : 195 000,4 passe (arrondi à l'unité), 195 001 échoue
    ligne = "| Exposition secteur Technologie | 195 000 USD"
    assert ligne in brief
    assert ecarts(brief.replace(ligne, ligne.replace("195 000", "195 000,4")), reference) == []
    assert ecarts(brief.replace(ligne, ligne.replace("195 000", "195 001")), reference) == [
        "Exposition secteur Technologie — mesure"]


def test_statut_modifie_echoue(reference):
    lignes = [l.replace("🟠 ALERTE", "🟢 OK") if l.startswith("| Exposition brute |") else l
              for l in rediger(reference).splitlines()]
    assert ecarts("\n".join(lignes), reference) == ["Exposition brute — statut"]


def test_depassement_absent_de_la_section_prioritaire(reference):
    lignes = [l for l in rediger(reference).splitlines()
              if not l.startswith("- 🔴 **Perte du jour**")]
    assert ecarts("\n".join(lignes), reference) == ["Perte du jour — à traiter en priorité"]


def test_section_manquante_echoue(reference):
    brief = rediger(reference).replace("## Synthèse", "## Résumé")
    assert ecarts(brief, reference) == ["P&L du jour", "P&L latent", "Exposition brute", "Exposition nette"]


@pytest.mark.parametrize("cellule,attendu", [
    ("**+25 463 USD**", (25463.0, "USD")),
    ("−213 866 USD", (-213866.0, "USD")),
    ("96,9 %", (96.9, "%")),
    ("0 USD", (0.0, "USD")),
    ("🟢 OK", None),
])
def test_lire_nombre(cellule, attendu):
    assert lire_nombre(cellule) == attendu


@pytest.mark.parametrize("nom,reconnu", [
    ("2026-10-09_T01.md", True),
    ("2026-10-09_synthese-desk.md", False),
    ("exemple_2026-10-09_T01.md", False),
])
def test_nom_de_brief(nom, reconnu):
    assert bool(NOM_BRIEF.fullmatch(nom)) is reconnu
