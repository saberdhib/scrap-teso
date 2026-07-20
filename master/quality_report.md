# Rapport qualité — référentiel canonique ACIEGE

Concepts : **2484** — 5 categorie, 23 groupe, 68 sous_groupe, 2388 terme.

## 1. Sources et fusion

| Source | Rôle | Autorité |
|---|---|---|
| Scraping aciege.org | ossature 4 niveaux, URLs, sources biblio | complète |
| Export Zthes 2026-01-15 | libellés, anglais, définitions, UF, RT | **fait foi** |

## 2. Couverture croisée des termes

- Termes présents dans les **deux** sources : 2387
- Termes **site uniquement** : 1 (362_19)
- Termes **export uniquement** : 0 (—)

## 3. Conflits de libellés (export retenu)

**133 libellés** divergent entre scraping et export ; l'export a été retenu (le scraping prenait parfois la définition pour le titre). Exemples :

| Code | Scraping | Export (retenu) |
|---|---|---|
| 111_23 | GOUVERNEMENT D'ENTREPRISE | GOUVERNANCE DE L'ENTREPRISE |
| 111_87 | CULTURE D'ENTREPRISE | CULTURE ORGANISATIONNELLE |
| 112_61 | Les concepts d’entrepreneuriat social et d’en | ENTREPRENEURIAT SOCIAL |
| 112_66 | COLLABORATION INTER-ENTREPRISES | COLLABORATION INTER ENTREPRISES |
| 112_78 | SOUS-TRAITANCE | SOUS TRAITANCE |
| 112_79 | Le portage salarial est une organisation du t | PORTAGE SALARIAL |
| 112_84 | 1. La fusion d'entreprises est le procédé de  | FUSION ACQUISITION |
| 113_33 | PRISE DE DECISION : 1. Action d'effectuer un  | PRISE DE DECISION |
| 113_75 | Déf 1. L'intelligence économique consiste en  | INTELLIGENCE ECONOMIQUE |
| 121_21 | Déf 1. Perception par le consommateur des car | ATTRIBUT DU PRODUIT |
| 121_91 | IMAGE DE MARQUE. Ensemble des représentations | IMAGE DE MARQUE |
| 123_81 | MARCHANDISAGE | MERCHANDISING |

## 4. Définitions

- Depuis l'export : 1806
- Depuis le site (fallback) : 0
- Aucune : 582
- Placeholders filtrés (note = libellé) : 573

## 5. Doublons et ambiguïtés

- **Libellés FR identiques** sur plusieurs termes : 1
  - « DOCTRINE » → 362_19, 362_38
- **Synonymes ambigus** (même variante → plusieurs termes) : 0
  > Pour la classification : lever l'ambiguïté par le contexte (chemin hiérarchique) plutôt que par le seul synonyme.

## 6. Intégrité du graphe

- Arêtes totales : 6384 {'structural': 2479, 'zthes_BT': 2321, 'zthes_RT': 1584}
- Relations RT pointant vers une cible absente : 0
- Concepts au parent manquant : 0 (aucun)

## 7. Bilinguisme

- Concepts avec libellé anglais : 2455
- Traductions exportées : 2455
- ⚠️ Les définitions anglaises de l'export sont majoritairement des placeholders (nom répété) : seules les vraies variantes sont conservées.

## 8. Hypothèses et points d'attention

1. **Identifiant canonique** underscore choisi pour rester compatible fichiers/URL et préserver la hiérarchie par préfixe.
2. **Un seul parent par concept** (arbre) ; les BT/NT multiples de l'export sont dans `concepts_edges.csv`.
3. **582 termes sans définition** (surtout géographie/langues, auto-descriptifs) : acceptable, le libellé + le chemin suffisent au modèle.
4. **362_19 DOCTRINE** absent de l'export officiel : conservé depuis le site, à confirmer avec l'équipe.
5. Le référentiel couvre le **management/gestion** : prévoir une classe « hors thésaurus » côté classifieur pour les thèses hors domaine.
