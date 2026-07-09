-- Schéma applicatif : thèses et résultats de vérification de classification.

CREATE TABLE IF NOT EXISTS theses (
    id            SERIAL PRIMARY KEY,
    objet_minio   TEXT UNIQUE NOT NULL,          -- clé du PDF dans le bucket
    titre         TEXT,
    code_actuel   TEXT,                          -- classification actuelle (code ACIEGE)
    statut        TEXT NOT NULL DEFAULT 'en_attente',
    -- en_attente -> texte_ok | erreur_texte -> classifie | erreur_classif
    texte         TEXT,
    pages_lues    INT,
    ocr_utilise   BOOLEAN DEFAULT FALSE,
    erreur        TEXT,
    cree_le       TIMESTAMPTZ NOT NULL DEFAULT now(),
    maj_le        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS resultats (
    id                SERIAL PRIMARY KEY,
    these_id          INT NOT NULL REFERENCES theses(id) ON DELETE CASCADE,
    code_suggere      TEXT,
    libelle_suggere   TEXT,
    score             REAL,                      -- similarité du meilleur candidat
    verdict           TEXT,                      -- bien_classe | a_reclasser | incertain | code_actuel_invalide
    confiance         REAL,
    candidats         JSONB,                     -- top-k [{code, libelle, score}]
    justification     TEXT,                      -- explication (LLM ou règle)
    modele            TEXT,
    decision_humaine  TEXT,                      -- rempli via l'UI de revue
    cree_le           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_theses_statut ON theses(statut);
CREATE INDEX IF NOT EXISTS idx_resultats_verdict ON resultats(verdict);
CREATE INDEX IF NOT EXISTS idx_resultats_these ON resultats(these_id);
