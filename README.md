# scrap-teso — Scraper pour aciege.org

## ⭐ `scrape_aciege.py` — scraper sur mesure du Thésaurus (à utiliser en priorité)

Produit directement les 2 tableaux attendus à partir de
<https://aciege.org/Schema_Fra.html> :

- **Table 1 — index** : catégorie ; thème ; groupe numérologie ; groupe titre ;
  sous-groupe numérologie ; sous-groupe ; lien schéma ; lien liste.
- **Table 2 — termes** : sous-groupe numérologie ; sous-groupe ; lien sous-groupe ;
  lien sous-sous-groupe ; code sous-sous-groupe ; titre ; définition ; source.

Les définitions et sources sont extraites de l'attribut `title` des balises
`<area>` des pages `Schm/Fra/FRA_xxx.html` (pas besoin de crawler les pages `Dct/`).

```bash
pip install -r requirements.txt

# Test rapide sur 3 schémas
python scrape_aciege.py --limit 3

# Tout le thésaurus
python scrape_aciege.py
```

Sorties dans `data/` : `table1_index.csv`, `table2_termes.csv` (séparateur `;`,
UTF-8 BOM → s'ouvrent directement dans Excel FR), `aciege.xlsx` (2 feuilles),
`aciege.json` (tout + erreurs éventuelles).

Une fois le scrape terminé, committez le dossier `data/` sur la branche pour
la phase de nettoyage :

```bash
git add -f data && git commit -m "Données brutes ACIEGE" && git push
```

---

## 🏗 `build_thesaurus.py` — thésaurus structuré pour l'annotation

Transforme `data/aciege.json` en thésaurus à 4 niveaux, prêt pour annoter un
corpus documentaire (thèses, articles…) :

```
catégorie (5) > groupe (23) > sous-groupe (68) > terme (1858)
```

```bash
python build_thesaurus.py     # -> thesaurus/
```

Sorties dans `thesaurus/` :

| Fichier | Usage |
|---|---|
| `concepts_flat.csv` | **Format pivot** : 1 concept/ligne avec `id`, `parent_id`, `niveau`, `code`, `libelle`, chemins complets, définition, source. À charger dans pandas ou un outil d'annotation. |
| `thesaurus.json` | Hiérarchie imbriquée pour usage programmatique. |
| `thesaurus.skos.ttl` | Export **SKOS** (standard des thésaurus) : importable dans VocBench, TemaTres, et la plupart des plateformes d'indexation. |
| `stats.md` | Statistiques de couverture. |

### Annoter un corpus avec cette classification

- **Identifiant d'annotation recommandé** : le `code` (`111` pour un
  sous-groupe, `111_48` pour un terme précis) — stable, compact, et la
  hiérarchie se retrouve par préfixe (`111_48` ⊂ `111` ⊂ `11` ⊂ `1`).
- **Granularité** : annoter au niveau **sous-groupe (68 classes)** est le bon
  pivot pour classer un gros corpus ; le niveau **terme (1858)** sert pour
  l'indexation fine. Une annotation multi-label (2-3 codes par document) est
  généralement plus fidèle qu'un code unique.
- Les **définitions** de `concepts_flat.csv` servent de critères d'annotation
  pour les annotateurs humains — ou de base à une pré-annotation automatique
  (matching embeddings / LLM entre résumé de thèse et définitions).

---

## `scraper.py` — miroir générique (optionnel)

Scraper / miroir récursif pour récupérer **tout** le contenu d'une page (et des
pages liées du même domaine) : HTML, sous-pages, images, PDF, documents, CSS, JS,
plus extraction du texte et des tableaux (en CSV).

Cible par défaut : <https://aciege.org/Schema_Fra.html>

## ⚠️ Important : à exécuter en local

Ce dépôt a été préparé dans l'environnement **Claude Code sur le web**, dont la
politique réseau **bloque tout accès sortant** vers Internet (sauf registres de
paquets et infra Anthropic/GitHub). Le proxy d'egress renvoie `403` sur la
connexion vers `aciege.org` :

```
connect_rejected : gateway answered 403 to CONNECT — host aciege.org:443
```

Le scraping ne peut donc **pas** tourner depuis le web. Lancez ce script
**sur votre machine** (ou tout environnement avec accès Internet).

Pour l'exécuter directement depuis une session Claude Code web, il faudrait
recréer l'environnement avec une politique réseau plus permissive
(voir <https://code.claude.com/docs/en/claude-code-on-the-web>, section network).

## Installation

```bash
pip install -r requirements.txt
```

## Utilisation

```bash
# Récupérer la page cible + ressources + sous-pages (profondeur 2 par défaut)
python scraper.py

# Une URL précise, dossier de sortie et profondeur personnalisés
python scraper.py https://aciege.org/Schema_Fra.html -o mirror_aciege --depth 3

# Se limiter aux pages situées sous le même dossier que la page de départ
python scraper.py https://aciege.org/Schema_Fra.html --same-path-only

# Rester poli : pause entre requêtes, et plafond de pages
python scraper.py --delay 1 --max-pages 200
```

### Options

| Option | Rôle | Défaut |
|---|---|---|
| `url` | URL de départ | `https://aciege.org/Schema_Fra.html` |
| `-o, --output` | Dossier de sortie | `mirror` |
| `-d, --depth` | Profondeur d'exploration des liens HTML | `2` |
| `--delay` | Pause (s) entre requêtes | `0.5` |
| `--same-path-only` | Rester sous le dossier de la page de départ | désactivé |
| `--max-pages` | Nombre max de pages HTML (`0` = illimité) | `0` |

## Ce qui est produit

Sous le dossier de sortie (`mirror/` par défaut) :

- **`<domaine>/…`** — le site en miroir, arborescence conservée (HTML + ressources).
- **`<page>.html.txt`** — le texte brut extrait de chaque page.
- **`_tables/…csv`** — chaque `<table>` de chaque page, exportée en CSV.
- **`manifest.json`** — inventaire complet : pages, ressources (taille, type),
  liens et erreurs.

## Notes

- En-têtes façon navigateur (User-Agent Chrome) pour éviter les blocages
  anti-bot basiques (403). Si le site protège plus fort (Cloudflare, JS
  obligatoire), passez à une version Playwright — demandez, je la fournis.
- Respectez le `robots.txt` et les conditions d'utilisation du site.
