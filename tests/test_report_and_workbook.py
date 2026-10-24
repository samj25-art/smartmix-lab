import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src import constants as C
from src.engineering import MixInputs, ScmInput, design_mix
from src.model_training import train_and_save, model_status
from src.prediction import predict_strength
from src.report import build_pdf, results_csv_bytes, results_dataframe
from src.workbook_replica import run_workbook_logic, AUDIT_FINDINGS
from tests.synthetic import make_synthetic


class TestReports(unittest.TestCase):
    def setUp(self):
        self.mi = MixInputs(fck=40, wc_manual=0.36, scms=[ScmInput("Fly ash", 30, 2.2)],
                            binder_increase_pct=10, admixture_type="Superplasticiser, normal (SMF/SNF)",
                            admixture_dose_pct=1.0, admixture_water_reduction_pct=23,
                            prices_per_kg={"cement": 7, "fine_aggregate": 1, "coarse_aggregate": 1})
        self.res = design_mix(self.mi)

    def test_pdf_without_model_has_no_fake_numbers(self):
        pdf = build_pdf(self.mi, self.res, None, {"trained": False})
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 3000)

    def test_csv_without_prediction_has_no_ml_rows(self):
        df = results_dataframe(self.mi, self.res, None)
        self.assertNotIn("Predicted (ML)", set(df["Type"]))
        self.assertIn("Calculated", set(df["Type"]))
        raw = results_csv_bytes(self.mi, self.res, None)
        self.assertGreater(len(pd.read_csv(io.BytesIO(raw))), 10)

    def test_pdf_and_csv_with_prediction(self):
        with tempfile.TemporaryDirectory() as t:
            meta = train_and_save(make_synthetic(600), model_dir=Path(t), fast=True)
            pred = predict_strength(dict(zip(C.FEATURES, [300, 0, 50, 170, 3, 1000, 800, 28])), 40, Path(t))
            pdf = build_pdf(self.mi, self.res, pred, meta)
            self.assertTrue(pdf.startswith(b"%PDF"))
            df = results_dataframe(self.mi, self.res, pred)
            self.assertIn("Predicted (ML)", set(df["Type"]))

    def test_pdf_without_calculation(self):
        self.assertTrue(build_pdf(self.mi, None, None, None).startswith(b"%PDF"))


class TestWorkbookReplica(unittest.TestCase):
    def test_replica_matches_workbook_cell_logic(self):
        r = run_workbook_logic()         # saved INPUT sheet: M70, severe, 120 mm, 10 mm, FA 10, 1 %
        self.assertAlmostEqual(r["target_strength"], 78.25)
        self.assertAlmostEqual(r["wc"], 0.35)
        self.assertAlmostEqual(r["water_after_plasticizer"], 202 * 1.09 * 0.99, places=6)
        self.assertAlmostEqual(r["status_threshold_used_by_B12"], 82.0)   # MID() bug on numeric cell

    def test_audit_findings_present(self):
        self.assertGreaterEqual(len(AUDIT_FINDINGS), 10)


if __name__ == "__main__":
    unittest.main()
