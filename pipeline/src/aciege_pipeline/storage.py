# -*- coding: utf-8 -*-
"""Accès MinIO (stockage objet S3)."""

import io

from minio import Minio

from . import config


def client() -> Minio:
    return Minio(
        config.MINIO_ENDPOINT,
        access_key=config.MINIO_ACCESS_KEY,
        secret_key=config.MINIO_SECRET_KEY,
        secure=config.MINIO_SECURE,
    )


def lire_objet(bucket: str, key: str) -> bytes:
    c = client()
    resp = c.get_object(bucket, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def ecrire_objet(bucket: str, key: str, data: bytes,
                 content_type: str = "application/octet-stream") -> None:
    client().put_object(bucket, key, io.BytesIO(data), len(data),
                        content_type=content_type)


def lister_pdfs(bucket: str) -> list[str]:
    return [o.object_name for o in client().list_objects(bucket, recursive=True)
            if o.object_name.lower().endswith(".pdf")]
