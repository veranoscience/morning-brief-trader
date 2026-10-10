---
name: risk-brief
description: Rédige le brief matinal de risque d'un trader (P&L, limites, mouvements de marché) à partir des chiffres calculés par scripts/compute_risk.py. À utiliser dès qu'on demande un brief, un point risque, un contrôle de limites ou le P&L d'un trader ou d'un desk.
---

# Brief matinal de risque

## Règles non négociables
1. **Aucun chiffre calculé de tête.** Tous les montants viennent de
   `python scripts/compute_risk.py --trader <ID>` (JSON). Si le script échoue,
   dis-le et arrête-toi : pas de brief avec des chiffres approximatifs.
2. **Lecture seule.** Ne jamais modifier la base, ne jamais proposer ni passer
   d'ordre. Tu peux suggérer des *points d'attention*, la décision reste au trader
   et au risk manager.
3. **Les dépassements d'abord.** Un statut `DEPASSEMENT` apparaît en tête du brief,
   avant tout le reste.
4. **Transparence sur les données.** Si `source_cours` contient `simulation`,
   l'indiquer en en-tête (« cours simulés — démonstration »).

## Étapes
1. Identifier le trader (ID `T01`, `T02`… ou `all`). Si on te donne un nom, retrouve
   l'ID dans la table `traders` via le connecteur `trading-db`.
2. Lancer `python scripts/compute_risk.py --trader <ID>` (ajouter `--date AAAA-MM-JJ`
   si une date est demandée).
3. Si besoin de contexte (historique d'un cours, détail d'une position), interroger
   la base en SQL via `trading-db`. Toujours en `SELECT`.
4. Rédiger le brief selon le modèle ci-dessous, en français, chiffres au format
   `1 234 567 USD`, pourcentages à une décimale.
5. Enregistrer dans `briefs/AAAA-MM-JJ_<ID>.md`.

## Modèle
```markdown
# Morning Brief — <Nom> (<Desk>)
**Séance du <date>** · comparée au <seance_precedente> · source des cours : <source>

## 🚨 À traiter en priorité
<une ligne par DEPASSEMENT : limite, mesure vs limite, % d'utilisation>
<si aucun : « Aucun dépassement de limite. »>

## Synthèse
| P&L du jour | P&L latent | Exposition brute | Exposition nette |
|---|---|---|---|

## Contrôle des limites
| Limite | Mesure | Limite | Utilisation | Statut |
(🔴 DEPASSEMENT · 🟠 ALERTE ≥ 80 % · 🟢 OK)

## Mouvements notables (|variation| ≥ 3 %)
<ticker, variation, impact P&L ; expliquer ce qui pèse le plus>

## Points d'attention
<2 à 4 puces factuelles, ex. « NVDA représente 28,6 % de l'exposition brute,
proche de la limite de 30 % ». Pas de recommandation d'achat/vente.>
```

## Ton
Factuel, court, lisible en 30 secondes. Un trader lit ce brief avant l'ouverture.
