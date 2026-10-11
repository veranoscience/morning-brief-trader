# Synthèse desk — Actions US
**Séance du 2026-10-09** · comparée au 2026-10-08 · source des cours : yfinance

> Synthèse préparée le dimanche 2026-10-11 pour le risk manager. Elle porte sur la dernière séance disponible, celle du vendredi 2026-10-09. Chiffres issus de `scripts/compute_risk.py --trader all`.

## Vue d'ensemble
| Trader | P&L du jour | Dépassements | Alertes | Brief |
|---|---|---|---|---|
| T01 — Léa Martin (Tech) | +25 463 USD | 0 | 3 | [2026-10-09_T01.md](2026-10-09_T01.md) |
| T02 — Marc Dubois (Financières & Énergie) | +31 684 USD | 1 | 2 | [2026-10-09_T02.md](2026-10-09_T02.md) |

## 🚨 Dépassements (du plus grave au moins grave)
| Rang | Trader | Limite | Mesure | Limite | Utilisation |
|---|---|---|---|---|---|
| 1 | T02 — Marc Dubois | Exposition secteur Énergie | 1 804 282 USD | 1 600 000 USD | 112,8 % |

Un seul dépassement sur le desk. Procédure applicable (`docs/politique-limites.md`) : le trader confirme la lecture et propose un plan de retour sous la limite ; le risk manager valide ou accorde une dérogation temporaire tracée.

## Alertes (utilisation entre 80 % et 100 %)
| Trader | Limite | Mesure | Limite | Utilisation |
|---|---|---|---|---|
| T01 — Léa Martin | Concentration (max : NVDA) | 29,1 % | 30,0 % | 96,9 % |
| T02 — Marc Dubois | Concentration (max : XOM) | 26,1 % | 30,0 % | 86,9 % |
| T01 — Léa Martin | Exposition brute | 5 132 183 USD | 6 000 000 USD | 85,5 % |
| T02 — Marc Dubois | Exposition brute | 4 231 686 USD | 5 000 000 USD | 84,6 % |
| T01 — Léa Martin | Exposition secteur Technologie | 3 702 399 USD | 4 500 000 USD | 82,3 % |

Les limites de perte journalière ne sont sollicitées pour aucun des deux traders (P&L du jour positif, 0,0 % d'utilisation).

## Qualité des données
- Cours réels (yfinance), aucun cours simulé.
- Les deux traders ont des positions et des cours pour la séance du 2026-10-09 et la séance précédente ; aucune donnée manquante signalée par le script.

## Briefs individuels
- [Léa Martin — T01](2026-10-09_T01.md)
- [Marc Dubois — T02](2026-10-09_T02.md)
