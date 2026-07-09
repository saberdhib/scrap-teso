# -*- coding: utf-8 -*-
"""Page « Revue » : validation humaine des verdicts, thèse par thèse.

Filtres (verdict, score, sous-groupe suggéré), pagination, choix du code parmi
les candidats, suivi de progression. Les décisions vont dans
resultats.decision_humaine (accepte:CODE / garde:CODE / manuel:CODE).
"""

import json

import pandas as pd
import streamlit as st

from aciege_pipeline import db

from . import couleurs as C

VERDICTS = ["a_reclasser", "incertain", "code_actuel_invalide", "bien_classe"]
BADGES = {"a_reclasser": "🔴 À reclasser", "incertain": "🟡 Incertain",
          "code_actuel_invalide": "⚫ Code invalide", "bien_classe": "🟢 Bien classée"}
PAR_PAGE = 15


@st.cache_data(ttl=30)
def charger(verdict: str, non_revues: bool) -> pd.DataFrame:
    q = """
        SELECT r.id AS resultat_id, t.objet_minio AS fichier, t.titre,
               t.code_actuel, r.code_suggere, r.libelle_suggere, r.score,
               r.verdict, r.justification, r.candidats, r.decision_humaine,
               LEFT(t.texte, 1800) AS extrait
        FROM resultats r JOIN theses t ON t.id = r.these_id
        WHERE r.verdict = %s {f}
        ORDER BY r.score DESC
    """.format(f="AND r.decision_humaine IS NULL" if non_revues else "")
    with db.conn() as c:
        return pd.read_sql(q, c, params=(verdict,))


@st.cache_data(ttl=30)
def progression() -> pd.DataFrame:
    with db.conn() as c:
        return pd.read_sql(
            "SELECT verdict, count(*) AS total, "
            "count(decision_humaine) AS revues "
            "FROM resultats GROUP BY verdict", c)


def enregistrer(resultat_id: int, decision: str) -> None:
    with db.conn() as c:
        c.cursor().execute(
            "UPDATE resultats SET decision_humaine=%s WHERE id=%s",
            (decision, resultat_id))
    charger.clear()
    progression.clear()


def options_candidats(r) -> list[tuple[str, str]]:
    """[(code, 'code — libellé (score)')] depuis le JSON candidats."""
    cands = r["candidats"]
    if isinstance(cands, str):
        cands = json.loads(cands or "[]")
    opts = []
    for c in (cands or [])[:8]:
        termes = ", ".join(t.get("libelle", "") for t in c.get("termes", [])[:2])
        opts.append((c["code"], f"{c['code']} — {termes} ({c['score']:.3f})"))
    return opts


def afficher() -> None:
    st.title("✅ Revue des verdicts")

    try:
        prog = progression()
    except Exception as e:  # noqa: BLE001
        st.error(f"Base de données injoignable : {e}")
        return
    if prog.empty:
        st.info("Pas encore de résultats — lancez d'abord le DAG dans Airflow.")
        return

    # ---- Progression globale ----
    cols = st.columns(len(prog))
    for col, (_, row) in zip(cols, prog.iterrows()):
        col.metric(BADGES.get(row["verdict"], row["verdict"]),
                   f"{int(row['revues'])} / {int(row['total'])}",
                   help="revues / total")
    tot, rev = int(prog["total"].sum()), int(prog["revues"].sum())
    st.progress(rev / tot if tot else 0.0,
                text=f"Progression de la revue : {rev}/{tot} ({rev / tot:.0%})"
                if tot else "")
    st.divider()

    # ---- Filtres ----
    with st.sidebar:
        st.subheader("Filtres")
        verdict = st.selectbox("Verdict", VERDICTS,
                               format_func=lambda v: BADGES[v])
        non_revues = st.checkbox("Seulement les non revues", value=True)
        df = charger(verdict, non_revues)
        if not df.empty:
            smin, smax = float(df["score"].min()), float(df["score"].max())
            if smin < smax:
                plage = st.slider("Score", smin, smax, (smin, smax), 0.01)
                df = df[df["score"].between(*plage)]
            sgs = ["(tous)"] + sorted(df["code_suggere"].dropna().unique())
            sg = st.selectbox("Sous-groupe suggéré", sgs)
            if sg != "(tous)":
                df = df[df["code_suggere"] == sg]
        st.write(f"**{len(df)}** thèses filtrées")

    if df.empty:
        st.success("Rien à revoir avec ces filtres. 🎉")
        return

    # ---- Pagination ----
    n_pages = (len(df) - 1) // PAR_PAGE + 1
    page = st.number_input(f"Page (1-{n_pages})", 1, n_pages, 1) - 1
    tranche = df.iloc[page * PAR_PAGE:(page + 1) * PAR_PAGE]

    for _, r in tranche.iterrows():
        with st.container(border=True):
            haut_g, haut_d = st.columns([3, 1])
            with haut_g:
                st.markdown(f"**📄 {r['fichier']}**"
                            + (f" — *{r['titre']}*" if r["titre"] else ""))
                st.markdown(
                    f"{BADGES[r['verdict']]} &nbsp;·&nbsp; "
                    f"actuel **`{r['code_actuel']}`** → suggéré "
                    f"**`{r['code_suggere']}`** {r['libelle_suggere'] or ''} "
                    f"&nbsp;·&nbsp; score **{r['score']:.3f}**")
                if r["justification"]:
                    st.caption(f"💬 {r['justification']}")
                with st.expander("Voir l'extrait de la thèse"):
                    st.text(r["extrait"] or "(pas de texte)")
            with haut_d:
                if r["decision_humaine"]:
                    st.success(f"Décidé : {r['decision_humaine']}")
                c1, c2 = st.columns(2)
                if c1.button("✅ Suggestion", key=f"ok{r['resultat_id']}",
                             use_container_width=True):
                    enregistrer(r["resultat_id"], f"accepte:{r['code_suggere']}")
                    st.rerun()
                if c2.button("↩️ Actuel", key=f"kp{r['resultat_id']}",
                             use_container_width=True):
                    enregistrer(r["resultat_id"], f"garde:{r['code_actuel']}")
                    st.rerun()
                opts = options_candidats(r)
                if opts:
                    choix = st.selectbox(
                        "Autre candidat", ["—"] + [o[1] for o in opts],
                        key=f"sel{r['resultat_id']}",
                        label_visibility="collapsed")
                    if choix != "—":
                        code = dict((o[1], o[0]) for o in opts)[choix]
                        if st.button(f"Appliquer {code}",
                                     key=f"ap{r['resultat_id']}",
                                     use_container_width=True):
                            enregistrer(r["resultat_id"], f"manuel:{code}")
                            st.rerun()
                libre = st.text_input("Code libre", key=f"in{r['resultat_id']}",
                                      placeholder="Code libre…",
                                      label_visibility="collapsed")
                if libre:
                    enregistrer(r["resultat_id"], f"manuel:{libre.strip()}")
                    st.rerun()
