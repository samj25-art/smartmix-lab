"""Command-line training (alternative to the 'AI Model' page).

    python train_model.py                      # uses data/concrete_data.csv or tries to download
    python train_model.py path\to\Concrete_Data.xls
    python train_model.py --fast               # smaller grids, quick demo
"""
import sys
from pathlib import Path

from src.data_loading import load_dataset, read_any, standardise, DatasetUnavailable, DatasetInvalid
from src.model_training import train_and_save

args = [a for a in sys.argv[1:] if not a.startswith("--")]
fast = "--fast" in sys.argv
try:
    df = standardise(read_any(Path(args[0]))) if args else load_dataset()
except (DatasetUnavailable, DatasetInvalid) as e:
    sys.exit(f"ERROR: {e}")
meta = train_and_save(df, fast=fast, progress=print)
print("\nSelected model:", meta["selected_model"])
print("Held-out test metrics:", {k: round(v, 3) for k, v in meta["test_metrics"].items()})
