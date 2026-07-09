# -*- coding: utf-8 -*-
"""Page « Revue » : validation humaine des verdicts, thèse par thèse."""

import pandas as pd
import streamlit as st

from aciege_pipeline import db

VERDICTS = ["a_reclasser", "incertain", "code_actuel_invalide", "bien_classe"]


@st.cache_data(ttl=30)
def charger(verdict: str, seulement_non_revues: bool) -> pd.DataFrame:
    q = """
        SELECT r.id AS resultat_id, t.objet_minio AS fichier, t.titre,
               t.code_actuel, r.code_suggere, r.libelle_suggere, r.score,
               r.verdict, r.confiance, r.justification, r.candidats,
               r.decision_humaine, LEFT(t.texte, 1500) AS extrait
        FROM resultats r JOIN theses t ON t.id = r.these_id
        WHERE r.verdict = %s {filtre}
        ORDER BY r.score DESC
    """.format(filtre="AND r.decision_humaine IS NULL" if seulement_non_revues else "")
    with db.conn() as c:
        return pd.read_sql(q, c, params=(verdict,))


def enregistrer_decision(resultat_id: int, decision: str) -> None:
    with db.conn() as c:
        c.cursor().execute(
            "UPDATE resultats SET decision_humaine=%s WHERE id=%s",
            (decision, resultat_id))
    charger.clear()


def afficher() -> None:
    st.title("✅ Revue des verdicts")

    try:
        with db.conn() as c:
            stats = pd.read_sql(
                "SELECT verdict, count(*) AS n FROM resultats GROUP BY verdict", c)
    except Exception as e:  # noqa: BLE001
        st.error(f"Base de données injoignable : {e}")
        return
    if stats.empty:
        st.info("Pas encore de résultats — lancez d'abord le DAG dans Airflow.")
        return

    cols = st.columns(max(len(stats), 1))
    for col, (_, row) in zip(cols, stats.iterrows()):
        col.metric(row["verdict"], int(row["n"]))

    verdict = st.sidebar.selectbox("Verdict à revoir", VERDICTS)
    non_revues = st.sidebar.checkbox("Seulement les non revues", value=True)
    df = charger(verdict, non_revues)
    st.sidebar.write(f"{len(df)} thèses")

    for _, r in df.head(50).iterrows():
        with st.expander(f"📄 {r['fichier']} — {r['code_actuel']} → "
                         f"{r['code_suggere']} {r['libelle_suggere']} "
                         f"(score {r['score']:.3f})"):
            gauche, droite = st.columns([2, 1])
            with gauche:
                if r["titre"]:
                    st.markdown(f"**{r['titre']}**")
                st.caption(r["justification"] or "")
                st.text(r["extrait"] or "(pas de texte)")
            with droite:
                st.json(r["candidats"], expanded=False)
                c1, c2, c3 = st.columns(3)
                if c1.button("✅ Suggestion", key=f"ok{r['resultat_id']}"):
                    enregistrer_decision(r["resultat_id"],
                                         f"accepte:{r['code_suggere']}")
                    st.rerun()
                if c2.button("↩️ Garder actuel", key=f"keep{r['resultat_id']}"):
                    enregistrer_decision(r["resultat_id"],
                                         f"garde:{r['code_actuel']}")
                    st.rerun()
                autre = c3.text_input("Autre code", key=f"in{r['resultat_id']}",
                                      label_visibility="collapsed",
                                      placeholder="Autre…")
                if autre:
                    enregistrer_decision(r["resultat_id"], f"manuel:{autre}")
                    st.rerun()
