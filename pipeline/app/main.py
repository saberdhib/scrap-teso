# -*- coding: utf-8 -*-
"""Interface du pipeline ACIEGE — navigation entre les pages."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

st.set_page_config(page_title="ACIEGE — classification des thèses",
                   page_icon="📚", layout="wide")

from views import revue, suivi, thesaurus  # noqa: E402

st.navigation([
    st.Page(thesaurus.afficher, title="Thésaurus", icon="📚",
            url_path="thesaurus", default=True),
    st.Page(suivi.afficher, title="Suivi du traitement", icon="📈",
            url_path="suivi"),
    st.Page(revue.afficher, title="Revue des verdicts", icon="✅",
            url_path="revue"),
]).run()
