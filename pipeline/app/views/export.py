# -*- coding: utf-8 -*-
"""Page « Export » : classification finale consolidée et téléchargement.

Consolide, pour chaque thèse : la décision humaine si elle existe, sinon le
verdict automatique. Deux modes :
  - prudent (défaut) : seules les corrections VALIDÉES par un humain sont
    appliquées ; le reste garde la classification actuelle.
  - auto : les suggestions « à reclasser » / « code invalide » sont aussi
    appliquées sans validation humaine.
"""

import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from aciege_pipeline import db

from . import couleurs as C


@st.cache_data(ttl=30)
def charger() -> pd.DataFrame:
    q = """
        SELECT t.objet_minio AS fichier, t.titre, t.code_actuel,
               r.code_suggere, r.libelle_suggere, r.score, r.verdict,
               r.decision_humaine
        FROM theses t
        LEFT JOIN LATERAL (SELECT * FROM resultats r
                           WHERE r.these_id = t.id
                           ORDER BY r.cree_le DESC LIMIT 1) r ON TRUE
        ORDER BY t.objet_minio
    """
    with db.conn() as c:
        return pd.read_sql(q, c)


def consolider(df: pd.DataFrame, mode_auto: bool) -> pd.DataFrame:
    df = df.copy()

    def ligne(r):
        d = r["decision_humaine"]
        if isinstance(d, str) and ":" in d:
            return d.split(":", 1)[1], "validé humain"
        if r["verdict"] == "bien_classe":
            return r["code_actuel"], "confirmé auto"
        if pd.isna(r["verdict"]):
            return r["code_actuel"], "non traité"
        if mode_auto and r["verdict"] in ("a_reclasser", "code_actuel_invalide"):
            return r["code_suggere"], "corrigé auto"
        return r["code_actuel"], "en attente de revue"

    res = df.apply(ligne, axis=1, result_type="expand")
    df["code_final"], df["origine_decision"] = res[0], res[1]
    df["change"] = df["code_final"].fillna("") != df["code_actuel"].fillna("")
    return df


def afficher() -> None:
    st.title("📤 Export de la classification finale")
    try:
        brut = charger()
    except Exception as e:  # noqa: BLE001
        st.error(f"Base de données injoignable : {e}")
        return
    if brut.empty:
        st.info("Rien à exporter pour l'instant — lancez d'abord le pipeline.")
        return

    mode_auto = st.toggle(
        "Mode auto : appliquer aussi les suggestions non validées par un humain",
        value=False,
        help="Désactivé (prudent) : seules les décisions humaines et les "
             "« bien classé » changent quelque chose. Activé : les verdicts "
             "« à reclasser » et « code invalide » sont appliqués tels quels.")
    df = consolider(brut, mode_auto)

    n = len(df)
    changes = int(df["change"].sum())
    valides = int((df["origine_decision"] == "validé humain").sum())
    attente = int((df["origine_decision"] == "en attente de revue").sum())
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Thèses", n)
    t2.metric("Classifications modifiées", changes)
    t3.metric("Décisions humaines", valides)
    t4.metric("En attente de revue", attente)
    st.divider()

    gauche, droite = st.columns([1, 1.3])
    with gauche:
        st.subheader("Origine des décisions")
        ordre = ["validé humain", "confirmé auto", "corrigé auto",
                 "en attente de revue", "non traité"]
        pal = {"validé humain": C.CATEGORIEL[0], "confirmé auto": "#008300",
               "corrigé auto": "#eda100", "en attente de revue": C.GRIS_NEUTRE,
               "non traité": "#52514e"}
        counts = df["origine_decision"].value_counts()
        present = [o for o in ordre if o in counts]
        fig = go.Figure(go.Pie(
            labels=present, values=[int(counts[o]) for o in present],
            hole=0.55, sort=False,
            marker=dict(colors=[pal[o] for o in present],
                        line=dict(color="#fcfcfb", width=2)),
            texttemplate="%{value}", textposition="inside",
            hovertemplate="%{label} : %{value} (%{percent})<extra></extra>"))
        fig.update_layout(**C.MISE_EN_FORME, height=330,
                          legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig, use_container_width=True)

    with droite:
        st.subheader("Sous-groupes finaux les plus fréquents")
        top = (df["code_final"].fillna("(aucun)").astype(str)
               .str.split("_").str[0].value_counts().head(15).sort_values())
        fig = go.Figure(go.Bar(
            x=top.values, y=[f"{c} " for c in top.index], orientation="h",
            marker=dict(color=C.BLEU, cornerradius=4),
            text=top.values, textposition="outside",
            hovertemplate="%{y} : %{x} thèses<extra></extra>"))
        fig.update_layout(**C.MISE_EN_FORME, height=330,
                          xaxis=dict(showgrid=True, gridcolor="#eceae4"),
                          yaxis=dict(type="category"))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Aperçu")
    apercu = df[["fichier", "titre", "code_actuel", "code_final",
                 "origine_decision", "verdict", "score"]]
    filtre = st.selectbox("Filtrer", ["tout", "modifiées seulement",
                                      "en attente de revue"])
    if filtre == "modifiées seulement":
        apercu = apercu[df["change"]]
    elif filtre == "en attente de revue":
        apercu = apercu[df["origine_decision"] == "en attente de revue"]
    st.dataframe(apercu, use_container_width=True, height=380, hide_index=True)

    buf = io.StringIO()
    df[["fichier", "titre", "code_actuel", "code_final", "origine_decision",
        "verdict", "code_suggere", "score", "decision_humaine"]].to_csv(
        buf, sep=";", index=False)
    st.download_button(
        "⬇️ Télécharger la classification finale (CSV)",
        data="﻿" + buf.getvalue(),
        file_name="classification_finale.csv", mime="text/csv",
        type="primary")
