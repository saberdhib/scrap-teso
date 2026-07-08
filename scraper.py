#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper / miroir de site pour aciege.org (ou n'importe quel site).

Récupère « tout » à partir d'une URL de départ :
  - la page HTML de départ,
  - récursivement, toutes les pages HTML du même domaine (profondeur configurable),
  - toutes les ressources liées : images, PDF, documents, CSS, JS, archives,
  - extrait pour chaque page : le texte, les liens, les tableaux (-> CSV),
  - écrit un manifeste global (JSON) de tout ce qui a été téléchargé.

Le tout est enregistré sous un dossier de sortie en conservant l'arborescence
du site, pour pouvoir naviguer le miroir hors ligne.

Usage typique :
    python scraper.py https://aciege.org/Schema_Fra.html
    python scraper.py https://aciege.org/Schema_Fra.html -o mirror_aciege --depth 3
    python scraper.py https://aciege.org/Schema_Fra.html --same-path-only

Dépendances : requests, beautifulsoup4, lxml  (voir requirements.txt)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag, unquote

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.stderr.write(
        "Dépendances manquantes. Installez-les avec :\n"
        "    pip install -r requirements.txt\n"
        "ou :\n"
        "    pip install requests beautifulsoup4 lxml\n"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# En-têtes façon navigateur — évite les blocages anti-bot basiques (403).
# ---------------------------------------------------------------------------
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
}

# Extensions considérées comme des « ressources » (téléchargées mais non explorées).
ASSET_EXT = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico",
    ".css", ".js", ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".webm",
    ".txt", ".csv", ".xml", ".json", ".dwg", ".dxf",
}
HTML_EXT = {".html", ".htm", ".xhtml", ".php", ".asp", ".aspx", ".jsp", ""}


def eprint(*a, **k):
    print(*a, file=sys.stderr, **k)


def safe_path(base_dir: str, url: str) -> str:
    """Transforme une URL en chemin de fichier local sûr, sous base_dir."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if not path or path.endswith("/"):
        path = path + "index.html"
    # racine « / » -> /index.html
    if path == "/index.html" and not parsed.path.endswith("/index.html"):
        pass
    # Nettoyage des segments dangereux.
    segments = [s for s in path.split("/") if s not in ("", ".", "..")]
    local = os.path.join(base_dir, parsed.netloc, *segments)
    # Ajoute la query dans le nom de fichier pour éviter les collisions.
    if parsed.query:
        q = re.sub(r"[^A-Za-z0-9._-]", "_", parsed.query)[:100]
        local = f"{local}__{q}"
    # Si pas d'extension et ça ressemble à du HTML -> ajoute .html
    root, ext = os.path.splitext(local)
    if ext == "":
        local = local + ".html"
    return local


def is_same_scope(url: str, root: str, same_path_only: bool) -> bool:
    """L'URL est-elle dans le périmètre d'exploration ?"""
    pu, pr = urlparse(url), urlparse(root)
    if pu.netloc != pr.netloc:
        return False
    if same_path_only:
        base = pr.path.rsplit("/", 1)[0] + "/"
        return pu.path.startswith(base)
    return True


def classify(url: str) -> str:
    """Retourne 'html', 'asset' ou 'skip' selon l'extension."""
    path = urlparse(url).path.lower()
    ext = os.path.splitext(path)[1]
    if ext in HTML_EXT:
        return "html"
    if ext in ASSET_EXT:
        return "asset"
    return "asset"  # par défaut on télécharge, sans explorer


def extract_tables(soup: BeautifulSoup, page_url: str, out_dir: str) -> list[str]:
    """Exporte chaque <table> de la page en CSV. Retourne les chemins créés."""
    created = []
    tables = soup.find_all("table")
    if not tables:
        return created
    tables_dir = os.path.join(out_dir, "_tables")
    os.makedirs(tables_dir, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", urlparse(page_url).path.strip("/")) or "index"
    for i, table in enumerate(tables):
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            rows.append([c.get_text(strip=True) for c in cells])
        if not rows:
            continue
        fp = os.path.join(tables_dir, f"{stem}__table{i + 1}.csv")
        with open(fp, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        created.append(fp)
    return created


def scrape(start_url: str, out_dir: str, max_depth: int, delay: float,
           same_path_only: bool, max_pages: int) -> None:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    os.makedirs(out_dir, exist_ok=True)
    manifest = {
        "start_url": start_url,
        "pages": [],       # pages HTML explorées
        "assets": [],      # ressources téléchargées
        "errors": [],      # échecs
    }
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    pages_done = 0

    while queue:
        url, depth = queue.popleft()
        url, _ = urldefrag(url)
        if url in seen:
            continue
        seen.add(url)

        kind = classify(url)
        try:
            resp = session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            eprint(f"[ERREUR] {url} -> {e}")
            manifest["errors"].append({"url": url, "error": str(e)})
            continue

        local = safe_path(out_dir, resp.url)
        os.makedirs(os.path.dirname(local), exist_ok=True)

        ctype = resp.headers.get("Content-Type", "")
        is_html = kind == "html" or "text/html" in ctype

        if is_html:
            with open(local, "wb") as f:
                f.write(resp.content)
            soup = BeautifulSoup(resp.content, "lxml")

            # Texte brut de la page.
            with open(local + ".txt", "w", encoding="utf-8") as f:
                f.write(soup.get_text("\n", strip=True))

            # Tableaux -> CSV.
            tables = extract_tables(soup, resp.url, out_dir)

            # Collecte des liens/ressources.
            found_links, found_assets = [], []
            attr_map = [("a", "href"), ("link", "href"), ("script", "src"),
                        ("img", "src"), ("img", "data-src"), ("source", "src"),
                        ("iframe", "src"), ("embed", "src"), ("object", "data")]
            for tag, attr in attr_map:
                for el in soup.find_all(tag):
                    raw = el.get(attr)
                    if not raw or raw.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
                        continue
                    absu = urljoin(resp.url, raw)
                    absu, _ = urldefrag(absu)
                    if classify(absu) == "html" and tag == "a":
                        found_links.append(absu)
                    else:
                        found_assets.append(absu)

            manifest["pages"].append({
                "url": resp.url,
                "file": os.path.relpath(local, out_dir),
                "depth": depth,
                "title": (soup.title.get_text(strip=True) if soup.title else ""),
                "n_links": len(set(found_links)),
                "n_assets": len(set(found_assets)),
                "tables_csv": [os.path.relpath(t, out_dir) for t in tables],
            })
            pages_done += 1
            eprint(f"[PAGE {pages_done}] (d{depth}) {resp.url}  "
                   f"({len(set(found_links))} liens, {len(set(found_assets))} ressources)")

            # File d'attente : ressources (toujours) + pages (si profondeur ok).
            for a in set(found_assets):
                if is_same_scope(a, start_url, same_path_only) and a not in seen:
                    queue.append((a, depth + 1))
            if depth < max_depth:
                for l in set(found_links):
                    if is_same_scope(l, start_url, same_path_only) and l not in seen:
                        queue.append((l, depth + 1))
        else:
            # Ressource binaire : on écrit tel quel.
            with open(local, "wb") as f:
                f.write(resp.content)
            manifest["assets"].append({
                "url": resp.url,
                "file": os.path.relpath(local, out_dir),
                "content_type": ctype,
                "bytes": len(resp.content),
            })
            eprint(f"[ASSET] {resp.url}  ({len(resp.content)} o, {ctype})")

        if max_pages and pages_done >= max_pages:
            eprint(f"[STOP] Limite de {max_pages} pages atteinte.")
            break
        if delay:
            time.sleep(delay)

    # Manifeste final.
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    eprint("\n===== TERMINÉ =====")
    eprint(f"Pages HTML : {len(manifest['pages'])}")
    eprint(f"Ressources : {len(manifest['assets'])}")
    eprint(f"Erreurs    : {len(manifest['errors'])}")
    eprint(f"Sortie     : {os.path.abspath(out_dir)}")
    eprint(f"Manifeste  : {os.path.join(os.path.abspath(out_dir), 'manifest.json')}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Scraper/miroir récursif d'un site web (par défaut aciege.org/Schema_Fra.html).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("url", nargs="?", default="https://aciege.org/Schema_Fra.html",
                   help="URL de départ à scraper.")
    p.add_argument("-o", "--output", default="mirror",
                   help="Dossier de sortie.")
    p.add_argument("-d", "--depth", type=int, default=2,
                   help="Profondeur maximale d'exploration des pages HTML.")
    p.add_argument("--delay", type=float, default=0.5,
                   help="Pause (secondes) entre deux requêtes, pour rester poli.")
    p.add_argument("--same-path-only", action="store_true",
                   help="N'explorer que les URL sous le dossier de la page de départ.")
    p.add_argument("--max-pages", type=int, default=0,
                   help="Nombre maximum de pages HTML (0 = illimité).")
    args = p.parse_args()

    scrape(args.url, args.output, args.depth, args.delay,
           args.same_path_only, args.max_pages)


if __name__ == "__main__":
    main()
