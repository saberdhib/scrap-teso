# -*- coding: utf-8 -*-
"""Accès PostgreSQL."""

import json
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from . import config


@contextmanager
def conn():
    c = psycopg2.connect(**config.DB)
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def upsert_these(cur, objet_minio: str, code_actuel: str, titre: str = "") -> None:
    cur.execute(
        """
        INSERT INTO theses (objet_minio, code_actuel, titre)
        VALUES (%s, %s, %s)
        ON CONFLICT (objet_minio)
        DO UPDATE SET code_actuel = EXCLUDED.code_actuel,
                      titre = COALESCE(NULLIF(EXCLUDED.titre, ''), theses.titre),
                      maj_le = now()
        """,
        (objet_minio, code_actuel, titre),
    )


def fetch_par_statut(cur, statut: str, limit: int):
    cur.execute(
        "SELECT id, objet_minio, titre, code_actuel, texte FROM theses "
        "WHERE statut = %s ORDER BY id LIMIT %s",
        (statut, limit),
    )
    return cur.fetchall()


def maj_texte(cur, these_id: int, texte: str, pages: int, ocr: bool) -> None:
    cur.execute(
        "UPDATE theses SET texte=%s, pages_lues=%s, ocr_utilise=%s, "
        "statut='texte_ok', erreur=NULL, maj_le=now() WHERE id=%s",
        (texte, pages, ocr, these_id),
    )


def maj_erreur(cur, these_id: int, statut: str, erreur: str) -> None:
    cur.execute(
        "UPDATE theses SET statut=%s, erreur=%s, maj_le=now() WHERE id=%s",
        (statut, erreur[:2000], these_id),
    )


def inserer_resultat(cur, these_id: int, res: dict) -> None:
    cur.execute(
        """
        INSERT INTO resultats (these_id, code_suggere, libelle_suggere, score,
                               verdict, confiance, candidats, justification, modele)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (these_id, res.get("code_suggere"), res.get("libelle_suggere"),
         res.get("score"), res.get("verdict"), res.get("confiance"),
         json.dumps(res.get("candidats", []), ensure_ascii=False),
         res.get("justification"), res.get("modele")),
    )
    cur.execute("UPDATE theses SET statut='classifie', maj_le=now() WHERE id=%s",
                (these_id,))
