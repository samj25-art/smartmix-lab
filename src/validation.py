"""Input validation for the engineering calculator and the ML predictor."""
from __future__ import annotations

from typing import Dict, List, Tuple

from . import constants as C


class InputError(ValueError):
    """Raised when inputs are missing / impossible. Message lists every problem."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def validate_mix_inputs(mi) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings) for a MixInputs object. Errors block calculation."""
    errors: List[str] = []
    warnings: List[str] = []

    if not (10 <= mi.fck <= 100):
        errors.append(f"Grade fck={mi.fck} MPa is outside the supported range M10-M100.")
    hsc = mi.fck >= 65
    allowed_msa = list(C.TABLE7_WATER) if hsc else list(C.TABLE4_WATER)
    if mi.msa not in allowed_msa:
        errors.append(
            f"Maximum aggregate size {mi.msa} mm is not covered by the "
            f"{'high-strength (Tables 6-10)' if hsc else 'ordinary/standard (Tables 3-5)'} "
            f"procedure. Allowed: {allowed_msa} mm."
        )
    if not (25 <= mi.slump <= 200):
        errors.append("Slump must be between 25 and 200 mm (the 3 %/25 mm rule is only a guide).")
    if mi.aggregate_shape not in C.SHAPE_WATER_REDUCTION:
        errors.append(f"Unknown aggregate shape '{mi.aggregate_shape}'.")
    zones = C.TABLE10_CA[mi.msa] if (hsc and mi.msa in C.TABLE10_CA) else (
        C.TABLE5_CA.get(mi.msa, {}))
    if zones and mi.fa_zone not in zones:
        errors.append(f"Fine aggregate zone '{mi.fa_zone}' is not tabulated for this case. "
                      f"Allowed: {list(zones)}.")
    for label, v in (("Cement SG", mi.cement_sg), ("Coarse aggregate SG", mi.sg_ca),
                     ("Fine aggregate SG", mi.sg_fa), ("Admixture SG", mi.admixture_sg)):
        if not (0.8 <= v <= 4.0):
            errors.append(f"{label} = {v} is not physically sensible (expected 0.8-4.0).")
    for label, v in (("Coarse aggregate absorption", mi.abs_ca),
                     ("Fine aggregate absorption", mi.abs_fa)):
        if not (0 <= v <= 20):
            errors.append(f"{label} = {v} % must be between 0 and 20 %.")
    for label, v in (("Admixture dose", mi.admixture_dose_pct),
                     ("Admixture water reduction", mi.admixture_water_reduction_pct),
                     ("Binder increase", mi.binder_increase_pct)):
        if v < 0:
            errors.append(f"{label} cannot be negative.")
    if mi.admixture_water_reduction_pct > 45:
        errors.append("Admixture water reduction above 45 % is not credible.")
    if mi.admixture_type == "None" and (mi.admixture_dose_pct > 0
                                        or mi.admixture_water_reduction_pct > 0):
        errors.append("Admixture type is 'None' but a dose / water reduction was entered.")
    if mi.admixture_dose_pct > 0 and mi.admixture_water_reduction_pct == 0:
        warnings.append("Admixture dose entered but water reduction is 0 %. The calculator never "
                        "derives water reduction from dose; enter the % established by trial "
                        "(or leave 0 for a conservative mix).")
    total_scm = sum(s.percent for s in mi.scms)
    if total_scm >= 80:
        errors.append("Total SCM replacement of 80 % or more is outside this tool's scope.")
    for s in mi.scms:
        if s.percent < 0:
            errors.append(f"{s.name} percentage cannot be negative.")
        if not (1.0 <= s.sg <= 4.0):
            errors.append(f"{s.name} specific gravity {s.sg} is not sensible.")
    max_pump = 5.0 if hsc else 10.0
    if not (0 <= mi.pumpable_ca_reduction_pct <= max_pump):
        errors.append(f"Coarse-aggregate reduction for pumping must be 0-{max_pump:.0f} % "
                      f"(IS 10262 cl. {'6.2.7' if hsc else '5.5.2'}).")
    for label, mode, tot, ab in (("Coarse", mi.moisture_mode_ca, mi.moisture_total_ca, mi.abs_ca),
                                 ("Fine", mi.moisture_mode_fa, mi.moisture_total_fa, mi.abs_fa)):
        if mode not in ("SSD", "Oven-dry", "Field moist"):
            errors.append(f"{label} aggregate condition '{mode}' unknown.")
        if mode == "Field moist" and tot < 0:
            errors.append(f"{label} aggregate total moisture cannot be negative.")
    if mi.wc_manual is not None and not (0.2 <= mi.wc_manual <= 0.8):
        errors.append("Manual w/c must be between 0.20 and 0.80.")
    if (not hsc) and mi.wc_manual is None and mi.cement_type not in ("OPC 43", "PPC"):
        errors.append(
            "For OPC 33 / OPC 53 the w/c has to be read from IS 10262 Fig. 1 (curve 1 / curve 3) "
            "and entered manually - the app only holds verified anchor points for curve 2.")
    return errors, warnings


def validate_prediction_row(row: Dict[str, float], ranges: Dict[str, Tuple[float, float]]
                            ) -> Tuple[List[str], List[str]]:
    """Errors for impossible input, warnings for values outside training range."""
    errors, warnings = [], []
    for f in C.FEATURES:
        if f not in row:
            errors.append(f"Missing feature '{f}'.")
            continue
        v = row[f]
        try:
            v = float(v)
        except (TypeError, ValueError):
            errors.append(f"{f} must be a number.")
            continue
        if v != v:  # NaN
            errors.append(f"{f} is NaN.")
            continue
        if v < 0:
            errors.append(f"{C.FEATURE_LABELS[f]} cannot be negative.")
        if f == "age" and v <= 0:
            errors.append("Curing age must be at least 1 day.")
        if f == "water" and v <= 0:
            errors.append("Water content must be positive.")
        if f in ranges and not errors:
            lo, hi = ranges[f]
            if v < lo or v > hi:
                warnings.append(
                    f"{C.FEATURE_LABELS[f]} = {v:g} is outside the training range "
                    f"[{lo:g}, {hi:g}] - extrapolation, prediction is unreliable.")
    return errors, warnings
