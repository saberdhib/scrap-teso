#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse l'export officiel Zthes du thésaurus ACIEGE (Ths_Export_YYYYMMDD.xml)
en une structure normalisée alignée sur les codes du scraping.

Le fichier Zthes contient, pour FR et EN :
    termType NL = étiquettes de noeud (les 68 sous-groupes, id « 001 »)
    termType PT = descripteurs (id « 001.16 » -> code scraping « 001_16 »)
    termType ND = non-descripteurs / renvois (id « 002.71/2 »)
    termNote    = définition (FR et EN)
    relations   : BT/NT (hiérarchie), UF/USE (synonymes), RT (termes
                  associés), LE (équivalent linguistique FR<->EN)

Sortie : data/zthes.json
    {
      "sous_groupes": { "001": {libelle, libelle_en, definition, definition_en} },
      "termes": { "001_16": {libelle, libelle_en, definition, definition_en,
                             synonymes, synonymes_en, tg, ts, associes} },
      "stats": {...}
    }

Usage :
    python parse_zthes.py                       # data/Ths_Export_*.xml -> data/zthes.json
    python parse_zthes.py -i fichier.xml -o data/zthes.json
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import xml.etree.ElementTree as ET


def code_norm(term_id: str) -> str:
    """« 001.16 » -> « 001_16 » ; « 001 » -> « 001 » ; ids EN/ND inchangés."""
    return (term_id or "").strip().replace(".", "_")


def est_pt_fr(tid: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+", tid))


def est_nl_fr(tid: str) -> bool:
    return bool(re.fullmatch(r"\d+", tid))


def parse(path: str) -> dict:
    raw = open(path, encoding="latin-1").read()
    root = ET.fromstring(raw)

    terms = {}
    for t in root.findall("term"):
        tid = (t.findtext("termId") or "").strip()
        terms[tid] = {
            "id": tid,
            "nom": (t.findtext("termName") or "").strip(),
            "type": (t.findtext("termType") or "").strip(),
            "langue": (t.findtext("termLanguage") or "").strip(),
            "note": (t.findtext("termNote") or "").strip(),
            "rel": [
                {"type": (r.findtext("relationType") or "").strip(),
                 "id": (r.findtext("termId") or "").strip(),
                 "nom": (r.findtext("termName") or "").strip(),
                 "langue": (r.findtext("termLanguage") or "").strip()}
                for r in t.findall("relation")
            ],
        }

    def equivalent_en(t: dict) -> dict | None:
        for r in t["rel"]:
            if r["type"] == "LE" and r["langue"] == "EN":
                return terms.get(r["id"])
        return None

    sous_groupes, termes = {}, {}
    stats = {"nl_fr": 0, "pt_fr": 0, "nd_fr": 0, "uf": 0, "rt": 0,
             "def_fr": 0, "def_en": 0, "en_lies": 0}

    for tid, t in terms.items():
        if t["langue"] != "FR":
            continue
        en = equivalent_en(t)
        if en:
            stats["en_lies"] += 1

        if t["type"] == "NL" and est_nl_fr(tid):
            stats["nl_fr"] += 1
            sous_groupes[tid] = {
                "libelle": t["nom"],
                "libelle_en": en["nom"] if en else "",
                "definition": t["note"],
                "definition_en": en["note"] if en else "",
            }
        elif t["type"] == "PT" and est_pt_fr(tid):
            stats["pt_fr"] += 1
            code = code_norm(tid)
            uf = [r["nom"] for r in t["rel"] if r["type"] == "UF"]
            uf_en = [r["nom"] for r in (en["rel"] if en else [])
                     if r["type"] == "UF"]
            rt = [code_norm(r["id"]) for r in t["rel"]
                  if r["type"] == "RT" and est_pt_fr(r["id"])]
            tg = [code_norm(r["id"]) for r in t["rel"]
                  if r["type"] == "BT" and est_pt_fr(r["id"])]
            ts = [code_norm(r["id"]) for r in t["rel"]
                  if r["type"] == "NT" and est_pt_fr(r["id"])]
            stats["uf"] += len(uf)
            stats["rt"] += len(rt)
            if t["note"]:
                stats["def_fr"] += 1
            if en and en["note"]:
                stats["def_en"] += 1
            termes[code] = {
                "libelle": t["nom"],
                "libelle_en": en["nom"] if en else "",
                "definition": t["note"],
                "definition_en": en["note"] if en else "",
                "synonymes": uf,
                "synonymes_en": uf_en,
                "tg": tg, "ts": ts, "associes": sorted(set(rt)),
            }
        elif t["type"] == "ND":
            stats["nd_fr"] += 1

    return {"sous_groupes": sous_groupes, "termes": termes, "stats": stats}


def main() -> None:
    p = argparse.ArgumentParser(description="Parse l'export Zthes ACIEGE -> data/zthes.json")
    p.add_argument("-i", "--input", default=None,
                   help="Fichier XML (défaut : data/Ths_Export_*.xml le plus récent).")
    p.add_argument("-o", "--output", default="data/zthes.json")
    args = p.parse_args()

    path = args.input
    if path is None:
        candidats = sorted(glob.glob("data/Ths_Export_*.xml"))
        if not candidats:
            sys.exit("Aucun data/Ths_Export_*.xml trouvé.")
        path = candidats[-1]

    res = parse(path)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"{path} ->")
    print(f"  sous-groupes : {len(res['sous_groupes'])}")
    print(f"  termes       : {len(res['termes'])}")
    print(f"  stats        : {res['stats']}")


if __name__ == "__main__":
    main()
