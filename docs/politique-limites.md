# Politique de limites de risque — Desk Actions US (fictive)

Document de référence chargé dans le Projet Claude. Les valeurs sont stockées dans la table `limites`.

## Types de limites
| Limite | Définition | Unité |
|---|---|---|
| Exposition brute | Somme des valeurs absolues de marché de toutes les positions (longues et courtes) | USD |
| Exposition secteur | Valeur de marché nette d'un secteur, en valeur absolue | USD |
| Concentration | Poids de la plus grosse ligne dans l'exposition brute | % |
| Perte journalière | Perte du jour (P&L journalier négatif) | USD |

## Statuts
- 🟢 **OK** : utilisation < 80 %
- 🟠 **ALERTE** : utilisation entre 80 % et 100 % — à surveiller, pas d'action obligatoire
- 🔴 **DÉPASSEMENT** : utilisation > 100 % — le trader informe le risk manager avant l'ouverture

## Limites en vigueur
| Trader | Brute | Secteur | Concentration | Perte jour |
|---|---|---|---|---|
| T01 — Léa Martin (Tech) | 6 000 000 | Technologie : 4 500 000 | 30 % | 120 000 |
| T02 — Marc Dubois (Fin. & Énergie) | 5 000 000 | Énergie : 1 600 000 | 30 % | 100 000 |

## Procédure en cas de dépassement
1. Le brief matinal signale le dépassement en tête.
2. Le trader confirme la lecture et propose un plan de retour sous la limite.
3. Le risk manager valide ou accorde une dérogation temporaire (tracée).

L'assistant IA **constate et signale**. Il ne décide pas et ne passe aucun ordre.
