# -*- coding: utf-8 -*-
"""Palette validée (CVD ΔE 24.2, cf. dataviz). Ordre catégoriel FIXE."""

# Séries catégorielles — assignées dans cet ordre, jamais recyclées.
CATEGORIEL = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7",
              "#e34948", "#e87ba4", "#eb6834"]

# Magnitude (une seule teinte)
BLEU = "#2a78d6"
BLEU_CLAIR = "#9ec5f4"
GRIS_NEUTRE = "#d5d4cf"

# Statuts (réservés aux états, jamais pour une « série 4 »)
STATUT = {
    "bien_classe": "#008300",           # bon
    "incertain": "#eda100",             # avertissement
    "a_reclasser": "#e34948",           # sérieux
    "code_actuel_invalide": "#52514e",  # neutre
}

TEXTE = "#52514e"

MISE_EN_FORME = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=TEXTE, size=13),
    margin=dict(l=10, r=10, t=40, b=10),
)
