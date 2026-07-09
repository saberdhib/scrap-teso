# -*- coding: utf-8 -*-
"""Extraction de texte « progressive » d'un PDF de thèse.

Le pipeline lit les pages une à une (au plus MAX_PAGES, 5 par défaut) et
s'arrête dès que le texte accumulé est jugé « informatif » : assez long ET
contenant des indices de contenu utile (résumé, mots-clés, introduction…).
Si une page n'a pas de couche texte (scan), elle passe par l'OCR Tesseract.
"""

from __future__ import annotations

import re

from . import config

MOTS_INDICES = re.compile(
    r"\b(r[ée]sum[ée]|abstract|mots[- ]cl[ée]s|keywords|introduction|"
    r"probl[ée]matique|sommaire|synth[èe]se)\b",
    re.IGNORECASE,
)


def _ocr_page(page) -> str:
    """OCR d'une page PyMuPDF via Tesseract (fra+eng)."""
    import pytesseract
    from PIL import Image

    pix = page.get_pixmap(dpi=220)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img, lang="fra+eng")


def est_informatif(texte: str, min_chars: int) -> bool:
    return len(texte) >= min_chars and bool(MOTS_INDICES.search(texte))


def extraire(pdf_bytes: bytes,
             max_pages: int | None = None,
             min_chars: int | None = None) -> tuple[str, int, bool]:
    """Retourne (texte, pages_lues, ocr_utilise).

    S'arrête avant max_pages dès que le texte est informatif ; continue
    au-delà du seuil de longueur seule tant qu'aucun indice (résumé,
    mots-clés…) n'est trouvé, dans la limite de max_pages.
    """
    import fitz  # PyMuPDF

    max_pages = max_pages or config.MAX_PAGES
    min_chars = min_chars or config.MIN_CHARS_INFORMATIF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    morceaux: list[str] = []
    ocr_utilise = False
    pages_lues = 0
    try:
        for page in doc:
            if pages_lues >= max_pages:
                break
            texte_page = page.get_text("text") or ""
            if len(texte_page.strip()) < 80:          # page scannée -> OCR
                try:
                    texte_page = _ocr_page(page)
                    ocr_utilise = True
                except Exception:                     # tesseract absent, image illisible…
                    texte_page = texte_page or ""
            morceaux.append(texte_page)
            pages_lues += 1
            if est_informatif("\n".join(morceaux), min_chars):
                break
    finally:
        doc.close()

    texte = re.sub(r"\n{3,}", "\n\n", "\n".join(morceaux)).strip()
    return texte, pages_lues, ocr_utilise
