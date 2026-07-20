# -*- coding: utf-8 -*-
"""Vérification de classification : embeddings + arbitrage LLM (Hugging Face).

Étage 1 — candidats : le texte de la thèse est comparé (cosinus) aux « cartes »
des concepts du thésaurus (libellé + synonymes + définition). Les scores des
termes sont agrégés par sous-groupe (max), qui est le niveau de verdict.

Étage 2 — verdict : règles de marge ; si HF_TOKEN est fourni, les cas
« incertains » sont arbitrés par un LLM via l'Inference API Hugging Face.
"""

from __future__ import annotations

import csv
import json
import re

from . import config

_EMBEDDER = None
_CONCEPTS_CACHE = None


# ---------------------------------------------------------------------------
# Thésaurus -> cartes de concepts
# ---------------------------------------------------------------------------
def charger_concepts(path: str | None = None) -> list[dict]:
    """Cartes des termes (niveau 4) : texte descriptif + code sous-groupe."""
    global _CONCEPTS_CACHE
    if _CONCEPTS_CACHE is not None and path is None:
        return _CONCEPTS_CACHE
    path = path or config.THESAURUS_CSV
    cartes = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["niveau"] != "4":
                continue
            morceaux = [r["libelle"]]
            if r.get("libelle_en"):
                morceaux.append("EN: " + r["libelle_en"])
            if r.get("synonymes"):
                morceaux.append("Synonymes : " + r["synonymes"])
            if r.get("definition"):
                morceaux.append(r["definition"][:400])
            cartes.append({
                "code": r["code"],
                "libelle": r["libelle"],
                "sous_groupe": r["code"].split("_")[0],
                "chemin": r["chemin_libelles"],
                "texte": ". ".join(morceaux),
            })
    if path == config.THESAURUS_CSV:
        _CONCEPTS_CACHE = cartes
    return cartes


def libelles_sous_groupes(path: str | None = None) -> dict[str, str]:
    path = path or config.THESAURUS_CSV
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["niveau"] == "3":
                out[r["code"]] = r["libelle"]
    return out


# ---------------------------------------------------------------------------
# Étage 1 : candidats par similarité d'embeddings
# ---------------------------------------------------------------------------
def _embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer(config.EMBED_MODEL,
                                        token=config.HF_TOKEN or None)
    return _EMBEDDER


def _embeddings_concepts(cartes: list[dict]):
    """Embeddings des cartes, encodés une fois par processus."""
    import numpy as np
    model = _embedder()
    vecs = model.encode([c["texte"] for c in cartes],
                        batch_size=64, normalize_embeddings=True,
                        show_progress_bar=False)
    return np.asarray(vecs)


class Classifieur:
    def __init__(self, cartes: list[dict] | None = None):
        self.cartes = cartes or charger_concepts()
        self._vecs = None

    def _vecteurs(self):
        if self._vecs is None:
            self._vecs = _embeddings_concepts(self.cartes)
        return self._vecs

    def candidats(self, texte: str, top_k: int | None = None) -> list[dict]:
        """Top-k sous-groupes [{code, libelle, score, meilleurs_termes}]."""
        import numpy as np
        top_k = top_k or config.TOP_K
        q = _embedder().encode([texte[:4000]], normalize_embeddings=True)[0]
        scores = self._vecteurs() @ np.asarray(q)
        return agreger_par_sous_groupe(self.cartes, scores.tolist(), top_k)


def agreger_par_sous_groupe(cartes: list[dict], scores: list[float],
                            top_k: int) -> list[dict]:
    """Agrège les scores des termes par sous-groupe (max + meilleurs termes).
    Fonction pure — testable sans modèle."""
    par_sg: dict[str, dict] = {}
    for carte, score in zip(cartes, scores):
        sg = carte["sous_groupe"]
        d = par_sg.setdefault(sg, {"code": sg, "score": -1.0, "termes": []})
        d["termes"].append({"code": carte["code"], "libelle": carte["libelle"],
                            "score": round(float(score), 4)})
        d["score"] = max(d["score"], float(score))
    for d in par_sg.values():
        d["termes"] = sorted(d["termes"], key=lambda t: -t["score"])[:3]
        d["score"] = round(d["score"], 4)
    return sorted(par_sg.values(), key=lambda d: -d["score"])[:top_k]


# ---------------------------------------------------------------------------
# Étage 2 : verdict
# ---------------------------------------------------------------------------
def normaliser_code(code: str) -> str:
    """'111_48' -> '111' ; '111' -> '111' ; '' -> ''."""
    code = (code or "").strip().replace(".", "_")
    m = re.match(r"^(\d+)(?:_\d+)?$", code)
    return m.group(1) if m else ""


def verdict_regles(code_actuel: str, candidats: list[dict],
                   codes_valides: set[str],
                   marge: float | None = None) -> dict:
    """Verdict par règles. Fonction pure — testable sans modèle."""
    marge = marge or config.MARGE_INCERTITUDE
    top = candidats[0]
    sg_actuel = normaliser_code(code_actuel)
    base = {
        "code_suggere": top["code"],
        "score": top["score"],
        "candidats": candidats,
    }
    if not sg_actuel or sg_actuel not in codes_valides:
        return {**base, "verdict": "code_actuel_invalide", "confiance": top["score"],
                "justification": f"Code actuel « {code_actuel} » absent du thésaurus."}
    if sg_actuel == top["code"]:
        return {**base, "verdict": "bien_classe", "confiance": top["score"],
                "justification": "La classification actuelle est le meilleur candidat."}
    rang = next((i for i, c in enumerate(candidats) if c["code"] == sg_actuel), None)
    if rang is not None and candidats[rang]["score"] >= marge * top["score"]:
        return {**base, "verdict": "incertain",
                "confiance": candidats[rang]["score"],
                "justification": (f"Code actuel classé {rang + 1}e "
                                  f"({candidats[rang]['score']}) proche du 1er "
                                  f"({top['code']}, {top['score']}).")}
    just = (f"Code actuel hors des candidats plausibles"
            if rang is None else
            f"Code actuel classé {rang + 1}e ({candidats[rang]['score']}), "
            f"nettement derrière {top['code']} ({top['score']}).")
    return {**base, "verdict": "a_reclasser", "confiance": top["score"],
            "justification": just}


def arbitrage_llm(texte: str, code_actuel: str, candidats: list[dict],
                  libelles_sg: dict[str, str]) -> dict | None:
    """Demande au LLM (HF Inference API) de trancher un cas incertain.
    Retourne {verdict, code_suggere, justification} ou None en cas d'échec."""
    if not config.HF_TOKEN:
        return None
    from huggingface_hub import InferenceClient

    options = "\n".join(
        f"- {c['code']} {libelles_sg.get(c['code'], '')} (score {c['score']}) : "
        + ", ".join(t["libelle"] for t in c["termes"])
        for c in candidats[:5]
    )
    prompt = f"""Tu es documentaliste. Classification actuelle d'une thèse : {code_actuel} {libelles_sg.get(normaliser_code(code_actuel), '')}.

Extrait de la thèse (premières pages) :
\"\"\"{texte[:3000]}\"\"\"

Candidats du thésaurus ACIEGE (classification management) :
{options}

La classification actuelle est-elle correcte, ou faut-il reclasser ? Réponds UNIQUEMENT en JSON :
{{"verdict": "bien_classe" ou "a_reclasser", "code": "<code sous-groupe retenu>", "justification": "<1 phrase>"}}"""

    try:
        client = InferenceClient(model=config.LLM_MODEL, token=config.HF_TOKEN)
        out = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200, temperature=0.0,
        )
        contenu = out.choices[0].message.content
        m = re.search(r"\{.*\}", contenu, re.DOTALL)
        rep = json.loads(m.group(0)) if m else {}
        if rep.get("verdict") in ("bien_classe", "a_reclasser"):
            return {"verdict": rep["verdict"],
                    "code_suggere": rep.get("code", ""),
                    "justification": "LLM : " + rep.get("justification", "")}
    except Exception:
        return None
    return None


def verifier(texte: str, code_actuel: str, clf: Classifieur,
             libelles_sg: dict[str, str]) -> dict:
    """Chaîne complète pour une thèse : candidats -> règles -> LLM si incertain."""
    candidats = clf.candidats(texte)
    res = verdict_regles(code_actuel, candidats, set(libelles_sg))
    res["modele"] = config.EMBED_MODEL
    if res["verdict"] == "incertain":
        llm = arbitrage_llm(texte, code_actuel, candidats, libelles_sg)
        if llm:
            res.update(llm)
            res["modele"] = f"{config.EMBED_MODEL} + {config.LLM_MODEL}"
    code = res.get("code_suggere", "")
    res["libelle_suggere"] = libelles_sg.get(normaliser_code(code), "")
    return res
