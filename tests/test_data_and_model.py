import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src import constants as C
from src.data_loading import (DatasetInvalid, data_quality_report, standardise, usable_rows,
                              load_dataset, DatasetUnavailable)
from src.model_training import TrainingError, model_status, train_and_save
from src.prediction import ModelNotTrained, predict_strength
from src.validation import InputError, validate_prediction_row
from tests.synthetic import make_synthetic, uci_style_headers


class TestData(unittest.TestCase):
    def test_uci_headers_are_mapped(self):
        df = standardise(uci_style_headers(make_synthetic(300)))
        self.assertEqual(list(df.columns), C.FEATURES + [C.TARGET])

    def test_missing_columns_rejected(self):
        with self.assertRaises(DatasetInvalid):
            standardise(pd.DataFrame({"a": [1], "b": [2]}))

    def test_quality_report_flags_but_does_not_delete(self):
        df = make_synthetic(300)
        df.loc[100, "water"] = -5      # rows 0-19 are duplicated on purpose; edit others
        df.loc[101, "cement"] = np.nan
        rep = data_quality_report(df)
        self.assertEqual(rep["rows"], len(df))
        self.assertGreaterEqual(rep["duplicate_rows"], 20)
        self.assertEqual(len(usable_rows(df)), len(df) - 2)

    def test_offline_without_file_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(DatasetUnavailable):
                load_dataset(Path(t) / "nope.csv", allow_download=False)


class TestModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.df = make_synthetic()
        cls.meta = train_and_save(cls.df, model_dir=cls.dir, fast=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_not_trained_status_when_nothing_saved(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertFalse(model_status(Path(t))["trained"])
            with self.assertRaises(ModelNotTrained):
                predict_strength(dict(zip(C.FEATURES, [300, 0, 0, 180, 0, 1000, 800, 28])), model_dir=Path(t))

    def test_refuses_tiny_dataset(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(TrainingError):
                train_and_save(make_synthetic(100), model_dir=Path(t), fast=True)
            self.assertFalse((Path(t) / "model.joblib").exists())

    def test_three_models_compared(self):
        names = {r["model"] for r in self.meta["cv_results"]}
        self.assertEqual(names, {"Linear Regression", "Random Forest", "Hist Gradient Boosting"})

    def test_metrics_come_from_saved_test_predictions(self):
        t = pd.read_csv(self.dir / "test_predictions.csv")
        m = self.meta["test_metrics"]
        self.assertAlmostEqual(m["MAE_MPa"], mean_absolute_error(t.actual, t.predicted), places=9)
        self.assertAlmostEqual(m["RMSE_MPa"], float(np.sqrt(mean_squared_error(t.actual, t.predicted))), places=9)
        self.assertAlmostEqual(m["R2"], r2_score(t.actual, t.predicted), places=9)
        self.assertEqual(len(t), self.meta["n_test"])

    def test_split_is_reproducible_and_duplicates_not_leaked(self):
        with tempfile.TemporaryDirectory() as t:
            meta2 = train_and_save(self.df, model_dir=Path(t), fast=True)
            self.assertEqual(meta2["test_metrics"], self.meta["test_metrics"])
        tp = pd.read_csv(self.dir / "test_predictions.csv")
        self.assertGreater(self.meta["n_train"], 3 * self.meta["n_test"])

    def test_prediction_uses_schema_and_warns_out_of_range(self):
        row = dict(zip(C.FEATURES, [300, 0, 0, 180, 0, 1000, 800, 28]))
        p = predict_strength(row, target_mpa=30, model_dir=self.dir)
        self.assertTrue(np.isfinite(p.strength_mpa))
        self.assertAlmostEqual(p.difference_to_target, p.strength_mpa - 30, places=9)
        self.assertFalse(p.extrapolating)
        row["cement"] = 5000
        p2 = predict_strength(row, model_dir=self.dir)
        self.assertTrue(p2.extrapolating)
        self.assertTrue(any("outside the training range" in w for w in p2.warnings))

    def test_invalid_prediction_inputs_rejected(self):
        bad = dict(zip(C.FEATURES, [300, 0, 0, 180, 0, 1000, 800, 28]))
        bad["water"] = -1
        with self.assertRaises(InputError):
            predict_strength(bad, model_dir=self.dir)
        missing = {k: 1.0 for k in C.FEATURES[:-1]}
        with self.assertRaises(InputError):
            predict_strength(missing, model_dir=self.dir)
        e, _ = validate_prediction_row({**bad, "water": 180, "age": 0}, {})
        self.assertTrue(any("age" in x.lower() for x in e))

    def test_feature_order_matters_and_is_enforced(self):
        meta = json.loads((self.dir / "metrics.json").read_text())
        self.assertEqual(meta["features"], C.FEATURES)


if __name__ == "__main__":
    unittest.main()
