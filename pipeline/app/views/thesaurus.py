# -*- coding: utf-8 -*-
"""Page « Thésaurus » : présentation propre de la classification ACIEGE,
avec répartitions (donut, barres, sunburst) et explorateur interactif."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from aciege_pipeline import config

from . import couleurs as C


@st.cache_data(ttl=600)
def charger_concepts() -> pd.DataFrame:
    df = pd.read_csv(config.THESAURUS_CSV, sep=";", encoding="utf-8-sig",
                     dtype=str).fillna("")
    df["niveau"] = df["niveau"].astype(int)
    return df


def afficher() -> None:
    st.title("📚 Thésaurus du Management ACIEGE")
    st.caption("Classification utilisée pour vérifier l'indexation des thèses — "
               "source : aciege.org (CC BY-NC-ND 4.0).")
    try:
        df = charger_concepts()
    except FileNotFoundError:
        st.error(f"Thésaurus introuvable : {config.THESAURUS_CSV}")
        return

    cats = df[df.niveau == 1]
    groupes = df[df.niveau == 2]
    sgs = df[df.niveau == 3]
    termes = df[df.niveau == 4].copy()
    termes["categorie"] = termes["chemin_codes"].str.split(" > ").str[0]
    termes["groupe"] = termes["chemin_codes"].str.split(" > ").str[1]
    n_syn = termes["synonymes"].str.split("|").apply(
        lambda l: len([s for s in l if s and s.strip()])).sum()

    # ---- Tuiles ----
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("Catégories", len(cats))
    t2.metric("Groupes", len(groupes))
    t3.metric("Sous-groupes", len(sgs))
    t4.metric("Termes", len(termes))
    t5.metric("Synonymes", int(n_syn))
    st.divider()

    cat_libelles = dict(zip(cats["code"], cats["libelle"]))
    ordre_cats = sorted(cat_libelles)                    # ordre FIXE des teintes
    couleur_cat = {c: C.CATEGORIEL[i] for i, c in enumerate(ordre_cats)}

    gauche, droite = st.columns([1, 1.4])

    # ---- Donut : termes par catégorie ----
    with gauche:
        st.subheader("Termes par catégorie")
        par_cat = termes.groupby("categorie").size().reindex(ordre_cats).fillna(0)
        etiquettes = [f"{c} — {cat_libelles[c]}" for c in ordre_cats]
        fig = go.Figure(go.Pie(
            labels=etiquettes, values=par_cat.values, hole=0.55, sort=False,
            marker=dict(colors=[couleur_cat[c] for c in ordre_cats],
                        line=dict(color="#fcfcfb", width=2)),
            texttemplate="%{value}", textposition="inside",
            hovertemplate="%{label}<br>%{value} termes (%{percent})<extra></extra>",
        ))
        fig.update_layout(**C.MISE_EN_FORME, height=380, showlegend=True,
                          legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, use_container_width=True)

    # ---- Barres : termes par groupe ----
    with droite:
        st.subheader("Termes par groupe")
        par_grp = (termes.groupby("groupe").size().sort_values()
                   .rename("n").reset_index())
        libelles_grp = dict(zip(groupes["code"], groupes["libelle"]))
        par_grp["nom"] = par_grp["groupe"].map(
            lambda g: f"{g} {libelles_grp.get(g, '')}")
        fig = go.Figure(go.Bar(
            x=par_grp["n"], y=par_grp["nom"], orientation="h",
            marker=dict(color=C.BLEU, cornerradius=4),
            text=par_grp["n"], textposition="outside",
            hovertemplate="%{y}<br>%{x} termes<extra></extra>",
        ))
        fig.update_layout(**C.MISE_EN_FORME, height=520,
                          xaxis=dict(showgrid=True, gridcolor="#eceae4"),
                          yaxis=dict(tickfont=dict(size=11)))
        st.plotly_chart(fig, use_container_width=True)

    # ---- Sunburst : hiérarchie complète ----
    st.subheader("Hiérarchie complète (catégorie → groupe → sous-groupe)")
    par_sg = termes.groupby(termes["chemin_codes"].str.split(" > ").str[2]) \
                   .size().to_dict()
    ids, parents, labels, values, colors = [], [], [], [], []
    for _, r in cats.iterrows():
        ids.append(r["code"]); parents.append("")
        labels.append(f"{r['code']} {r['libelle']}")
        values.append(0); colors.append(couleur_cat.get(r["code"], C.BLEU))
    for _, r in groupes.iterrows():
        ids.append(r["code"]); parents.append(r["chemin_codes"].split(" > ")[0])
        labels.append(f"{r['code']} {r['libelle']}")
        values.append(0); colors.append("")
    for _, r in sgs.iterrows():
        chemin = r["chemin_codes"].split(" > ")
        ids.append(r["code"]); parents.append(chemin[1])
        labels.append(f"{r['code']} {r['libelle']}")
        values.append(int(par_sg.get(r["code"], 0)) or 1); colors.append("")
    fig = go.Figure(go.Sunburst(
        ids=ids, parents=parents, labels=labels, values=values,
        branchvalues="remainder",
        marker=dict(colors=colors, line=dict(color="#fcfcfb", width=2)),
        hovertemplate="%{label}<br>%{value} termes<extra></extra>",
    ))
    fig.update_layout(**C.MISE_EN_FORME, height=560)
    st.plotly_chart(fig, use_container_width=True)

    # ---- Couverture définitions / synonymes ----
    st.subheader("Couverture des termes")
    avec_def = int((termes["definition"] != "").sum())
    avec_syn = int((termes["synonymes"] != "").sum())
    total = len(termes)
    fig = go.Figure()
    for nom, avec, couleur in [("Définition", avec_def, C.BLEU),
                               ("Synonymes", avec_syn, C.BLEU)]:
        fig.add_bar(y=[nom], x=[avec], orientation="h", name="Avec",
                    marker=dict(color=couleur, cornerradius=4),
                    text=[f"{avec} avec"], textposition="inside",
                    showlegend=False)
        fig.add_bar(y=[nom], x=[total - avec], orientation="h", name="Sans",
                    marker=dict(color=C.GRIS_NEUTRE, cornerradius=4),
                    text=[f"{total - avec} sans"], textposition="inside",
                    showlegend=False)
    fig.update_layout(**C.MISE_EN_FORME, barmode="stack", height=160,
                      bargap=0.35, xaxis=dict(range=[0, total]))
    st.plotly_chart(fig, use_container_width=True)

    # ---- Explorateur ----
    st.subheader("🔎 Explorer la classification")
    recherche = st.text_input(
        "Recherche (libellé, synonyme ou définition)",
        placeholder="ex. marketing, VRP, apprentissage…")
    visibles = termes
    if recherche:
        q = recherche.strip().lower()
        masque = (termes["libelle"].str.lower().str.contains(q, regex=False)
                  | termes["synonymes"].str.lower().str.contains(q, regex=False)
                  | termes["definition"].str.lower().str.contains(q, regex=False))
        visibles = termes[masque]
        st.caption(f"{len(visibles)} terme(s) trouvé(s)")
    else:
        choix = st.selectbox(
            "Catégorie", ordre_cats,
            format_func=lambda c: f"{c} — {cat_libelles[c]}")
        visibles = termes[termes["categorie"] == choix]
    st.dataframe(
        visibles[["code", "libelle", "chemin_libelles", "synonymes",
                  "definition"]].rename(columns={
            "code": "Code", "libelle": "Terme", "chemin_libelles": "Chemin",
            "synonymes": "Synonymes", "definition": "Définition"}),
        use_container_width=True, height=420, hide_index=True)
