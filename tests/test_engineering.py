"""Engineering calculator tests.

The reference numbers are the worked examples PRINTED in IS 10262:2019 (Annex A, B, D).
IS rounds intermediate values (e.g. water 147.52 -> 148, cement 411 -> 412), so a tolerance
of 1 % is used - this is the limit of what an exact re-computation can reproduce.
"""
import unittest

from src import constants as C
from src.engineering import (MixInputs, ScmInput, design_mix, estimate_wc_from_fig1_curve2,
                             result_to_ml_features)
from src.validation import InputError


def close(a, b, rel=0.01):
    return abs(a - b) <= rel * abs(b)


class TestTargetStrength(unittest.TestCase):
    def test_tables(self):
        self.assertEqual(C.table1_X(40), 6.5)
        self.assertEqual(C.table1_X(70), 8.0)
        self.assertEqual(C.table2_S(40), 5.0)
        self.assertEqual(C.table2_S(70), 6.0)

    def test_m40_and_m70_independent_arithmetic(self):
        # independent hand calculation: M40 -> max(40+1.65*5, 40+6.5) = 48.25
        r = design_mix(MixInputs(fck=40, wc_manual=0.45))
        self.assertAlmostEqual(r.target_strength, 48.25, places=6)
        # M70 -> max(70+1.65*6, 70+8) = 79.9
        r = design_mix(MixInputs(fck=70, cement_type="OPC 53", admixture_type="Superplasticiser, PCE",
                                 admixture_dose_pct=0.5, admixture_water_reduction_pct=30,
                                 admixture_sg=1.08))
        self.assertAlmostEqual(r.target_strength, 79.9, places=6)

    def test_fair_site_control_adds_1mpa_to_S(self):
        r = design_mix(MixInputs(fck=40, site_control="Fair", wc_manual=0.45))
        self.assertAlmostEqual(r.target_strength, 40 + 1.65 * 6, places=6)


class TestAgainstIS10262Examples(unittest.TestCase):
    def test_annex_A_ppc_m40(self):
        r = design_mix(MixInputs(
            fck=40, cement_type="PPC", cement_sg=2.88, exposure="Severe", msa=20, slump=75,
            wc_manual=0.36, admixture_type="Superplasticiser, normal (SMF/SNF)",
            admixture_dose_pct=1.0, admixture_water_reduction_pct=23, admixture_sg=1.145,
            moisture_mode_ca="Oven-dry", moisture_mode_fa="Oven-dry"))
        self.assertTrue(close(r.water_net, 147.52, 0.002))
        self.assertTrue(close(r.cement, 412, 0.01))
        self.assertTrue(close(r.ca_ssd, 1234, 0.01))
        self.assertTrue(close(r.fa_ssd, 648, 0.01))
        self.assertTrue(close(r.ca_field, 1228, 0.01))
        self.assertTrue(close(r.fa_field, 642, 0.01))
        self.assertTrue(close(r.water_to_add, 160, 0.01))

    def test_annex_B_fly_ash_wet_aggregates(self):
        r = design_mix(MixInputs(
            fck=40, exposure="Severe", msa=20, slump=120, wc_manual=0.36,
            scms=[ScmInput("Fly ash", 30, 2.2)], binder_increase_pct=10,
            admixture_type="Superplasticiser, normal (SMF/SNF)", admixture_dose_pct=1.0,
            admixture_water_reduction_pct=23, pumpable_ca_reduction_pct=10,
            moisture_mode_ca="Field moist", moisture_total_ca=2.0,
            moisture_mode_fa="Field moist", moisture_total_fa=5.0))
        self.assertTrue(close(r.water_net, 155, 0.01))
        self.assertTrue(close(r.cement, 332, 0.01))
        self.assertTrue(close(r.scm_masses["Fly ash"], 142, 0.01))
        self.assertAlmostEqual(r.wcm_final, 0.327, places=2)
        self.assertTrue(close(r.ca_ssd, 1069, 0.01))
        self.assertTrue(close(r.fa_ssd, 719, 0.01))
        self.assertTrue(close(r.ca_field, 1085, 0.01))
        self.assertTrue(close(r.fa_field, 748, 0.01))
        self.assertTrue(close(r.water_to_add, 110, 0.02))
        self.assertTrue(close(r.admixture_mass, 4.74, 0.01))

    def test_annex_D_high_strength_m70(self):
        r = design_mix(MixInputs(
            fck=70, cement_type="OPC 53", exposure="Severe", msa=20, slump=120,
            scms=[ScmInput("Fly ash", 15, 2.2), ScmInput("Silica fume", 5, 2.2)],
            binder_increase_pct=10, admixture_type="Superplasticiser, PCE", admixture_dose_pct=0.5,
            admixture_water_reduction_pct=30, admixture_sg=1.08))
        self.assertAlmostEqual(r.target_strength, 79.9, places=6)
        self.assertTrue(close(r.wc_strength, 0.29, 0.01))
        self.assertTrue(close(r.water_net, 141, 0.01))
        self.assertTrue(close(r.binder_total, 535, 0.01))
        self.assertTrue(close(r.cement, 428, 0.01))
        self.assertTrue(close(r.ca_ssd, 1219, 0.01))
        self.assertTrue(close(r.fa_ssd, 589, 0.01))
        self.assertTrue(close(r.admixture_mass, 2.67, 0.02))


class TestInvariants(unittest.TestCase):
    def _mix(self, **kw):
        base = dict(fck=30, msa=20, slump=100, wc_manual=0.45, exposure="Moderate",
                    scms=[ScmInput("Fly ash", 25, 2.2)], binder_increase_pct=10)
        base.update(kw)
        return design_mix(MixInputs(**base))

    def test_volume_and_mass_balance(self):
        r = self._mix(moisture_mode_ca="Field moist", moisture_total_ca=1.5,
                      moisture_mode_fa="Field moist", moisture_total_fa=4.0)
        self.assertAlmostEqual(sum(r.volumes_m3.values()), 1.0, places=9)
        names = {c.name: c.status for c in r.checks}
        self.assertEqual(names["Absolute-volume balance = 1 m³"], "PASS")
        self.assertEqual(names["Mass balance (SSD batch vs field batch)"], "PASS")

    def test_no_double_counting_of_scm(self):
        r = self._mix()
        self.assertAlmostEqual(r.cement + sum(r.scm_masses.values()), r.binder_total, places=9)
        self.assertAlmostEqual(r.scm_masses["Fly ash"], 0.25 * r.binder_total, places=9)

    def test_dose_does_not_change_water_reduction(self):
        a = self._mix(admixture_type="Superplasticiser, normal (SMF/SNF)", admixture_dose_pct=0.6,
                      admixture_water_reduction_pct=0)
        b = self._mix(admixture_type="Superplasticiser, normal (SMF/SNF)", admixture_dose_pct=1.4,
                      admixture_water_reduction_pct=0)
        self.assertAlmostEqual(a.water_net, b.water_net, places=9)

    def test_slump_applied_once(self):
        r50 = design_mix(MixInputs(fck=30, slump=50, wc_manual=0.45, exposure="Moderate"))
        r100 = design_mix(MixInputs(fck=30, slump=100, wc_manual=0.45, exposure="Moderate"))
        self.assertAlmostEqual(r100.water_net / r50.water_net, 1.06, places=9)

    def test_min_binder_is_enforced(self):
        r = design_mix(MixInputs(fck=15, wc_manual=0.75 - 0.0, exposure="Severe"))
        self.assertGreaterEqual(r.binder_total, 320)

    def test_ml_feature_mapping_keys(self):
        r = self._mix()
        self.assertEqual(list(result_to_ml_features(r, 28)), C.FEATURES)

    def test_fig1_anchor_points(self):
        for strength, wc in C.FIG1_CURVE2_ANCHORS:
            self.assertAlmostEqual(estimate_wc_from_fig1_curve2(strength)[0], wc, places=3)
        w, extrap = estimate_wc_from_fig1_curve2(70)
        self.assertTrue(extrap)


class TestValidation(unittest.TestCase):
    def test_bad_inputs_raise_readable_errors(self):
        with self.assertRaises(InputError) as cm:
            design_mix(MixInputs(fck=40, msa=12.5, wc_manual=0.4))
        self.assertIn("12.5", str(cm.exception))
        with self.assertRaises(InputError):
            design_mix(MixInputs(fck=40, wc_manual=0.4, admixture_type="None", admixture_dose_pct=1.0))
        with self.assertRaises(InputError):
            design_mix(MixInputs(fck=40, cement_type="OPC 53"))   # needs manual w/c from Fig.1
        with self.assertRaises(InputError):
            design_mix(MixInputs(fck=40, wc_manual=0.4, pumpable_ca_reduction_pct=15))
        with self.assertRaises(InputError):
            design_mix(MixInputs(fck=40, wc_manual=0.4, moisture_mode_ca="Field moist",
                                 moisture_total_ca=-1))


if __name__ == "__main__":
    unittest.main()
