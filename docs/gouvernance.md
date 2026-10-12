# Gouvernance : accès, permissions et garde-fous

Un assistant IA branché sur des données de trading doit être **utile sans être dangereux**. Voici comment ce projet sépare les droits.

## Matrice des accès
| Acteur | Positions & limites | Cours | Écriture en base | Passage d'ordre |
|---|---|---|---|---|
| `trader_admin` (pipeline de données) | Lecture / écriture | Lecture / écriture | ✅ | ❌ |
| `brief_reader` (Claude, connecteur MCP, calculs) | Lecture | Lecture | ❌ | ❌ |
| Agent `morning-brief` | Lecture via MCP | Lecture via MCP | ❌ (fichiers `briefs/` seulement) | ❌ |
| Application Streamlit (`app/streamlit_app.py`) | Lecture (rôle `brief_reader`) | Lecture (rôle `brief_reader`) | ❌ (fichiers `briefs/` seulement) | ❌ |
| Claude appelé par l'application (API) | Aucun accès : reçoit le JSON déjà calculé | Aucun accès | ❌ | ❌ |

## Défense en profondeur (4 niveaux)
1. **Base de données** : le rôle `brief_reader` n'a que des droits `SELECT`, et ses transactions sont en `read-only` par défaut. Un `DELETE` est refusé par PostgreSQL lui-même.
2. **Connecteur MCP** : le serveur PostgreSQL n'expose qu'un outil `query` exécuté dans une transaction en lecture seule.
3. **Claude Code** (`.claude/settings.json`) : `psql` est interdit, le fichier `.env` est illisible, seuls le script de calcul et l'écriture dans `briefs/` sont pré-autorisés.
4. **Instructions** (skill et agent) : aucun chiffre calculé de tête, aucune recommandation d'ordre, signalement explicite des données manquantes ou simulées.

## Pourquoi les calculs sont dans un script
Le modèle rédige, le code calcule. Les chiffres sont donc reproductibles, testés (`pytest`) et auditables : on peut relancer le script sur une date passée et retrouver exactement le même brief.

Le code relit aussi : `scripts/check_brief.py` compare chaque brief rédigé au calcul de référence (P&L, expositions, mesure, % d'utilisation et statut de chaque limite, présence des dépassements en tête) ; l'agent `morning-brief` le lance après la rédaction et signale tout écart dans la synthèse du desk.

## Application web (Streamlit)
L'application donne aux traders et au risk manager une vue desk, un détail par trader et le brief IA. Elle applique le même principe, avec un périmètre encore plus étroit pour le modèle :

- **Lecture seule** : l'application se connecte avec `DATABASE_URL`, par défaut le rôle `brief_reader`. Elle liste les séances et les traders, puis appelle `compute_risk.py` ; elle ne contient aucune requête d'écriture.
- **Claude ne voit que des chiffres déjà calculés** : l'appel à l'API contient les consignes de la skill `risk-brief` et le JSON produit par `compute_risk.py`, rien d'autre. Aucun outil n'est déclaré dans cet appel : Claude ne peut ni interroger la base, ni lancer un script, ni écrire un fichier.
- **Écriture limitée à `briefs/`** : c'est l'application, et non Claude, qui enregistre le texte renvoyé dans `briefs/<séance>_<trader>.md`.
- **Aucun ordre** : l'application ne comporte aucune fonction de passage d'ordre.
- **Clé API** : `ANTHROPIC_API_KEY` est lue dans l'environnement, jamais dans le dépôt. Sans clé, la génération est désactivée et l'application affiche les briefs existants.

Limites à connaître : un brief généré depuis l'application n'est pas contrôlé automatiquement ; il faut lancer `scripts/check_brief.py <brief>` (l'agent `morning-brief`, lui, le fait après chaque rédaction). Générer un brief remplace le fichier existant pour ce trader et cette séance. Les chiffres du trader sont envoyés à l'API d'Anthropic : sans conséquence ici (données fictives), à valider avant tout usage sur des positions réelles. Enfin, l'application n'a pas d'authentification : toute personne qui y accède voit tous les traders.

## Ce qu'il faudrait ajouter en production
- Authentification par utilisateur (SSO) et rôles par desk : un trader ne voit que ses positions.
- Journal d'audit des requêtes de l'agent.
- Secrets dans un coffre-fort (pas de mot de passe dans `.mcp.json`).
- Revue humaine avant toute diffusion du brief hors du desk.
