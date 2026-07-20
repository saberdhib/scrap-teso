#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Construit un thésaurus structuré à partir des données brutes scrapées
(data/aciege.json) — prêt pour l'annotation documentaire (ex. corpus de thèses).

Hiérarchie à 4 niveaux :
    1  catégorie      ex. « 1 — L'entreprise et son management »
    2  groupe         ex. « 11 — Gestion de l'entreprise »
    3  sous-groupe    ex. « 111 — ORGANISATION »   <- niveau d'annotation pivot
    4  terme          ex. « 111_48 — ANALYSE DES SYSTEMES » (+ définition, source)

Sorties (dossier thesaurus/) :
    concepts_flat.csv   un concept par ligne : id, parent_id, niveau, code,
                        libellé, chemin codes, chemin libellés, définition,
                        source, url — format pivot pour annotation / pandas.
    thesaurus.json      hiérarchie imbriquée (catégories > groupes >
                        sous-groupes > termes).
    thesaurus.skos.ttl  export SKOS (Turtle) : standard des thésaurus
                        documentaires (VocBench, TemaTres, plateformes
                        d'indexation).
    stats.md            statistiques de couverture.

Usage :
    python build_thesaurus.py                 # lit data/aciege.json -> thesaurus/
    python build_thesaurus.py -i data/aciege.json -o thesaurus
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re

SEP = " > "
FLAT_COLS = [
    "id", "parent_id", "niveau", "niveau_nom", "code", "libelle", "libelle_en",
    "chemin_codes", "chemin_libelles", "definition", "definition_en",
    "source", "url", "synonymes", "synonymes_en",
    "terme_generique_code", "termes_specifiques_codes", "termes_associes_codes",
]
NIVEAUX = {1: "categorie", 2: "groupe", 3: "sous_groupe", 4: "terme"}


def build(index_rows: list[dict], terme_rows: list[dict]):
    """Assemble la hiérarchie ; retourne (liste_plate, fonction_sérialisation).
    La fonction retournée produit l'arbre imbriqué à partir de l'état COURANT
    des noeuds — l'appeler après merge_relations() pour inclure les relations."""
    flat: list[dict] = []
    tree: dict[str, dict] = {}          # id catégorie -> noeud
    seen: set[str] = set()

    def add(node_id: str, parent_id: str, niveau: int, code: str, libelle: str,
            definition: str = "", source: str = "", url: str = "",
            chemin_codes: str = "", chemin_libelles: str = "") -> dict:
        node = {
            "id": node_id, "parent_id": parent_id,
            "niveau": niveau, "niveau_nom": NIVEAUX[niveau],
            "code": code, "libelle": libelle,
            "chemin_codes": chemin_codes, "chemin_libelles": chemin_libelles,
            "definition": definition, "source": source, "url": url,
        }
        flat.append(node)
        return node

    # Niveaux 1-3 depuis l'index.
    for r in index_rows:
        if not r["sous_groupe_numerologie"] and not r["sous_groupe"]:
            continue                                   # ligne d'espacement vide
        cat, cat_lib = r["categorie"], r["theme"]
        grp, grp_lib = r["groupe_numerologie"], r["groupe_titre"]
        sg, sg_lib = r["sous_groupe_numerologie"], r["sous_groupe"]

        cat_id = f"cat:{cat}"
        if cat_id not in seen:
            seen.add(cat_id)
            n = add(cat_id, "", 1, cat, cat_lib,
                    chemin_codes=cat, chemin_libelles=cat_lib)
            tree[cat_id] = {**n, "groupes": {}}
        grp_id = f"grp:{grp}"
        if grp_id not in seen:
            seen.add(grp_id)
            n = add(grp_id, cat_id, 2, grp, grp_lib,
                    chemin_codes=SEP.join([cat, grp]),
                    chemin_libelles=SEP.join([cat_lib, grp_lib]))
            tree[cat_id]["groupes"][grp_id] = {**n, "sous_groupes": {}}
        sg_id = f"sg:{sg}"
        if sg_id not in seen:
            seen.add(sg_id)
            n = add(sg_id, grp_id, 3, sg, sg_lib,
                    definition="", source="",
                    url=r.get("lien_sous_groupe_schema") or r.get("lien_sous_groupe_liste", ""),
                    chemin_codes=SEP.join([cat, grp, sg]),
                    chemin_libelles=SEP.join([cat_lib, grp_lib, sg_lib]))
            tree[cat_id]["groupes"][grp_id]["sous_groupes"][sg_id] = {**n, "termes": []}

    # Index inverse sous-groupe -> noeud d'arbre + chemins.
    sg_nodes: dict[str, dict] = {}
    for cat in tree.values():
        for grp in cat["groupes"].values():
            for sg in grp["sous_groupes"].values():
                sg_nodes[sg["code"]] = sg
    sg_meta = sg_nodes

    # Niveau 4 : termes.
    for t in terme_rows:
        sg = t["sous_groupe_numerologie"]
        parent = sg_meta.get(sg)
        if parent is None:
            continue
        code = f"{sg}_{t['code_sous_sous_groupe']}"
        term_id = f"term:{code}"
        if term_id in seen:
            continue
        seen.add(term_id)
        node = add(
            term_id, f"sg:{sg}", 4, code, t["titre"],
            definition=t["definition"], source=t["source"],
            url=t["lien_sous_sous_groupe"],
            chemin_codes=parent["chemin_codes"] + SEP + code,
            chemin_libelles=parent["chemin_libelles"] + SEP + t["titre"],
        )
        sg_nodes[sg]["termes"].append(node)

    # Champs relations/multilingues (remplis par merge_relations / merge_zthes).
    for n in flat:
        for champ in ("synonymes", "terme_generique_code", "termes_specifiques_codes",
                      "libelle_en", "definition_en", "synonymes_en",
                      "termes_associes_codes"):
            n.setdefault(champ, "")

    # dicts -> listes pour le JSON final.
    def as_tree() -> list[dict]:
        cats = []
        for cat in tree.values():
            c = {k: cat[k] for k in ("code", "libelle")}
            c["groupes"] = []
            for grp in cat["groupes"].values():
                g = {k: grp[k] for k in ("code", "libelle")}
                g["sous_groupes"] = []
                for sg in grp["sous_groupes"].values():
                    s = {k: sg[k] for k in ("code", "libelle", "url")}
                    s["termes"] = [
                        {k: t.get(k, "") for k in
                         ("code", "libelle", "libelle_en", "definition",
                          "definition_en", "source", "url", "synonymes",
                          "synonymes_en", "terme_generique_code",
                          "termes_specifiques_codes", "termes_associes_codes")}
                        for t in sg["termes"]
                    ]
                    g["sous_groupes"].append(s)
                c["groupes"].append(g)
            cats.append(c)
        return cats

    def add_term(sg_code: str, code: str, libelle: str, url: str = "") -> dict | None:
        """Ajoute après coup un terme découvert dans les pages Liste
        (sous-groupes sans schéma). Retourne le noeud créé, ou None."""
        parent = sg_nodes.get(sg_code)
        term_id = f"term:{code}"
        if parent is None or term_id in seen:
            return None
        seen.add(term_id)
        node = add(
            term_id, f"sg:{sg_code}", 4, code, libelle, url=url,
            chemin_codes=parent["chemin_codes"] + SEP + code,
            chemin_libelles=parent["chemin_libelles"] + SEP + libelle,
        )
        node.setdefault("synonymes", "")
        node.setdefault("terme_generique_code", "")
        node.setdefault("termes_specifiques_codes", "")
        parent["termes"].append(node)
        return node

    return flat, as_tree, add_term


def merge_relations(flat: list[dict], add_term, listes_path: str) -> dict:
    """Enrichit les termes avec les relations des pages Liste (CS) :
    synonymes (Employé Pour -> skos:altLabel), terme générique et termes
    spécifiques (hiérarchie entre termes). Les descripteurs présents dans les
    listes mais absents des schémas (sous-groupes sans schéma : langues,
    géographie, organisations…) sont créés comme termes. Retourne des compteurs."""
    with open(listes_path, encoding="utf-8") as f:
        listes = json.load(f)["sous_groupes"]

    by_code = {n["code"]: n for n in flat if n["niveau"] == 4}
    stats = {"descripteurs_liste": 0, "synonymes": 0, "tg": 0, "ts": 0,
             "crees_depuis_listes": 0, "codes_inconnus": 0}

    # Passe 1 : créer les termes manquants (pour que les relations TG/TS
    # entre eux se résolvent en passe 2).
    for sg_code, sg in listes.items():
        for b in sg["descripteurs"]:
            if b["code"] and b["code"] not in by_code \
                    and re.fullmatch(r"\d+_\d+", b["code"]):
                node = add_term(sg_code, b["code"], b["libelle"], b.get("url", ""))
                if node is not None:
                    by_code[b["code"]] = node
                    stats["crees_depuis_listes"] += 1

    # Passe 2 : appliquer les relations.
    for sg in listes.values():
        for b in sg["descripteurs"]:
            stats["descripteurs_liste"] += 1
            node = by_code.get(b["code"])
            if node is None:
                stats["codes_inconnus"] += 1
                continue
            eps = [e["libelle"] for e in b["employe_pour"] if e.get("libelle")]
            if eps:
                node["synonymes"] = " | ".join(dict.fromkeys(eps))
                stats["synonymes"] += len(eps)
            tgs = [e["code"] for e in b["terme_generique"] if e.get("code") in by_code]
            if tgs:
                node["terme_generique_code"] = tgs[0]
                stats["tg"] += 1
            tss = [e["code"] for e in b["terme_specifique"] if e.get("code") in by_code]
            if tss:
                node["termes_specifiques_codes"] = " | ".join(dict.fromkeys(tss))
                stats["ts"] += len(tss)
    return stats


def merge_zthes(flat: list[dict], zthes_path: str) -> dict:
    """Fusionne l'export officiel Zthes (source d'autorité) :
    - corrige les libellés FR erronés issus du scraping ;
    - comble les définitions manquantes (FR) et ajoute les définitions EN ;
    - ajoute libellés/synonymes anglais et termes associés (RT) ;
    - complète synonymes (UF) et terme générique.
    Retourne des compteurs."""
    with open(zthes_path, encoding="utf-8") as f:
        z = json.load(f)

    def utile(note: str, nom: str) -> str:
        """Écarte les notes qui ne font que répéter le libellé."""
        note = (note or "").strip()
        if note.upper().rstrip(".") == (nom or "").strip().upper().rstrip("."):
            return ""
        return note

    stats = {"libelles_corriges": 0, "def_fr_comblees": 0, "def_en": 0,
             "libelles_en": 0, "synonymes_ajoutes": 0, "rt": 0,
             "absents_du_xml": 0}
    for n in flat:
        if n["niveau"] == 3:
            sg = z["sous_groupes"].get(n["code"])
            if sg:
                n["libelle_en"] = sg["libelle_en"]
                if not n["definition"]:
                    n["definition"] = utile(sg["definition"], sg["libelle"])
                n["definition_en"] = utile(sg["definition_en"], sg["libelle_en"])
            continue
        if n["niveau"] != 4:
            continue
        t = z["termes"].get(n["code"])
        if t is None:
            stats["absents_du_xml"] += 1
            continue
        # Libellé : le XML fait foi.
        if t["libelle"] and n["libelle"].strip().upper() != t["libelle"].strip().upper():
            stats["libelles_corriges"] += 1
            # Le scraping avait pris la définition pour le titre : la
            # définition scrapée est suspecte, on repart de celle du XML.
            n["libelle"] = t["libelle"]
            n["definition"] = ""
            morceaux = n["chemin_libelles"].split(SEP)
            n["chemin_libelles"] = SEP.join(morceaux[:-1] + [t["libelle"]])
        if t["libelle_en"]:
            n["libelle_en"] = t["libelle_en"]
            stats["libelles_en"] += 1
        if not n["definition"]:
            d = utile(t["definition"], t["libelle"])
            if d:
                n["definition"] = d
                stats["def_fr_comblees"] += 1
        d_en = utile(t["definition_en"], t["libelle_en"])
        if d_en:
            n["definition_en"] = d_en
            stats["def_en"] += 1
        # Synonymes : union scraping (Employé Pour) + XML (UF).
        existants = [s.strip() for s in n["synonymes"].split("|") if s.strip()]
        vus = {s.upper() for s in existants}
        for syn in t["synonymes"]:
            if syn.strip() and syn.strip().upper() not in vus:
                existants.append(syn.strip())
                vus.add(syn.strip().upper())
                stats["synonymes_ajoutes"] += 1
        n["synonymes"] = " | ".join(existants)
        n["synonymes_en"] = " | ".join(dict.fromkeys(
            s.strip() for s in t["synonymes_en"] if s.strip()))
        if not n["terme_generique_code"] and t["tg"]:
            n["terme_generique_code"] = t["tg"][0]
        if t["associes"]:
            n["termes_associes_codes"] = " | ".join(t["associes"])
            stats["rt"] += len(t["associes"])
    return stats


def ttl_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "")


def write_skos(path: str, flat: list[dict]) -> None:
    """Export SKOS minimal : ConceptScheme + Concepts + broader/narrower."""
    base = "https://aciege.org/concept/"
    lines = [
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "@prefix dct:  <http://purl.org/dc/terms/> .",
        "",
        f"<{base}scheme> a skos:ConceptScheme ;",
        '    dct:title "Thésaurus du Management ACIEGE"@fr ;',
        '    dct:license "CC BY-NC-ND 4.0" .',
        "",
    ]
    ids = {n["id"] for n in flat}
    children: dict[str, list[str]] = {}
    for n in flat:
        if n["parent_id"]:
            children.setdefault(n["parent_id"], []).append(n["id"])

    def uri(node_id: str) -> str:
        return base + node_id.replace(":", "/")

    for n in flat:
        lines.append(f"<{uri(n['id'])}> a skos:Concept ;")
        lines.append(f'    skos:prefLabel "{ttl_escape(n["libelle"])}"@fr ;')
        if n.get("libelle_en"):
            lines.append(f'    skos:prefLabel "{ttl_escape(n["libelle_en"])}"@en ;')
        lines.append(f'    skos:notation "{ttl_escape(n["code"])}" ;')
        for alt in filter(None, (s.strip() for s in n.get("synonymes", "").split("|"))):
            lines.append(f'    skos:altLabel "{ttl_escape(alt)}"@fr ;')
        for alt in filter(None, (s.strip() for s in n.get("synonymes_en", "").split("|"))):
            lines.append(f'    skos:altLabel "{ttl_escape(alt)}"@en ;')
        if n["definition"]:
            lines.append(f'    skos:definition "{ttl_escape(n["definition"])}"@fr ;')
        if n.get("definition_en"):
            lines.append(f'    skos:definition "{ttl_escape(n["definition_en"])}"@en ;')
        for rt in filter(None, (s.strip() for s in n.get("termes_associes_codes", "").split("|"))):
            if f"term:{rt}" in ids:
                lines.append(f"    skos:related <{uri('term:' + rt)}> ;")
        if n["source"]:
            lines.append(f'    dct:source "{ttl_escape(n["source"])}" ;')
        if n["parent_id"] in ids:
            lines.append(f"    skos:broader <{uri(n['parent_id'])}> ;")
        else:
            lines.append(f"    skos:topConceptOf <{base}scheme> ;")
        tg = n.get("terme_generique_code", "")
        if tg and f"term:{tg}" in ids:
            lines.append(f"    skos:broader <{uri('term:' + tg)}> ;")
        for ts in filter(None, (s.strip() for s in n.get("termes_specifiques_codes", "").split("|"))):
            if f"term:{ts}" in ids:
                lines.append(f"    skos:narrower <{uri('term:' + ts)}> ;")
        for child in children.get(n["id"], []):
            lines.append(f"    skos:narrower <{uri(child)}> ;")
        lines.append(f"    skos:inScheme <{base}scheme> .")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_stats(path: str, flat: list[dict]) -> None:
    by_lvl = {i: [n for n in flat if n["niveau"] == i] for i in NIVEAUX}
    termes = by_lvl[4]
    sans_def = sum(1 for t in termes if not t["definition"])
    sans_src = sum(1 for t in termes if not t["source"])
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Thésaurus ACIEGE — statistiques\n\n")
        f.write("| Niveau | Nom | Nombre |\n|---|---|---|\n")
        for i, name in NIVEAUX.items():
            f.write(f"| {i} | {name} | {len(by_lvl[i])} |\n")
        f.write(f"\n- Termes sans définition : **{sans_def}** / {len(termes)}\n")
        f.write(f"- Termes sans source : **{sans_src}** / {len(termes)}\n")
        avec_syn = sum(1 for t in termes if t.get("synonymes"))
        n_syn = sum(len(t["synonymes"].split("|")) for t in termes if t.get("synonymes"))
        avec_tg = sum(1 for t in termes if t.get("terme_generique_code"))
        f.write(f"- Termes avec synonymes (« Employé Pour ») : **{avec_syn}** "
                f"({n_syn} synonymes au total)\n")
        f.write(f"- Termes avec terme générique (hiérarchie fine) : **{avec_tg}**\n")
        avec_en = sum(1 for t in termes if t.get("libelle_en"))
        avec_def_en = sum(1 for t in termes if t.get("definition_en"))
        avec_rt = sum(1 for t in termes if t.get("termes_associes_codes"))
        f.write(f"- Termes avec libellé anglais : **{avec_en}** "
                f"(dont {avec_def_en} avec définition anglaise)\n")
        f.write(f"- Termes avec termes associés (RT) : **{avec_rt}**\n")
        f.write("\n## Termes par catégorie\n\n")
        cats = {n["code"]: n["libelle"] for n in by_lvl[1]}
        for code, lib in sorted(cats.items()):
            n_terms = sum(1 for t in termes if t["chemin_codes"].split(SEP)[0] == code)
            f.write(f"- **{code} {lib}** : {n_terms} termes\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Construit le thésaurus structuré depuis data/aciege.json.")
    p.add_argument("-i", "--input", default="data/aciege.json")
    p.add_argument("-o", "--output", default="thesaurus")
    args = p.parse_args()

    with open(args.input, encoding="utf-8") as f:
        raw = json.load(f)
    flat, as_tree, add_term = build(raw["index"], raw["termes"])

    listes_path = os.path.join(os.path.dirname(args.input) or ".", "listes.json")
    if os.path.exists(listes_path):
        rel_stats = merge_relations(flat, add_term, listes_path)
        print(f"Relations fusionnées depuis {listes_path} : {rel_stats}")
    else:
        print(f"({listes_path} absent : pas d'enrichissement synonymes/hiérarchie)")

    zthes_path = os.path.join(os.path.dirname(args.input) or ".", "zthes.json")
    if os.path.exists(zthes_path):
        z_stats = merge_zthes(flat, zthes_path)
        print(f"Export officiel fusionné depuis {zthes_path} : {z_stats}")
    else:
        print(f"({zthes_path} absent : pas d'enrichissement bilingue/officiel)")
    tree = as_tree()

    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "concepts_flat.csv"), "w",
              newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FLAT_COLS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(flat)
    with open(os.path.join(args.output, "thesaurus.json"), "w", encoding="utf-8") as f:
        json.dump({"scheme": "Thésaurus du Management ACIEGE",
                   "licence": "CC BY-NC-ND 4.0",
                   "categories": tree}, f, ensure_ascii=False, indent=2)
    write_skos(os.path.join(args.output, "thesaurus.skos.ttl"), flat)
    write_stats(os.path.join(args.output, "stats.md"), flat)

    print(f"OK : {len(flat)} concepts -> {args.output}/")
    for i, name in NIVEAUX.items():
        print(f"  niveau {i} ({name}) : {sum(1 for n in flat if n['niveau'] == i)}")


if __name__ == "__main__":
    main()
