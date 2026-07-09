# BESOINS — ce qu'il me faut de toi pour lancer le pipeline

Le pipeline (dossier `pipeline/`) est prêt : PostgreSQL + MinIO + Airflow +
interface de revue. Voici exactement ce que tu dois fournir, dans l'ordre.

## 1. Clé Hugging Face 🔑 (la seule clé nécessaire)

Un **token de lecture** (`hf_…`) créé sur <https://huggingface.co/settings/tokens>
(type « Read » suffit ; coche l'accès *Inference API / Providers*).
À mettre dans `pipeline/.env` → `HF_TOKEN=hf_…`

Il sert à deux choses :

| Usage | Modèle par défaut | Alternative |
|---|---|---|
| **Embeddings** (candidats) — tourne en local, le token sert juste au téléchargement | `BAAI/bge-m3` (multilingue, excellent en FR) | `intfloat/multilingual-e5-large` |
| **Arbitrage LLM** (cas incertains) — via l'Inference API, rien à installer | `mistralai/Mistral-7B-Instruct-v0.3` | `Qwen/Qwen2.5-72B-Instruct` (meilleur, plus lent) — ou n'importe quel modèle dispo chez les Inference Providers HF |

⚠️ Certains modèles (Mistral, Llama) sont « gated » : clique « Agree and
access » sur leur page HF une fois, avec le compte du token.

**OCR : aucune clé nécessaire** — Tesseract (fra+eng) est intégré à l'image
Docker et ne se déclenche que sur les pages scannées sans couche texte.

## 2. Les 10 000 fichiers + leur classification actuelle 📄

- **Les PDF** : à copier dans le bucket MinIO `theses` (commande dans
  `pipeline/README.md`). Sous-dossiers acceptés.
- **Le manifeste** `manifest.csv` (séparateur `;`, UTF-8), une ligne par thèse :

```csv
fichier;code_actuel;titre
dossier1/these_0001.pdf;124;Optimisation de la force de vente…
dossier1/these_0002.pdf;111_48;(titre optionnel)
these_0003.pdf;331;
```

- `fichier` = chemin exact dans le bucket.
- `code_actuel` = code ACIEGE (`124` = sous-groupe, ou `124_85` = terme fin,
  les deux sont acceptés — le verdict se fait au niveau sous-groupe).
- `titre` = optionnel mais améliore la classification.

❓ **Question importante** : ta classification actuelle est-elle déjà en codes
ACIEGE ? Si c'est un autre référentiel (tes propres catégories), il me faut la
**table de correspondance** (ton code → code ACIEGE), ou dis-le-moi et
j'ajoute une étape de mapping.

## 3. Une machine avec Docker 🖥

- Docker + Docker Compose, ~10 Go de disque (images + modèle d'embeddings).
- **CPU suffit** (~30-60 min pour les 10 000 en embeddings). Un GPU NVIDIA
  accélère mais n'est pas requis — le LLM tourne côté API HF, pas en local.
- Ports libres : 8080 (Airflow), 9000/9001 (MinIO), 8501 (revue), 5432 (PG).

## 4. Deux réglages à confirmer (des défauts raisonnables sont en place)

1. **Pages lues** : 5 max, arrêt anticipé dès que résumé/mots-clés trouvés
   (`MAX_PAGES` dans `.env`).
2. **Sévérité** : un code actuel classé 2e-3e proche du 1er → « incertain »
   (arbitré par le LLM) plutôt que « à reclasser » (`MARGE_INCERTITUDE=0.93`).

## Lancement (résumé)

```bash
cd pipeline
cp .env.example .env   # + HF_TOKEN et mots de passe
docker compose up -d --build
# charger PDF + manifest.csv dans MinIO (cf. pipeline/README.md)
# Airflow http://localhost:8080 -> déclencher aciege_verification_theses
# Résultats : rapport CSV dans MinIO + revue sur http://localhost:8501
```

## Ce que tu obtiens à la fin

Pour chaque thèse : `verdict` (**bien_classe** / **a_reclasser** /
**incertain** / **code_actuel_invalide**), le **code suggéré** avec son
libellé et score, les 10 candidats, et une **justification** — dans un CSV,
dans PostgreSQL, et dans l'interface de revue où tu valides en un clic.
