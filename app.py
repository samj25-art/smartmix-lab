"""
AI-Based Software Interface for Concrete Mix Design  -  Streamlit application
Run:  streamlit run app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import constants as C  # noqa: E402
from src.data_loading import (DatasetInvalid, DatasetUnavailable, data_quality_report,  # noqa: E402
                              load_dataset, read_any, standardise, DEFAULT_CSV, try_download)
from src.engineering import (MixInputs, ScmInput, design_mix, result_to_ml_features)  # noqa: E402
from src.model_training import MODEL_DIR, TrainingError, model_status, train_and_save  # noqa: E402
from src.prediction import ModelNotTrained, predict_strength  # noqa: E402
from src.report import build_pdf, new_report_id, results_csv_bytes  # noqa: E402
from src.validation import InputError  # noqa: E402
from src.workbook_replica import AUDIT_FINDINGS, run_workbook_logic  # noqa: E402

st.set_page_config(page_title="AI Concrete Mix Design", page_icon="🏗️", layout="wide")

PAGES = ["🏠 Home", "📝 Mix Input", "🧮 Engineering Calculator", "🤖 AI Model (train / evaluate)",
         "🔮 AI Strength Prediction", "⚖️ Candidate Comparison", "📊 Results & Reports",
         "🔎 Workbook Audit"]

DISCLAIMER = ("**Research prototype.** This software is an academic project. It is **not** a substitute "
              "for an approved mix design, trial mixes and laboratory testing, and makes no claim of "
              "IS-code certification.")

ML_DEFAULTS = {"cement": 300.0, "slag": 0.0, "fly_ash": 0.0, "water": 180.0,
               "superplasticizer": 0.0, "coarse_agg": 1000.0, "fine_agg": 800.0, "age": 28.0}


# ------------------------------------------------------------------------------ state
def ss_init():
    st.session_state.setdefault("mi", None)          # MixInputs
    st.session_state.setdefault("res", None)         # MixResult
    st.session_state.setdefault("pred", None)        # Prediction
    st.session_state.setdefault("ml_row", dict(ML_DEFAULTS))
    st.session_state.setdefault("ml_row_confirmed", False)
    st.session_state.setdefault("target_mpa", None)
    st.session_state.setdefault("report_id", new_report_id())
    st.session_state.setdefault("cand_df", None)


def badge(status: str) -> str:
    return {"PASS": "🟢 PASS", "FAIL": "🔴 FAIL", "REVIEW": "🟠 REVIEW", "PENDING": "⚪ PENDING"}.get(status, status)


def provenance_legend():
    st.caption("🟦 **User-provided** · 🟩 **Calculated** (IS 10262 procedure) · 🟪 **Predicted** (ML model) · "
               "🟥 **Needs laboratory verification**")


# ------------------------------------------------------------------------------ pages
def page_home():
    st.title("🏗️ AI-Based Software Interface for Concrete Mix Design")
    st.caption("Government College of Engineering, Amravati - Department of Civil Engineering - Minor Project")
    st.warning(DISCLAIMER)

    c1, c2, c3 = st.columns(3)
    status = model_status()
    c1.metric("ML model", "Trained" if status.get("trained") else "NOT trained")
    if status.get("trained"):
        m = status["test_metrics"]
        c2.metric("Test RMSE (MPa)", f"{m['RMSE_MPa']:.2f}")
        c3.metric("Test R²", f"{m['R2']:.3f}")
    else:
        c2.metric("Test RMSE (MPa)", "-")
        c3.metric("Test R²", "-")
        st.info("No model has been trained yet, so **no accuracy figures exist**. Go to "
                "**AI Model** to train on the UCI dataset.")
    if status.get("trained"):
        st.caption(f"Selected: **{status['selected_model']}** · trained {status['trained_at_utc']} UTC · "
                   f"{status['dataset_rows_used']} rows used ({status['n_train']} train / {status['n_test']} test) "
                   "· metrics are from the held-out test set.")

    st.subheader("Objectives")
    st.markdown("""
- Automate concrete mix proportioning following the **IS 10262:2019** procedure (replacing manual look-ups and arithmetic).
- Provide a **machine-learning estimate** of compressive strength trained on a public laboratory dataset (UCI, 1030 mixes).
- Keep the two **strictly separate**: a deterministic engineering calculator and a statistical predictor.
- Generate traceable **CSV / PDF reports** with assumptions, warnings and verification status.
""")
    st.subheader("System workflow")
    st.markdown("""
```
Mix Input ─► Engineering Calculator (IS 10262, deterministic) ─► quantities + code checks ─┐
     │                                                                                     ├─► Results & PDF/CSV
     └────► AI Strength Prediction (UCI-trained model, 8 inputs) ─► MPa + uncertainty ──────┘
                         ▲
        AI Model page: load data → validate → split → cross-validate → test once → save
```
""")
    st.subheader("Modules")
    st.table(pd.DataFrame({
        "Module": ["Mix Input", "Engineering Calculator", "AI Model", "AI Strength Prediction",
                   "Candidate Comparison (experimental)", "Results & Reports", "Workbook Audit"],
        "Purpose": ["Collect inputs, show which feed which module",
                    "IS 10262 Sections 2-3: target strength, w/c, water, binder, aggregates, corrections",
                    "Train / compare / evaluate Linear, Random Forest, Hist-GB",
                    "Predict MPa from 8 mix features + age, with range warnings",
                    "Compare user-entered candidate mixes (no automatic 'best' claim)",
                    "Dashboard, CSV, PDF", "Compare your Excel workbook against the IS-based calculator"]}))
    st.subheader("What this tool does NOT do")
    st.markdown("- It does not predict slump, durability or permeability.\n"
                "- Self-compacting and mass concrete (IS 10262 Sections 4-5) are not implemented.\n"
                "- The AI model does not 'design' mixes and is not IS-compliant by itself.\n"
                "- IS 456:2000 limits are not in the supplied files → flagged for verification.")


def _scm_inputs():
    st.markdown("**Supplementary cementitious materials** (percent of *total* cementitious material)")
    c1, c2, c3 = st.columns(3)
    out = []
    fa = c1.number_input("Fly ash %", 0.0, 60.0, 0.0, 1.0, key="scm_fa")
    fa_sg = c1.number_input("Fly ash SG", 1.5, 3.5, C.DEFAULT_SG["Fly ash"], 0.01, key="scm_fa_sg")
    gg = c2.number_input("GGBS %", 0.0, 70.0, 0.0, 1.0, key="scm_gg")
    gg_sg = c2.number_input("GGBS SG", 2.0, 3.5, C.DEFAULT_SG["GGBS"], 0.01, key="scm_gg_sg")
    sf = c3.number_input("Silica fume %", 0.0, 15.0, 0.0, 0.5, key="scm_sf")
    sf_sg = c3.number_input("Silica fume SG", 1.8, 3.0, C.DEFAULT_SG["Silica fume"], 0.01, key="scm_sf_sg")
    for name, pct, sg in (("Fly ash", fa, fa_sg), ("GGBS", gg, gg_sg), ("Silica fume", sf, sf_sg)):
        if pct > 0:
            out.append(ScmInput(name, float(pct), float(sg)))
    return out


def page_mix_input():
    st.title("📝 Concrete Mix Input")
    provenance_legend()
    st.info("**Which inputs feed what?**  Section A feeds the *engineering calculator*. Section B (8 values) "
            "feeds the *AI model*. Section C (prices) is only used for cost comparison. Nothing is silently "
            "invented: values marked *(default)* are taken from the IS 10262 worked examples and you must "
            "confirm them on the calculator page.")

    st.header("A · Engineering calculator inputs")
    c1, c2, c3 = st.columns(3)
    grade = c1.selectbox("Grade of concrete", C.ALL_GRADES, index=C.ALL_GRADES.index(40),
                         format_func=lambda g: f"M{g}")
    site = c1.selectbox("Degree of site control", ["Good", "Fair"])
    sd_over = c1.number_input("Established standard deviation (MPa) - 0 = use IS Table 2", 0.0, 15.0, 0.0, 0.1)
    cement_type = c2.selectbox("Cement type", ["OPC 43", "OPC 53", "OPC 33", "PPC"])
    cement_sg = c2.number_input("Specific gravity of cement", 2.5, 3.3,
                                C.DEFAULT_SG["PPC" if cement_type == "PPC" else "OPC"], 0.01)
    reinforced = c2.checkbox("Reinforced concrete member", True)
    exposure = c3.selectbox("Exposure condition (IS 456)", list(C.IS456_REINFORCED), index=2)
    hsc = grade >= 65
    msa_opts = list(C.TABLE7_WATER) if hsc else list(C.TABLE4_WATER)
    msa = c3.selectbox("Nominal maximum aggregate size (mm)", msa_opts,
                       index=msa_opts.index(20.0))
    slump = c3.number_input("Required slump at placing (mm)", 25.0, 200.0, 75.0, 5.0)

    c1, c2, c3 = st.columns(3)
    shape = c1.selectbox("Coarse aggregate type", list(C.SHAPE_WATER_REDUCTION))
    zones = list(C.TABLE10_CA[msa]) if hsc else list(C.TABLE5_CA[msa])
    zone = c2.selectbox("Fine aggregate grading zone (IS 383)", zones, index=zones.index("II") if "II" in zones else 0)
    wc_manual = None
    if not hsc:
        use_manual = c3.checkbox("Enter w/c read from IS 10262 Fig. 1 myself", cement_type in ("OPC 33", "OPC 53"))
        if use_manual:
            wc_manual = c3.number_input("w/c from Fig. 1", 0.20, 0.80, 0.40, 0.005)
        else:
            c3.caption("w/c will be *estimated* from Fig. 1 curve 2 (3 anchor points from the standard).")
    else:
        c3.caption("High strength: w/cm from IS 10262 Table 8 (interpolated).")

    c1, c2, c3 = st.columns(3)
    sg_ca = c1.number_input("SG coarse aggregate (SSD) (default)", 2.0, 3.2, C.DEFAULT_SG["Coarse aggregate"], 0.01)
    sg_fa = c2.number_input("SG fine aggregate (SSD) (default)", 2.0, 3.2, C.DEFAULT_SG["Fine aggregate"], 0.01)
    air_over = c3.number_input("Air content override % (0 = IS table; needs ≥5 site results)", 0.0, 5.0, 0.0, 0.1)
    c1, c2, c3 = st.columns(3)
    abs_ca = c1.number_input("Water absorption - coarse (%) (default)", 0.0, 10.0, 0.5, 0.1)
    abs_fa = c2.number_input("Water absorption - fine (%) (default)", 0.0, 10.0, 1.0, 0.1)
    c1, c2 = st.columns(2)
    cond_ca = c1.selectbox("Coarse aggregate condition", ["SSD", "Oven-dry", "Field moist"])
    tot_ca = c1.number_input("Coarse total moisture % (field moist)", 0.0, 15.0, 0.0, 0.1) if cond_ca == "Field moist" else 0.0
    cond_fa = c2.selectbox("Fine aggregate condition", ["SSD", "Oven-dry", "Field moist"])
    tot_fa = c2.number_input("Fine total moisture % (field moist)", 0.0, 25.0, 0.0, 0.1) if cond_fa == "Field moist" else 0.0

    scms = _scm_inputs()
    c1, c2, c3 = st.columns(3)
    inc = c1.number_input("Cementitious increase for SCM mixes (%) (cl. 5.4.1: ~10 for fly ash ≥ 20 %)",
                          0.0, 25.0, 0.0, 1.0)
    pump = c2.number_input("Coarse-aggregate reduction for pumping (%)", 0.0, 10.0 if not hsc else 5.0, 0.0, 1.0)
    adm_type = c3.selectbox("Chemical admixture", list(C.ADMIXTURE_TYPES))
    c1, c2, c3 = st.columns(3)
    adm_dose = c1.number_input("Admixture dose (% by mass of cementitious)", 0.0, 3.0, 0.0, 0.05)
    adm_red = c2.number_input("Water reduction from TRIALS (%) - never inferred from dose", 0.0, 45.0, 0.0, 1.0)
    adm_sg = c3.number_input("Admixture SG", 1.0, 1.3, C.DEFAULT_SG["Admixture"], 0.005)

    st.header("B · AI model inputs (8 features the model was trained on)")
    st.caption("Units: kg per m³ of concrete, age in days. **Placeholder example values are shown until you "
               "edit and confirm them.** Silica fume, aggregate shape, cement grade and admixture type are not "
               "model inputs.")
    row = st.session_state["ml_row"]
    cols = st.columns(4)
    new_row = {}
    for i, f in enumerate(C.FEATURES):
        new_row[f] = cols[i % 4].number_input(C.FEATURE_LABELS[f], 0.0, 2000.0 if f != "age" else 3650.0,
                                              float(row[f]), 1.0 if f != "superplasticizer" else 0.1, key=f"ml_{f}")
    if new_row != row:
        st.session_state["ml_row_confirmed"] = False
    st.session_state["ml_row"] = new_row
    st.checkbox("I confirm these 8 values describe my mix", key="ml_row_confirmed")
    target = st.number_input("Requested target strength to compare with (MPa) - 0 = none", 0.0, 120.0, 0.0, 0.5)
    st.session_state["target_mpa"] = float(target) if target > 0 else None

    st.header("C · Material costs (optional, per kg)")
    use_cost = st.checkbox("Enter material prices for cost comparison", False)
    prices = {}
    if use_cost:
        c1, c2, c3, c4 = st.columns(4)
        prices = {"cement": c1.number_input("Cement price /kg", 0.0, 100.0, 0.0, 0.1),
                  "fine_aggregate": c2.number_input("Fine aggregate /kg", 0.0, 10.0, 0.0, 0.05),
                  "coarse_aggregate": c3.number_input("Coarse aggregate /kg", 0.0, 10.0, 0.0, 0.05),
                  "admixture": c4.number_input("Admixture /kg", 0.0, 1000.0, 0.0, 1.0)}
        c1, c2, c3 = st.columns(3)
        prices["Fly ash"] = c1.number_input("Fly ash /kg", 0.0, 50.0, 0.0, 0.1)
        prices["GGBS"] = c2.number_input("GGBS /kg", 0.0, 50.0, 0.0, 0.1)
        prices["Silica fume"] = c3.number_input("Silica fume /kg", 0.0, 500.0, 0.0, 1.0)

    st.session_state["mi"] = MixInputs(
        fck=float(grade), site_control=site, std_dev_override=float(sd_over) or None,
        cement_type=cement_type, cement_sg=float(cement_sg), exposure=exposure, reinforced=reinforced,
        msa=float(msa), slump=float(slump), aggregate_shape=shape, fa_zone=zone, wc_manual=wc_manual,
        scms=scms, binder_increase_pct=float(inc), admixture_type=adm_type,
        admixture_dose_pct=float(adm_dose), admixture_water_reduction_pct=float(adm_red),
        admixture_sg=float(adm_sg), pumpable_ca_reduction_pct=float(pump), sg_ca=float(sg_ca),
        sg_fa=float(sg_fa), abs_ca=float(abs_ca), abs_fa=float(abs_fa), moisture_mode_ca=cond_ca,
        moisture_mode_fa=cond_fa, moisture_total_ca=float(tot_ca), moisture_total_fa=float(tot_fa),
        air_override_pct=float(air_over) or None, prices_per_kg=prices)
    st.success("Inputs stored. Continue to **Engineering Calculator** or **AI Strength Prediction**.")


def page_calculator():
    st.title("🧮 Engineering Mix Calculator (IS 10262:2019)")
    st.caption("Deterministic calculation - independent of the AI model.")
    mi = st.session_state["mi"]
    if mi is None:
        st.info("Fill in **Mix Input** first.")
        return
    defaults = [f"SG coarse {mi.sg_ca}, SG fine {mi.sg_fa}", f"absorption {mi.abs_ca} % / {mi.abs_fa} %",
                f"admixture water reduction {mi.admixture_water_reduction_pct} %",
                f"slump {mi.slump:g} mm", f"cement SG {mi.cement_sg}"]
    st.markdown("**Please confirm these important engineering inputs:** " + "; ".join(defaults))
    ok = st.checkbox("I have checked these values against my material test reports", False)
    if st.button("Run engineering calculation", disabled=not ok):
        try:
            st.session_state["res"] = design_mix(mi)
        except InputError as e:
            st.session_state["res"] = None
            for p in e.problems:
                st.error(p)
    res = st.session_state["res"]
    if res is None:
        return
    provenance_legend()
    st.subheader(f"Result - {res.path}")
    c = st.columns(5)
    c[0].metric("Target strength", f"{res.target_strength:.1f} MPa")
    c[1].metric("Free w/cm", f"{res.wcm_final:.3f}")
    c[2].metric("Cementitious", f"{res.binder_total:.0f} kg/m³")
    c[3].metric("Water to add", f"{res.water_to_add:.0f} L/m³")
    c[4].metric("Fresh density", f"{res.fresh_density:.0f} kg/m³")
    st.dataframe(pd.DataFrame(res.to_rows()), hide_index=True)
    if res.cost_per_m3 is not None:
        st.metric("Material cost (user prices)", f"{res.cost_per_m3:,.0f} per m³")
    for w in res.warnings:
        st.warning(w)
    st.subheader("Engineering checks")
    st.dataframe(pd.DataFrame([{"Status": badge(k.status), "Check": k.name, "Detail": k.detail,
                                "Source": k.source} for k in res.checks]), hide_index=True)
    st.subheader("Calculation trace (formulas, units, sources)")
    st.dataframe(pd.DataFrame([{"Step": s.no, "Description": s.name, "Formula / basis": s.formula,
                                "Result": s.value, "Source": s.source} for s in res.steps]), hide_index=True)
    mix_chart(res)


def mix_chart(res):
    parts = {"Cement": res.cement, **res.scm_masses, "Water": res.water_to_add,
             "Fine agg.": res.fa_field, "Coarse agg.": res.ca_field, "Admixture ×10": res.admixture_mass * 10}
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.bar(list(parts), list(parts.values()), color="#2f6fb0")
    ax.set_ylabel("kg/m³ (water L/m³)")
    ax.set_title("Mix quantities per m³ (field condition)")
    plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def page_model():
    st.title("🤖 AI Model - train and evaluate")
    st.caption("Dataset: UCI Concrete Compressive Strength (1030 lab mixes). Source: " + C.UCI_PAGE)
    status = model_status()

    st.subheader("1 · Dataset")
    df = None
    c1, c2 = st.columns(2)
    if c1.button("Load local file / try automatic download"):
        try:
            df = load_dataset(allow_download=True)
            st.session_state["train_df"] = df
            st.success(f"Loaded {len(df)} rows.")
        except (DatasetUnavailable, DatasetInvalid) as e:
            st.error(str(e))
            st.info("**Offline?** Download the dataset from the UCI page above, then upload it below "
                    "(CSV, XLS/XLSX or the UCI .zip).")
    up = c2.file_uploader("…or upload the dataset", type=["csv", "xls", "xlsx", "zip"])
    if up is not None:
        try:
            df = standardise(read_any(up))
            st.session_state["train_df"] = df
            st.success(f"Uploaded and recognised {len(df)} rows.")
        except DatasetInvalid as e:
            st.error(str(e))
    df = st.session_state.get("train_df")
    if df is None and DEFAULT_CSV.exists():
        try:
            df = load_dataset(allow_download=False)
            st.session_state["train_df"] = df
        except DatasetInvalid as e:
            st.error(str(e))
    if df is None:
        st.warning("No dataset loaded - the model cannot be trained.")
    else:
        rep = data_quality_report(df)
        st.write(f"**{rep['rows']} rows.** Duplicates: {rep['duplicate_rows']} · Missing: "
                 f"{sum(rep['missing_values'].values())} · IQR outliers (information only, none removed): "
                 f"{sum(rep['iqr_outlier_counts'].values())}")
        for p in rep["problems"]:
            st.warning(p)
        st.dataframe(df.describe().T)

    st.subheader("2 · Train")
    fast = st.checkbox("Fast mode (smaller grids - for a quick demo)", False)
    if st.button("Train and evaluate", disabled=df is None):
        box = st.empty()
        try:
            with st.spinner("Training ... (a few minutes on a laptop in full mode)"):
                train_and_save(df, fast=fast, progress=lambda m: box.write("⏳ " + m))
            box.success("Training finished.")
            status = model_status()
        except TrainingError as e:
            box.error(str(e))
        except Exception as e:  # noqa: BLE001
            box.error(f"Training failed: {e}")

    st.subheader("3 · Results")
    if not status.get("trained"):
        st.error("**Model not trained.** No metrics are shown because none exist.")
        return
    m = status["test_metrics"]
    c = st.columns(4)
    c[0].metric("MAE (test)", f"{m['MAE_MPa']:.2f} MPa")
    c[1].metric("RMSE (test)", f"{m['RMSE_MPa']:.2f} MPa")
    c[2].metric("R² (test)", f"{m['R2']:.3f}")
    c[3].metric("Selected", status["selected_model"])
    st.caption(f"Trained {status['trained_at_utc']} UTC · {status['dataset_rows_used']} rows used "
               f"({status['rows_excluded']} excluded) · train {status['n_train']} / test {status['n_test']} · "
               f"seed {status['seed']} · scikit-learn {status['versions']['sklearn']}")
    st.markdown("**Model comparison (5-fold grouped cross-validation on the training set only; the test set "
                "was not used for selection)**")
    st.dataframe(pd.DataFrame(status["cv_results"]), hide_index=True)
    st.markdown("Test-set scores of every candidate (shown for transparency, not used for selection):")
    st.dataframe(pd.DataFrame(status["test_metrics_all_models_for_information"]).T)
    tp = MODEL_DIR / "test_predictions.csv"
    if tp.exists():
        t = pd.read_csv(tp)
        a, b = st.columns(2)
        fig, ax = plt.subplots(figsize=(4.5, 4))
        ax.scatter(t["actual"], t["predicted"], s=12, alpha=.6)
        lim = [min(t["actual"].min(), t["predicted"].min()), max(t["actual"].max(), t["predicted"].max())]
        ax.plot(lim, lim, "r--", lw=1)
        ax.set_xlabel("Actual strength (MPa)")
        ax.set_ylabel("Predicted strength (MPa)")
        ax.set_title("Actual vs predicted (test set)")
        fig.tight_layout()
        a.pyplot(fig)
        plt.close(fig)
        fig, ax = plt.subplots(figsize=(4.5, 4))
        ax.scatter(t["predicted"], t["residual"], s=12, alpha=.6)
        ax.axhline(0, color="r", lw=1)
        ax.set_xlabel("Predicted (MPa)")
        ax.set_ylabel("Residual (actual - predicted)")
        ax.set_title("Residuals (test set)")
        fig.tight_layout()
        b.pyplot(fig)
        plt.close(fig)
    fi = MODEL_DIR / "feature_importance.csv"
    if fi.exists():
        imp = pd.read_csv(fi)
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.barh(imp["feature"][::-1], imp["importance_rmse_increase"][::-1], xerr=imp["std"][::-1], color="#2f6fb0")
        ax.set_xlabel("Increase in test RMSE when feature is shuffled (MPa)")
        ax.set_title("Permutation importance")
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)


def page_prediction():
    st.title("🔮 AI Compressive-Strength Prediction")
    status = model_status()
    if not status.get("trained"):
        st.error("**The model is not trained.** Train it on the *AI Model* page first. No prediction is possible.")
        return
    st.info("Prediction uses **only** the 8 trained features. It does not predict slump, durability or "
            "permeability, and it is not a guaranteed 28-day strength - the strength is for the **curing age "
            "you enter**.")
    row = dict(st.session_state["ml_row"])
    for f in C.FEATURES:
        st.session_state.setdefault(f"pred_{f}", float(row[f]))
    if st.button("⬅ Use the mix calculated on the Engineering page"):
        res = st.session_state["res"]
        if res is None:
            st.warning("Run the engineering calculation first.")
        else:
            feats = result_to_ml_features(res, st.session_state.get("pred_age", row["age"]))
            for k, v in feats.items():
                st.session_state[f"pred_{k}"] = float(round(v, 2))
            st.session_state["ml_row_confirmed"] = False
            mi = st.session_state["mi"]
            if mi and any(s.name in ("Silica fume", "Metakaolin") for s in mi.scms):
                st.warning("Silica fume / metakaolin have no column in the model and were dropped - "
                           "this will under-predict.")
    cols = st.columns(4)
    edited = {}
    for i, f in enumerate(C.FEATURES):
        edited[f] = cols[i % 4].number_input(C.FEATURE_LABELS[f], 0.0, 2000.0 if f != "age" else 3650.0,
                                             step=1.0 if f != "superplasticizer" else 0.1, key=f"pred_{f}")
    if edited != row:
        st.session_state["ml_row_confirmed"] = False
    st.session_state["ml_row"] = edited
    target = st.session_state.get("target_mpa")
    target = st.number_input("Target strength (MPa) to compare with - 0 = none", 0.0, 120.0,
                             float(target or 0.0), 0.5)
    confirmed = st.checkbox("I confirm these values describe my mix (not the placeholder example)",
                            key="ml_row_confirmed")
    if st.button("Predict strength", disabled=not confirmed):
        try:
            st.session_state["pred"] = predict_strength(edited, target if target > 0 else None)
        except InputError as e:
            st.session_state["pred"] = None
            for p in e.problems:
                st.error(p)
        except ModelNotTrained as e:
            st.error(str(e))
    p = st.session_state["pred"]
    if p is None:
        return
    st.subheader("🟪 Predicted values")
    c = st.columns(4)
    c[0].metric(f"Strength at {p.age_days:g} d", f"{p.strength_mpa:.1f} MPa")
    c[1].metric("Approx. 90 % band", f"{p.interval_low:.1f} – {p.interval_high:.1f}")
    if p.target_mpa is not None:
        c[2].metric("Target", f"{p.target_mpa:.1f} MPa")
        c[3].metric("Predicted − target", f"{p.difference_to_target:+.1f} MPa")
    fig, ax = plt.subplots(figsize=(6, 2.2))
    ax.barh(["Predicted"], [p.strength_mpa], xerr=[[p.strength_mpa - p.interval_low], [p.interval_high - p.strength_mpa]],
            color="#7b4bb7", capsize=5)
    if p.target_mpa is not None:
        ax.axvline(p.target_mpa, color="r", ls="--", label="Target")
        ax.legend()
    ax.set_xlabel("MPa")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    for w in p.warnings:
        (st.warning if "outside the training" in w or "unusual" in w or "meaningless" in w else st.info)(w)
    st.caption(f"Model: {p.model_name} · test MAE {p.test_metrics['MAE_MPa']:.2f} MPa, "
               f"RMSE {p.test_metrics['RMSE_MPa']:.2f} MPa, R² {p.test_metrics['R2']:.3f}")


def page_candidates():
    st.title("⚖️ Candidate Mix Comparison (experimental)")
    st.warning("Transparent comparison table only. The app does **not** rank, optimise or recommend, and "
               "nothing here is approved or code-compliant until trial mixes and lab tests confirm it.")
    if not model_status().get("trained"):
        st.error("Train the AI model first (strength column needs it).")
        return
    if st.session_state["cand_df"] is None:
        base = dict(st.session_state["ml_row"])
        rows = []
        for i, d in enumerate((0, -10, -20), start=1):
            r = dict(base)
            r["water"] = max(1.0, base["water"] + d)
            r = {"name": f"Candidate {i}", **r}
            rows.append(r)
        st.session_state["cand_df"] = pd.DataFrame(rows)
    st.caption("Edit or add rows (units kg/m³, age in days).")
    df = st.data_editor(st.session_state["cand_df"], num_rows="dynamic")
    st.session_state["cand_df"] = df
    c1, c2, c3 = st.columns(3)
    target = c1.number_input("Target strength (MPa)", 0.0, 120.0, float(st.session_state.get("target_mpa") or 0.0), 0.5)
    p_cem = c2.number_input("Cement price /kg", 0.0, 100.0, 0.0, 0.1)
    p_agg = c3.number_input("Aggregate price /kg (both)", 0.0, 10.0, 0.0, 0.01)
    c1, c2, c3 = st.columns(3)
    p_slag = c1.number_input("Slag price /kg", 0.0, 50.0, 0.0, 0.1)
    p_fa = c2.number_input("Fly ash price /kg", 0.0, 50.0, 0.0, 0.1)
    p_sp = c3.number_input("Superplasticizer price /kg", 0.0, 1000.0, 0.0, 1.0)
    min_binder = st.number_input("Minimum binder content constraint (kg/m³) - from your exposure condition",
                                 0.0, 600.0, 0.0, 10.0)
    max_wb = st.number_input("Maximum water/binder ratio constraint - 0 = none", 0.0, 1.0, 0.0, 0.01)
    if st.button("Compare candidates"):
        out = []
        for _, r in df.iterrows():
            row = {f: float(r[f]) for f in C.FEATURES}
            line = {"Candidate": r.get("name", "")}
            try:
                pr = predict_strength(row, target if target > 0 else None)
                line["Predicted MPa"] = round(pr.strength_mpa, 1)
                line["90 % band"] = f"{pr.interval_low:.0f}-{pr.interval_high:.0f}"
                line["vs target"] = None if pr.difference_to_target is None else round(pr.difference_to_target, 1)
                line["Extrapolating?"] = "YES" if pr.extrapolating else "no"
            except InputError as e:
                line["Predicted MPa"] = "invalid: " + "; ".join(e.problems)
            binder = row["cement"] + row["slag"] + row["fly_ash"]
            line["Binder kg/m³"] = round(binder, 0)
            line["w/b"] = round(row["water"] / binder, 3) if binder else None
            line["Binder ≥ min?"] = "-" if not min_binder else ("ok" if binder >= min_binder else "FAIL")
            line["w/b ≤ max?"] = "-" if not max_wb else ("ok" if binder and row["water"] / binder <= max_wb else "FAIL")
            vols = (row["cement"] / 3.15 + row["slag"] / 2.9 + row["fly_ash"] / 2.2 + row["water"]
                    + row["superplasticizer"] / 1.1 + row["coarse_agg"] / 2.74 + row["fine_agg"] / 2.65) / 1000
            line["Volume check (≈1 m³)"] = f"{vols:.3f}" + ("" if 0.96 <= vols <= 1.02 else " ⚠")
            cost = (row["cement"] * p_cem + (row["coarse_agg"] + row["fine_agg"]) * p_agg + row["slag"] * p_slag
                    + row["fly_ash"] * p_fa + row["superplasticizer"] * p_sp)
            line["Cost /m³"] = round(cost, 0) if (p_cem or p_agg or p_slag or p_fa or p_sp) else "-"
            out.append(line)
        st.dataframe(pd.DataFrame(out), hide_index=True)
        st.caption("Volume check uses default SGs (cement 3.15, slag 2.9, fly ash 2.2, admixture 1.1, CA 2.74, "
                   "FA 2.65) and ignores air (~1-2 %). A high predicted strength alone is not a recommendation.")


def page_results():
    st.title("📊 Results Dashboard & Reports")
    mi, res, pred = st.session_state["mi"], st.session_state["res"], st.session_state["pred"]
    meta = model_status()
    provenance_legend()
    if mi is None:
        st.info("Nothing to report yet - fill in **Mix Input**.")
        return
    st.subheader("🟦 Input summary")
    st.write(f"M{mi.fck:g} · {mi.cement_type} · {mi.exposure} exposure · {mi.msa:g} mm · slump {mi.slump:g} mm · "
             f"admixture: {mi.admixture_type} (water reduction {mi.admixture_water_reduction_pct:g} % user value)")
    st.subheader("🟩 Calculated (IS 10262 procedure)")
    if res is None:
        st.warning("Engineering calculation not run.")
    else:
        st.dataframe(pd.DataFrame(res.to_rows()), hide_index=True)
        mix_chart(res)
        st.dataframe(pd.DataFrame([{"Status": badge(k.status), "Check": k.name, "Detail": k.detail} for k in res.checks]),
                     hide_index=True)
        n_fail = sum(k.status == "FAIL" for k in res.checks)
        st.metric("Engineering check status", "FAIL" if n_fail else "No failed check (trials still pending)")
    st.subheader("🟪 Predicted (ML)")
    if pred is None:
        st.info("No ML prediction available (model not trained or prediction not run).")
    else:
        st.write(f"**{pred.strength_mpa:.1f} MPa** at {pred.age_days:g} days (approx. 90 % band "
                 f"{pred.interval_low:.1f}–{pred.interval_high:.1f}) - model {pred.model_name}")
    st.subheader("Model evaluation")
    if meta.get("trained"):
        m = meta["test_metrics"]
        st.write(f"MAE {m['MAE_MPa']:.2f} MPa · RMSE {m['RMSE_MPa']:.2f} MPa · R² {m['R2']:.3f} "
                 f"(held-out test, n={meta['n_test']})")
    else:
        st.write("Model not trained - no metrics.")
    st.subheader("🟥 Needs laboratory verification")
    st.write("Trial mixes, workability, 28-day cube strength, durability, IS 456 limits - **not done by this software**.")
    st.subheader("Downloads")
    c1, c2 = st.columns(2)
    c1.download_button("⬇ Results CSV", results_csv_bytes(mi, res, pred), "mix_results.csv", "text/csv")
    try:
        pdf = build_pdf(mi, res, pred, meta, st.session_state["report_id"])
        c2.download_button("⬇ PDF report", pdf, f"{st.session_state['report_id']}.pdf", "application/pdf")
    except Exception as e:  # noqa: BLE001
        c2.error(f"PDF generation failed: {e}")


def page_audit():
    st.title("🔎 Workbook Audit")
    st.caption("Findings from inspecting MINOR_PROJECT_DONE_BY_KRUSHNA.xlsm (kept unchanged). The workbook logic "
               "is replicated in Python so it can be compared with the IS-based calculator.")
    st.dataframe(pd.DataFrame(AUDIT_FINDINGS), hide_index=True)
    st.subheader("Same input, two calculations")
    c1, c2, c3 = st.columns(3)
    grade = c1.selectbox("Grade", ["M40", "M50", "M60", "M70", "M80"], index=3)
    slump = c2.selectbox("Slump", [50, 75, 100, 120], index=3)
    fa = c3.number_input("Fly ash %", 0, 40, 0)
    wb = run_workbook_logic(grade=grade, slump=slump, agg_size=20, fly_ash_pct=fa, plasticizer_pct=1,
                            fine_pct=40, coarse_pct=60)
    try:
        mi = MixInputs(fck=float(grade[1:]), msa=20.0, slump=float(slump), exposure="Severe", cement_type="OPC 53",
                       scms=[ScmInput("Fly ash", float(fa), 2.2)] if fa else [],
                       binder_increase_pct=10.0 if fa >= 20 else 0.0,
                       admixture_type="Superplasticiser, PCE" if int(grade[1:]) >= 65 else "Superplasticiser, normal (SMF/SNF)",
                       admixture_dose_pct=1.0, admixture_water_reduction_pct=25.0,
                       wc_manual=0.36 if int(grade[1:]) < 65 else None,
                       aggregate_shape="Crushed angular")
        r = design_mix(mi)
        comp = pd.DataFrame({"Quantity": ["Target strength MPa", "w/c (workbook) vs w/cm (IS)", "Water kg/m³",
                                          "Cementitious kg/m³", "Fine agg kg/m³", "Coarse agg kg/m³"],
                             "Workbook logic": [wb["target_strength"], wb["wc"], wb["final_water"],
                                                wb["total_binder"], wb["fine_agg"], wb["coarse_agg"]],
                             "IS-based calculator": [r.target_strength, r.wcm_final, r.water_net,
                                                     r.binder_total, r.fa_ssd, r.ca_ssd]})
        st.dataframe(comp.round(3), hide_index=True)
        st.caption("The IS column uses *assumed* illustrative inputs (OPC 53, 25 % water reduction by trial, "
                   "w/c 0.36 for ordinary grades) - it demonstrates the structural differences, not a design.")
    except InputError as e:
        st.error("; ".join(e.problems))


# ------------------------------------------------------------------------------ router
def main():
    ss_init()
    st.sidebar.title("🏗️ Concrete Mix AI")
    page = st.sidebar.radio("Navigate", PAGES)
    st.sidebar.caption("Research prototype - verify with trial mixes and lab tests.")
    {"🏠 Home": page_home, "📝 Mix Input": page_mix_input, "🧮 Engineering Calculator": page_calculator,
     "🤖 AI Model (train / evaluate)": page_model, "🔮 AI Strength Prediction": page_prediction,
     "⚖️ Candidate Comparison": page_candidates, "📊 Results & Reports": page_results,
     "🔎 Workbook Audit": page_audit}[page]()


main()
