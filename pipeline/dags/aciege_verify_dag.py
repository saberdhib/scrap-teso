# -*- coding: utf-8 -*-
"""DAG Airflow : vérification de la classification des thèses (ACIEGE).

    manifeste -> extraction texte (5 pages / OCR) -> classification -> rapport

Déclenchement manuel (ou relance) : chaque tâche ne traite que les thèses au
statut attendu, donc le DAG est rejouable et reprend où il s'était arrêté.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime

from airflow.decorators import dag, task

log = logging.getLogger(__name__)


@dag(
    dag_id="aciege_verification_theses",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["aciege", "classification"],
)
def aciege_verification_theses():

    @task
    def enregistrer_manifeste() -> int:
        """Lit manifest.csv du bucket (fichier;code_actuel[;titre]) et upsert en base."""
        from aciege_pipeline import config, db, storage

        data = storage.lire_objet(config.BUCKET_THESES, config.MANIFEST_KEY)
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")),
                                   delimiter=";"))
        pdfs = set(storage.lister_pdfs(config.BUCKET_THESES))
        n, absents = 0, []
        with db.conn() as c:
            cur = c.cursor()
            for r in rows:
                fichier = (r.get("fichier") or "").strip()
                if not fichier:
                    continue
                if fichier not in pdfs:
                    absents.append(fichier)
                    continue
                db.upsert_these(cur, fichier, (r.get("code_actuel") or "").strip(),
                                (r.get("titre") or "").strip())
                n += 1
        if absents:
            log.warning("%d fichiers du manifeste absents du bucket, ex.: %s",
                        len(absents), absents[:5])
        log.info("%d thèses enregistrées.", n)
        return n

    @task
    def extraire_textes(_: int) -> int:
        """Extraction progressive (max 5 pages, OCR si scan) des thèses en attente."""
        from aciege_pipeline import config, db, ocr, storage

        n_ok = n_err = 0
        with db.conn() as c:
            cur = c.cursor()
            lots = db.fetch_par_statut(cur, "en_attente", config.BATCH_SIZE)
            for these_id, objet, _titre, _code, _texte in lots:
                try:
                    pdf = storage.lire_objet(config.BUCKET_THESES, objet)
                    texte, pages, avec_ocr = ocr.extraire(pdf)
                    if len(texte) < 200:
                        raise ValueError(f"texte trop court ({len(texte)} car.)")
                    db.maj_texte(cur, these_id, texte, pages, avec_ocr)
                    n_ok += 1
                except Exception as e:  # noqa: BLE001
                    db.maj_erreur(cur, these_id, "erreur_texte", str(e))
                    n_err += 1
        log.info("Extraction : %d ok, %d erreurs.", n_ok, n_err)
        return n_ok

    @task
    def classifier(_: int) -> int:
        """Candidats par embeddings + verdict (règles, LLM si incertain)."""
        from aciege_pipeline import classify, config, db

        clf = classify.Classifieur()
        libelles = classify.libelles_sous_groupes()
        n = 0
        with db.conn() as c:
            cur = c.cursor()
            lots = db.fetch_par_statut(cur, "texte_ok", config.BATCH_SIZE)
            for these_id, _objet, titre, code_actuel, texte in lots:
                try:
                    contenu = (titre + "\n\n" if titre else "") + (texte or "")
                    res = classify.verifier(contenu, code_actuel or "", clf, libelles)
                    db.inserer_resultat(cur, these_id, res)
                    n += 1
                except Exception as e:  # noqa: BLE001
                    db.maj_erreur(cur, these_id, "erreur_classif", str(e))
        log.info("Classification : %d thèses.", n)
        return n

    @task
    def rapport(_: int) -> str:
        """Exporte le rapport CSV vers MinIO (bucket rapports)."""
        from aciege_pipeline import config, db, storage

        with db.conn() as c:
            cur = c.cursor()
            cur.execute("""
                SELECT t.objet_minio, t.titre, t.code_actuel,
                       r.code_suggere, r.libelle_suggere, r.score,
                       r.verdict, r.confiance, r.justification,
                       t.pages_lues, t.ocr_utilise
                FROM theses t
                JOIN LATERAL (SELECT * FROM resultats r
                              WHERE r.these_id = t.id
                              ORDER BY r.cree_le DESC LIMIT 1) r ON TRUE
                ORDER BY r.verdict, r.score DESC
            """)
            lignes = cur.fetchall()
            cols = ["fichier", "titre", "code_actuel", "code_suggere",
                    "libelle_suggere", "score", "verdict", "confiance",
                    "justification", "pages_lues", "ocr"]
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(cols)
        w.writerows(lignes)
        key = f"rapport_{datetime.now():%Y%m%d_%H%M%S}.csv"
        storage.ecrire_objet(config.BUCKET_RAPPORTS, key,
                             ("﻿" + buf.getvalue()).encode("utf-8"),
                             content_type="text/csv")
        log.info("Rapport : %d lignes -> %s/%s", len(lignes),
                 config.BUCKET_RAPPORTS, key)
        return key

    rapport(classifier(extraire_textes(enregistrer_manifeste())))


aciege_verification_theses()
