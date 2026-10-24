"""Prediction with the saved model: schema check, range check, approximate error band."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import pandas as pd

from . import constants as C
from .model_training import MODEL_DIR
from .validation import InputError, validate_prediction_row


class ModelNotTrained(RuntimeError):
    pass


@dataclass
class Prediction:
    strength_mpa: float
    interval_low: float
    interval_high: float
    age_days: float
    target_mpa: Optional[float]
    difference_to_target: Optional[float]
    warnings: List[str] = field(default_factory=list)
    model_name: str = ""
    test_metrics: Dict[str, float] = field(default_factory=dict)
    extrapolating: bool = False


def load_model(model_dir: Path = MODEL_DIR) -> dict:
    p = Path(model_dir) / "model.joblib"
    if not p.exists():
        raise ModelNotTrained("No trained model found. Train one on the 'AI Model' page first.")
    bundle = joblib.load(p)
    if bundle["meta"].get("features") != C.FEATURES:
        raise ModelNotTrained("The saved model uses a different feature schema than this app "
                              f"({bundle['meta'].get('features')} vs {C.FEATURES}). Retrain it.")
    return bundle


def predict_strength(row: Dict[str, float], target_mpa: Optional[float] = None,
                     model_dir: Path = MODEL_DIR) -> Prediction:
    bundle = load_model(model_dir)
    meta = bundle["meta"]
    ranges = {k: tuple(v) for k, v in meta["training_ranges"].items()}
    errors, warns = validate_prediction_row(row, ranges)
    if errors:
        raise InputError(errors)
    X = pd.DataFrame([[float(row[f]) for f in meta["features"]]], columns=meta["features"])
    y = float(bundle["pipeline"].predict(X)[0])

    # extra plausibility warnings (training-range based, not code based)
    binder = row["cement"] + row["slag"] + row["fly_ash"]
    if binder > 0:
        wb = row["water"] / binder
        if wb < 0.2 or wb > 1.0:
            warns.append(f"Water/binder ratio {wb:.2f} is unusual for the training data.")
    else:
        warns.append("No cementitious material entered - prediction is meaningless.")
    extrap = any("outside the training range" in w for w in warns)
    q = meta["residual_quantiles_test"]
    lo, hi = y + q["q05"], y + q["q95"]
    diff = None if target_mpa is None else y - target_mpa
    warns.append("Prediction uncertainty: the approximate 90 % band comes from residuals on the "
                 "held-out test set of the public lab dataset; your materials, cement, curing and "
                 "testing differ, so real strength can fall outside it. Confirm by cube tests.")
    return Prediction(strength_mpa=y, interval_low=lo, interval_high=hi,
                      age_days=float(row["age"]), target_mpa=target_mpa,
                      difference_to_target=diff, warnings=warns,
                      model_name=meta["selected_model"], test_metrics=meta["test_metrics"],
                      extrapolating=extrap)
