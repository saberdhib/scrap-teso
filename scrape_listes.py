#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scrape les pages « Liste » (microthésaurus) du thésaurus ACIEGE :
CS/Fra/FRA_xxx.html.

Chaque page liste les descripteurs d'un sous-groupe sous forme de blocs :
    <h1 id="FrNNNNN">NOM DU DESCRIPTEUR  <a href=".../Dct/Fra/Fra_124_85.html">124.85</a></h1>
    <table class="CdrTb">
        td.TGf  « Terme Générique »   / td.TGt   -> terme générique (BT)
        td.Descf « Descripteur »      / td.Desct -> le descripteur lui-même
        td.EPf  « Employé Pour »      / td.EPt   -> non-descripteurs = synonymes (UF)
        td.TSf  « Termes Spécifiques »/ td.TSt   -> termes spécifiques (NT)
    </table>

Sorties (dans -o, défaut data/) :
    listes.json            blocs complets par sous-groupe.
    table3_relations.csv   1 ligne par relation :
        sous_groupe;descripteur_code;descripteur;relation;cible_code;cible_libelle;cible_url
        relation ∈ {terme_generique, terme_specifique, employe_pour}

Usage :
    python scrape_listes.py                  # lit data/aciege.json pour les URLs
    python scrape_listes.py --limit 2        # test rapide
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

REL_COLS = ["sous_groupe", "descripteur_code", "descripteur",
            "relation", "cible_code", "cible_libelle", "cible_url"]
SECTION_BY_PREFIX = {"TG": "terme_generique", "TS": "terme_specifique",
                     "EP": "employe_pour", "Desc": "descripteur"}
SECTION_BY_LABEL = {"terme générique": "terme_generique",
                    "termes spécifiques": "terme_specifique",
                    "terme spécifique": "terme_specifique",
                    "employé pour": "employe_pour",
                    "descripteur": "descripteur"}


def eprint(*a, **k):
    print(*a, file=sys.stderr, **k)


def clean(s: str) -> str:
    return re.sub(r"[ \t]+", " ", (s or "").replace("\xa0", " ")).strip()


def code_from_href(href: str) -> str:
    """.../Dct/Fra/Fra_124_85.html -> 124_85 ; .../Ag_2413.html -> Ag_2413."""
    stem = os.path.splitext(os.path.basename(href or ""))[0]
    m = re.match(r"(?:Fra|Eng|Esp)_(\d+_\d+)$", stem, re.IGNORECASE)
    if m:
        return m.group(1)
    return stem


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
        resp.encoding = resp.apparent_encoding or "utf-8"
    return BeautifulSoup(resp.text, "lxml")


def extract_entries(td, page_url: str) -> list[dict]:
    """Liens d'une cellule -> [{libelle, code, url}]. Les ancres '#FrNNN' dont
    le texte ressemble à un code (124_67) complètent l'entrée précédente."""
    entries = []
    for a in td.find_all("a"):
        href = a.get("href", "")
        text = clean(a.get_text())
        if not text:
            continue
        if href.startswith("#") or not href:
            if re.fullmatch(r"\d+[_.]\d+", text) and entries:
                entries[-1]["code"] = text.replace(".", "_")
            continue
        absu = urljoin(page_url, href)
        entries.append({"libelle": text, "code": code_from_href(href), "url": absu})
    return entries


def parse_liste_page(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """Retourne les blocs descripteurs d'une page CS."""
    blocks = []
    for h1 in soup.find_all("h1", id=True):
        # Nom = texte du h1 privé du code (dernier lien, ex. « 124.85 »).
        code = ""
        for a in h1.find_all("a", href=True):
            if "/dct/" in a["href"].lower():
                code = code_from_href(a["href"])
        name = clean(re.sub(r"\d+[_.]\d+\s*$", "", h1.get_text()))
        block = {"code": code, "libelle": name, "url": "",
                 "terme_generique": [], "terme_specifique": [], "employe_pour": []}

        table = h1.find_next("table", class_="CdrTb")
        if table is not None:
            current = None
            for td in table.find_all("td"):
                classes = " ".join(td.get("class", []))
                text = clean(td.get_text()).lower()
                # Cellule-étiquette ?
                section = None
                for prefix, sec in SECTION_BY_PREFIX.items():
                    if re.match(rf"{prefix}[ft]\b", classes):
                        section = sec
                        current = sec if classes.endswith("f") or text in SECTION_BY_LABEL else sec
                        break
                if section is None and text in SECTION_BY_LABEL:
                    current = SECTION_BY_LABEL[text]
                    continue
                # Cellule de contenu : rattache les liens à la section courante.
                entries = extract_entries(td, page_url)
                if not entries:
                    continue
                sec = section or current
                if sec == "descripteur":
                    e = entries[0]
                    block["url"] = block["url"] or e["url"]
                    block["code"] = block["code"] or e["code"]
                    block["libelle"] = block["libelle"] or e["libelle"]
                elif sec in ("terme_generique", "terme_specifique", "employe_pour"):
                    block[sec].extend(entries)
        if block["code"] or block["libelle"]:
            blocks.append(block)
    return blocks


def main() -> None:
    p = argparse.ArgumentParser(description="Scrape les pages Liste (CS) du thésaurus ACIEGE.")
    p.add_argument("-i", "--index", default="data/aciege.json",
                   help="aciege.json produit par scrape_aciege.py (fournit les URLs Liste).")
    p.add_argument("-o", "--output", default="data")
    p.add_argument("--delay", type=float, default=0.3)
    p.add_argument("--limit", type=int, default=0, help="Ne traiter que N pages (0 = toutes).")
    args = p.parse_args()

    with open(args.index, encoding="utf-8") as f:
        index = json.load(f)["index"]
    todo = [r for r in index
            if r.get("lien_sous_groupe_liste") and r.get("sous_groupe_numerologie")]
    if args.limit:
        todo = todo[: args.limit]

    session = requests.Session()
    session.headers.update(HEADERS)

    results, relations, errors = {}, [], []
    eprint(f"{len(todo)} pages Liste à parcourir…")
    for i, row in enumerate(todo, 1):
        sg, url = row["sous_groupe_numerologie"], row["lien_sous_groupe_liste"]
        try:
            blocks = parse_liste_page(get_soup(session, url), url)
            results[sg] = {"sous_groupe": row["sous_groupe"], "url": url, "descripteurs": blocks}
            n_rel = 0
            for b in blocks:
                for rel in ("terme_generique", "terme_specifique", "employe_pour"):
                    for e in b[rel]:
                        relations.append({
                            "sous_groupe": sg,
                            "descripteur_code": b["code"], "descripteur": b["libelle"],
                            "relation": rel,
                            "cible_code": e["code"], "cible_libelle": e["libelle"],
                            "cible_url": e["url"],
                        })
                        n_rel += 1
            eprint(f"  [{i}/{len(todo)}] {sg} {row['sous_groupe']} : "
                   f"{len(blocks)} descripteurs, {n_rel} relations")
        except Exception as e:  # noqa: BLE001
            eprint(f"  [{i}/{len(todo)}] ERREUR {url} : {e}")
            errors.append({"url": url, "error": str(e)})
        time.sleep(args.delay)

    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "listes.json"), "w", encoding="utf-8") as f:
        json.dump({"sous_groupes": results, "erreurs": errors}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.output, "table3_relations.csv"), "w",
              newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=REL_COLS, delimiter=";")
        w.writeheader()
        w.writerows(relations)

    eprint("\n===== TERMINÉ =====")
    eprint(f"Pages      : {len(results)}")
    eprint(f"Relations  : {len(relations)}")
    eprint(f"Erreurs    : {len(errors)}")


if __name__ == "__main__":
    main()
