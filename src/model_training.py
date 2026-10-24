"""
Reproducible training pipeline for compressive-strength prediction.

Protocol
--------
1. Validate the data, drop only physically impossible/missing rows (reported, not hidden).
2. One held-out TEST set (default 20 %), created with a fixed seed. Identical rows (the UCI
   file contains duplicates) share a group id so they cannot appear on both sides (leakage).
3. Model comparison + hyper-parameter tuning use ONLY the training part, with GroupKFold CV.
4. The selection criterion is cross-validated RMSE. The test set is touched exactly once,
   after the winner has been chosen, to compute MAE / RMSE / R2.
5. Artefacts are written to models/: model.joblib, metrics.json, test_predictions.csv,
   feature_importance.csv, cv_results.csv. Nothing is written if training fails.
"""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import constants as C
from .data_loading import data_quality_report, usable_rows

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
SEED = 42


class TrainingError(RuntimeError):
    pass


def _candidates(seed: int, fast: bool = False):
    rf_grid = {"model__n_estimators": [150] if fast else [300],
               "model__max_depth": [None, 20],
               "model__min_samples_leaf": [1, 2]}
    hgb_grid = {"model__learning_rate": [0.05, 0.1],
                "model__max_iter": [200] if fast else [300, 600],
                "model__max_leaf_nodes": [15, 31],
                "model__l2_regularization": [0.0, 1.0]}
    return {
        "Linear Regression": (Pipeline([("scale", StandardScaler()), ("model", LinearRegression())]), {}),
        "Random Forest": (Pipeline([("model", RandomForestRegressor(random_state=seed, n_jobs=-1))]), rf_grid),
        "Hist Gradient Boosting": (Pipeline([("model", HistGradientBoostingRegressor(random_state=seed))]), hgb_grid),
    }


def _rmse(y, p):
    return float(np.sqrt(mean_squared_error(y, p)))


def train_and_save(df_raw: pd.DataFrame, model_dir: Path = MODEL_DIR, seed: int = SEED,
                   test_size: float = 0.2, cv_folds: int = 5, fast: bool = False,
                   progress: Optional[Callable[[str], None]] = None) -> Dict[str, object]:
    say = progress or (lambda m: None)
    model_dir = Path(model_dir)

    say("Checking data quality ...")
    quality = data_quality_report(df_raw)
    df = usable_rows(df_raw)
    if len(df) < 200:
        raise TrainingError(f"Only {len(df)} valid rows - refusing to train a model on so little data.")
    dropped = int(len(df_raw) - len(df))

    X, y = df[C.FEATURES], df[C.TARGET]
    groups = df.groupby(C.FEATURES + [C.TARGET], sort=False).ngroup().to_numpy()

    say("Creating reproducible train/test split ...")
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    tr_idx, te_idx = next(gss.split(X, y, groups))
    X_tr, X_te, y_tr, y_te = X.iloc[tr_idx], X.iloc[te_idx], y.iloc[tr_idx], y.iloc[te_idx]
    g_tr = groups[tr_idx]
    cv = GroupKFold(n_splits=cv_folds)

    results, fitted = [], {}
    for name, (pipe, grid) in _candidates(seed, fast).items():
        say(f"Cross-validating {name} ...")
        gs = GridSearchCV(pipe, grid if grid else {}, cv=cv,
                          scoring="neg_root_mean_squared_error", n_jobs=1, refit=True)
        gs.fit(X_tr, y_tr, groups=g_tr)
        results.append({"model": name, "cv_rmse": float(-gs.best_score_),
                        "best_params": {k.replace("model__", ""): v for k, v in gs.best_params_.items()}})
        fitted[name] = gs.best_estimator_

    cv_table = pd.DataFrame(results).sort_values("cv_rmse").reset_index(drop=True)
    best_name = str(cv_table.loc[0, "model"])
    best = fitted[best_name]

    say("Evaluating the selected model ONCE on the held-out test set ...")
    pred = best.predict(X_te)
    metrics = {"MAE_MPa": float(mean_absolute_error(y_te, pred)),
               "RMSE_MPa": _rmse(y_te, pred),
               "R2": float(r2_score(y_te, pred))}
    # for transparency: test metrics of the non-selected models are NOT used for selection
    other_test = {n: {"MAE_MPa": float(mean_absolute_error(y_te, m.predict(X_te))),
                      "RMSE_MPa": _rmse(y_te, m.predict(X_te)),
                      "R2": float(r2_score(y_te, m.predict(X_te)))} for n, m in fitted.items()}
    resid = (y_te.to_numpy() - pred)
    q05, q95 = np.quantile(resid, [0.05, 0.95])

    say("Computing permutation importance ...")
    imp = permutation_importance(best, X_te, y_te, n_repeats=10, random_state=seed,
                                 scoring="neg_root_mean_squared_error")
    imp_df = pd.DataFrame({"feature": C.FEATURES,
                           "importance_rmse_increase": imp.importances_mean,
                           "std": imp.importances_std}).sort_values(
        "importance_rmse_increase", ascending=False)

    meta = {
        "trained": True,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selected_model": best_name,
        "selected_params": results[[r["model"] for r in results].index(best_name)]["best_params"],
        "dataset_rows_raw": int(len(df_raw)), "dataset_rows_used": int(len(df)),
        "rows_excluded": dropped, "n_train": int(len(tr_idx)), "n_test": int(len(te_idx)),
        "duplicate_rows_in_data": quality["duplicate_rows"],
        "test_size": test_size, "cv_folds": cv_folds, "seed": seed,
        "dataset_sha256": hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest(),
        "features": C.FEATURES, "target": C.TARGET, "units": "kg/m3 (age in days) -> MPa",
        "training_ranges": {f: [float(df[f].min()), float(df[f].max())] for f in C.FEATURES},
        "strength_range": [float(y.min()), float(y.max())],
        "test_metrics": metrics, "test_metrics_all_models_for_information": other_test,
        "cv_results": results,
        "residual_quantiles_test": {"q05": float(q05), "q95": float(q95)},
        "versions": {"sklearn": sklearn.__version__, "python": platform.python_version(),
                     "pandas": pd.__version__, "numpy": np.__version__},
        "data_quality": {k: quality[k] for k in ("duplicate_rows", "missing_values",
                                                 "iqr_outlier_counts", "problems")},
    }

    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": best, "meta": meta}, model_dir / "model.joblib")
    (model_dir / "metrics.json").write_text(json.dumps(meta, indent=2))
    pd.DataFrame({"actual": y_te.to_numpy(), "predicted": pred, "residual": resid}
                 ).to_csv(model_dir / "test_predictions.csv", index=False)
    imp_df.to_csv(model_dir / "feature_importance.csv", index=False)
    cv_table.to_csv(model_dir / "cv_results.csv", index=False)
    say("Done.")
    return meta


def model_status(model_dir: Path = MODEL_DIR) -> Dict[str, object]:
    """Return metadata of the saved model, or {'trained': False}. Never invents values."""
    f = Path(model_dir) / "metrics.json"
    if not (Path(model_dir) / "model.joblib").exists() or not f.exists():
        return {"trained": False}
    try:
        meta = json.loads(f.read_text())
        return meta if meta.get("trained") else {"trained": False}
    except Exception:  # noqa: BLE001
        return {"trained": False, "error": "metrics.json unreadable"}
