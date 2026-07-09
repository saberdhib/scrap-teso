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
