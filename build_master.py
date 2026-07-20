#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Construit la version CANONIQUE du référentiel ACIEGE à partir des deux sources :

  A. Scraping du site   -> data/aciege.json (index + termes) + data/listes.json
  B. Export officiel     -> data/zthes.json  (parse de Ths_Export_YYYYMMDD.xml)

Produit dans master/ :
  concepts_master.csv        table canonique (1 ligne / concept, 4 niveaux)
  concepts_hierarchy.csv     arbre parent/enfant (structure taxonomique)
  concepts_synonyms.csv      synonymes et variantes (non-descripteurs)
  concepts_translations.csv  correspondances FR / EN
  concepts_edges.csv         graphe relationnel complet (broader/narrower/related)
  concepts_json.json         hiérarchie imbriquée prête navigation / IA
  data_dictionary.md         description des colonnes et règles de gestion
  quality_report.md          écarts, doublons, manques, conflits, hypothèses

Règle d'autorité : l'export officiel Zthes FAIT FOI pour les libellés et la
langue anglaise ; le scraping complète (URLs, sources bibliographiques, le
terme 362_19 absent de l'export, l'ossature catégorie/groupe).

Usage : python build_master.py            (sources dans data/, sortie master/)
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict

SEP = " > "
OUT = "master"
LEVEL_NAME = {1: "categorie", 2: "groupe", 3: "sous_groupe", 4: "terme"}


# ---------------------------------------------------------------------------
# Normalisation des identifiants — un format unique : chiffres + underscore
#   catégorie 1 | groupe 11 | sous-groupe 111 (ou 001) | terme 111_48
#   « 001.16 » -> « 001_16 » ; « 002.71/2 » -> « 002_71_2 »
# ---------------------------------------------------------------------------
def norm_id(raw: str) -> str:
    return re.sub(r"[./]", "_", (raw or "").strip())


def clean(s: str) -> str:
    return re.sub(r"[ \t]+", " ", (s or "").replace("\xa0", " ").replace("\r", "")).strip()


def utile(note: str, label: str) -> str:
    """Écarte une définition qui ne fait que répéter le libellé (placeholder)."""
    note = clean(note)
    if not note:
        return ""
    tete = note.split("\n", 1)[0]
    if tete.strip().upper().rstrip(".") == clean(label).upper().rstrip("."):
        # la 1re ligne répète le titre : garder la suite si elle existe
        reste = note.split("\n", 1)[1].strip() if "\n" in note else ""
        return clean(reste)
    return clean(note.replace("\n", " "))


def parent_de(code: str, niveau: int) -> str:
    if niveau == 4:
        return code.split("_")[0]
    if niveau == 3:
        return code[:2]
    if niveau == 2:
        return code[:1]
    return ""


# ---------------------------------------------------------------------------
# Chargement des sources
# ---------------------------------------------------------------------------
def charger():
    a = json.load(open("data/aciege.json", encoding="utf-8"))
    listes = json.load(open("data/listes.json", encoding="utf-8"))["sous_groupes"]
    z = json.load(open("data/zthes.json", encoding="utf-8"))
    return a, listes, z


def construire():
    a, listes, z = charger()
    conflits = {"libelles": [], "def_zthes": 0, "def_site": 0, "def_aucune": 0,
                "site_seul": [], "zthes_seul": [], "placeholders_filtres": 0}

    # ---- Ossature niveaux 1-3 depuis l'index scrapé ----
    concepts: dict[str, dict] = {}
    for r in a["index"]:
        if not r["sous_groupe_numerologie"]:
            continue
        cat, grp, sg = r["categorie"], r["groupe_numerologie"], r["sous_groupe_numerologie"]
        concepts.setdefault(cat, dict(concept_id=cat, level=1, label_site=clean(r["theme"]),
                                      in_site=True, in_zthes=False, scheme_url=""))
        concepts.setdefault(grp, dict(concept_id=grp, level=2, label_site=clean(r["groupe_titre"]),
                                      in_site=True, in_zthes=False, scheme_url=""))
        concepts.setdefault(sg, dict(concept_id=sg, level=3, label_site=clean(r["sous_groupe"]),
                                     in_site=True, in_zthes=False,
                                     scheme_url=r.get("lien_sous_groupe_schema") or r.get("lien_sous_groupe_liste", "")))

    # ---- Termes scrapés (schémas + listes) ----
    site_terms: dict[str, dict] = {}
    for t in a["termes"]:
        code = f"{t['sous_groupe_numerologie']}_{t['code_sous_sous_groupe']}"
        site_terms[code] = dict(label=clean(t["titre"]), definition=clean(t["definition"]),
                                source=clean(t["source"]), url=t["lien_sous_sous_groupe"])
    for sg_code, sg in listes.items():
        for d in sg["descripteurs"]:
            code = norm_id(d["code"])
            if not re.fullmatch(r"\d+_\d+", code):
                continue
            site_terms.setdefault(code, dict(label=clean(d["libelle"]), definition="",
                                             source="", url=d.get("url", "")))

    # ---- Univers des termes = union site ∪ zthes ----
    codes_termes = set(site_terms) | set(z["termes"])
    for code in sorted(codes_termes):
        zt = z["termes"].get(code)
        st = site_terms.get(code)
        in_site, in_zthes = st is not None, zt is not None
        if in_zthes and not in_site:
            conflits["zthes_seul"].append(code)
        if in_site and not in_zthes:
            conflits["site_seul"].append(code)

        # Libellé : Zthes fait foi ; sinon site.
        label_z = clean(zt["libelle"]) if zt else ""
        label_s = clean(st["label"]) if st else ""
        label = label_z or label_s
        if label_z and label_s and label_z.upper() != label_s.upper():
            conflits["libelles"].append((code, label_s, label_z))

        # Définition : Zthes prioritaire (filtré), sinon site.
        def_fr = utile(zt["definition"], label) if zt else ""
        if def_fr:
            conflits["def_zthes"] += 1
        elif st and utile(st["definition"], label):
            def_fr = utile(st["definition"], label)
            conflits["def_site"] += 1
        else:
            conflits["def_aucune"] += 1
        if zt and clean(zt["definition"]) and not utile(zt["definition"], label):
            conflits["placeholders_filtres"] += 1

        concepts[code] = dict(
            concept_id=code, level=4, label_site=label_s,
            label=label, label_en=clean(zt["libelle_en"]) if zt else "",
            definition_fr=def_fr,
            definition_en=utile(zt["definition_en"], zt["libelle_en"]) if zt else "",
            source_biblio=clean(st["source"]) if st else "",
            scheme_url=(st["url"] if st else ""),
            in_site=in_site, in_zthes=in_zthes,
            syn_site=[clean(s["libelle"]) for sg in [listes.get(code.split("_")[0], {})]
                      for d in sg.get("descripteurs", []) if norm_id(d["code"]) == code
                      for s in d["employe_pour"]],
            syn_uf=[clean(s) for s in (zt["synonymes"] if zt else [])],
            syn_en=[clean(s) for s in (zt["synonymes_en"] if zt else [])],
            tg=[norm_id(x) for x in (zt["tg"] if zt else [])],
            ts=[norm_id(x) for x in (zt["ts"] if zt else [])],
            rt=[norm_id(x) for x in (zt["associes"] if zt else [])],
        )

    # ---- Overlay Zthes sur les sous-groupes (libellé/def/EN) ----
    for code, sg in z["sous_groupes"].items():
        n = concepts.get(code)
        if n is None:  # sous-groupe présent dans l'export mais pas le site (aucun ici)
            n = concepts[code] = dict(concept_id=code, level=3, label_site="",
                                      in_site=False, scheme_url="")
        n["in_zthes"] = True
        n["label"] = clean(sg["libelle"]) or n.get("label_site", "")
        n["label_en"] = clean(sg["libelle_en"])
        n["definition_fr"] = utile(sg["definition"], sg["libelle"])
        n["definition_en"] = utile(sg["definition_en"], sg["libelle_en"])

    # ---- Finalisation : libellé, parent, chemins, autorité ----
    for c in concepts.values():
        c.setdefault("label", c.get("label_site", ""))
        c.setdefault("label_en", "")
        c.setdefault("definition_fr", "")
        c.setdefault("definition_en", "")
        c.setdefault("source_biblio", "")
        c.setdefault("in_zthes", False)
        for k in ("syn_site", "syn_uf", "syn_en", "tg", "ts", "rt"):
            c.setdefault(k, [])
        c["parent_id"] = parent_de(c["concept_id"], c["level"])
        c["source_authority"] = ("zthes" if c["in_zthes"] and c["level"] >= 3
                                 else "site")

    # chemins (codes + libellés) en remontant les parents
    def chemin(code):
        ids, labels = [], []
        cur = code
        while cur:
            n = concepts.get(cur)
            if not n:
                break
            ids.insert(0, cur)
            labels.insert(0, n["label"])
            cur = n["parent_id"]
        return SEP.join(ids), SEP.join(labels)

    for c in concepts.values():
        c["path_ids"], c["path_labels"] = chemin(c["concept_id"])

    # comptages enfants
    n_children = Counter(c["parent_id"] for c in concepts.values() if c["parent_id"])
    for c in concepts.values():
        c["n_children"] = n_children.get(c["concept_id"], 0)

    return concepts, conflits


# ---------------------------------------------------------------------------
# Écriture des livrables
# ---------------------------------------------------------------------------
def w(path, rows, cols):
    with open(os.path.join(OUT, path), "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=cols, delimiter=";", extrasaction="ignore")
        wr.writeheader()
        wr.writerows(rows)


def ecrire(concepts, conflits):
    os.makedirs(OUT, exist_ok=True)
    ordre = sorted(concepts.values(), key=lambda c: (c["level"], c["concept_id"]))

    # 1) concepts_master.csv
    master_cols = ["concept_id", "level", "level_name", "label_fr", "label_en",
                   "definition_fr", "definition_en", "source_biblio", "parent_id",
                   "path_ids", "path_labels", "in_site", "in_zthes",
                   "source_authority", "scheme_url", "n_children", "n_synonyms",
                   "n_related", "has_definition"]
    master = []
    for c in ordre:
        syns = _synonymes(c)
        master.append(dict(
            concept_id=c["concept_id"], level=c["level"], level_name=LEVEL_NAME[c["level"]],
            label_fr=c["label"], label_en=c["label_en"],
            definition_fr=c["definition_fr"], definition_en=c["definition_en"],
            source_biblio=c["source_biblio"], parent_id=c["parent_id"],
            path_ids=c["path_ids"], path_labels=c["path_labels"],
            in_site=int(c.get("in_site", False)), in_zthes=int(c["in_zthes"]),
            source_authority=c["source_authority"], scheme_url=c["scheme_url"],
            n_children=c["n_children"], n_synonyms=len(syns),
            n_related=len(c["rt"]), has_definition=int(bool(c["definition_fr"]))))
    w("concepts_master.csv", master, master_cols)

    # 2) concepts_hierarchy.csv
    hier = [dict(concept_id=c["concept_id"], parent_id=c["parent_id"],
                 level=c["level"], label_fr=c["label"],
                 parent_label_fr=concepts[c["parent_id"]]["label"] if c["parent_id"] in concepts else "")
            for c in ordre if c["parent_id"]]
    w("concepts_hierarchy.csv", hier, ["concept_id", "parent_id", "level",
                                       "label_fr", "parent_label_fr"])

    # 3) concepts_synonyms.csv
    syn_rows = []
    for c in ordre:
        for s in _synonymes(c):
            syn_rows.append(dict(concept_id=c["concept_id"], label_fr=c["label"],
                                 synonym=s["texte"], lang=s["lang"],
                                 relation="altLabel", source=s["source"]))
    w("concepts_synonyms.csv", syn_rows, ["concept_id", "label_fr", "synonym",
                                          "lang", "relation", "source"])

    # 4) concepts_translations.csv
    tr = [dict(concept_id=c["concept_id"], label_fr=c["label"], label_en=c["label_en"],
               definition_fr=c["definition_fr"], definition_en=c["definition_en"])
          for c in ordre if c["label_en"] or c["definition_en"]]
    w("concepts_translations.csv", tr, ["concept_id", "label_fr", "label_en",
                                        "definition_fr", "definition_en"])

    # 5) concepts_edges.csv (graphe complet)
    ids = set(concepts)
    edges = []
    for c in ordre:
        if c["parent_id"] in ids:
            edges.append(dict(source_id=c["concept_id"], target_id=c["parent_id"],
                              relation="skos:broader", kind="structural"))
        for tg in c["tg"]:
            if tg in ids and tg != c["parent_id"]:
                edges.append(dict(source_id=c["concept_id"], target_id=tg,
                                  relation="skos:broader", kind="zthes_BT"))
        for rt in c["rt"]:
            if rt in ids:
                edges.append(dict(source_id=c["concept_id"], target_id=rt,
                                  relation="skos:related", kind="zthes_RT"))
    w("concepts_edges.csv", edges, ["source_id", "target_id", "relation", "kind"])

    # 6) concepts_json.json (arbre imbriqué)
    ecrire_json(concepts)

    # 7-8) docs
    ecrire_data_dictionary()
    stats = dict(
        n=len(concepts),
        par_niveau={LEVEL_NAME[i]: sum(1 for c in concepts.values() if c["level"] == i)
                    for i in LEVEL_NAME},
        synonymes=len(syn_rows), traductions=len(tr), aretes=len(edges),
        aretes_kind=dict(Counter(e["kind"] for e in edges)),
        avec_def=sum(1 for c in concepts.values() if c["definition_fr"]),
        avec_en=sum(1 for c in concepts.values() if c["label_en"]),
    )
    ecrire_quality_report(concepts, conflits, stats)
    return stats


def _synonymes(c) -> list[dict]:
    """Union dédupliquée des synonymes d'un concept (site EP + Zthes UF + EN)."""
    out, vus = [], set()
    for txt in c["syn_site"] + c["syn_uf"]:
        k = txt.upper()
        if txt and k not in vus:
            vus.add(k)
            src = "site_employe_pour" if txt in c["syn_site"] else "zthes_UF"
            out.append(dict(texte=txt, lang="fr", source=src))
    for txt in c["syn_en"]:
        k = ("EN", txt.upper())
        if txt and k not in vus:
            vus.add(k)
            out.append(dict(texte=txt, lang="en", source="zthes_UF"))
    return out


def ecrire_json(concepts):
    enfants = defaultdict(list)
    for c in concepts.values():
        if c["parent_id"]:
            enfants[c["parent_id"]].append(c["concept_id"])

    def noeud(code):
        c = concepts[code]
        d = dict(id=code, level=c["level"], label_fr=c["label"], label_en=c["label_en"])
        if c["definition_fr"]:
            d["definition_fr"] = c["definition_fr"]
        if c["definition_en"]:
            d["definition_en"] = c["definition_en"]
        syns = _synonymes(c)
        if syns:
            d["synonyms"] = [{"text": s["texte"], "lang": s["lang"]} for s in syns]
        if c["rt"]:
            d["related"] = c["rt"]
        if c["source_biblio"]:
            d["source"] = c["source_biblio"]
        kids = sorted(enfants.get(code, []),
                      key=lambda x: (concepts[x]["level"], concepts[x]["concept_id"]))
        if kids:
            d["children"] = [noeud(k) for k in kids]
        return d

    racines = sorted((c["concept_id"] for c in concepts.values() if not c["parent_id"]))
    arbre = dict(scheme="Thésaurus du Management ACIEGE",
                 licence="CC BY-NC-ND 4.0",
                 sources=["Scraping aciege.org", "Export officiel Zthes 2026-01-15"],
                 categories=[noeud(r) for r in racines])
    with open(os.path.join(OUT, "concepts_json.json"), "w", encoding="utf-8") as f:
        json.dump(arbre, f, ensure_ascii=False, indent=1)


def ecrire_data_dictionary():
    txt = """# Dictionnaire de données — référentiel canonique ACIEGE

Version canonique consolidée à partir de deux sources : le **scraping du site**
aciege.org et l'**export officiel Zthes** (`Ths_Export_20260115.xml`).

## Identifiant canonique (`concept_id`)

Format unique : **chiffres séparés par des underscores**, sans point ni slash.

| Niveau | `level` | Forme | Exemple | Parent |
|---|---|---|---|---|
| Catégorie | 1 | `N` | `1` | — |
| Groupe | 2 | `NN` | `12` | 1er chiffre (`1`) |
| Sous-groupe | 3 | `NNN` | `124` | 2 premiers chiffres (`12`) |
| Terme | 4 | `NNN_NN` | `124_85` | avant le `_` (`124`) |

Le parent se **déduit du code** : la hiérarchie taxonomique est donc auto-portée
par l'identifiant (préfixe). Les identifiants sources `001.16` et `002.71/2`
sont normalisés en `001_16` et `002_71_2`.

## `concepts_master.csv` — table canonique (1 ligne / concept)

| Colonne | Description | Règle |
|---|---|---|
| `concept_id` | Identifiant canonique | unique, normalisé |
| `level` / `level_name` | 1..4 / categorie…terme | |
| `label_fr` | Libellé français | **Zthes fait foi** ; sinon site |
| `label_en` | Libellé anglais | Zthes (relation LE) |
| `definition_fr` | Définition française | Zthes prioritaire, sinon site ; placeholders filtrés |
| `definition_en` | Définition anglaise | Zthes (souvent placeholder → vide) |
| `source_biblio` | Source bibliographique de la définition | extraite du site |
| `parent_id` | Concept parent | déduit du code |
| `path_ids` / `path_labels` | Chemin racine→concept | séparateur ` > ` |
| `in_site` / `in_zthes` | Présence dans chaque source | 0/1 |
| `source_authority` | Source retenue pour le libellé | `zthes` si présent (niveau ≥ 3), sinon `site` |
| `scheme_url` | URL de la fiche sur aciege.org | site |
| `n_children` | Nombre d'enfants directs | calculé |
| `n_synonyms` | Nombre de synonymes (FR+EN) | calculé |
| `n_related` | Nombre de termes associés (RT) | calculé |
| `has_definition` | Définition FR présente | 0/1 |

## `concepts_hierarchy.csv` — arbre taxonomique

`concept_id ; parent_id ; level ; label_fr ; parent_label_fr`
Une ligne par concept non-racine. Arbre strict : **un seul parent** par concept.

## `concepts_synonyms.csv` — synonymes et variantes

`concept_id ; label_fr ; synonym ; lang ; relation ; source`
- `relation` = `altLabel` (SKOS). `lang` ∈ {fr, en}.
- `source` ∈ {`site_employe_pour`, `zthes_UF`} — union dédupliquée (casse ignorée).

## `concepts_translations.csv` — correspondances FR / EN

`concept_id ; label_fr ; label_en ; definition_fr ; definition_en`
Uniquement les concepts ayant au moins un champ anglais.

## `concepts_edges.csv` — graphe relationnel complet

`source_id ; target_id ; relation ; kind`
- `skos:broader` / `kind=structural` : lien taxonomique enfant→parent.
- `skos:broader` / `kind=zthes_BT` : terme générique hors arbre structurel.
- `skos:related` / `kind=zthes_RT` : terme associé (relation transverse).

## `concepts_json.json` — hiérarchie imbriquée

Arbre `categories → groupes → sous-groupes → termes`. Chaque nœud porte
`id, level, label_fr, label_en`, et si présents `definition_fr/en`,
`synonyms[]`, `related[]`, `source`, `children[]`. Format cible pour la
navigation et l'alimentation d'un classifieur (cartes de concepts).

## Règles de gestion

1. **Autorité** : l'export Zthes prime pour les libellés et l'anglais ; le
   scraping complète (URLs, sources, ossature catégorie/groupe, termes absents
   de l'export).
2. **Définitions** : une note qui ne fait que répéter le libellé est un
   placeholder → ignorée.
3. **Synonymes** : union des deux sources, dédupliquée sans tenir compte de la
   casse.
4. **Hiérarchie** : l'arbre structurel (déduit du code) est la référence ; les
   relations BT/NT entre termes de l'export sont ajoutées au graphe, pas à
   l'arbre, pour garantir un parent unique.
"""
    with open(os.path.join(OUT, "data_dictionary.md"), "w", encoding="utf-8") as f:
        f.write(txt)


def ecrire_quality_report(concepts, conflits, stats):
    termes = [c for c in concepts.values() if c["level"] == 4]
    # doublons de libellés (même libellé FR pour plusieurs concepts)
    par_label = defaultdict(list)
    for c in termes:
        par_label[c["label"].upper()].append(c["concept_id"])
    doublons_label = {k: v for k, v in par_label.items() if len(v) > 1}
    # synonymes ambigus (même variante -> plusieurs concepts)
    syn_map = defaultdict(set)
    for c in termes:
        for s in _synonymes(c):
            syn_map[s["texte"].upper()].add(c["concept_id"])
    syn_ambigus = {k: sorted(v) for k, v in syn_map.items() if len(v) > 1}
    # RT cassés (cible absente)
    rt_casses = [(c["concept_id"], rt) for c in termes for rt in c["rt"] if rt not in concepts]

    L = []
    L.append("# Rapport qualité — référentiel canonique ACIEGE\n")
    L.append(f"Concepts : **{stats['n']}** — " +
             ", ".join(f"{v} {k}" for k, v in stats["par_niveau"].items()) + ".\n")
    L.append("## 1. Sources et fusion\n")
    L.append("| Source | Rôle | Autorité |\n|---|---|---|")
    L.append("| Scraping aciege.org | ossature 4 niveaux, URLs, sources biblio | complète |")
    L.append("| Export Zthes 2026-01-15 | libellés, anglais, définitions, UF, RT | **fait foi** |\n")
    L.append("## 2. Couverture croisée des termes\n")
    L.append(f"- Termes présents dans les **deux** sources : "
             f"{sum(1 for c in termes if c['in_site'] and c['in_zthes'])}")
    L.append(f"- Termes **site uniquement** : {len(conflits['site_seul'])} "
             f"({', '.join(conflits['site_seul']) or '—'})")
    L.append(f"- Termes **export uniquement** : {len(conflits['zthes_seul'])} "
             f"({', '.join(conflits['zthes_seul'][:10]) or '—'})\n")
    L.append("## 3. Conflits de libellés (export retenu)\n")
    L.append(f"**{len(conflits['libelles'])} libellés** divergent entre scraping et export ; "
             "l'export a été retenu (le scraping prenait parfois la définition pour le titre). "
             "Exemples :\n")
    L.append("| Code | Scraping | Export (retenu) |\n|---|---|---|")
    for code, s, z in conflits["libelles"][:12]:
        L.append(f"| {code} | {s[:45]} | {z} |")
    L.append("")
    L.append("## 4. Définitions\n")
    L.append(f"- Depuis l'export : {conflits['def_zthes']}")
    L.append(f"- Depuis le site (fallback) : {conflits['def_site']}")
    L.append(f"- Aucune : {conflits['def_aucune']}")
    L.append(f"- Placeholders filtrés (note = libellé) : {conflits['placeholders_filtres']}\n")
    L.append("## 5. Doublons et ambiguïtés\n")
    L.append(f"- **Libellés FR identiques** sur plusieurs termes : {len(doublons_label)}")
    for k, v in list(doublons_label.items())[:5]:
        L.append(f"  - « {k} » → {', '.join(v)}")
    L.append(f"- **Synonymes ambigus** (même variante → plusieurs termes) : {len(syn_ambigus)}")
    for k, v in list(syn_ambigus.items())[:5]:
        L.append(f"  - « {k} » → {', '.join(v)}")
    L.append("  > Pour la classification : lever l'ambiguïté par le contexte "
             "(chemin hiérarchique) plutôt que par le seul synonyme.\n")
    L.append("## 6. Intégrité du graphe\n")
    L.append(f"- Arêtes totales : {stats['aretes']} {stats['aretes_kind']}")
    L.append(f"- Relations RT pointant vers une cible absente : {len(rt_casses)}")
    orphelins = [c["concept_id"] for c in concepts.values()
                 if c["parent_id"] and c["parent_id"] not in concepts]
    L.append(f"- Concepts au parent manquant : {len(orphelins)} "
             f"({', '.join(orphelins[:10]) or 'aucun'})\n")
    L.append("## 7. Bilinguisme\n")
    L.append(f"- Concepts avec libellé anglais : {stats['avec_en']}")
    L.append(f"- Traductions exportées : {stats['traductions']}")
    L.append("- ⚠️ Les définitions anglaises de l'export sont majoritairement des "
             "placeholders (nom répété) : seules les vraies variantes sont conservées.\n")
    L.append("## 8. Hypothèses et points d'attention\n")
    L.append("1. **Identifiant canonique** underscore choisi pour rester "
             "compatible fichiers/URL et préserver la hiérarchie par préfixe.")
    L.append("2. **Un seul parent par concept** (arbre) ; les BT/NT multiples de "
             "l'export sont dans `concepts_edges.csv`.")
    L.append(f"3. **{conflits['def_aucune']} termes sans définition** (surtout "
             "géographie/langues, auto-descriptifs) : acceptable, le libellé + le "
             "chemin suffisent au modèle.")
    L.append("4. **362_19 DOCTRINE** absent de l'export officiel : conservé "
             "depuis le site, à confirmer avec l'équipe.")
    L.append("5. Le référentiel couvre le **management/gestion** : prévoir une "
             "classe « hors thésaurus » côté classifieur pour les thèses hors domaine.")
    with open(os.path.join(OUT, "quality_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main():
    concepts, conflits = construire()
    stats = ecrire(concepts, conflits)
    print(f"OK -> {OUT}/")
    print(f"  concepts : {stats['n']} {stats['par_niveau']}")
    print(f"  synonymes: {stats['synonymes']} | traductions: {stats['traductions']} "
          f"| aretes: {stats['aretes']} {stats['aretes_kind']}")
    print(f"  avec def : {stats['avec_def']} | avec EN : {stats['avec_en']}")


if __name__ == "__main__":
    main()
