"""Stand-alone LECA lightweight-concrete app.   Run:  streamlit run leca_app.py"""
import streamlit as st

from src.lwac_ui import render_leca_page

st.set_page_config(page_title="LECA Lightweight Concrete Mix Design", page_icon="🪶", layout="wide")
render_leca_page()
