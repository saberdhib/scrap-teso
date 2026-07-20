# Dictionnaire de données — référentiel canonique ACIEGE

Version canonique consolidée à partir de deux sources : le **scraping du site**
aciege.org et l'**export officiel Zthes** (`Ths_Export_20260115.xml`).

## Identifiant canonique (`concept_id`)

Format unique : **chiffres séparés par des underscores**, sans point ni slash.

| Niveau | `level` | Forme | Exemple | Parent |
|---|---|---|---|---|
| Catégorie | 1 | `N` | `1` | — |
| Groupe | 2 | `NN` | `12` | 1er chiffre (`1`) |
| Sous-groupe | 3 | `NNN` | `124` | 2 premiers chiffres (`12`) |
| Terme | 4 | `NNN_NN` | `124_85` | avant le `_` (`124`) |

Le parent se **déduit du code** : la hiérarchie taxonomique est donc auto-portée
par l'identifiant (préfixe). Les identifiants sources `001.16` et `002.71/2`
sont normalisés en `001_16` et `002_71_2`.

## `concepts_master.csv` — table canonique (1 ligne / concept)

| Colonne | Description | Règle |
|---|---|---|
| `concept_id` | Identifiant canonique | unique, normalisé |
| `level` / `level_name` | 1..4 / categorie…terme | |
| `label_fr` | Libellé français | **Zthes fait foi** ; sinon site |
| `label_en` | Libellé anglais | Zthes (relation LE) |
| `definition_fr` | Définition française | Zthes prioritaire, sinon site ; placeholders filtrés |
| `definition_en` | Définition anglaise | Zthes (souvent placeholder → vide) |
| `source_biblio` | Source bibliographique de la définition | extraite du site |
| `parent_id` | Concept parent | déduit du code |
| `path_ids` / `path_labels` | Chemin racine→concept | séparateur ` > ` |
| `in_site` / `in_zthes` | Présence dans chaque source | 0/1 |
| `source_authority` | Source retenue pour le libellé | `zthes` si présent (niveau ≥ 3), sinon `site` |
| `scheme_url` | URL de la fiche sur aciege.org | site |
| `n_children` | Nombre d'enfants directs | calculé |
| `n_synonyms` | Nombre de synonymes (FR+EN) | calculé |
| `n_related` | Nombre de termes associés (RT) | calculé |
| `has_definition` | Définition FR présente | 0/1 |

## `concepts_hierarchy.csv` — arbre taxonomique

`concept_id ; parent_id ; level ; label_fr ; parent_label_fr`
Une ligne par concept non-racine. Arbre strict : **un seul parent** par concept.

## `concepts_synonyms.csv` — synonymes et variantes

`concept_id ; label_fr ; synonym ; lang ; relation ; source`
- `relation` = `altLabel` (SKOS). `lang` ∈ {fr, en}.
- `source` ∈ {`site_employe_pour`, `zthes_UF`} — union dédupliquée (casse ignorée).

## `concepts_translations.csv` — correspondances FR / EN

`concept_id ; label_fr ; label_en ; definition_fr ; definition_en`
Uniquement les concepts ayant au moins un champ anglais.

## `concepts_edges.csv` — graphe relationnel complet

`source_id ; target_id ; relation ; kind`
- `skos:broader` / `kind=structural` : lien taxonomique enfant→parent.
- `skos:broader` / `kind=zthes_BT` : terme générique hors arbre structurel.
- `skos:related` / `kind=zthes_RT` : terme associé (relation transverse).

## `concepts_json.json` — hiérarchie imbriquée

Arbre `categories → groupes → sous-groupes → termes`. Chaque nœud porte
`id, level, label_fr, label_en`, et si présents `definition_fr/en`,
`synonyms[]`, `related[]`, `source`, `children[]`. Format cible pour la
navigation et l'alimentation d'un classifieur (cartes de concepts).

## Règles de gestion

1. **Autorité** : l'export Zthes prime pour les libellés et l'anglais ; le
   scraping complète (URLs, sources, ossature catégorie/groupe, termes absents
   de l'export).
2. **Définitions** : une note qui ne fait que répéter le libellé est un
   placeholder → ignorée.
3. **Synonymes** : union des deux sources, dédupliquée sans tenir compte de la
   casse.
4. **Hiérarchie** : l'arbre structurel (déduit du code) est la référence ; les
   relations BT/NT entre termes de l'export sont ajoutées au graphe, pas à
   l'arbre, pour garantir un parent unique.
