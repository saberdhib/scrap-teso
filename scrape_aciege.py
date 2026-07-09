#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper sur mesure pour le Thésaurus du Management ACIEGE
(https://aciege.org/Schema_Fra.html).

Produit exactement les 2 tableaux attendus :

TABLE 1 — index (une ligne par sous-groupe) :
    catégorie | thème | groupe numérologie | groupe titre |
    sous-groupe numérologie | sous-groupe | lien sous-groupe schéma | lien sous-groupe liste

TABLE 2 — termes (une ligne par terme d'un schéma) :
    sous-groupe numérologie | sous-groupe | lien sous-groupe |
    lien sous-sous-groupe | code sous-sous-groupe | titre | définition | source

Fonctionnement :
  1. Télécharge et parse Schema_Fra.html : la hiérarchie est portée par les
     classes CSS ThCol1Fra/Col1Fra (catégorie), ThCol2Fra/Col2Fra (groupe),
     ThCol3Fra + td.Fra (sous-groupe) avec liens "Schéma" (Schm/Fra/FRA_xxx.html)
     et "Liste" (CS/Fra/FRA_xxx.html).
  2. Pour chaque sous-groupe ayant un schéma, télécharge Schm/Fra/FRA_xxx.html
     et parse les <area> de la <map> : href -> lien/code du terme,
     title -> "TITRE\\n définition ... Source : ...".
  3. Exporte : table1.csv, table2.csv (utf-8-sig, séparateur ';' pour Excel FR),
     aciege.xlsx (2 feuilles) si openpyxl est installé, et aciege.json.

Usage :
    python scrape_aciege.py                     # tout, sortie dans ./data
    python scrape_aciege.py -o data --delay 0.3
    python scrape_aciege.py --limit 3           # test rapide : 3 schémas

Dépendances : requests, beautifulsoup4, lxml (+ openpyxl pour le .xlsx)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.stderr.write("pip install -r requirements.txt\n")
    sys.exit(1)

BASE_URL = "https://aciege.org/Schema_Fra.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

TABLE1_COLS = [
    "categorie", "theme",
    "groupe_numerologie", "groupe_titre",
    "sous_groupe_numerologie", "sous_groupe",
    "lien_sous_groupe_schema", "lien_sous_groupe_liste",
]
TABLE2_COLS = [
    "sous_groupe_numerologie", "sous_groupe", "lien_sous_groupe",
    "lien_sous_sous_groupe", "code_sous_sous_groupe",
    "titre", "definition", "source",
]


def eprint(*a, **k):
    print(*a, file=sys.stderr, **k)


def clean(text: str) -> str:
    """Normalise espaces insécables et blancs superflus."""
    if text is None:
        return ""
    text = text.replace("\xa0", " ").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    # Sites anciens : l'en-tête ment parfois sur l'encodage.
    if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
        resp.encoding = resp.apparent_encoding or "utf-8"
    return BeautifulSoup(resp.text, "lxml")


# ---------------------------------------------------------------------------
# Étape 1 — index Schema_Fra.html -> TABLE 1
# ---------------------------------------------------------------------------
def parse_index(soup: BeautifulSoup, base_url: str) -> list[dict]:
    rows = []
    cat_num = cat_title = grp_num = grp_title = ""
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        if th is None:
            continue
        th_class = " ".join(th.get("class", []))
        tds = tr.find_all("td")

        if "ThCol1" in th_class:                       # catégorie (1 chiffre)
            cat_num = clean(th.get_text())
            cat_title = clean(tds[0].get_text()) if tds else ""
            grp_num = grp_title = ""
        elif "ThCol2" in th_class:                     # groupe (2 chiffres)
            grp_num = clean(th.get_text())
            grp_title = clean(tds[0].get_text()) if tds else ""
        elif "ThCol3" in th_class:                     # sous-groupe (3 chiffres)
            sg_num = clean(th.get_text())
            sg_name = clean(tds[0].get_text()) if tds else ""
            if not sg_num and not sg_name:             # ligne d'espacement vide
                continue
            schema_link = liste_link = ""
            for a in tr.find_all("a", href=True):
                href = a["href"]
                absu = urljoin(base_url, href)
                label = clean(a.get_text()).lower()
                if "/schm/" in absu.lower() or "sch" in label:
                    schema_link = absu
                elif "/cs/" in absu.lower() or "liste" in label:
                    liste_link = absu
            rows.append({
                "categorie": cat_num,
                "theme": cat_title,
                "groupe_numerologie": grp_num,
                "groupe_titre": grp_title,
                "sous_groupe_numerologie": sg_num,
                "sous_groupe": sg_name,
                "lien_sous_groupe_schema": schema_link,
                "lien_sous_groupe_liste": liste_link,
            })
    return rows


# ---------------------------------------------------------------------------
# Étape 2 — pages Schm/Fra/FRA_xxx.html -> TABLE 2
# ---------------------------------------------------------------------------
def split_title_attr(title_attr: str) -> tuple[str, str, str]:
    """Découpe l'attribut title d'une <area> en (titre, définition, sources)."""
    raw = (title_attr or "").replace("\r", "").strip()
    if not raw:
        return "", "", ""
    lines = raw.split("\n")
    titre = clean(lines[0])
    definition = clean("\n".join(lines[1:]).replace("\n", " "))
    # Toutes les mentions « Source : ... » (jusqu'à la mention suivante ou la fin).
    sources = re.findall(
        r"Source\s*:\s*(.+?)(?=(?:D[ée]f(?:inition)?\s*\d*\s*:)|(?:Source\s*:)|$)",
        definition, flags=re.IGNORECASE | re.DOTALL,
    )
    source = " | ".join(clean(s).rstrip(" .»") + "." for s in sources if clean(s))
    if not source:
        # Variante sans préfixe : citation entre parenthèses en fin de définition,
        # ex. « (SILEM A.. -Lexique d'économie. -3ème éd. -Dalloz, 1989.) »
        m = re.search(r"\(([^()]{15,})\)\s*$", definition)
        if m:
            source = clean(m.group(1))
    return titre, definition, source


def parse_schema_page(soup: BeautifulSoup, page_url: str,
                      sg_num: str, sg_name: str) -> list[dict]:
    terms, seen = [], set()
    for area in soup.find_all("area"):
        href = area.get("href")
        if not href:
            continue
        absu = urljoin(page_url, href)
        if absu in seen:
            continue
        seen.add(absu)
        # .../Dct/Fra/Fra_111_48.html -> code "48"
        m = re.search(r"[/_](?:Fra|Eng|Esp)_(\d+)_(\d+)\.html?$", absu, re.IGNORECASE)
        code = m.group(2) if m else os.path.splitext(os.path.basename(absu))[0]
        titre, definition, source = split_title_attr(area.get("title", ""))
        terms.append({
            "sous_groupe_numerologie": sg_num,
            "sous_groupe": sg_name,
            "lien_sous_groupe": page_url,
            "lien_sous_sous_groupe": absu,
            "code_sous_sous_groupe": code,
            "titre": titre,
            "definition": definition,
            "source": source,
        })
    return terms


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
def write_csv(path: str, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_xlsx(path: str, t1: list[dict], t2: list[dict]) -> bool:
    try:
        from openpyxl import Workbook
    except ImportError:
        return False
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Index sous-groupes"
    ws1.append(TABLE1_COLS)
    for r in t1:
        ws1.append([r.get(c, "") for c in TABLE1_COLS])
    ws2 = wb.create_sheet("Termes et définitions")
    ws2.append(TABLE2_COLS)
    for r in t2:
        ws2.append([r.get(c, "") for c in TABLE2_COLS])
    wb.save(path)
    return True


def main() -> None:
    p = argparse.ArgumentParser(
        description="Scrape le thésaurus ACIEGE en 2 tableaux (index + termes/définitions).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("url", nargs="?", default=BASE_URL, help="URL de la page index.")
    p.add_argument("-o", "--output", default="data", help="Dossier de sortie.")
    p.add_argument("--delay", type=float, default=0.3, help="Pause (s) entre requêtes.")
    p.add_argument("--limit", type=int, default=0,
                   help="Ne traiter que N schémas (0 = tous) — pratique pour tester.")
    args = p.parse_args()

    os.makedirs(args.output, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    eprint(f"[1/2] Index : {args.url}")
    table1 = parse_index(get_soup(session, args.url), args.url)
    eprint(f"      {len(table1)} sous-groupes trouvés.")
    if not table1:
        eprint("ERREUR : aucun sous-groupe détecté — structure inattendue ?")
        sys.exit(2)

    table2, errors = [], []
    todo = [r for r in table1 if r["lien_sous_groupe_schema"]]
    if args.limit:
        todo = todo[: args.limit]
    eprint(f"[2/2] {len(todo)} pages de schéma à parcourir…")
    for i, row in enumerate(todo, 1):
        url = row["lien_sous_groupe_schema"]
        try:
            soup = get_soup(session, url)
            terms = parse_schema_page(
                soup, url, row["sous_groupe_numerologie"], row["sous_groupe"])
            table2.extend(terms)
            eprint(f"  [{i}/{len(todo)}] {row['sous_groupe_numerologie']} "
                   f"{row['sous_groupe']} -> {len(terms)} termes")
        except Exception as e:  # noqa: BLE001
            eprint(f"  [{i}/{len(todo)}] ERREUR {url} : {e}")
            errors.append({"url": url, "error": str(e)})
        time.sleep(args.delay)

    out = args.output
    write_csv(os.path.join(out, "table1_index.csv"), table1, TABLE1_COLS)
    write_csv(os.path.join(out, "table2_termes.csv"), table2, TABLE2_COLS)
    with open(os.path.join(out, "aciege.json"), "w", encoding="utf-8") as f:
        json.dump({"index": table1, "termes": table2, "erreurs": errors},
                  f, ensure_ascii=False, indent=2)
    has_xlsx = write_xlsx(os.path.join(out, "aciege.xlsx"), table1, table2)

    eprint("\n===== TERMINÉ =====")
    eprint(f"Table 1 (index)  : {len(table1)} lignes -> {out}/table1_index.csv")
    eprint(f"Table 2 (termes) : {len(table2)} lignes -> {out}/table2_termes.csv")
    eprint(f"JSON             : {out}/aciege.json")
    eprint(f"Excel            : {out}/aciege.xlsx" if has_xlsx
           else "Excel            : non généré (pip install openpyxl)")
    if errors:
        eprint(f"Erreurs          : {len(errors)} (détail dans aciege.json)")


if __name__ == "__main__":
    main()
