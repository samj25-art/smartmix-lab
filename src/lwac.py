"""
Lightweight Aggregate Concrete (LWAC) mix design engine for LECA
(Lightweight Expanded Clay Aggregate).

Independent of the IS 10262 engine and of the ML model.  IS 10262 cannot be used for LECA
because its aggregate-volume tables assume SG ~2.6-2.8, ~0.5 % absorption and 2300-2500 kg/m3
concrete.  Here the aggregate split is obtained by *density closure* instead of tables.

KEY IDEAS
---------
1. Particle volume.  A LECA particle contains internal pores.  Using the OVEN-DRY particle
   relative density (SG_dry, pores included) the particle volume is
        V = M_dry / (SG_dry * 1000)
   Water that soaks into those pores occupies space that is ALREADY inside V, so the absolute
   volume balance counts only the *net* (free) mixing water, never the absorbed water.
2. Two kinds of water.
        net water       : free water in the paste -> sets w/cm, strength, workability
        absorption water: water held in the LECA pores (A x M_dry) -> adds mass, no volume
   Batch water = net + absorption deficit (A - current moisture) - surface-moisture credit.
   Supplying the absorption water (by pre-soaking or by adding it) stops the dry LECA from
   pulling mixing water out of the paste.
3. Fine / coarse split.  Paste volume and mass are fixed by w/cm, water and binder.  The
   remaining volume V_agg is shared by LECA (particle density rho_c) and fine aggregate
   (rho_f) so that the fresh density equals the target:
        V_f = (rho_t - M_paste - rho_c * V_agg) / (rho_f - rho_c),   V_c = V_agg - V_f

Every default marked ASSUMPTION is an engineering starting value, NOT a code value: no LWAC code
(ACI 211.2, ACI 213R, IS 9142 ...) was supplied while building this module.  The output is a
first trial proportion; trial mixes and laboratory tests are mandatory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from . import constants as C
from .engineering import Check, ScmInput, Step, estimate_wc_from_fig1_curve2
from .validation import InputError

SRC_ASSUME = "ASSUMPTION - engineering default, confirm by trial mixes"
SRC_IDENTITY = "Calculation identity"
SRC_IS = "IS 10262:2019 cl. 4.2, Tables 1-2 (statistical target strength rule)"

STATE_DRY = "Oven-dry"
STATE_SSD = "SSD (pre-soaked)"
STATE_MC = "Moisture content entered"
MOISTURE_STATES = (STATE_DRY, STATE_SSD, STATE_MC)

# commonly quoted structural-LWC window (ACI 213R-type) - indicative only
STRUCTURAL_MIN_MPA = 17.0
STRUCTURAL_EQ_DENSITY = (1120.0, 1920.0)
HYDRATION_FACTOR = 1.2        # oven-dry density ~ dry aggregates + 1.2 x binder  (rule of thumb)
EQUILIBRIUM_EXTRA = 50.0      # equilibrium density ~ oven-dry + 50 kg/m3         (rule of thumb)


# ------------------------------------------------------------------------------ inputs
@dataclass
class LightAgg:
    """Properties of one aggregate fraction (LECA coarse, or fine: sand / LECA fines)."""
    name: str
    sg_dry: float                       # oven-dry PARTICLE relative density (pores included)
    abs24_pct: float                    # 24 h water absorption, % of oven-dry mass
    bulk_density_dry: Optional[float] = None   # loose dry bulk density, kg/m3
    moisture_state: str = STATE_DRY
    moisture_pct: float = 0.0           # total moisture % of dry mass (STATE_MC only)
    absorption_fraction: float = 1.0    # share of abs24 that is taken up before the paste sets
                                        # (ignored for SSD; 1.0 = design for full absorption)

    def moisture(self) -> float:        # current moisture, fraction of dry mass
        if self.moisture_state == STATE_DRY:
            return 0.0
        if self.moisture_state == STATE_SSD:
            return self.abs24_pct / 100.0
        return self.moisture_pct / 100.0

    def design_absorption(self) -> float:   # absorption held at time of set, fraction of dry mass
        if self.moisture_state == STATE_SSD:
            return self.abs24_pct / 100.0
        return self.abs24_pct / 100.0 * self.absorption_fraction

    @property
    def particle_density_wet(self) -> float:  # kg/m3 of particle incl. design absorption water
        return self.sg_dry * 1000.0 * (1.0 + self.design_absorption())


def default_leca() -> LightAgg:
    return LightAgg("LECA (coarse)", 1.20, 12.0, 650.0, STATE_SSD)


def default_sand() -> LightAgg:
    return LightAgg("Natural sand", 2.62, 1.0, 1600.0, STATE_SSD)


@dataclass
class LecaInputs:
    fck: float = 25.0                                  # characteristic strength, MPa
    site_control: str = "Good"                         # Good | Fair (+1 MPa on S)
    std_dev_override: Optional[float] = None
    target_fresh_density: Optional[float] = 1800.0     # kg/m3; None -> use fine_vol_fraction
    density_tolerance: float = 50.0                    # +/- kg/m3 accepted
    fine_vol_fraction: Optional[float] = None          # fine share of aggregate VOLUME (when no density)
    coarse: LightAgg = field(default_factory=default_leca)
    fine: LightAgg = field(default_factory=default_sand)
    leca_strength_ceiling_mpa: Optional[float] = None  # supplier / lab ceiling for this LECA grade
    cement_type: str = "OPC 43"
    cement_sg: float = 3.15
    scms: List[ScmInput] = field(default_factory=list)  # % of TOTAL binder
    wcm_manual: Optional[float] = None
    strength_efficiency: float = 0.85                  # ASSUMPTION: LWAC strength / normal-wt strength at same w/cm
    slump: float = 75.0
    water_base_50mm: float = 170.0                     # ASSUMPTION: net water at 50 mm slump, kg/m3
    admixture_type: str = "Superplasticiser, PCE"
    admixture_dose_pct: float = 0.8                    # % of binder
    admixture_water_reduction_pct: float = 0.0         # trial value; never derived from dose
    admixture_sg: float = 1.08
    air_pct: float = 2.0                               # ASSUMPTION: entrapped air, non-air-entrained
    min_binder: float = 300.0                          # ASSUMPTION (check project spec / IS 456 exposure)
    max_binder: float = 550.0                          # ASSUMPTION: shrinkage / heat warning only
    prices_per_kg: Dict[str, float] = field(default_factory=dict)


@dataclass
class LecaResult:
    target_strength: float
    std_dev: float
    wcm_strength: float
    wcm_final: float
    water_net: float
    binder_total: float
    cement: float
    scm_masses: Dict[str, float]
    admixture_mass: float
    air_pct: float
    # aggregates
    coarse_dry: float
    fine_dry: float
    coarse_batch: float           # as-batched (current moisture)
    fine_batch: float
    coarse_vol_m3: float
    fine_vol_m3: float
    fine_vol_fraction: float
    leca_loose_bulk_m3: Optional[float]
    # water split
    absorption_water_total: float          # held in aggregate pores at design
    absorption_from_aggregate_moisture: float
    absorption_water_to_add: float
    surface_moisture_credit: float
    water_to_add: float                    # what goes in the mixer
    # densities
    fresh_density: float
    oven_dry_density_est: float
    equilibrium_density_est: float
    volumes_m3: Dict[str, float]
    cost_per_m3: Optional[float]
    steps: List[Step]
    checks: List[Check]
    warnings: List[str]

    def to_rows(self) -> List[Dict[str, object]]:
        rows = [("Cement (OPC/PPC)", self.cement, "kg/m³")]
        rows += [(k, v, "kg/m³") for k, v in self.scm_masses.items()]
        rows += [
            ("Total cementitious", self.binder_total, "kg/m³"),
            ("Net mixing water (free, in paste)", self.water_net, "kg/m³"),
            ("Absorption water (held in aggregate pores)", self.absorption_water_total, "kg/m³"),
            ("  of which already in aggregate (pre-soak / moisture)",
             self.absorption_from_aggregate_moisture, "kg/m³"),
            ("  of which added at the mixer", self.absorption_water_to_add, "kg/m³"),
            ("Surface-moisture credit", -self.surface_moisture_credit, "kg/m³"),
            ("WATER TO ADD AT MIXER", self.water_to_add, "kg/m³"),
            ("Fine aggregate - batch (as-is)", self.fine_batch, "kg/m³"),
            ("Coarse LECA - batch (as-is)", self.coarse_batch, "kg/m³"),
            ("Fine aggregate - oven-dry", self.fine_dry, "kg/m³"),
            ("Coarse LECA - oven-dry", self.coarse_dry, "kg/m³"),
            ("Chemical admixture", self.admixture_mass, "kg/m³"),
            ("Fresh density (design)", self.fresh_density, "kg/m³"),
            ("Oven-dry density (estimate)", self.oven_dry_density_est, "kg/m³"),
            ("Equilibrium density (estimate)", self.equilibrium_density_est, "kg/m³"),
            ("Free w/cm", self.wcm_final, "-"),
        ]
        return [{"Item": a, "Value": round(float(b), 3), "Unit": u} for a, b, u in rows]


# ------------------------------------------------------------------------------ validation
def _validate(mi: LecaInputs) -> (List[str], List[str]):
    err: List[str] = []
    warn: List[str] = []
    if not (10 <= mi.fck <= 80):
        err.append(f"Grade fck={mi.fck} MPa is outside 10-80 MPa for this LWAC module.")
    if not (25 <= mi.slump <= 200):
        err.append("Slump must be 25-200 mm.")
    if mi.target_fresh_density is None:
        if mi.fine_vol_fraction is None or not (0.0 <= mi.fine_vol_fraction <= 1.0):
            err.append("Give a target fresh density OR a fine fraction of aggregate volume (0-1).")
    elif not (1000 <= mi.target_fresh_density <= 2300):
        err.append(f"Target fresh density {mi.target_fresh_density} kg/m³ is outside 1000-2300.")
    if not (0.8 <= mi.cement_sg <= 4.0):
        err.append("Cement SG is not sensible.")
    if not (0.15 <= mi.strength_efficiency <= 1.2):
        err.append("Strength efficiency factor must be between 0.15 and 1.2.")
    if mi.wcm_manual is not None and not (0.2 <= mi.wcm_manual <= 0.8):
        err.append("Manual w/cm must be 0.20-0.80.")
    if mi.density_tolerance <= 0:
        err.append("Density tolerance must be positive.")
    if mi.air_pct < 0 or mi.air_pct > 10:
        err.append("Air content must be 0-10 %.")
    if mi.admixture_dose_pct < 0 or not (0 <= mi.admixture_water_reduction_pct <= 40):
        err.append("Admixture dose must be >= 0 and water reduction 0-40 %.")
    if mi.admixture_type == "None" and (mi.admixture_dose_pct or mi.admixture_water_reduction_pct):
        err.append("Admixture type is 'None' but a dose / water reduction was entered.")
    if mi.admixture_dose_pct > 0 and not (0.8 <= mi.admixture_sg <= 2.0):
        err.append("Admixture SG is not sensible.")
    if sum(s.percent for s in mi.scms) >= 70 or any(s.percent < 0 for s in mi.scms):
        err.append("SCM percentages must be >= 0 and total below 70 %.")
    for s in mi.scms:
        if not (1.0 <= s.sg <= 4.0):
            err.append(f"{s.name} SG is not sensible.")
    for tag, a, lo, hi in (("Coarse (LECA)", mi.coarse, 0.3, 2.0), ("Fine", mi.fine, 0.3, 3.2)):
        if not (lo <= a.sg_dry <= hi):
            err.append(f"{tag}: oven-dry particle SG {a.sg_dry} outside {lo}-{hi}.")
        if not (0 <= a.abs24_pct <= 40):
            err.append(f"{tag}: 24 h absorption {a.abs24_pct} % must be 0-40 %.")
        if a.moisture_state not in MOISTURE_STATES:
            err.append(f"{tag}: unknown moisture state '{a.moisture_state}'.")
        if a.moisture_state == STATE_MC and a.moisture_pct < 0:
            err.append(f"{tag}: moisture content cannot be negative.")
        if not (0.0 <= a.absorption_fraction <= 1.0):
            err.append(f"{tag}: absorption fraction must be 0-1.")
        if a.bulk_density_dry is not None:
            if a.bulk_density_dry >= a.sg_dry * 1000:
                err.append(f"{tag}: loose bulk density {a.bulk_density_dry} kg/m³ cannot reach the "
                           f"particle density {a.sg_dry * 1000:.0f} kg/m³ - check SG vs bulk density.")
            else:
                packing = a.bulk_density_dry / (a.sg_dry * 1000)
                if not (0.35 <= packing <= 0.72):
                    warn.append(f"{tag}: bulk/particle density = {packing:.2f}; loose packing is normally "
                                "0.45-0.65. Re-check SG (must be oven-dry PARTICLE SG, not solid SG).")
        if a.abs24_pct > 25:
            warn.append(f"{tag}: absorption {a.abs24_pct:g} % is very high - strict pre-soaking and "
                        "slump-loss control are essential.")
    if mi.coarse.sg_dry > 2.0 or mi.coarse.sg_dry < 0.5:
        warn.append("LECA particle SG is outside the usual 0.5-2.0 range.")
    return err, warn


# ------------------------------------------------------------------------------ engine
def design_leca_mix(mi: LecaInputs) -> LecaResult:
    err, warnings = _validate(mi)
    if err:
        raise InputError(err)
    steps: List[Step] = []
    checks: List[Check] = []
    ca, fa = mi.coarse, mi.fine

    # 1. target strength -----------------------------------------------------------------
    S = mi.std_dev_override if mi.std_dev_override else C.table2_S(mi.fck)
    if not mi.std_dev_override and mi.site_control == "Fair":
        S += 1.0
    X = C.table1_X(mi.fck)
    target = max(mi.fck + 1.65 * S, mi.fck + X)
    steps.append(Step("1", "Target mean strength f'ck",
                      f"max(fck+1.65S, fck+X) = max({mi.fck + 1.65 * S:.2f}, {mi.fck + X:.2f})",
                      f"{target:.2f} MPa", SRC_IS + " - statistical rule only; LWAC code not supplied"))

    # 2. w/cm from strength -----------------------------------------------------------------
    if mi.wcm_manual is not None:
        wcm_s, src = mi.wcm_manual, "User input (from trials / supplier data)"
    else:
        equiv = target / mi.strength_efficiency
        wcm_s, extrap = estimate_wc_from_fig1_curve2(equiv)
        src = (f"{SRC_ASSUME}: normal-weight Abrams-type curve (IS 10262 Fig. 1 anchors) evaluated at "
               f"f'ck / efficiency = {target:.1f}/{mi.strength_efficiency:g} = {equiv:.1f} MPa")
        warnings.append("w/cm was ESTIMATED with a normal-weight strength curve and an efficiency factor. "
                        "LECA particle strength limits the achievable strength - calibrate with trials "
                        "or enter w/cm manually.")
        if extrap:
            warnings.append("Equivalent strength lies outside the curve anchors (20.8-48.3 MPa); extrapolated.")
        if not (0.25 <= wcm_s <= 0.70):
            warnings.append(f"Estimated w/cm {wcm_s:.2f} was clamped into 0.25-0.70.")
            wcm_s = min(max(wcm_s, 0.25), 0.70)
    steps.append(Step("2", "Free w/cm for strength", "strength curve / manual", f"{wcm_s:.3f}", src))

    # 3. net water ---------------------------------------------------------------------------
    w_slump = mi.water_base_50mm * (1 + (mi.slump - 50.0) / 25.0 * C.SLUMP_STEP_PERCENT / 100.0)
    w_net = w_slump * (1 - mi.admixture_water_reduction_pct / 100.0)
    steps.append(Step("3", "Net (free) mixing water",
                      f"{mi.water_base_50mm:g} x (1+{(mi.slump - 50) / 25 * 0.03:.3f}) x "
                      f"(1-{mi.admixture_water_reduction_pct:g}/100)",
                      f"{w_net:.1f} kg/m³", SRC_ASSUME + " (3 %/25 mm slump rule as IS 10262 cl. 5.3)"))

    # 4. binder ---------------------------------------------------------------------------------
    b0 = w_net / wcm_s
    binder = max(b0, mi.min_binder)
    if binder > b0 + 1e-9:
        warnings.append(f"Binder raised from {b0:.0f} to the minimum {mi.min_binder:g} kg/m³; w/cm lowered.")
    wcm = w_net / binder
    scm_masses = {s.name: binder * s.percent / 100.0 for s in mi.scms if s.percent > 0}
    cement = binder - sum(scm_masses.values())
    steps.append(Step("4", "Binder and cement/SCM split",
                      f"w/cm {wcm_s:.3f} -> {w_net:.1f}/{wcm_s:.3f} = {b0:.1f}; adopted {binder:.1f}; "
                      "SCM are PART of the binder",
                      f"cement {cement:.1f}; " + ("; ".join(f"{k} {v:.1f}" for k, v in scm_masses.items())
                                                 or "no SCM") + f"; w/cm {wcm:.3f}",
                      SRC_ASSUME))
    adm = binder * mi.admixture_dose_pct / 100.0

    # 5. absolute volume of the paste ------------------------------------------------------------
    v = {"cement": cement / (mi.cement_sg * 1000), "water (net only)": w_net / 1000.0,
         "admixture": adm / (mi.admixture_sg * 1000), "air": mi.air_pct / 100.0}
    for s in mi.scms:
        if s.percent > 0:
            v[s.name] = scm_masses[s.name] / (s.sg * 1000)
    v_agg = 1.0 - sum(v.values())
    if v_agg <= 0.25:
        raise InputError([f"Aggregate volume {v_agg:.3f} m³ is too small - paste volume too large."])
    m_paste = binder + w_net + adm
    steps.append(Step("5", "Absolute volume - aggregate space",
                      "V_agg = 1 - air - Σ(mass/(SG x 1000)); ABSORBED water is not counted "
                      "(it sits inside the particle volume)", f"{v_agg:.4f} m³", SRC_IDENTITY))

    # 6. fine / coarse split ---------------------------------------------------------------------
    rho_c, rho_f = ca.particle_density_wet, fa.particle_density_wet
    d_min = m_paste + rho_c * v_agg            # 100 % LECA aggregate
    d_max = m_paste + rho_f * v_agg            # 100 % fine aggregate
    lo_d, hi_d = min(d_min, d_max), max(d_min, d_max)
    if mi.target_fresh_density is not None:
        if abs(rho_f - rho_c) < 1.0:
            raise InputError(["Fine and coarse particle densities are identical - density cannot be solved. "
                              "Enter a fine volume fraction instead."])
        vf = (mi.target_fresh_density - m_paste - rho_c * v_agg) / (rho_f - rho_c)
        if not (-1e-9 <= vf <= v_agg + 1e-9):
            raise InputError([
                f"Target fresh density {mi.target_fresh_density:g} kg/m³ is not achievable with this paste "
                f"and these aggregates. Achievable range: {lo_d:.0f}-{hi_d:.0f} kg/m³ "
                f"(all-LECA aggregate = {d_min:.0f}, all-fine = {d_max:.0f}). Change target density, "
                "LECA grade, binder/water or aggregate absorption."])
        vf = min(max(vf, 0.0), v_agg)
        how = (f"V_f = (ρt - M_paste - ρc·V_agg)/(ρf - ρc) = ({mi.target_fresh_density:g} - {m_paste:.1f} - "
               f"{rho_c:.0f}x{v_agg:.4f})/({rho_f:.0f}-{rho_c:.0f})")
    else:
        vf = mi.fine_vol_fraction * v_agg
        how = f"V_f = fine fraction x V_agg = {mi.fine_vol_fraction:.3f} x {v_agg:.4f}"
    vc = v_agg - vf
    m_c_dry = vc * ca.sg_dry * 1000
    m_f_dry = vf * fa.sg_dry * 1000
    steps.append(Step("6", "Fine / coarse volumes and dry masses",
                      how + f";  V_c = {vc:.4f};  M_dry = V x SG x 1000",
                      f"LECA {m_c_dry:.1f} kg (V {vc:.4f} m³); fine {m_f_dry:.1f} kg (V {vf:.4f} m³)",
                      "Density closure (replaces IS 10262 Tables 5/10)"))
    v["LECA coarse (particle)"] = vc
    v["fine aggregate (particle)"] = vf

    # 7. water split -----------------------------------------------------------------------------
    absorb_total = absorb_have = absorb_add = surface = 0.0
    for agg, m_dry in ((ca, m_c_dry), (fa, m_f_dry)):
        A, m = agg.design_absorption(), agg.moisture()
        absorb_total += A * m_dry
        absorb_have += min(A, m) * m_dry
        absorb_add += max(A - m, 0.0) * m_dry
        surface += max(m - A, 0.0) * m_dry
    w_add = w_net + absorb_add - surface
    c_batch = m_c_dry * (1 + ca.moisture())
    f_batch = m_f_dry * (1 + fa.moisture())
    steps.append(Step("7", "Water split (net vs absorption)",
                      f"water to add = net {w_net:.1f} + absorption still needed {absorb_add:.1f} "
                      f"- surface-moisture credit {surface:.1f}",
                      f"{w_add:.1f} kg/m³ (absorption water in aggregate pores: {absorb_total:.1f})",
                      "Mass balance; absorption water adds mass but no volume"))

    # 8. densities and checks ----------------------------------------------------------------------
    fresh = binder + w_net + adm + m_c_dry * (1 + ca.design_absorption()) + m_f_dry * (1 + fa.design_absorption())
    batch_mass = binder + w_add + adm + c_batch + f_batch
    oven = m_c_dry + m_f_dry + HYDRATION_FACTOR * binder
    equil = oven + EQUILIBRIUM_EXTRA
    vol_sum = sum(v.values())
    steps.append(Step("8", "Densities",
                      "fresh = Σ masses with aggregate at design absorption; oven-dry ≈ dry aggregate + "
                      f"{HYDRATION_FACTOR} x binder; equilibrium ≈ oven-dry + {EQUILIBRIUM_EXTRA:g}",
                      f"fresh {fresh:.0f}; oven-dry ~{oven:.0f}; equilibrium ~{equil:.0f} kg/m³",
                      "Fresh = identity; oven-dry/equilibrium = " + SRC_ASSUME))

    checks.append(Check("Absolute-volume balance = 1 m³ (absorbed water excluded)",
                        "PASS" if abs(vol_sum - 1) < 1e-9 else "FAIL", f"Σ = {vol_sum:.6f} m³", SRC_IDENTITY))
    checks.append(Check("Mass balance (as-batched vs design)",
                        "PASS" if abs(batch_mass - fresh) < 1e-6 else "FAIL",
                        f"batch {batch_mass:.2f} kg vs design {fresh:.2f} kg", SRC_IDENTITY))
    if mi.target_fresh_density is not None:
        dev = fresh - mi.target_fresh_density
        checks.append(Check("Fresh density vs target",
                            "PASS" if abs(dev) <= mi.density_tolerance else "FAIL",
                            f"{fresh:.0f} vs {mi.target_fresh_density:g} kg/m³ (dev {dev:+.1f}, tol "
                            f"±{mi.density_tolerance:g})", SRC_IDENTITY))
    checks.append(Check("Binder content window",
                        "PASS" if mi.min_binder <= binder <= mi.max_binder else "REVIEW",
                        f"{binder:.0f} kg/m³ vs {mi.min_binder:g}-{mi.max_binder:g}", SRC_ASSUME))
    bulk_m3 = None
    if ca.bulk_density_dry:
        bulk_m3 = m_c_dry / ca.bulk_density_dry
        checks.append(Check("LECA loose bulk volume per m³ of concrete",
                            "PASS" if bulk_m3 <= 1.2 else "REVIEW",
                            f"{bulk_m3:.3f} m³ loose LECA per m³ (>1.2 suggests a harsh, segregation-prone "
                            "mix); also use it for batching by volume", SRC_ASSUME))
    if fa.sg_dry < 2.0:
        warnings.append("Fine aggregate is lightweight (all-lightweight mix): expect higher water demand "
                        "and lower strength per w/cm - verify the efficiency factor by trial.")
    if mi.leca_strength_ceiling_mpa is not None:
        ok = target <= mi.leca_strength_ceiling_mpa
        checks.append(Check("Target strength vs LECA strength ceiling", "PASS" if ok else "FAIL",
                            f"f'ck {target:.1f} vs ceiling {mi.leca_strength_ceiling_mpa:g} MPa. If FAIL, "
                            "lowering w/cm will NOT help - the aggregate governs; use a stronger/denser LECA.",
                            "User / supplier data"))
    else:
        checks.append(Check("Target strength vs LECA strength ceiling", "REVIEW",
                            "No ceiling entered. LECA particle strength caps concrete strength; ask the "
                            "supplier or test.", SRC_ASSUME))
    structural = mi.fck >= STRUCTURAL_MIN_MPA and STRUCTURAL_EQ_DENSITY[0] <= equil <= STRUCTURAL_EQ_DENSITY[1]
    checks.append(Check("Structural-LWC window (indicative)", "PASS" if structural else "REVIEW",
                        f"Commonly quoted: ≥{STRUCTURAL_MIN_MPA:g} MPa and equilibrium density "
                        f"{STRUCTURAL_EQ_DENSITY[0]:g}-{STRUCTURAL_EQ_DENSITY[1]:g} kg/m³. Yours: "
                        f"fck {mi.fck:g}, ~{equil:.0f}. Not a code check.", SRC_ASSUME))
    if ca.moisture_state == STATE_DRY and ca.abs24_pct >= 8:
        checks.append(Check("Dry LECA with high absorption", "REVIEW",
                            f"Dry LECA (abs {ca.abs24_pct:g} %) takes {absorb_add:.0f} kg/m³ from the mix; "
                            "pre-soak or pre-wet to avoid slump loss and paste dehydration.", SRC_ASSUME))
    if ca.moisture_state == STATE_MC and ca.moisture() > ca.design_absorption() + 1e-12:
        warnings.append("LECA carries surface water beyond the design absorption; credited against mixing water.")
    checks.append(Check("Trial mixes", "PENDING", "Trial batches (fresh density, slump, 28-day cubes) are "
                        "NOT performed by this software.", SRC_ASSUME))
    checks.append(Check("Laboratory verification", "PENDING", "Result is a starting proportion only.", SRC_ASSUME))

    cost = None
    if mi.prices_per_kg:
        p = mi.prices_per_kg
        cost = (cement * p.get("cement", 0) + adm * p.get("admixture", 0)
                + m_c_dry * p.get("leca", 0) + m_f_dry * p.get("fine_aggregate", 0)
                + sum(m * p.get(k, 0) for k, m in scm_masses.items()))

    return LecaResult(
        target_strength=target, std_dev=S, wcm_strength=wcm_s, wcm_final=wcm, water_net=w_net,
        binder_total=binder, cement=cement, scm_masses=scm_masses, admixture_mass=adm, air_pct=mi.air_pct,
        coarse_dry=m_c_dry, fine_dry=m_f_dry, coarse_batch=c_batch, fine_batch=f_batch,
        coarse_vol_m3=vc, fine_vol_m3=vf, fine_vol_fraction=vf / v_agg, leca_loose_bulk_m3=bulk_m3,
        absorption_water_total=absorb_total, absorption_from_aggregate_moisture=absorb_have,
        absorption_water_to_add=absorb_add, surface_moisture_credit=surface, water_to_add=w_add,
        fresh_density=fresh, oven_dry_density_est=oven, equilibrium_density_est=equil,
        volumes_m3=v, cost_per_m3=cost, steps=steps, checks=checks, warnings=warnings)


# ------------------------------------------------------------------------------ flat API
def design_leca_mix_simple(
        fck: float, target_fresh_density: float,
        leca_sg_dry: float, leca_bulk_density: float, leca_abs24_pct: float,
        leca_moisture_state: str = STATE_SSD, leca_moisture_pct: float = 0.0,
        fine_sg_dry: float = 2.62, fine_abs_pct: float = 1.0,
        fine_moisture_state: str = STATE_SSD, fine_moisture_pct: float = 0.0,
        scm: Optional[Dict[str, float]] = None, **extra) -> dict:
    """Flat-parameter convenience wrapper. scm = {"GGBS": 30, "Fly ash": 10} (% of binder).
    Any other LecaInputs field (slump, wcm_manual, admixture_dose_pct, ...) goes in **extra.
    Returns a plain dict of batch quantities (kg/m³)."""
    sg = {"GGBS": C.DEFAULT_SG["GGBS"], "Fly ash": C.DEFAULT_SG["Fly ash"],
          "Silica fume": C.DEFAULT_SG["Silica fume"], "Metakaolin": C.DEFAULT_SG["Metakaolin"]}
    mi = LecaInputs(
        fck=fck, target_fresh_density=target_fresh_density,
        coarse=LightAgg("LECA (coarse)", leca_sg_dry, leca_abs24_pct, leca_bulk_density,
                        leca_moisture_state, leca_moisture_pct),
        fine=LightAgg("Fine aggregate", fine_sg_dry, fine_abs_pct, None,
                      fine_moisture_state, fine_moisture_pct),
        scms=[ScmInput(k, float(p), sg.get(k, 2.5)) for k, p in (scm or {}).items() if p > 0], **extra)
    r = design_leca_mix(mi)
    return {
        "cement": r.cement, **{f"scm_{k}": v for k, v in r.scm_masses.items()},
        "net_water": r.water_net, "absorption_water": r.absorption_water_total,
        "water_to_add_at_mixer": r.water_to_add,
        "fine_aggregate_oven_dry": r.fine_dry, "fine_aggregate_batch": r.fine_batch,
        "leca_oven_dry": r.coarse_dry, "leca_batch": r.coarse_batch,
        "admixture": r.admixture_mass, "fresh_density": r.fresh_density,
        "wcm": r.wcm_final, "target_strength_mpa": r.target_strength,
        "warnings": r.warnings,
    }


def result_to_dict(res: LecaResult) -> dict:
    return asdict(res)
