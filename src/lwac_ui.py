"""Streamlit page for the LECA / lightweight-aggregate-concrete module.

render_leca_page() is used both by the main app (app.py) and by the stand-alone leca_app.py.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .engineering import ScmInput
from .lwac import (MOISTURE_STATES, STATE_DRY, STATE_MC, STATE_SSD, LecaInputs, LightAgg,
                   design_leca_mix)
from .validation import InputError
from . import constants as C

BADGE = {"PASS": "🟢 PASS", "FAIL": "🔴 FAIL", "REVIEW": "🟠 REVIEW", "PENDING": "⚪ PENDING"}


def _agg_inputs(col, title, name, sg, ab, bulk, state, key):
    col.markdown(f"**{title}**")
    sg_v = col.number_input("Oven-dry particle SG (pores included)", 0.3, 3.2, sg, 0.01, key=f"{key}_sg")
    ab_v = col.number_input("24 h water absorption (% of dry mass)", 0.0, 40.0, ab, 0.5, key=f"{key}_ab")
    bk_v = col.number_input("Loose dry bulk density (kg/m³)", 0.0, 2000.0, bulk, 10.0, key=f"{key}_bk")
    st_v = col.selectbox("Moisture state", MOISTURE_STATES, MOISTURE_STATES.index(state), key=f"{key}_st")
    mc = 0.0
    if st_v == STATE_MC:
        mc = col.number_input("Current total moisture (% of dry mass)", 0.0, 60.0, 0.0, 0.5, key=f"{key}_mc")
    frac = 1.0
    if st_v != STATE_SSD:
        frac = col.slider("Share of 24 h absorption taken up before set", 0.0, 1.0, 1.0, 0.05,
                          key=f"{key}_fr", help="1.0 = design for full absorption (safest for paste water).")
    return LightAgg(name, float(sg_v), float(ab_v), float(bk_v) if bk_v > 0 else None, st_v, float(mc), float(frac))


def render_leca_page():
    st.title("🪶 Lightweight Aggregate Concrete (LECA) mix design")
    st.warning("**Research prototype.** Defaults marked ASSUMPTION are engineering starting values, not code "
               "values (no LWAC code was supplied). Trial mixes and lab tests are mandatory.")
    st.caption("Method: absolute-volume balance on oven-dry particle SG → net water vs absorption-water split → "
               "fine/coarse volumes by density closure. See docs/LECA_METHOD.md.")

    a, b = st.columns(2)
    with a:
        st.subheader("Strength and density")
        fck = st.number_input("Characteristic strength fck (MPa)", 10.0, 80.0, 25.0, 1.0, key="leca_fck")
        site = st.selectbox("Site control", ["Good", "Fair"], key="leca_site")
        mode = st.radio("Aggregate split by", ["Target fresh density", "Fine fraction of aggregate volume"],
                        key="leca_mode")
        dens, ffrac = None, None
        if mode == "Target fresh density":
            dens = st.number_input("Target fresh density (kg/m³)", 1000.0, 2300.0, 1800.0, 10.0, key="leca_dens")
        else:
            ffrac = st.slider("Fine share of aggregate volume", 0.0, 1.0, 0.35, 0.01, key="leca_ff")
        tol = st.number_input("Density tolerance ± (kg/m³)", 5.0, 200.0, 50.0, 5.0, key="leca_tol")
        ceil_on = st.checkbox("I know the strength ceiling of this LECA grade", key="leca_ceil_on")
        ceil = st.number_input("LECA strength ceiling (MPa)", 5.0, 100.0, 40.0, 1.0, key="leca_ceil") if ceil_on else None
        slump = st.number_input("Slump (mm)", 25.0, 200.0, 75.0, 5.0, key="leca_slump")
    with b:
        st.subheader("Binder, water, admixture")
        wc_on = st.checkbox("Enter w/cm manually (recommended once trial data exist)", key="leca_wc_on")
        wcm = st.number_input("Free w/cm", 0.20, 0.80, 0.45, 0.01, key="leca_wcm") if wc_on else None
        eff = st.number_input("Strength efficiency vs normal-weight (ASSUMPTION)", 0.15, 1.2, 0.85, 0.01,
                              key="leca_eff", disabled=wc_on)
        w50 = st.number_input("Net water at 50 mm slump (kg/m³, ASSUMPTION)", 100.0, 260.0, 170.0, 1.0, key="leca_w50")
        cement_sg = st.number_input("Cement SG", 2.5, 3.3, 3.15, 0.01, key="leca_csg")
        c1, c2 = st.columns(2)
        gg = c1.number_input("GGBS % of binder", 0.0, 60.0, 0.0, 1.0, key="leca_gg")
        fl = c2.number_input("Fly ash % of binder", 0.0, 40.0, 0.0, 1.0, key="leca_fl")
        adm_dose = c1.number_input("Admixture dose % of binder", 0.0, 3.0, 0.8, 0.1, key="leca_ad")
        adm_red = c2.number_input("Water reduction % (from trials)", 0.0, 40.0, 0.0, 1.0, key="leca_ar")
        air = c1.number_input("Air %", 0.0, 10.0, 2.0, 0.5, key="leca_air")
        minb = c2.number_input("Minimum binder (kg/m³)", 200.0, 500.0, 300.0, 10.0, key="leca_minb")

    st.subheader("Aggregates")
    c, f = st.columns(2)
    coarse = _agg_inputs(c, "LECA (coarse)", "LECA (coarse)", 1.20, 12.0, 650.0, STATE_SSD, "leca_c")
    fine = _agg_inputs(f, "Fine aggregate (sand or LECA fines)", "Fine aggregate", 2.62, 1.0, 1600.0,
                       STATE_SSD, "leca_f")

    scms = [ScmInput(n, float(p), C.DEFAULT_SG[n]) for n, p in (("GGBS", gg), ("Fly ash", fl)) if p > 0]
    mi = LecaInputs(
        fck=fck, site_control=site, target_fresh_density=dens, density_tolerance=tol,
        fine_vol_fraction=ffrac, coarse=coarse, fine=fine, leca_strength_ceiling_mpa=ceil,
        cement_sg=cement_sg, scms=scms, wcm_manual=wcm, strength_efficiency=eff, slump=slump,
        water_base_50mm=w50, admixture_type="None" if (adm_dose == 0 and adm_red == 0) else "Superplasticiser",
        admixture_dose_pct=adm_dose, admixture_water_reduction_pct=adm_red, air_pct=air, min_binder=minb)

    if not st.button("Calculate LECA mix", type="primary", key="leca_go"):
        return
    try:
        r = design_leca_mix(mi)
    except InputError as e:
        st.error("\n\n".join(e.problems))
        return

    st.session_state["leca_res"] = r
    m = st.columns(4)
    m[0].metric("Fresh density", f"{r.fresh_density:.0f} kg/m³")
    m[1].metric("Free w/cm", f"{r.wcm_final:.3f}")
    m[2].metric("Water to add", f"{r.water_to_add:.0f} kg/m³")
    m[3].metric("Target mean strength", f"{r.target_strength:.1f} MPa")
    for w in r.warnings:
        st.warning(w)
    df = pd.DataFrame(r.to_rows())
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button("Download batch quantities (CSV)", df.to_csv(index=False).encode("utf-8"),
                       "leca_mix.csv", "text/csv", key="leca_csv")
    st.subheader("Checks")
    st.dataframe(pd.DataFrame([{"Status": BADGE.get(k.status, k.status), "Check": k.name, "Detail": k.detail}
                               for k in r.checks]), hide_index=True, use_container_width=True)
    with st.expander("Step-by-step trace"):
        st.dataframe(pd.DataFrame([{"Step": s.no, "Name": s.name, "Formula": s.formula, "Value": s.value,
                                    "Source": s.source} for s in r.steps]), hide_index=True,
                     use_container_width=True)
