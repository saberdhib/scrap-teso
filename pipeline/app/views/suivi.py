# -*- coding: utf-8 -*-
"""Page « Suivi du traitement » : ingestion, avancement, verdicts, erreurs."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from aciege_pipeline import db

from . import couleurs as C

LIBELLES_STATUT = {
    "en_attente": "En attente",
    "texte_ok": "Texte extrait",
    "classifie": "Classifiée",
    "erreur_texte": "Erreur extraction",
    "erreur_classif": "Erreur classification",
}
LIBELLES_VERDICT = {
    "bien_classe": "Bien classée",
    "a_reclasser": "À reclasser",
    "incertain": "Incertain",
    "code_actuel_invalide": "Code invalide",
}


@st.cache_data(ttl=30)
def charger():
    with db.conn() as c:
        statuts = pd.read_sql(
            "SELECT statut, count(*) AS n FROM theses GROUP BY statut", c)
        verdicts = pd.read_sql(
            "SELECT verdict, count(*) AS n FROM resultats GROUP BY verdict", c)
        ocr = pd.read_sql(
            "SELECT ocr_utilise, count(*) AS n, avg(pages_lues) AS pages "
            "FROM theses WHERE statut IN ('texte_ok','classifie') "
            "GROUP BY ocr_utilise", c)
        par_jour = pd.read_sql(
            "SELECT date_trunc('day', maj_le)::date AS jour, count(*) AS n "
            "FROM theses WHERE statut='classifie' GROUP BY 1 ORDER BY 1", c)
        revues = pd.read_sql(
            "SELECT count(*) FILTER (WHERE decision_humaine IS NOT NULL) AS revues, "
            "count(*) AS total FROM resultats", c)
        erreurs = pd.read_sql(
            "SELECT objet_minio, statut, erreur, maj_le FROM theses "
            "WHERE statut LIKE 'erreur%' ORDER BY maj_le DESC LIMIT 20", c)
    return statuts, verdicts, ocr, par_jour, revues, erreurs


def afficher() -> None:
    st.title("📈 Suivi du traitement")
    try:
        statuts, verdicts, ocr, par_jour, revues, erreurs = charger()
    except Exception as e:  # noqa: BLE001
        st.error(f"Base de données injoignable : {e}")
        return

    n = dict(zip(statuts["statut"], statuts["n"]))
    total = int(statuts["n"].sum())
    if total == 0:
        st.info("Aucune fiche ingérée pour l'instant. Déposez les PDF et le "
                "manifest.csv dans MinIO puis déclenchez le DAG "
                "`aciege_verification_theses` dans Airflow.")
        return

    classifiees = int(n.get("classifie", 0))
    en_erreur = int(n.get("erreur_texte", 0) + n.get("erreur_classif", 0))

    # ---- Tuiles ----
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("Fiches ingérées", total)
    t2.metric("Textes extraits", int(n.get("texte_ok", 0)) + classifiees)
    t3.metric("Classifiées", classifiees)
    t4.metric("En erreur", en_erreur)
    r = revues.iloc[0]
    t5.metric("Revues humaines", f"{int(r['revues'])} / {int(r['total'])}")

    avancement = classifiees / total if total else 0
    st.progress(avancement, text=f"Avancement : {classifiees}/{total} fiches "
                                 f"traitées ({avancement:.0%})")
    st.divider()

    gauche, droite = st.columns(2)

    # ---- File de traitement par statut ----
    with gauche:
        st.subheader("File de traitement")
        ordre = ["en_attente", "texte_ok", "classifie",
                 "erreur_texte", "erreur_classif"]
        vals = [int(n.get(s, 0)) for s in ordre]
        fig = go.Figure(go.Bar(
            x=[LIBELLES_STATUT[s] for s in ordre], y=vals,
            marker=dict(color=C.BLEU, cornerradius=4),
            text=vals, textposition="outside",
            hovertemplate="%{x} : %{y}<extra></extra>",
        ))
        fig.update_layout(**C.MISE_EN_FORME, height=340,
                          yaxis=dict(showgrid=True, gridcolor="#eceae4"))
        st.plotly_chart(fig, use_container_width=True)

    # ---- Verdicts ----
    with droite:
        st.subheader("Verdicts de classification")
        if verdicts.empty:
            st.caption("Pas encore de verdict — la classification n'a pas tourné.")
        else:
            ordre_v = [v for v in LIBELLES_VERDICT if v in set(verdicts["verdict"])]
            vals = dict(zip(verdicts["verdict"], verdicts["n"]))
            fig = go.Figure(go.Pie(
                labels=[LIBELLES_VERDICT[v] for v in ordre_v],
                values=[int(vals[v]) for v in ordre_v],
                hole=0.55, sort=False,
                marker=dict(colors=[C.STATUT[v] for v in ordre_v],
                            line=dict(color="#fcfcfb", width=2)),
                texttemplate="%{value}", textposition="inside",
                hovertemplate="%{label} : %{value} (%{percent})<extra></extra>",
            ))
            fig.update_layout(**C.MISE_EN_FORME, height=340,
                              legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig, use_container_width=True)

    # ---- Lecture des documents ----
    g2, d2 = st.columns(2)
    with g2:
        st.subheader("Lecture des documents")
        if ocr.empty:
            st.caption("Pas encore d'extraction.")
        else:
            sans = ocr[~ocr["ocr_utilise"].astype(bool)]["n"].sum()
            avec = ocr[ocr["ocr_utilise"].astype(bool)]["n"].sum()
            pages_moy = (ocr["pages"] * ocr["n"]).sum() / max(ocr["n"].sum(), 1)
            c1, c2, c3 = st.columns(3)
            c1.metric("Texte natif", int(sans))
            c2.metric("Passées par l'OCR", int(avec))
            c3.metric("Pages lues (moy.)", f"{pages_moy:.1f}")

    # ---- Débit par jour ----
    with d2:
        st.subheader("Fiches classifiées par jour")
        if par_jour.empty:
            st.caption("Rien de classifié pour l'instant.")
        else:
            fig = go.Figure(go.Bar(
                x=par_jour["jour"], y=par_jour["n"],
                marker=dict(color=C.BLEU, cornerradius=4),
                text=par_jour["n"], textposition="outside",
                hovertemplate="%{x} : %{y} fiches<extra></extra>",
            ))
            fig.update_layout(**C.MISE_EN_FORME, height=280,
                              yaxis=dict(showgrid=True, gridcolor="#eceae4"))
            st.plotly_chart(fig, use_container_width=True)

    # ---- Dernières erreurs ----
    if not erreurs.empty:
        st.subheader("⚠️ Dernières erreurs")
        st.dataframe(erreurs.rename(columns={
            "objet_minio": "Fichier", "statut": "Statut",
            "erreur": "Erreur", "maj_le": "Quand"}),
            use_container_width=True, hide_index=True)
