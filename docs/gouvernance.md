# Gouvernance : accès, permissions et garde-fous

Un assistant IA branché sur des données de trading doit être **utile sans être dangereux**. Voici comment ce projet sépare les droits.

## Matrice des accès
| Acteur | Positions & limites | Cours | Écriture en base | Passage d'ordre |
|---|---|---|---|---|
| `trader_admin` (pipeline de données) | Lecture / écriture | Lecture / écriture | ✅ | ❌ |
| `brief_reader` (Claude, connecteur MCP, calculs) | Lecture | Lecture | ❌ | ❌ |
| Agent `morning-brief` | Lecture via MCP | Lecture via MCP | ❌ (fichiers `briefs/` seulement) | ❌ |

## Défense en profondeur (4 niveaux)
1. **Base de données** : le rôle `brief_reader` n'a que des droits `SELECT`, et ses transactions sont en `read-only` par défaut. Un `DELETE` est refusé par PostgreSQL lui-même.
2. **Connecteur MCP** : le serveur PostgreSQL n'expose qu'un outil `query` exécuté dans une transaction en lecture seule.
3. **Claude Code** (`.claude/settings.json`) : `psql` est interdit, le fichier `.env` est illisible, seuls le script de calcul et l'écriture dans `briefs/` sont pré-autorisés.
4. **Instructions** (skill et agent) : aucun chiffre calculé de tête, aucune recommandation d'ordre, signalement explicite des données manquantes ou simulées.

## Pourquoi les calculs sont dans un script
Le modèle rédige, le code calcule. Les chiffres sont donc reproductibles, testés (`pytest`) et auditables : on peut relancer le script sur une date passée et retrouver exactement le même brief.

Le code relit aussi : `scripts/check_brief.py` compare chaque brief rédigé au calcul de référence (P&L, expositions, mesure, % d'utilisation et statut de chaque limite, présence des dépassements en tête) ; l'agent `morning-brief` le lance après la rédaction et signale tout écart dans la synthèse du desk.

## Ce qu'il faudrait ajouter en production
- Authentification par utilisateur (SSO) et rôles par desk : un trader ne voit que ses positions.
- Journal d'audit des requêtes de l'agent.
- Secrets dans un coffre-fort (pas de mot de passe dans `.mcp.json`).
- Revue humaine avant toute diffusion du brief hors du desk.
