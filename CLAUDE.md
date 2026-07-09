# CLAUDE.md — contexte du projet pour les sessions Claude

## Objectif

Extraire le Thésaurus du Management ACIEGE (<https://aciege.org/Schema_Fra.html>),
le structurer en classification exploitable, puis vérifier/corriger la
classification d'un corpus d'environ 50 000 thèses (PDF).

## Architecture

```
scrape_aciege.py   scrape des schémas (index + Schm/Fra/FRA_xxx.html)  -> data/
scrape_listes.py   scrape des listes CS/Fra (relations TG/TS, synonymes) -> data/
build_thesaurus.py fusion -> thesaurus/ (concepts_flat.csv, JSON, SKOS)
pipeline/          stack Docker : PostgreSQL + MinIO + Airflow + Streamlit
```

- Le **fichier pivot** est `thesaurus/concepts_flat.csv` : 2 484 concepts en
  4 niveaux (5 catégories > 23 groupes > 68 sous-groupes > 2 388 termes),
  avec synonymes, définitions, sources et hiérarchie fine entre termes.
- Le pipeline (`pipeline/docker-compose.yml`) vérifie la classification des
  thèses : extraction progressive du texte (max 5 pages, OCR Tesseract si
  scan), candidats par embeddings (BAAI/bge-m3), verdict par règles +
  arbitrage LLM Hugging Face, revue humaine via Streamlit (3 pages :
  Thésaurus, Suivi, Revue).

## Contraintes d'environnement — IMPORTANT

- **Aucun accès réseau sortant** depuis l'environnement Claude Code web (le
  proxy d'egress répond 403 sur tout domaine externe, y compris aciege.org,
  huggingface.co et la Wayback Machine). Seuls PyPI/npm et GitHub passent.
- **Tout scraping ou téléchargement de modèle doit donc passer par le
  workflow GitHub Actions** `.github/workflows/scrape.yml` (déclenché par
  push sur la branche, hors `data/`, `thesaurus/`, `pipeline/`, `*.md`)
  ou être exécuté par l'utilisateur en local.
- Docker n'est pas exécutable dans la sandbox : la stack `pipeline/` se teste
  chez l'utilisateur ; ne valider ici que la logique pure (compile, unités,
  Streamlit lancé localement avec THESAURUS_CSV pointé sur thesaurus/).

## Conventions git

- Branche de travail : `claude/web-scraping-1qouc5` (ne pas pousser ailleurs).
- Le workflow Actions committe sur la même branche après chaque run (le
  `.xlsx` change à chaque exécution à cause de ses horodatages internes) :
  faire `git pull --rebase origin claude/web-scraping-1qouc5` avant tout push.
- Ne pas committer de secrets ; `pipeline/.env` est local (`.env.example`
  fait référence).

## Pièges connus des données

- L'index du site contient des lignes d'espacement vides (th sans code) :
  déjà filtrées dans `parse_index` et `build_thesaurus`.
- Les pages Liste contiennent ~1 291 blocs sans code : ce sont les renvois de
  non-descripteurs (« Entrepreneur → voir CHEF D'ENTREPRISE »), volontairement
  ignorés car couverts par les synonymes « Employé Pour ».
- 530 termes n'existent que dans les listes (langues, géographie, secteurs…)
  et n'ont pas de définition ; 871 termes sans définition au total.
- Encodage : le site ment parfois sur l'encodage — `get_soup` force
  `apparent_encoding`.
- Les « Claude » présents dans `thesaurus/` et `data/` sont des auteurs cités
  (Jean-Claude Colli, Claude Marcel…) : ne pas les « nettoyer ».

## Commandes utiles

```bash
python scrape_aciege.py --limit 3      # test scrape (nécessite réseau)
python scrape_listes.py --limit 2      # test listes (nécessite réseau)
python build_thesaurus.py              # reconstruire thesaurus/ (hors ligne OK)
cd pipeline && docker compose up -d --build   # stack complète (chez l'utilisateur)
```
