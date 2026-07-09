# scrap-teso — Thésaurus du Management ACIEGE

Extraction, structuration et exploitation du **Thésaurus du Management de
l'ACIEGE** (<https://aciege.org/Schema_Fra.html>) pour l'annotation d'un corpus
documentaire (~50 000 thèses).

## Le pipeline en un coup d'œil

```
aciege.org ──[1. scrape_aciege.py]──> data/ ──[2. build_thesaurus.py]──> thesaurus/
 (site web)                        (données brutes)                  (classification prête
                                                                      pour l'annotation)
```

| Étape | Script | Entrée | Sortie |
|---|---|---|---|
| 1. Scraping | `scrape_aciege.py` | le site aciege.org | `data/` (CSV, XLSX, JSON bruts) |
| 2. Structuration | `build_thesaurus.py` | `data/aciege.json` | `thesaurus/` (CSV pivot, JSON, SKOS) |
| 3. Annotation | *à venir* | `thesaurus/` + corpus de thèses | pré-annotation automatique |

## Installation

```bash
pip install -r requirements.txt
```

---

## 1. `scrape_aciege.py` — scraping du thésaurus

Récupère l'intégralité du thésaurus en deux passes :

1. **La page index** `Schema_Fra.html` : la hiérarchie catégorie → groupe →
   sous-groupe est portée par les classes CSS `ThCol1Fra` / `ThCol2Fra` /
   `ThCol3Fra`, avec pour chaque sous-groupe ses liens « Schéma » et « Liste ».
2. **Les pages schéma** `Schm/Fra/FRA_xxx.html` : chaque terme est une zone
   cliquable `<area>` dont l'attribut `title` contient le nom, la définition
   et la ou les sources — pas besoin de visiter les pages de détail `Dct/`.

```bash
python scrape_aciege.py --limit 3   # test rapide (3 schémas)
python scrape_aciege.py             # tout le thésaurus (~2 min)
```

Sorties dans `data/` :

- `table1_index.csv` — 1 ligne par sous-groupe : catégorie ; thème ; groupe ;
  sous-groupe ; liens Schéma/Liste.
- `table2_termes.csv` — 1 ligne par terme : sous-groupe ; liens ; code ;
  titre ; définition ; source.
- `aciege.xlsx` — les 2 tableaux en 2 feuilles Excel.
- `aciege.json` — tout, plus les erreurs éventuelles.

Les CSV utilisent `;` et l'UTF-8 BOM : ils s'ouvrent directement dans Excel FR.

### ⚠️ Exécution : GitHub Actions (pas depuis Claude Code web)

L'environnement Claude Code web n'a **pas d'accès réseau sortant** (le proxy
d'egress répond `403` sur tout domaine externe). Le scraping tourne donc via
le workflow **`.github/workflows/scrape.yml`** : tout push sur la branche
`claude/web-scraping-1qouc5` (hors `data/`) — ou un déclenchement manuel
*workflow_dispatch* — lance le scrape sur un runner GitHub, qui committe
`data/` sur la branche. Vous pouvez aussi simplement le lancer sur votre
machine avec les commandes ci-dessus.

---

## 2. `build_thesaurus.py` — structuration en thésaurus

Transforme les données brutes en classification propre à 4 niveaux :

```
5 catégories > 23 groupes > 68 sous-groupes > 1 858 termes   (1 954 concepts)
```

```bash
python build_thesaurus.py           # data/aciege.json -> thesaurus/
```

Sorties dans `thesaurus/` :

| Fichier | Usage |
|---|---|
| `concepts_flat.csv` | **Format pivot** : 1 concept par ligne avec `id`, `parent_id`, `niveau`, `code`, `libelle`, chemins complets (codes et libellés), définition, source, URL. À charger dans pandas ou un outil d'annotation. |
| `thesaurus.json` | Hiérarchie imbriquée (catégories > groupes > sous-groupes > termes) pour usage programmatique. |
| `thesaurus.skos.ttl` | Export **SKOS** (Turtle), le standard des thésaurus documentaires : importable dans VocBench, TemaTres et la plupart des plateformes d'indexation. |
| `stats.md` | Statistiques de couverture. |

---

## 3. Annoter un corpus avec cette classification

- **Étiquette = le `code`** : `111` (sous-groupe ORGANISATION) ou `111_48`
  (terme ANALYSE DES SYSTEMES). La hiérarchie se retrouve par préfixe
  (`111_48` ⊂ `111` ⊂ `11` ⊂ `1`), donc les statistiques s'agrègent à
  n'importe quel niveau après coup.
- **Granularité** : le niveau **sous-groupe (68 classes)** est le bon pivot
  pour classer un gros corpus ; le niveau **terme (1 858)** sert à
  l'indexation fine.
- **Multi-label** : une thèse chevauche souvent 2-3 sous-groupes — prévoir un
  code principal + des codes secondaires.
- **Les définitions sont les critères d'annotation** : consignes pour les
  annotateurs humains, ou base d'une pré-annotation automatique (matching
  embeddings / LLM entre résumé de thèse et définitions du thésaurus).

## État des données (scrape du 2026-07-09)

- 68 sous-groupes, dont **53 avec schéma** (les catégories « Listes outils »
  et « Géographie » n'ont que des pages « Liste »).
- 1 858 termes, **0 erreur** de scraping, aucun doublon.
- 341 termes sans définition dans la bulle du schéma (elle existe peut-être
  sur leur page `Dct/`) ; 478 sans source identifiée.

## Fichiers annexes

- `scraper.py` — miroir générique récursif (HTML + ressources + tableaux),
  indépendant du thésaurus ; utile pour archiver n'importe quel site.
  `python scraper.py <url> -o mirror --depth 3`
- `.github/workflows/scrape.yml` — le workflow GitHub Actions décrit plus haut.

## Licence des données

Le Thésaurus du Management de l'ACIEGE est diffusé sous licence
**Creative Commons BY-NC-ND 4.0** (Attribution, Pas d'Utilisation Commerciale,
Pas de Modification). Les données extraites ici en héritent : citez l'ACIEGE
et respectez ces conditions.
