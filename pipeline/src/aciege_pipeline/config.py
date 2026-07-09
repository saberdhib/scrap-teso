# -*- coding: utf-8 -*-
"""Configuration du pipeline — tout vient des variables d'environnement."""

import os


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


DB = dict(
    host=env("APP_DB_HOST", "localhost"),
    port=int(env("APP_DB_PORT", "5432")),
    dbname=env("APP_DB_NAME", "aciege"),
    user=env("APP_DB_USER", "aciege"),
    password=env("APP_DB_PASSWORD", "aciege"),
)

MINIO_ENDPOINT = env("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = env("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = env("MINIO_SECRET_KEY", "minio12345")
MINIO_SECURE = env("MINIO_SECURE", "false").lower() == "true"
BUCKET_THESES = env("MINIO_BUCKET_THESES", "theses")
BUCKET_RAPPORTS = env("MINIO_BUCKET_RAPPORTS", "rapports")
MANIFEST_KEY = env("MANIFEST_KEY", "manifest.csv")

THESAURUS_CSV = env("THESAURUS_CSV", "/opt/thesaurus/concepts_flat.csv")

HF_TOKEN = env("HF_TOKEN")
EMBED_MODEL = env("EMBED_MODEL", "BAAI/bge-m3")
LLM_MODEL = env("LLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")

MAX_PAGES = int(env("MAX_PAGES", "5"))
MIN_CHARS_INFORMATIF = int(env("MIN_CHARS_INFORMATIF", "1200"))
BATCH_SIZE = int(env("BATCH_SIZE", "1000"))
TOP_K = int(env("TOP_K", "10"))
# Un code actuel classé 2e/3e avec un score >= MARGE * top1 => « incertain »
MARGE_INCERTITUDE = float(env("MARGE_INCERTITUDE", "0.93"))
