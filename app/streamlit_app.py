"""Morning Brief Trader — application web pour les traders et le risk manager.

    streamlit run app/streamlit_app.py

- Les chiffres viennent de scripts/compute_risk.py (rôle PostgreSQL en lecture seule).
- Le brief IA est rédigé par Claude via l'API, à partir de ces chiffres uniquement :
  Claude ne reçoit ni accès à la base, ni outil, ni droit d'écriture.
- Variables d'environnement : DATABASE_URL, ANTHROPIC_API_KEY (optionnelle), CLAUDE_MODEL (optionnelle).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import psycopg
import streamlit as st

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))
from compute_risk import DB_URL, SEUIL_ALERTE, charger_et_evaluer  # noqa: E402

DOSSIER_BRIEFS = RACINE / "briefs"
SKILL = RACINE / ".claude" / "skills" / "risk-brief" / "SKILL.md"
MODELE_CLAUDE = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

# Couleurs de statut (toujours accompagnées d'une icône et d'un libellé)
STATUTS = {
    "DEPASSEMENT": {"libelle": "Dépassement", "icone": "🔴", "couleur": "#d03b3b"},
    "ALERTE": {"libelle": "Alerte", "icone": "🟠", "couleur": "#fab219"},
    "OK": {"libelle": "OK", "icone": "🟢", "couleur": "#0ca30c"},
}
COULEUR_SERIE = "#2a78d6"
ENCRE_SECONDAIRE = "#52514e"

st.set_page_config(page_title="Morning Brief Trader", page_icon="📈", layout="wide")


# ---------------------------------------------------------------- données
@st.cache_data(ttl=300)
def lister_seances_et_traders() -> tuple[list[date], pd.DataFrame]:
    with psycopg.connect(DB_URL) as conn:
        dates = [r[0] for r in conn.execute("SELECT DISTINCT date_cours FROM cours ORDER BY date_cours DESC")]
        cur = conn.execute("SELECT trader_id, nom, desk FROM traders ORDER BY trader_id")
        traders = pd.DataFrame(cur.fetchall(), columns=["trader_id", "nom", "desk"])
    return dates, traders


@st.cache_data(ttl=300)
def risque(trader_id: str, jour: date) -> dict:
    return charger_et_evaluer(trader_id, jour)


def usd(x: float, signe: bool = False) -> str:
    texte = f"{abs(x):,.0f}".replace(",", " ") + " USD"
    if signe:
        return ("+" if x >= 0 else "−") + texte
    return ("−" if x < 0 else "") + texte


def pct(x: float) -> str:
    return f"{x:.1f} %".replace(".", ",")


def valeur_limite(c: dict, cle: str) -> str:
    return pct(c[cle]) if c["type"] == "concentration" else usd(c[cle])


def badge(statut: str) -> str:
    s = STATUTS[statut]
    return f"{s['icone']} {s['libelle']}"


# ---------------------------------------------------------------- graphiques
def graphique_limites(controles: list[dict]) -> alt.LayerChart:
    df = pd.DataFrame(controles)
    df["Statut"] = df["statut"].map(lambda s: STATUTS[s]["libelle"])
    df["Utilisation"] = df["utilisation_pct"]
    df["Étiquette"] = df["utilisation_pct"].map(pct)
    ordre = df["limite"].tolist()
    domaine = [STATUTS[k]["libelle"] for k in STATUTS]
    couleurs = [STATUTS[k]["couleur"] for k in STATUTS]

    barres = alt.Chart(df).mark_bar(cornerRadiusEnd=4, height=18).encode(
        x=alt.X("Utilisation:Q", title="Utilisation de la limite (%)",
                scale=alt.Scale(domain=[0, max(120, df["Utilisation"].max() + 15)])),
        y=alt.Y("limite:N", sort=ordre, title=None, axis=alt.Axis(labelLimit=260)),
        color=alt.Color("Statut:N", scale=alt.Scale(domain=domaine, range=couleurs),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("limite:N", title="Limite"), alt.Tooltip("Statut:N"),
                 alt.Tooltip("Étiquette:N", title="Utilisation"),
                 alt.Tooltip("mesure:Q", title="Mesure", format=",.0f"),
                 alt.Tooltip("valeur_limite:Q", title="Limite", format=",.0f")],
    )
    etiquettes = alt.Chart(df).mark_text(align="left", dx=6, color=ENCRE_SECONDAIRE).encode(
        x="Utilisation:Q", y=alt.Y("limite:N", sort=ordre), text="Étiquette:N")
    seuils = pd.DataFrame({"x": [SEUIL_ALERTE * 100, 100], "texte": ["80 %", "100 %"]})
    regles = alt.Chart(seuils).mark_rule(strokeDash=[4, 4], color=ENCRE_SECONDAIRE).encode(x="x:Q")
    textes_regles = alt.Chart(seuils).mark_text(
        align="center", dy=-4, baseline="bottom", color=ENCRE_SECONDAIRE, fontSize=11
    ).encode(x="x:Q", y=alt.value(0), text="texte:N")
    return (barres + etiquettes + regles + textes_regles).properties(height=44 * len(df) + 30)


def graphique_secteurs(expo: dict) -> alt.Chart:
    df = pd.DataFrame({"Secteur": list(expo), "Exposition": [v / 1e6 for v in expo.values()]})
    df["Étiquette"] = [usd(v) for v in expo.values()]
    return alt.Chart(df).mark_bar(cornerRadiusEnd=4, height=18, color=COULEUR_SERIE).encode(
        x=alt.X("Exposition:Q", title="Exposition nette (millions USD)", axis=alt.Axis(format=".1f")),
        y=alt.Y("Secteur:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
        tooltip=[alt.Tooltip("Secteur:N"), alt.Tooltip("Étiquette:N", title="Exposition nette")],
    ).properties(height=40 * len(df) + 20)


# ---------------------------------------------------------------- brief IA
def chemin_brief(trader_id: str, jour: date) -> Path:
    return DOSSIER_BRIEFS / f"{jour}_{trader_id}.md"


def generer_brief(donnees: dict) -> str:
    import anthropic

    consignes = SKILL.read_text(encoding="utf-8")
    systeme = (
        "Tu rédiges un brief de risque en appliquant la skill ci-dessous. "
        "Les chiffres sont DÉJÀ calculés et fournis en JSON : n'en calcule aucun autre, "
        "ne lance aucun script, n'invente aucune donnée. Réponds uniquement par le brief en Markdown.\n\n"
        + consignes
    )
    client = anthropic.Anthropic()
    reponse = client.messages.create(
        model=MODELE_CLAUDE,
        max_tokens=2000,
        system=systeme,
        messages=[{"role": "user", "content": "Chiffres calculés par compute_risk.py :\n```json\n"
                   + json.dumps(donnees, ensure_ascii=False, default=str) + "\n```"}],
    )
    return "".join(b.text for b in reponse.content if b.type == "text")


# ---------------------------------------------------------------- interface
try:
    seances, traders = lister_seances_et_traders()
except psycopg.OperationalError as e:
    st.error(f"Base de données injoignable. Vérifiez que PostgreSQL tourne et que DATABASE_URL est correcte.\n\n{e}")
    st.stop()

with st.sidebar:
    st.title("📈 Morning Brief Trader")
    jour = st.selectbox("Séance", seances, format_func=lambda d: d.strftime("%d/%m/%Y"))
    st.caption("Comparée à la séance précédente.")
    st.divider()
    st.markdown(
        "**Gouvernance**\n\n"
        "- Base de données en lecture seule\n"
        "- Chiffres calculés par du code testé\n"
        "- Claude rédige à partir de ces chiffres, sans accès à la base\n"
        "- Aucun ordre ne peut être passé"
    )

resultats = {t: risque(t, jour) for t in traders["trader_id"]}
source = sorted({s for r in resultats.values() for s in r["source_cours"]})
if any("simulation" in s for s in source):
    st.warning("Cours simulés — démonstration.", icon="⚠️")

onglet_desk, onglet_trader, onglet_brief = st.tabs(["Vue desk", "Détail trader", "Brief IA"])

# --- Vue desk
with onglet_desk:
    st.subheader(f"Desk Actions US — séance du {jour:%d/%m/%Y}")
    depassements = [(r["trader"]["nom"], c) for r in resultats.values()
                    for c in r["controles_limites"] if c["statut"] == "DEPASSEMENT"]
    if depassements:
        for nom, c in sorted(depassements, key=lambda x: -x[1]["utilisation_pct"]):
            st.error(f"**{nom}** — {c['limite']} : {valeur_limite(c, 'mesure')} pour une limite de "
                     f"{valeur_limite(c, 'valeur_limite')} ({pct(c['utilisation_pct'])})", icon="🚨")
    else:
        st.success("Aucun dépassement de limite.", icon="✅")

    synthese = pd.DataFrame([{
        "Trader": r["trader"]["nom"],
        "Desk": r["trader"]["desk"],
        "P&L du jour": usd(r["synthese"]["pnl_jour"], signe=True),
        "P&L latent": usd(r["synthese"]["pnl_latent"], signe=True),
        "Exposition brute": usd(r["synthese"]["exposition_brute"]),
        "Dépassements": r["synthese"]["nb_depassements"],
        "Alertes": r["synthese"]["nb_alertes"],
    } for r in resultats.values()])
    st.dataframe(synthese, hide_index=True, use_container_width=True)

# --- Détail trader
with onglet_trader:
    choix = st.selectbox("Trader", traders["trader_id"],
                         format_func=lambda t: f"{t} — {traders.set_index('trader_id').at[t, 'nom']}")
    r = resultats[choix]
    s = r["synthese"]
    st.subheader(f"{r['trader']['nom']} · {r['trader']['desk']}")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("P&L du jour", usd(s["pnl_jour"], signe=True))
    k2.metric("P&L latent", usd(s["pnl_latent"], signe=True))
    k3.metric("Exposition brute", usd(s["exposition_brute"]))
    k4.metric("Exposition nette", usd(s["exposition_nette"]))

    gauche, droite = st.columns([3, 2])
    with gauche:
        st.markdown("**Contrôle des limites**")
        st.altair_chart(graphique_limites(r["controles_limites"]), use_container_width=True)
        st.dataframe(pd.DataFrame([{
            "Statut": badge(c["statut"]), "Limite": c["limite"], "Utilisation": pct(c["utilisation_pct"]),
            "Mesure": valeur_limite(c, "mesure"), "Limite autorisée": valeur_limite(c, "valeur_limite"),
        } for c in r["controles_limites"]]), hide_index=True, use_container_width=True)
    with droite:
        st.markdown("**Exposition nette par secteur**")
        st.altair_chart(graphique_secteurs(r["exposition_par_secteur"]), use_container_width=True)
        st.markdown("**Mouvements notables (|variation| ≥ 3 %)**")
        if r["mouvements_notables"]:
            st.dataframe(pd.DataFrame([{
                "Titre": m["ticker"], "Variation": pct(m["variation_pct"]), "Impact P&L": usd(m["pnl_jour"], signe=True),
            } for m in r["mouvements_notables"]]), hide_index=True, use_container_width=True)
        else:
            st.caption("Aucun mouvement de plus de 3 %.")

    st.markdown("**Positions**")
    st.dataframe(pd.DataFrame([{
        "Titre": p["ticker"], "Secteur": p["secteur"],
        "Quantité": f"{p['quantite']:,.0f}".replace(",", " "), "Cours": f"{p['cours']:.2f}".replace(".", ","),
        "Valeur de marché": usd(p["valeur_marche"]), "Poids": pct(p["poids_pct"]),
        "P&L du jour": usd(p["pnl_jour"], signe=True), "P&L latent": usd(p["pnl_latent"], signe=True),
    } for p in r["positions"]]), hide_index=True, use_container_width=True)

# --- Brief IA
with onglet_brief:
    choix_brief = st.selectbox("Trader ", traders["trader_id"], key="brief_trader",
                               format_func=lambda t: f"{t} — {traders.set_index('trader_id').at[t, 'nom']}")
    fichier = chemin_brief(choix_brief, jour)
    cle_api = bool(os.environ.get("ANTHROPIC_API_KEY"))

    col1, col2 = st.columns([1, 3])
    with col1:
        generer = st.button("✍️ Générer avec Claude", disabled=not cle_api, type="primary")
    with col2:
        if not cle_api:
            st.caption("Définissez ANTHROPIC_API_KEY pour générer un brief depuis l'application. "
                       "Les briefs produits par l'agent dans Claude Code s'affichent ci-dessous.")
        else:
            st.caption(f"Modèle : {MODELE_CLAUDE}. Claude ne reçoit que les chiffres calculés.")

    if generer:
        with st.spinner("Claude rédige le brief…"):
            try:
                texte = generer_brief(resultats[choix_brief])
                fichier.write_text(texte, encoding="utf-8")
                st.success(f"Brief enregistré : briefs/{fichier.name}")
            except Exception as e:  # clé invalide, quota, réseau…
                st.error(f"Échec de la génération : {e}")

    if fichier.exists():
        with st.container(border=True):
            st.markdown(fichier.read_text(encoding="utf-8"))
        st.download_button("Télécharger le brief (.md)", fichier.read_bytes(), file_name=fichier.name)
    else:
        st.info(f"Aucun brief pour {choix_brief} à la séance du {jour:%d/%m/%Y}.")
