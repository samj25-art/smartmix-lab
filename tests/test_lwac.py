"""LECA / LWAC engine tests (identities + independent hand calculations)."""
import unittest

from src.engineering import ScmInput
from src.lwac import (STATE_DRY, STATE_MC, STATE_SSD, LecaInputs, LightAgg, design_leca_mix,
                      design_leca_mix_simple)
from src.validation import InputError


def mk(**kw):
    base = dict(wcm_manual=0.45, admixture_dose_pct=0.0, admixture_type="None")
    base.update(kw)
    return LecaInputs(**base)


class TestIdentities(unittest.TestCase):
    def test_volume_and_mass_balance_and_density(self):
        for state in (STATE_DRY, STATE_SSD):
            r = design_leca_mix(mk(coarse=LightAgg("L", 1.2, 12, 650, state)))
            self.assertAlmostEqual(sum(r.volumes_m3.values()), 1.0, places=9)
            self.assertAlmostEqual(r.fresh_density, 1800.0, places=6)
            batch = (r.binder_total + r.water_to_add + r.admixture_mass + r.coarse_batch + r.fine_batch)
            self.assertAlmostEqual(batch, r.fresh_density, places=6)

    def test_hand_calculation(self):
        # w/cm 0.45, water 170*(1+0.03)=175.1, binder 389.11, no SCM / admixture, air 2 %
        r = design_leca_mix(mk())
        w = 170 * 1.03
        b = w / 0.45
        v_paste = b / 3150 + w / 1000 + 0.02
        v_agg = 1 - v_paste
        m_paste = b + w
        rho_c, rho_f = 1200 * 1.12, 2620 * 1.01
        vf = (1800 - m_paste - rho_c * v_agg) / (rho_f - rho_c)
        self.assertAlmostEqual(r.fine_dry, vf * 2620, places=6)
        self.assertAlmostEqual(r.coarse_dry, (v_agg - vf) * 1200, places=6)


class TestWaterSplit(unittest.TestCase):
    def test_dry_leca_needs_absorption_water_but_same_fresh_density(self):
        soaked = design_leca_mix(mk(coarse=LightAgg("L", 1.2, 12, 650, STATE_SSD)))
        dry = design_leca_mix(mk(coarse=LightAgg("L", 1.2, 12, 650, STATE_DRY)))
        self.assertAlmostEqual(soaked.coarse_dry, dry.coarse_dry, places=9)
        self.assertAlmostEqual(dry.water_to_add - soaked.water_to_add, 0.12 * dry.coarse_dry, places=6)
        self.assertAlmostEqual(dry.absorption_water_to_add, 0.12 * dry.coarse_dry, places=6)
        self.assertAlmostEqual(soaked.water_net, dry.water_net)

    def test_absorption_water_never_changes_volume_or_wcm(self):
        a = design_leca_mix(mk(coarse=LightAgg("L", 1.2, 5, 650, STATE_DRY)))
        b = design_leca_mix(mk(coarse=LightAgg("L", 1.2, 20, 650, STATE_DRY), target_fresh_density=None,
                               fine_vol_fraction=a.fine_vol_fraction))
        self.assertAlmostEqual(a.wcm_final, b.wcm_final)
        self.assertAlmostEqual(a.coarse_dry, b.coarse_dry, places=6)   # same volumes -> same dry masses

    def test_surface_moisture_is_credited(self):
        r = design_leca_mix(mk(coarse=LightAgg("L", 1.2, 12, 650, STATE_MC, 15.0, 1.0)))
        self.assertAlmostEqual(r.surface_moisture_credit, 0.03 * r.coarse_dry, places=6)
        self.assertAlmostEqual(r.water_to_add, r.water_net - r.surface_moisture_credit, places=6)

    def test_partial_absorption_fraction(self):
        r = design_leca_mix(mk(coarse=LightAgg("L", 1.2, 12, 650, STATE_DRY, 0, 0.5)))
        self.assertAlmostEqual(r.absorption_water_total, 0.06 * r.coarse_dry + 0.01 * r.fine_dry, places=6)


class TestSplitAndLimits(unittest.TestCase):
    def test_fine_fraction_mode(self):
        r = design_leca_mix(mk(target_fresh_density=None, fine_vol_fraction=0.30))
        self.assertAlmostEqual(r.fine_vol_fraction, 0.30, places=9)
        self.assertAlmostEqual(sum(r.volumes_m3.values()), 1.0, places=9)

    def test_unachievable_density_message_has_range(self):
        with self.assertRaises(InputError) as cm:
            design_leca_mix(mk(target_fresh_density=1300))
        self.assertIn("Achievable range", str(cm.exception))
        with self.assertRaises(InputError):   # target above the all-fine limit
            design_leca_mix(mk(target_fresh_density=2000, fine=LightAgg("F", 1.5, 10, None, STATE_SSD)))

    def test_sg_vs_bulk_density_validation(self):
        with self.assertRaises(InputError):
            design_leca_mix(mk(coarse=LightAgg("L", 0.6, 12, 700, STATE_SSD)))

    def test_scm_is_part_of_binder(self):
        r = design_leca_mix(mk(scms=[ScmInput("GGBS", 30, 3.0), ScmInput("Fly ash", 10, 2.2)]))
        self.assertAlmostEqual(r.cement + sum(r.scm_masses.values()), r.binder_total, places=9)
        self.assertAlmostEqual(r.cement, 0.6 * r.binder_total, places=9)

    def test_min_binder_lowers_wcm(self):
        r = design_leca_mix(mk(wcm_manual=0.65, min_binder=350))
        self.assertAlmostEqual(r.binder_total, 350)
        self.assertLess(r.wcm_final, 0.65)

    def test_all_lightweight_mix(self):
        r = design_leca_mix(mk(target_fresh_density=1600,
                               fine=LightAgg("LECA fines", 1.6, 15, None, STATE_SSD)))
        self.assertAlmostEqual(r.fresh_density, 1600, places=6)
        self.assertTrue(any("all-lightweight" in w for w in r.warnings))

    def test_flat_api(self):
        d = design_leca_mix_simple(30, 1850, 1.35, 700, 15, leca_moisture_state=STATE_DRY, scm={"GGBS": 30})
        self.assertAlmostEqual(d["fresh_density"], 1850, places=6)
        self.assertGreater(d["water_to_add_at_mixer"], d["net_water"])


if __name__ == "__main__":
    unittest.main()
