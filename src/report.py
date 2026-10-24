"""CSV and PDF export. Only values that were actually calculated / predicted are written."""
from __future__ import annotations

import io
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Dict, Optional
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from .engineering import MixInputs, MixResult
from .prediction import Prediction

TITLE = "AI-Based Software Interface for Concrete Mix Design"
DISCLAIMER = ("Research / academic prototype. Not a substitute for an approved mix design, "
              "trial mixes and laboratory testing. IS 10262:2019 procedure was followed as "
              "implemented from the supplied copy; IS 456:2000 limits were NOT in the supplied "
              "attachments and are marked for verification. No certification is claimed.")


def new_report_id() -> str:
    return "CMD-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4].upper()


# ----------------------------------------------------------------------------- CSV
def results_dataframe(mi: MixInputs, res: Optional[MixResult], pred: Optional[Prediction]
                      ) -> pd.DataFrame:
    rows = []

    def add(kind, item, value, unit="", note=""):
        rows.append({"Type": kind, "Item": item, "Value": value, "Unit": unit, "Note": note})

    d = asdict(mi)
    for k in ("scms", "prices_per_kg"):
        d.pop(k, None)
    for k, v in d.items():
        add("User input", k, v)
    for s in mi.scms:
        add("User input", f"SCM {s.name} (% of total binder)", s.percent, "%", f"SG {s.sg}")
    if res is not None:
        add("Calculated", "Target mean strength", round(res.target_strength, 2), "MPa", "IS 10262 cl. 4.2")
        add("Calculated", "Free w/cm (final)", round(res.wcm_final, 3), "-")
        add("Calculated", "Cement", round(res.cement, 1), "kg/m3")
        for k, v in res.scm_masses.items():
            add("Calculated", k, round(v, 1), "kg/m3")
        add("Calculated", "Total cementitious", round(res.binder_total, 1), "kg/m3")
        add("Calculated", "Net mixing water (SSD basis)", round(res.water_net, 1), "L/m3")
        add("Calculated", "Water to add (field)", round(res.water_to_add, 1), "L/m3")
        add("Calculated", "Fine aggregate SSD", round(res.fa_ssd, 1), "kg/m3")
        add("Calculated", "Coarse aggregate SSD", round(res.ca_ssd, 1), "kg/m3")
        add("Calculated", "Fine aggregate field", round(res.fa_field, 1), "kg/m3")
        add("Calculated", "Coarse aggregate field", round(res.ca_field, 1), "kg/m3")
        add("Calculated", "Admixture", round(res.admixture_mass, 2), "kg/m3")
        for c in res.checks:
            add("Engineering check", c.name, c.status, "", c.detail)
        for w in res.warnings:
            add("Warning", "", "", "", w)
    if pred is not None:
        add("Predicted (ML)", f"Compressive strength at {pred.age_days:g} d",
            round(pred.strength_mpa, 1), "MPa", f"model: {pred.model_name}; NOT a guarantee")
        add("Predicted (ML)", "Approx. 90 % band", f"{pred.interval_low:.1f} - {pred.interval_high:.1f}", "MPa",
            "from held-out test residuals")
        for w in pred.warnings:
            add("Warning", "", "", "", w)
    add("Status", "Trial mixes", "NOT DONE", "", "required by IS 10262 cl. 5.8")
    add("Status", "Laboratory verification", "NOT DONE", "", "")
    return pd.DataFrame(rows)


def results_csv_bytes(mi, res, pred) -> bytes:
    return results_dataframe(mi, res, pred).to_csv(index=False).encode("utf-8-sig")


# ----------------------------------------------------------------------------- PDF
def _tbl(data, widths=None, header=True):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.96, 0.98)])]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.12, 0.25, 0.45)),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def build_pdf(mi: MixInputs, res: Optional[MixResult], pred: Optional[Prediction],
              model_meta: Optional[Dict[str, object]], report_id: Optional[str] = None) -> bytes:
    report_id = report_id or new_report_id()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm, title=TITLE)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=16, textColor=colors.Color(0.12, 0.25, 0.45))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, spaceBefore=8,
                        textColor=colors.Color(0.12, 0.25, 0.45))
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=9.5)
    P = lambda t, s=body: Paragraph(escape(str(t)), s)  # noqa: E731

    el = [Paragraph(escape(TITLE), h1),
          P(f"Report ID: {report_id}    Date: {datetime.now():%d %b %Y %H:%M}"),
          Spacer(1, 4), P(DISCLAIMER, small)]

    # inputs
    el.append(Paragraph("1. Input parameters (user-provided)", h2))
    inp = [["Parameter", "Value"],
           ["Grade", f"M{mi.fck:g}"], ["Site control", mi.site_control],
           ["Cement type / SG", f"{mi.cement_type} / {mi.cement_sg}"],
           ["Exposure / member", f"{mi.exposure} / {'reinforced' if mi.reinforced else 'plain'}"],
           ["Max aggregate size", f"{mi.msa:g} mm"], ["Slump", f"{mi.slump:g} mm"],
           ["Aggregate shape / FA zone", f"{mi.aggregate_shape} / Zone {mi.fa_zone}"],
           ["SG coarse / fine", f"{mi.sg_ca} / {mi.sg_fa}"],
           ["Absorption coarse / fine", f"{mi.abs_ca} % / {mi.abs_fa} %"],
           ["Aggregate condition (CA / FA)", f"{mi.moisture_mode_ca} / {mi.moisture_mode_fa}"],
           ["SCMs (% of total binder)", ", ".join(f"{s.name} {s.percent:g}% (SG {s.sg})" for s in mi.scms) or "none"],
           ["Binder increase", f"{mi.binder_increase_pct:g} %"],
           ["Admixture", f"{mi.admixture_type}; dose {mi.admixture_dose_pct:g} %; "
                         f"water reduction {mi.admixture_water_reduction_pct:g} % (user value)"],
           ["Pumping CA reduction", f"{mi.pumpable_ca_reduction_pct:g} %"]]
    el.append(_tbl([[P(a), P(b)] for a, b in inp], [55 * mm, 125 * mm]))

    # quantities
    el.append(Paragraph("2. Mix quantities (calculated, IS 10262 procedure)", h2))
    if res is None:
        el.append(P("Engineering calculation not run - no quantities available."))
    else:
        q = [["Item", "Value", "Unit"]] + [[r["Item"], f"{r['Value']:.3f}".rstrip("0").rstrip("."), r["Unit"]]
                                           for r in res.to_rows()]
        q.insert(1, ["Target mean strength", f"{res.target_strength:.2f}", "MPa"])
        el.append(_tbl([[P(c) for c in r] for r in q], [95 * mm, 40 * mm, 45 * mm]))
        el.append(P(f"Procedure: {res.path}. Quantities are for 1 m3 and must be proven by trial mixes.", small))
        if res.cost_per_m3 is not None:
            el.append(P(f"Material cost (user-supplied prices, excl. water, transport, wastage): "
                        f"{res.cost_per_m3:,.0f} per m3.", small))

    # ML
    el.append(Paragraph("3. Machine-learning strength prediction", h2))
    if pred is None:
        el.append(P("No prediction included (model not trained or prediction not run)."))
    else:
        el.append(P(f"Predicted compressive strength at {pred.age_days:g} days: {pred.strength_mpa:.1f} MPa "
                    f"(approx. 90 % band {pred.interval_low:.1f}-{pred.interval_high:.1f} MPa). "
                    f"Model: {pred.model_name}. This is a statistical estimate, not a guaranteed strength."))
        if pred.target_mpa is not None:
            el.append(P(f"Requested target: {pred.target_mpa:.1f} MPa; difference (pred - target): "
                        f"{pred.difference_to_target:+.1f} MPa."))
        for w in pred.warnings:
            el.append(P("- " + w, small))
    if model_meta and model_meta.get("trained"):
        m = model_meta["test_metrics"]
        el.append(P(f"Model evaluation (held-out test set, n={model_meta['n_test']}, trained "
                    f"{model_meta['trained_at_utc']}, dataset rows used {model_meta['dataset_rows_used']}): "
                    f"MAE {m['MAE_MPa']:.2f} MPa, RMSE {m['RMSE_MPa']:.2f} MPa, R2 {m['R2']:.3f}."))
    else:
        el.append(P("Model evaluation: model NOT trained - no metrics available."))

    # methodology
    el.append(Paragraph("4. Calculation methodology", h2))
    if res is not None:
        steps = [["No.", "Step", "Formula / basis", "Result", "Source"]] + [
            [s.no, s.name, s.formula, s.value, s.source] for s in res.steps]
        el.append(_tbl([[P(c, small) for c in r] for r in steps],
                       [9 * mm, 30 * mm, 55 * mm, 35 * mm, 51 * mm]))

    # assumptions + checklist
    el.append(Paragraph("5. Assumptions and limitations", h2))
    lim = ["Only IS 10262:2019 Sections 2 and 3 are implemented (no SCC, mass or air-entrained concrete).",
           "IS 456:2000 durability limits are NOT in the supplied attachments: verify Table 5 and cl. 8.2.4.2.",
           "Fig. 1 w/c is an estimate anchored on three points printed in IS 10262 unless entered manually.",
           "Admixture water reduction is a user/trial value and is never derived from the dose.",
           "The ML model is trained on a public lab dataset (UCI, 1030 mixes) and does not cover silica fume, "
           "metakaolin, aggregate shape, cement grade or admixture type.",
           "ML prediction and engineering calculation are independent; the AI model does not design mixes."]
    for l in lim:
        el.append(P("- " + l, small))
    if res is not None:
        for w in res.warnings:
            el.append(P("- WARNING: " + w, small))

    el.append(Paragraph("6. Engineering validation checklist", h2))
    if res is not None:
        chk = [["Check", "Status", "Detail", "Source"]] + [[c.name, c.status, c.detail, c.source] for c in res.checks]
        el.append(_tbl([[P(c, small) for c in r] for r in chk], [42 * mm, 17 * mm, 77 * mm, 44 * mm]))
    el.append(Paragraph("7. Trial-mix and laboratory verification status", h2))
    el.append(_tbl([[P("Item"), P("Status")],
                    [P("Trial mix 1 (workability, segregation, bleeding)"), P("NOT DONE")],
                    [P("Trial mixes 2-4 (w/cm +/-10 %), strength vs w/c graph"), P("NOT DONE")],
                    [P("28-day cube compressive strength"), P("NOT DONE")],
                    [P("Approval by engineer-in-charge"), P("NOT DONE")]], [120 * mm, 60 * mm]))

    doc.build(el)
    return buf.getvalue()
