"""Contrôle de cohérence entre un brief rédigé et le calcul de référence.

Le modèle rédige, le code calcule… et le code relit : ce script relance
compute_risk.py pour la date et le trader du brief, puis vérifie que les
chiffres recopiés dans le Markdown sont bien ceux du calcul.

    python scripts/check_brief.py briefs/2026-10-09_T01.md
    python scripts/check_brief.py --all

Sortie : un tableau OK / ÉCART par élément. Code retour 1 s'il y a au moins un écart.
Variable d'environnement : DATABASE_URL (rôle en lecture seule suffit).
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

from compute_risk import charger_et_evaluer

DOSSIER_BRIEFS = Path(__file__).parents[1] / "briefs"
NOM_BRIEF = re.compile(r"(\d{4}-\d{2}-\d{2})_([A-Za-z0-9]+)\.md")

TOLERANCE = {"USD": 0.5, "%": 0.05}   # arrondi à l'unité (USD) et à 0,1 (%)
EPSILON = 1e-9

SYNTHESE = [("P&L du jour", "pnl_jour"), ("P&L latent", "pnl_latent"),
            ("Exposition brute", "exposition_brute"), ("Exposition nette", "exposition_nette")]

NOMBRE = re.compile(r"([+-]?)\s*(\d{1,3}(?: \d{3})+|\d+)(?:[.,](\d+))?\s*(USD|%)?")
STATUT = re.compile(r"\b(DEPASSEMENT|ALERTE|OK)\b")


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, sans emoji ni gras : pour comparer des libellés."""
    sans_accents = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    gardes = "".join(c if c.isalnum() or c in "&%:()" else " " for c in sans_accents)
    return " ".join(gardes.lower().split())


def lire_nombre(cellule: str) -> tuple[float, str | None] | None:
    """« **+25 463 USD** » -> (25463.0, "USD") ; « 96,9 % » -> (96.9, "%")."""
    propre = cellule.replace("*", "")
    for espace in (" ", " ", " "):
        propre = propre.replace(espace, " ")
    for moins in ("−", "–"):
        propre = propre.replace(moins, "-")
    m = NOMBRE.search(propre)
    if not m:
        return None
    signe, entier, decimales, unite = m.groups()
    valeur = float(entier.replace(" ", "") + "." + (decimales or "0"))
    return (-valeur if signe == "-" else valeur), unite


def lire_statut(cellule: str) -> str | None:
    m = STATUT.search(normaliser(cellule).upper())
    return m.group(1) if m else None


def sections(markdown: str) -> dict[str, str]:
    """Découpe le brief sur les titres « ## » : titre normalisé -> contenu."""
    resultat, titre, lignes = {}, None, []
    for ligne in markdown.splitlines():
        if ligne.startswith("## "):
            if titre is not None:
                resultat[titre] = "\n".join(lignes)
            titre, lignes = normaliser(ligne[3:]), []
        elif titre is not None:
            lignes.append(ligne)
    if titre is not None:
        resultat[titre] = "\n".join(lignes)
    return resultat


def lire_tableau(contenu: str) -> tuple[list[str], list[list[str]]]:
    """Premier tableau Markdown d'une section : (en-têtes normalisés, lignes de cellules)."""
    lignes = []
    for ligne in contenu.splitlines():
        ligne = ligne.strip()
        if not ligne.startswith("|"):
            if lignes:
                break
            continue
        cellules = [c.strip() for c in ligne.strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", c) for c in cellules):
            continue
        lignes.append(cellules)
    if not lignes:
        return [], []
    return [normaliser(c) for c in lignes[0]], lignes[1:]


def trouver_section(par_titre: dict[str, str], debut: str) -> str | None:
    return next((c for t, c in par_titre.items() if t.startswith(debut)), None)


def comparer(element: str, cellule: str | None, attendu: float, unite: str) -> dict:
    ligne = {"element": element, "brief": cellule or "absent",
             "reference": f"{attendu:.2f} {unite}", "ok": False}
    lu = lire_nombre(cellule) if cellule else None
    if lu is not None:
        valeur, unite_lue = lu
        ligne["ok"] = unite_lue == unite and abs(valeur - attendu) <= TOLERANCE[unite] + EPSILON
    return ligne


def controler(markdown: str, reference: dict) -> list[dict]:
    """Calcul pur (sans base de données), testable unitairement.

    reference : sortie de compute_risk.evaluer / charger_et_evaluer.
    Retourne une ligne par élément contrôlé : element, brief, reference, ok.
    """
    par_titre = sections(markdown)
    resultats = []

    entetes, lignes = lire_tableau(trouver_section(par_titre, "synthese") or "")
    valeurs = dict(zip(entetes, lignes[0])) if lignes else {}
    for libelle, cle in SYNTHESE:
        resultats.append(comparer(libelle, valeurs.get(normaliser(libelle)),
                                  reference["synthese"][cle], "USD"))

    entetes, lignes = lire_tableau(trouver_section(par_titre, "controle des limites") or "")
    par_limite = {normaliser(l[0]): dict(zip(entetes[1:], l[1:])) for l in lignes if l}
    priorite = normaliser(trouver_section(par_titre, "a traiter en priorite") or "")
    for c in reference["controles_limites"]:
        cellules = par_limite.get(normaliser(c["limite"]), {})
        unite = "%" if c["type"] == "concentration" else "USD"
        resultats.append(comparer(f"{c['limite']} — mesure", cellules.get("mesure"), c["mesure"], unite))
        resultats.append(comparer(f"{c['limite']} — utilisation", cellules.get("utilisation"),
                                  c["utilisation_pct"], "%"))
        statut_lu = cellules.get("statut")
        resultats.append({"element": f"{c['limite']} — statut", "brief": statut_lu or "absent",
                          "reference": c["statut"],
                          "ok": statut_lu is not None and lire_statut(statut_lu) == c["statut"]})
        if c["statut"] == "DEPASSEMENT":
            present = normaliser(c["limite"]) in priorite
            resultats.append({"element": f"{c['limite']} — à traiter en priorité",
                              "brief": "présent" if present else "absent",
                              "reference": "présent", "ok": present})
    return resultats


def controler_fichier(chemin: Path) -> list[dict]:
    m = NOM_BRIEF.fullmatch(chemin.name)
    if not m:
        raise SystemExit(f"Nom de brief inattendu (AAAA-MM-JJ_<ID>.md) : {chemin.name}")
    jour, trader = date.fromisoformat(m.group(1)), m.group(2)
    try:
        reference = charger_et_evaluer(trader, jour)
    except SystemExit as e:   # trader inconnu, pas de cours à cette date
        return [{"element": "Calcul de référence", "brief": chemin.name,
                 "reference": str(e), "ok": False}]
    return controler(chemin.read_text(encoding="utf-8"), reference)


def afficher(chemin: Path, resultats: list[dict]) -> None:
    colonnes = ["element", "brief", "reference"]
    titres = {"element": "Élément", "brief": "Brief", "reference": "Référence"}
    largeurs = {c: max(len(titres[c]), *(len(r[c]) for r in resultats)) for c in colonnes}
    print(f"\n{chemin}")
    print(" | ".join(titres[c].ljust(largeurs[c]) for c in colonnes) + " | Résultat")
    print("-|-".join("-" * largeurs[c] for c in colonnes) + "-|---------")
    for r in resultats:
        print(" | ".join(r[c].ljust(largeurs[c]) for c in colonnes)
              + " | " + ("OK" if r["ok"] else "ÉCART"))


def main() -> int:
    p = argparse.ArgumentParser(description="Contrôle de cohérence brief / calcul de référence")
    p.add_argument("briefs", nargs="*", type=Path, help="chemin(s) de brief (ex. briefs/2026-10-09_T01.md)")
    p.add_argument("--all", action="store_true", help="contrôler tous les briefs du dossier briefs/")
    args = p.parse_args()

    chemins = list(args.briefs)
    if args.all:
        chemins += sorted(c for c in DOSSIER_BRIEFS.glob("*.md") if NOM_BRIEF.fullmatch(c.name))
    if not chemins:
        p.error("indiquer un brief ou --all")

    nb_ecarts = 0
    for chemin in chemins:
        resultats = controler_fichier(chemin)
        afficher(chemin, resultats)
        nb_ecarts += sum(not r["ok"] for r in resultats)
    print(f"\n{len(chemins)} brief(s) contrôlé(s), {nb_ecarts} écart(s).")
    return 1 if nb_ecarts else 0


if __name__ == "__main__":
    sys.exit(main())
