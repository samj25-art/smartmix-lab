"""
Deterministic concrete mix-proportioning calculator following the procedure of
IS 10262:2019 (Sections 2 and 3: ordinary/standard grades M10-M60 and high strength M65+).

This module is completely independent of the machine-learning model.

Not covered (flagged in the UI): self-compacting concrete (Section 4), mass concrete
(Section 5), air-entrained concrete, lightweight aggregate, early-strength adjustments.

Every number is returned together with the formula / source that produced it
(see MixResult.steps) so it can be traced in the report.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from . import constants as C
from .validation import InputError, validate_mix_inputs


# ----------------------------------------------------------------------------- data
@dataclass
class ScmInput:
    name: str            # "Fly ash" | "GGBS" | "Silica fume" | "Metakaolin"
    percent: float       # % of TOTAL cementitious material (not of cement)
    sg: float


@dataclass
class MixInputs:
    fck: float = 40.0
    site_control: str = "Good"            # Good | Fair (Table 2 note 1: +1 MPa)
    std_dev_override: Optional[float] = None
    cement_type: str = "OPC 43"           # OPC 33 | OPC 43 | OPC 53 | PPC
    cement_sg: float = 3.15
    exposure: str = "Severe"
    reinforced: bool = True
    msa: float = 20.0
    slump: float = 75.0
    aggregate_shape: str = "Crushed angular"
    fa_zone: str = "II"
    wc_manual: Optional[float] = None     # w/c read from Fig. 1 (ordinary grades)
    scms: List[ScmInput] = field(default_factory=list)
    binder_increase_pct: float = 0.0      # IS 10262 cl. 5.4.1 allows ~10 % for fly ash >= 20 %
    admixture_type: str = "None"
    admixture_dose_pct: float = 0.0       # % by mass of total cementitious
    admixture_water_reduction_pct: float = 0.0   # established by trial - NOT derived from dose
    admixture_sg: float = 1.145
    pumpable_ca_reduction_pct: float = 0.0
    sg_ca: float = 2.74
    sg_fa: float = 2.65
    abs_ca: float = 0.5
    abs_fa: float = 1.0
    moisture_mode_ca: str = "SSD"         # SSD | Oven-dry | Field moist
    moisture_mode_fa: str = "SSD"
    moisture_total_ca: float = 0.0        # total moisture % (Field moist only)
    moisture_total_fa: float = 0.0
    air_override_pct: Optional[float] = None
    prices_per_kg: Dict[str, float] = field(default_factory=dict)  # optional cost inputs


@dataclass
class Step:
    no: str
    name: str
    formula: str
    value: str
    source: str


@dataclass
class Check:
    name: str
    status: str      # PASS | FAIL | REVIEW | PENDING
    detail: str
    source: str


@dataclass
class MixResult:
    path: str                         # "Ordinary/standard (Section 2)" | "High strength (Section 3)"
    target_strength: float
    std_dev: float
    x_factor: float
    wc_strength: float
    wc_durability: Optional[float]
    wc_adopted: float
    wcm_final: float
    water_net: float                  # net mixing water (SSD basis), kg/m3 = L/m3
    water_to_add: float               # after aggregate moisture correction
    cement: float
    scm_masses: Dict[str, float]
    binder_total: float
    admixture_mass: float
    ca_fraction: float
    fa_fraction: float
    ca_ssd: float
    fa_ssd: float
    ca_field: float
    fa_field: float
    air_pct: float
    volumes_m3: Dict[str, float]
    fresh_density: float
    cost_per_m3: Optional[float]
    steps: List[Step]
    checks: List[Check]
    warnings: List[str]

    # convenience -------------------------------------------------------------------
    def to_rows(self) -> List[Dict[str, object]]:
        rows = [
            ("Cement (OPC/PPC)", self.cement, "kg/m³"),
        ]
        for k, v in self.scm_masses.items():
            rows.append((k, v, "kg/m³"))
        rows += [
            ("Total cementitious", self.binder_total, "kg/m³"),
            ("Water to add (after moisture correction)", self.water_to_add, "L/m³"),
            ("Net mixing water (SSD basis)", self.water_net, "L/m³"),
            ("Fine aggregate (field condition)", self.fa_field, "kg/m³"),
            ("Coarse aggregate (field condition)", self.ca_field, "kg/m³"),
            ("Fine aggregate (SSD)", self.fa_ssd, "kg/m³"),
            ("Coarse aggregate (SSD)", self.ca_ssd, "kg/m³"),
            ("Admixture", self.admixture_mass, "kg/m³"),
            ("Free w/cm", self.wcm_final, "-"),
        ]
        return [{"Item": a, "Value": round(float(b), 3), "Unit": u} for a, b, u in rows]


# ------------------------------------------------------------------------- helpers
def estimate_wc_from_fig1_curve2(target: float) -> (float, bool):
    """
    Estimate free w/c for the OPC 43 / curve-2 relationship of IS 10262 Fig. 1.

    The figure itself cannot be read to better than ~0.01-0.02 from the supplied PDF image.
    The only exact readings printed in the standard text are the three anchor points in
    constants.FIG1_CURVE2_ANCHORS. Between them we interpolate ln(strength) linearly in w/c
    (Abrams-type behaviour). Outside them we extrapolate and flag it.
    Returns (w_c, extrapolated?)
    """
    pts = sorted((w, math.log(f)) for f, w in C.FIG1_CURVE2_ANCHORS)   # ascending w/c
    y = math.log(target)
    # strength decreases with w/c -> ln f decreasing along w
    extrap = y > pts[0][1] or y < pts[-1][1]
    # choose segment
    seg = None
    for (w0, y0), (w1, y1) in zip(pts[:-1], pts[1:]):
        if y1 <= y <= y0:
            seg = ((w0, y0), (w1, y1))
            break
    if seg is None:
        seg = (pts[0], pts[1]) if y > pts[0][1] else (pts[-2], pts[-1])
    (w0, y0), (w1, y1) = seg
    w = w0 + (y - y0) * (w1 - w0) / (y1 - y0)
    return float(w), extrap


def _interp_target_wcm_table8(target: float, msa: float) -> (float, bool):
    keys = sorted(C.TABLE8_WCM)
    extrap = target < keys[0] or target > keys[-1]
    t = min(max(target, keys[0]), keys[-1])
    for k0, k1 in zip(keys[:-1], keys[1:]):
        if k0 <= t <= k1:
            w0, w1 = C.TABLE8_WCM[k0][msa], C.TABLE8_WCM[k1][msa]
            return w0 + (t - k0) * (w1 - w0) / (k1 - k0), extrap
    return C.TABLE8_WCM[keys[-1]][msa], extrap


def _moisture_adjust(mass_ssd: float, absorption: float, mode: str, total_moist: float):
    """Return (field mass, water delta in kg: + water must be ADDED, - water supplied by aggregate)."""
    if mode == "SSD":
        return mass_ssd, 0.0
    if mode == "Oven-dry":   # IS 10262 Annex A-11
        dry = mass_ssd / (1.0 + absorption / 100.0)
        return dry, mass_ssd - dry
    # Field moist: IS 10262 Annex B-11 (free moisture = total moisture - absorption)
    free = total_moist - absorption
    wet = mass_ssd * (1.0 + free / 100.0)
    return wet, -(wet - mass_ssd)


# ------------------------------------------------------------------------ main routine
def design_mix(mi: MixInputs) -> MixResult:
    errors, warnings = validate_mix_inputs(mi)
    if errors:
        raise InputError(errors)

    steps: List[Step] = []
    checks: List[Check] = []
    hsc = mi.fck >= 65
    path = "High strength (Section 3, M65+)" if hsc else "Ordinary/standard (Section 2, M10-M60)"
    IS = C.SOURCE_IS10262

    # 1. target strength ---------------------------------------------------------------
    S = mi.std_dev_override if mi.std_dev_override else C.table2_S(mi.fck)
    if not mi.std_dev_override and mi.site_control == "Fair":
        S += 1.0
    X = C.table1_X(mi.fck)
    t1, t2 = mi.fck + 1.65 * S, mi.fck + X
    target = max(t1, t2)
    steps.append(Step("1", "Target mean strength f'ck",
                      f"max(fck+1.65S, fck+X) = max({mi.fck:g}+1.65x{S:g}, {mi.fck:g}+{X:g}) "
                      f"= max({t1:.2f}, {t2:.2f})",
                      f"{target:.2f} MPa", IS + " cl. 4.2, Tables 1-2"))

    # 2. air content ---------------------------------------------------------------------
    if mi.air_override_pct is not None:
        air = mi.air_override_pct
        air_src = C.SOURCE_ASSUMPTION + " (site data override, needs >=5 results, cl. 5.2.1)"
    else:
        air = (C.TABLE6_AIR if hsc else C.TABLE3_AIR)[mi.msa]
        air_src = IS + (" Table 6" if hsc else " Table 3")
    steps.append(Step("2", "Entrapped air", f"table value for {mi.msa:g} mm", f"{air:.2f} %", air_src))

    # 3. water-cement ratio ----------------------------------------------------------------
    wc_note = ""
    if hsc:
        wc_strength, extrap = _interp_target_wcm_table8(target, mi.msa)
        wc_src = IS + " Table 8 (interpolated)"
        if extrap:
            warnings.append(f"Target {target:.1f} MPa is outside Table 8 (70-100 MPa); w/cm was "
                            "clamped to the nearest tabulated row. Verify by trials.")
    elif mi.wc_manual is not None:
        wc_strength, wc_src = mi.wc_manual, "User reading of IS 10262 Fig. 1 (manual input)"
        extrap = False
    else:
        wc_strength, extrap = estimate_wc_from_fig1_curve2(target)
        wc_src = ("Estimate from Fig. 1 curve 2 using the 3 anchor points printed in IS 10262 "
                  "Annex A/E/F (OPC 43; PPC assumed same)")
        warnings.append("w/c is an ESTIMATE of Fig. 1 curve 2 - confirm against the printed "
                        "chart or enter the w/c manually.")
        if extrap:
            warnings.append(f"Target strength {target:.1f} MPa lies outside the anchor range "
                            "(20.8-48.3 MPa); w/c extrapolated - read Fig. 1 directly.")
    steps.append(Step("3", "Free w/c for strength",
                      "HSC: Table 8 | ordinary: Fig. 1", f"{wc_strength:.3f}", wc_src))

    dur = (C.IS456_REINFORCED if mi.reinforced else C.IS456_PLAIN).get(mi.exposure)
    wc_dur, min_binder = (dur if dur else (None, None))
    wc_adopted = min(wc_strength, wc_dur) if wc_dur else wc_strength
    steps.append(Step("3b", "Adopted w/c (lower of strength & durability, cl. 5.1.1)",
                      f"min({wc_strength:.3f}, {wc_dur})", f"{wc_adopted:.3f}",
                      C.SOURCE_IS456 + " for the durability limit"))
    checks.append(Check("w/c within durability limit",
                        "PASS" if (wc_dur is None or wc_adopted <= wc_dur + 1e-9) else "FAIL",
                        f"strength w/c {wc_strength:.3f} vs limit {wc_dur} "
                        f"({'RC' if mi.reinforced else 'plain'}, {mi.exposure}); "
                        f"adopted {wc_adopted:.3f} (lower value, cl. 5.1.1).",
                        C.SOURCE_IS456))

    # 4. water content -----------------------------------------------------------------------
    base = (C.TABLE7_WATER if hsc else C.TABLE4_WATER)[mi.msa]
    slump_adj = (mi.slump - 50.0) / 25.0 * C.SLUMP_STEP_PERCENT / 100.0
    w_slump = base * (1.0 + slump_adj)
    shape_red = 0.0 if hsc else C.SHAPE_WATER_REDUCTION[mi.aggregate_shape]
    if hsc and mi.aggregate_shape != "Crushed angular":
        warnings.append("Table 7 is for angular aggregate; IS 10262 gives no shape reduction for "
                        "high-strength mixes - establish water demand by trial.")
    w_shape = w_slump - shape_red
    w_net = w_shape * (1.0 - mi.admixture_water_reduction_pct / 100.0)
    steps.append(Step("4", "Water content",
                      f"{base:g} x (1+{slump_adj:.3f}) - {shape_red:g} = {w_shape:.2f}; "
                      f"x (1-{mi.admixture_water_reduction_pct:g}/100)",
                      f"{w_net:.2f} kg/m³",
                      IS + (" Table 7 + cl. 6.2.4" if hsc else " Table 4 + cl. 5.3") +
                      "; water reduction is the user's trial value, not derived from dose"))

    # 5. binder -----------------------------------------------------------------------------
    binder0 = w_net / wc_adopted
    inc = mi.binder_increase_pct
    binder = binder0 * (1 + inc / 100.0)
    steps.append(Step("5", "Cementitious content",
                      f"water / (w/c) = {w_net:.2f}/{wc_adopted:.3f} = {binder0:.1f}; "
                      f"x(1+{inc:g}/100)", f"{binder:.1f} kg/m³", IS + " cl. 5.4.1 / 6.2.6"))
    min_note = ""
    if min_binder and binder < min_binder:
        min_note = f"raised from {binder:.1f} to the durability minimum {min_binder}"
        binder = float(min_binder)
        warnings.append("Cementitious content was RAISED to the IS 456 minimum "
                        f"({min_binder} kg/m³); w/cm recalculated.")
    checks.append(Check("Minimum cementitious content",
                        "PASS" if (min_binder is None or binder >= min_binder) else "FAIL",
                        f"{binder:.1f} kg/m³ vs minimum {min_binder} {min_note}", C.SOURCE_IS456))

    scm_total_pct = sum(s.percent for s in mi.scms)
    scm_masses = {s.name: binder * s.percent / 100.0 for s in mi.scms if s.percent > 0}
    cement = binder - sum(scm_masses.values())   # no double counting: SCMs are PART of binder
    wcm = w_net / binder
    steps.append(Step("5b", "Cement / SCM split",
                      f"SCM = {scm_total_pct:g} % of total binder; cement = binder - SCM",
                      f"cement {cement:.1f}; " + "; ".join(f"{k} {v:.1f}" for k, v in scm_masses.items()),
                      C.SOURCE_ASSUMPTION + " (percentages chosen by user) / IS 10262 cl. 5.4.2"))
    steps.append(Step("5c", "Final free w/cm", f"{w_net:.2f}/{binder:.1f}", f"{wcm:.3f}", IS))
    checks.append(Check("Free w/cm within durability limit",
                        "PASS" if (wc_dur is None or wcm <= wc_dur + 1e-9) else "FAIL",
                        f"w/cm {wcm:.3f} vs {wc_dur}", C.SOURCE_IS456))
    checks.append(Check("Maximum cement (OPC/PPC) content",
                        "PASS" if cement <= C.IS456_MAX_CEMENT_KG else "FAIL",
                        f"{cement:.1f} kg/m³ vs {C.IS456_MAX_CEMENT_KG:g}. If exceeded, IS 10262 "
                        "cl. 6.2.6 demands special design for shrinkage, thermal cracking, ASR.",
                        C.SOURCE_IS456))
    fly = next((s for s in mi.scms if s.name == "Fly ash"), None)
    if fly and fly.percent >= 20 and inc == 0:
        warnings.append("Fly ash >= 20 %: IS 10262 cl. 5.4.1 says the cementitious content may need "
                        "to rise (~10 % for the preliminary trial). Binder increase is currently 0 %.")
    if hsc:
        for s in mi.scms:
            lo, hi = C.TABLE9_SCM_RANGE.get(s.name, (0, 100))
            ok = lo <= s.percent <= hi
            checks.append(Check(f"{s.name} dosage (Table 9)", "PASS" if ok else "REVIEW",
                                f"{s.percent:g} % vs recommended {lo}-{hi} %", IS + " Table 9"))
        if not any(s.name == "Silica fume" for s in mi.scms) or mi.cement_type != "OPC 53":
            checks.append(Check("Table 8 applicability", "REVIEW",
                                "Table 8 w/cm is recommended for OPC 53-grade cement with silica "
                                "fume and HRWRA; lower the w/cm if cement strength is less.",
                                IS + " Table 8 note"))

    # 6. coarse aggregate fraction -----------------------------------------------------------
    if hsc:
        base_ca, ref_wc = C.TABLE10_CA[mi.msa][mi.fa_zone], 0.30
    else:
        base_ca, ref_wc = C.TABLE5_CA[mi.msa][mi.fa_zone], 0.50
    adj = (ref_wc - wcm) / 0.05 * 0.01
    ca_frac = base_ca + adj
    pump = mi.pumpable_ca_reduction_pct / 100.0
    ca_frac_final = ca_frac * (1 - pump)
    fa_frac = 1 - ca_frac_final
    steps.append(Step("6", "Coarse aggregate volume fraction",
                      f"{base_ca:.2f} {adj:+.4f} (0.01 per 0.05 w/cm from {ref_wc}) "
                      f"= {ca_frac:.4f}; x(1-{pump:.2f}) = {ca_frac_final:.4f}",
                      f"CA {ca_frac_final:.4f} / FA {fa_frac:.4f}",
                      IS + (" Table 10 / cl. 6.2.7" if hsc else " Table 5 / cl. 5.5")))
    if (not hsc) and mi.fa_zone == "IV" and mi.reinforced:
        warnings.append("Fine aggregate Zone IV should not be used in reinforced concrete unless "
                        "suitability is proven by tests (Table 5 note 4).")

    # 7. absolute volume ---------------------------------------------------------------------
    adm_mass = binder * mi.admixture_dose_pct / 100.0
    v = {
        "cement": cement / (mi.cement_sg * 1000.0),
        "water": w_net / 1000.0,
        "admixture": adm_mass / (mi.admixture_sg * 1000.0),
        "air": air / 100.0,
    }
    for s in mi.scms:
        if s.percent > 0:
            v[s.name] = scm_masses[s.name] / (s.sg * 1000.0)
    v_agg = 1.0 - sum(v.values())
    if v_agg <= 0.2:
        raise InputError([f"Aggregate volume {v_agg:.3f} m³ is implausibly small - the paste "
                          "volume is too large; revisit w/c, water or binder."])
    ca_ssd = v_agg * ca_frac_final * mi.sg_ca * 1000.0
    fa_ssd = v_agg * fa_frac * mi.sg_fa * 1000.0
    v["aggregate"] = v_agg
    steps.append(Step("7", "Absolute volume (1 m³)",
                      "V_agg = 1 - air - sum(mass/(SG x 1000))", f"{v_agg:.4f} m³",
                      IS + " cl. 5.7 / 6.2.8"))
    steps.append(Step("7b", "Aggregate masses (SSD)",
                      "V_agg x fraction x SG x 1000", f"CA {ca_ssd:.1f}; FA {fa_ssd:.1f} kg/m³", IS))

    # 8. moisture correction -----------------------------------------------------------------
    ca_f, dca = _moisture_adjust(ca_ssd, mi.abs_ca, mi.moisture_mode_ca, mi.moisture_total_ca)
    fa_f, dfa = _moisture_adjust(fa_ssd, mi.abs_fa, mi.moisture_mode_fa, mi.moisture_total_fa)
    w_add = w_net + dca + dfa
    if w_add <= 0:
        raise InputError(["After moisture correction no water needs to be added (aggregates supply "
                          "more than the mixing water) - check the moisture inputs."])
    steps.append(Step("8", "Aggregate moisture correction",
                      f"CA {mi.moisture_mode_ca}, FA {mi.moisture_mode_fa}; water to add = "
                      f"{w_net:.1f} {dca + dfa:+.2f}",
                      f"water {w_add:.1f} L; CA {ca_f:.1f}; FA {fa_f:.1f} kg/m³",
                      IS + " Annex A-11 / B-11"))

    # 9. checks ------------------------------------------------------------------------------
    vol_sum = sum(val for k, val in v.items() if k != "aggregate") + v_agg \
        + 0.0  # air already in v
    checks.append(Check("Absolute-volume balance = 1 m³", "PASS" if abs(vol_sum - 1) < 1e-9 else "FAIL",
                        f"sum of volumes incl. air = {vol_sum:.6f} m³", "Calculation identity"))
    mass_ssd_total = cement + sum(scm_masses.values()) + w_net + adm_mass + ca_ssd + fa_ssd
    mass_field_total = cement + sum(scm_masses.values()) + w_add + adm_mass + ca_f + fa_f
    checks.append(Check("Mass balance (SSD batch vs field batch)",
                        "PASS" if abs(mass_ssd_total - mass_field_total) < 1e-6 else "FAIL",
                        f"SSD {mass_ssd_total:.2f} kg vs field {mass_field_total:.2f} kg",
                        "Calculation identity"))
    lo, hi = C.DENSITY_SANITY_RANGE
    checks.append(Check("Fresh density plausibility",
                        "PASS" if lo <= mass_ssd_total <= hi else "REVIEW",
                        f"{mass_ssd_total:.0f} kg/m³ (indicative window {lo:.0f}-{hi:.0f}; not a code limit)",
                        C.SOURCE_ASSUMPTION))
    rng = C.ADMIXTURE_TYPES.get(mi.admixture_type)
    if rng and mi.admixture_type != "None":
        d_ok = rng["dose"][0] <= mi.admixture_dose_pct <= rng["dose"][1]
        r_ok = rng["reduction"][0] <= mi.admixture_water_reduction_pct <= rng["reduction"][1]
        checks.append(Check("Admixture dose / water reduction vs Annex G typical ranges",
                            "PASS" if (d_ok and r_ok) else "REVIEW",
                            f"dose {mi.admixture_dose_pct:g} % (typical {rng['dose']}); water "
                            f"reduction {mi.admixture_water_reduction_pct:g} % (typical "
                            f"{rng['reduction']}). Must be confirmed by trials with the actual "
                            "cement (cement-admixture compatibility, Annex G-5).",
                            IS + " Annex G (informative)"))
    if hsc and mi.admixture_type == "None":
        checks.append(Check("High-strength mix without HRWRA", "REVIEW",
                            "w/cm of 0.24-0.36 is normally attainable only with HRWRA (cl. 6.1.4).",
                            IS + " cl. 6.1.4"))
    checks.append(Check("Trial mixes (Trial 1 + 3 further w/cm trials, +/-10 %)", "PENDING",
                        "IS 10262 cl. 5.8 / 6.2.9 requires trial batches and workability / strength "
                        "testing. NOT performed by this software.", IS + " cl. 5.8"))
    checks.append(Check("Laboratory verification of cube strength", "PENDING",
                        "Mix is a starting proportion only.", C.SOURCE_ASSUMPTION))

    # 10. cost (optional) --------------------------------------------------------------------
    cost = None
    if mi.prices_per_kg:
        p = mi.prices_per_kg
        cost = (cement * p.get("cement", 0) + fa_ssd * p.get("fine_aggregate", 0)
                + ca_ssd * p.get("coarse_aggregate", 0) + adm_mass * p.get("admixture", 0)
                + sum(m * p.get(k, 0) for k, m in scm_masses.items()))

    if mi.cement_type == "PPC" and not scm_masses:
        warnings.append("PPC already contains fly ash/pozzolana; its SG was taken from user input. "
                        "Do not add fly ash again unless justified (IS 10262 Annex A/B).")

    return MixResult(
        path=path, target_strength=target, std_dev=S, x_factor=X,
        wc_strength=wc_strength, wc_durability=wc_dur, wc_adopted=wc_adopted, wcm_final=wcm,
        water_net=w_net, water_to_add=w_add, cement=cement, scm_masses=scm_masses,
        binder_total=binder, admixture_mass=adm_mass, ca_fraction=ca_frac_final,
        fa_fraction=fa_frac, ca_ssd=ca_ssd, fa_ssd=fa_ssd, ca_field=ca_f, fa_field=fa_f,
        air_pct=air, volumes_m3=v, fresh_density=mass_ssd_total, cost_per_m3=cost,
        steps=steps, checks=checks, warnings=warnings)


def result_to_ml_features(res: MixResult, age_days: float = 28.0) -> Dict[str, float]:
    """Map a calculated mix to the 8 UCI features (kg/m3 SSD basis, net mixing water).

    CAUTION: silica fume / metakaolin have no column in the UCI dataset and are dropped, and
    the UCI 'superplasticizer' column is assumed to be admixture mass in kg/m3.
    """
    return {
        "cement": res.cement,
        "slag": res.scm_masses.get("GGBS", 0.0),
        "fly_ash": res.scm_masses.get("Fly ash", 0.0),
        "water": res.water_net,
        "superplasticizer": res.admixture_mass,
        "coarse_agg": res.ca_ssd,
        "fine_agg": res.fa_ssd,
        "age": float(age_days),
    }


def result_to_dict(res: MixResult) -> dict:
    return asdict(res)
