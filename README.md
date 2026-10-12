# Morning Brief Trader 📈

**Un assistant IA de risque pour un desk de trading, construit avec Claude : Skill, agent, connecteur MCP et gouvernance des accès.**

Chaque matin, avant l'ouverture, l'agent prépare pour chaque trader un brief de 30 secondes : P&L de la veille, contrôle des limites de risque, mouvements de marché importants. Les dépassements de limites apparaissent en tête.

> Projet de démonstration — portefeuilles, traders et limites sont fictifs. Les cours sont réels (yfinance).

![Onglet Détail trader : indicateurs clés, contrôle des limites, exposition nette par secteur et positions de Léa Martin (T01)](docs/images/detail-trader.webp)

## Le problème métier
Au middle office, le contrôle des limites du matin est souvent manuel : extraction, tableur, mise en forme, e-mail. C'est répétitif et une erreur peut coûter cher. Ce projet montre comment l'automatiser **sans donner à l'IA de pouvoir sur les positions**.

## Architecture

```mermaid
flowchart LR
    Y[yfinance<br/>cours de clôture] --> S[seed.py<br/>pipeline de données]
    S -->|trader_admin<br/>écriture| DB[(PostgreSQL<br/>trading)]
    DB -->|brief_reader<br/>lecture seule| MCP[Connecteur MCP<br/>trading-db]
    DB -->|lecture seule| R[compute_risk.py<br/>calculs testés]
    MCP --> A[Agent Claude<br/>morning-brief]
    R --> A
    K[Skill risk-brief<br/>règles + modèle] --> A
    P[Projet Claude<br/>glossaire + politique] -.questions métier.-> U[Trader / Risk manager]
    A --> B[briefs/*.md]
    B --> U
```

| Brique | Fichier | Rôle |
|---|---|---|
| Données | `db/01_schema.sql`, `scripts/seed.py` | Positions, limites, cours ; rôle lecture seule pour Claude |
| Calcul | `scripts/compute_risk.py` | P&L, expositions, contrôle des limites → JSON. Testé avec `pytest` |
| Contrôle | `scripts/check_brief.py` | Relit chaque brief et le compare au calcul de référence (OK / ÉCART, code retour 1 en cas d'écart). Testé avec `pytest` |
| Connecteur MCP | `.mcp.json` | Claude interroge la base en SQL, en lecture seule |
| Skill | `.claude/skills/risk-brief/SKILL.md` | Règles et modèle du brief |
| Agent | `.claude/agents/morning-brief.md` | Enchaîne tous les traders et produit la synthèse du desk |
| Application web | `app/streamlit_app.py` | Vue desk, détail trader et brief IA pour les traders et le risk manager |
| Gouvernance | `.claude/settings.json`, `docs/gouvernance.md` | Permissions et garde-fous |
| Projet Claude | `docs/glossaire.md`, `docs/politique-limites.md` | Base de connaissances pour les équipes métier |

**Principe clé : le modèle rédige, le code calcule.** Aucun chiffre du brief n'est produit « de tête » par le modèle.

## Démarrage rapide

Prérequis : Python 3.11+, Docker, Node.js (pour le connecteur MCP), [Claude Code](https://docs.claude.com/en/docs/claude-code/overview).

```bash
# 1. Base de données (crée le schéma et le rôle lecture seule)
docker compose up -d

# 2. Environnement Python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Données (cours réels si disponibles, sinon simulés)
python scripts/seed.py                        # scénario normal
python scripts/seed.py --scenario krach_tech  # forte baisse de la tech

# 4. Vérifications
pytest -q
python scripts/compute_risk.py --trader T01
```

### Sans Docker (PostgreSQL déjà installé, ex. Homebrew)

```bash
# en tant que super-utilisateur local (sur Homebrew : votre compte macOS)
psql -d postgres -c "CREATE ROLE trader_admin LOGIN PASSWORD 'admin' CREATEROLE"
psql -d postgres -c "CREATE DATABASE trading OWNER trader_admin"
psql "postgresql://trader_admin:admin@localhost:5432/trading" -f db/01_schema.sql
```

`CREATEROLE` est nécessaire : le schéma crée lui-même le rôle en lecture seule `brief_reader`.
Le connecteur MCP a aussi besoin de Node.js (`brew install node`).

## Application web (Streamlit)

Pour les traders et le risk manager, sans passer par le terminal :

```bash
streamlit run app/streamlit_app.py
```

L'application s'ouvre sur http://localhost:8501. On choisit la séance dans le panneau latéral, puis :

| Onglet | Contenu |
|---|---|
| **Vue desk** | Dépassements de limites en tête, puis une ligne par trader : P&L du jour, P&L latent, exposition brute, nombre de dépassements et d'alertes |
| **Détail trader** | Indicateurs clés, utilisation de chaque limite (seuils 80 % et 100 %), exposition nette par secteur, mouvements notables, positions |
| **Brief IA** | Affiche le brief du trader pour la séance (`briefs/`), le fait rédiger par Claude et permet de le télécharger |

Variables d'environnement : `DATABASE_URL` (par défaut le rôle en lecture seule `brief_reader`), `ANTHROPIC_API_KEY` (facultative : sans elle, le bouton de génération est désactivé et l'onglet affiche les briefs déjà produits par l'agent), `CLAUDE_MODEL` (facultative).

**Dans l'application, Claude ne reçoit que les chiffres déjà calculés** par `compute_risk.py`, transmis en JSON avec les consignes de la skill `risk-brief`. Il n'a ni accès à la base, ni outil, ni droit d'écriture : il renvoie un texte, et c'est l'application qui l'enregistre dans `briefs/`. Pour contrôler un brief généré depuis l'application, lancer `python scripts/check_brief.py <brief>`.

## Utilisation avec Claude Code

```bash
claude
```

Puis, par exemple :
- `Prépare les briefs du jour` → l'agent `morning-brief` produit un brief par trader et une synthèse du desk.
- `Fais le brief risque de Léa Martin` → la skill `risk-brief` seule.
- `Quelle est l'exposition de Marc au secteur Énergie depuis 5 jours ?` → requête SQL via le connecteur MCP.

Exemple de sortie : [`briefs/2026-10-09_T01.md`](briefs/2026-10-09_T01.md).

## Projet Claude pour les équipes métier
Dans claude.ai, créer un Projet « Desk Actions US », y ajouter `docs/glossaire.md` et `docs/politique-limites.md`, et ces instructions :

> Tu aides les traders et le risk manager du desk Actions US. Appuie-toi sur le glossaire et la politique de limites. Tu expliques et tu constates, tu ne recommandes jamais d'achat ou de vente.

## Scénarios de test
| Scénario | Résultat attendu |
|---|---|
| `normal` | Marc : dépassement de la limite secteur Énergie. Léa : alertes, dont la concentration NVDA proche de 30 %, sans dépassement |
| `krach_tech` | Léa : dépassement de la perte journalière (≈ 245 % de la limite) |

Valeurs obtenues avec les cours simulés (`--offline`) ; avec les cours réels, les pourcentages varient selon le marché.
| Requête d'écriture depuis Claude | Refusée par PostgreSQL (`read-only transaction`) |

## Pistes d'évolution
- Envoi du brief par e-mail ou Slack via un connecteur.
- Planification quotidienne (tâche programmée) avant l'ouverture.
- Indicateurs de risque supplémentaires : VaR historique, bêta par rapport au S&P 500.

## Auteure
**Ksenia Dautel** — Data Scientist, anciennement back office bancaire.
[Portfolio](https://veranoscience.github.io/portfolio/) · [GitHub](https://github.com/veranoscience)
