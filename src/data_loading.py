"""
Loading / cleaning / validating the UCI Concrete Compressive Strength dataset.

Source: https://archive.ics.uci.edu/dataset/165/concrete+compressive+strength
Expected: 1030 rows, 8 inputs (kg/m3 except age in days) + compressive strength (MPa).

Nothing is ever fabricated here. If the file cannot be downloaded the caller gets a clear
`DatasetUnavailable` error and the UI offers an upload box instead.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import constants as C

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CSV = DATA_DIR / "concrete_data.csv"


class DatasetUnavailable(RuntimeError):
    """Raised when the dataset cannot be loaded (e.g. no internet and no CSV supplied)."""


class DatasetInvalid(ValueError):
    """Raised when the file does not have the expected columns / content."""


# keyword -> standard name (matched on lower-cased original header)
_COLUMN_RULES = [
    (r"blast|slag", "slag"),
    (r"fly\s*ash", "fly_ash"),
    (r"superplast", "superplasticizer"),
    (r"coarse", "coarse_agg"),
    (r"fine", "fine_agg"),
    (r"^cement|cement\s*\(", "cement"),
    (r"^water|water\s*\(", "water"),
    (r"^age|age\s*\(", "age"),
    (r"strength", "strength"),
]


def clean_column_names(columns) -> Dict[str, str]:
    """Map arbitrary UCI/Kaggle-style headers to the standard feature names."""
    mapping = {}
    for col in columns:
        low = str(col).strip().lower()
        for pattern, std in _COLUMN_RULES:
            if re.search(pattern, low):
                mapping[col] = std
                break
    return mapping


def standardise(df: pd.DataFrame) -> pd.DataFrame:
    mapping = clean_column_names(df.columns)
    out = df.rename(columns=mapping)
    missing = [c for c in C.FEATURES + [C.TARGET] if c not in out.columns]
    if missing:
        raise DatasetInvalid(
            f"Missing required columns {missing}. Found: {list(df.columns)}. Expected the UCI "
            "dataset: cement, slag, fly ash, water, superplasticizer, coarse aggregate, fine "
            "aggregate, age, compressive strength.")
    dup_names = [c for c in out.columns if list(out.columns).count(c) > 1]
    if dup_names:
        raise DatasetInvalid(f"Ambiguous duplicate column names after cleaning: {set(dup_names)}")
    return out[C.FEATURES + [C.TARGET]].apply(pd.to_numeric, errors="coerce")


def read_any(file_or_path) -> pd.DataFrame:
    """Read CSV, XLS/XLSX (UCI ships an .xls) or a UCI zip from a path or an uploaded buffer."""
    name = getattr(file_or_path, "name", str(file_or_path)).lower()
    try:
        if name.endswith(".zip"):
            buf = file_or_path if hasattr(file_or_path, "read") else open(file_or_path, "rb")
            with zipfile.ZipFile(buf) as z:
                member = next((m for m in z.namelist()
                               if m.lower().endswith((".csv", ".xlsx", ".xls"))), None)
                if member is None:
                    raise DatasetInvalid("The zip contains no CSV/XLS file.")
                data = z.read(member)
            if member.lower().endswith(".csv"):
                return pd.read_csv(io.BytesIO(data))
            return pd.read_excel(io.BytesIO(data))
        if name.endswith((".xlsx", ".xls")):
            return pd.read_excel(file_or_path)
        return pd.read_csv(file_or_path)
    except DatasetInvalid:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any parsing problem clearly
        raise DatasetInvalid(f"Could not read the file: {exc}") from exc


def try_download(dest: Path = DEFAULT_CSV, timeout: int = 20) -> Path:
    """Attempt to fetch the dataset; raise DatasetUnavailable (never crash) when offline."""
    try:
        import urllib.request
        with urllib.request.urlopen(C.UCI_URL, timeout=timeout) as resp:  # nosec - fixed URL
            payload = resp.read()
        df = standardise(read_any(_NamedBytes(payload, "uci.zip")))
        dest.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(dest, index=False)
        return dest
    except Exception as exc:  # noqa: BLE001
        raise DatasetUnavailable(
            f"Could not download the dataset automatically ({type(exc).__name__}: {exc}). "
            f"Download it manually from {C.UCI_PAGE} and either place it at {dest} "
            "or upload it on the 'AI Model' page.") from exc


class _NamedBytes(io.BytesIO):
    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name


def load_dataset(path: Optional[Path] = None, allow_download: bool = True) -> pd.DataFrame:
    """Load from the given/default CSV; otherwise try a download; otherwise raise."""
    path = Path(path) if path else DEFAULT_CSV
    if path.exists():
        return standardise(read_any(path))
    if allow_download:
        return standardise(read_any(try_download(path)))
    raise DatasetUnavailable(f"No dataset at {path}. Upload the UCI CSV on the 'AI Model' page.")


def data_quality_report(df: pd.DataFrame) -> Dict[str, object]:
    """Report problems WITHOUT deleting anything."""
    feats = C.FEATURES + [C.TARGET]
    rep: Dict[str, object] = {"rows": int(len(df)), "columns": list(df.columns)}
    rep["missing_values"] = {c: int(df[c].isna().sum()) for c in feats}
    rep["duplicate_rows"] = int(df.duplicated().sum())
    neg = {c: int((df[c] < 0).sum()) for c in feats}
    rep["negative_values"] = neg
    rep["non_positive_age"] = int((df["age"] <= 0).sum())
    rep["non_positive_strength"] = int((df[C.TARGET] <= 0).sum())
    rep["non_positive_water"] = int((df["water"] <= 0).sum())
    out = {}
    for c in feats:
        q1, q3 = df[c].quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out[c] = int(((df[c] < lo) | (df[c] > hi)).sum())
    rep["iqr_outlier_counts"] = out   # flagged for information only - never auto-removed
    rep["ranges"] = {c: (float(df[c].min()), float(df[c].max())) for c in feats}
    problems: List[str] = []
    if rep["rows"] < 200:
        problems.append(f"Only {rep['rows']} rows - too few for a meaningful ML model.")
    if any(rep["missing_values"].values()):
        problems.append("Missing values present - rows with missing values will be excluded "
                        "from training (they are not imputed).")
    if any(neg.values()) or rep["non_positive_age"] or rep["non_positive_water"]:
        problems.append("Physically impossible values (negative / zero water or age) present - "
                        "those rows will be excluded from training.")
    if rep["duplicate_rows"]:
        problems.append(f"{rep['duplicate_rows']} duplicate rows found. They are kept, but "
                        "identical rows are forced into the same train/test side to avoid leakage.")
    rep["problems"] = problems
    return rep


def usable_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows that are physically valid (everything else stays in the raw df for reporting)."""
    m = df.notna().all(axis=1)
    for c in C.FEATURES + [C.TARGET]:
        m &= df[c] >= 0
    m &= (df["age"] > 0) & (df["water"] > 0) & (df[C.TARGET] > 0)
    return df[m].reset_index(drop=True)
