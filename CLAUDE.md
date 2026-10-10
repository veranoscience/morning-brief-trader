# Morning Brief Trader — contexte pour Claude Code

Assistant de risque pour un desk Actions US (données fictives). Il produit chaque matin un brief par trader : P&L, contrôle des limites, mouvements de marché.

- Base PostgreSQL `trading`, accessible en lecture seule via le connecteur MCP `trading-db`.
- Calculs : `scripts/compute_risk.py` (JSON). Ne jamais refaire ces calculs de tête.
- Rédaction : skill `risk-brief`. Orchestration du desk : agent `morning-brief`.
- Références métier : `docs/glossaire.md`, `docs/politique-limites.md`, `docs/gouvernance.md`.
- Tests : `pytest -q`. Toute modification de `compute_risk.py` doit garder les tests au vert.
- Interdits : modifier la base depuis Claude, proposer ou passer des ordres.
