"""Regenerate the grade/slump comparison table strictly from the app engines.
Run:  python reference_table.py [water_reduction_pct]   -> reference_table_app_results.csv

COMMON settings (from the user's input sheet) apply to every row; per-row values are only grade,
slump, mix type and SCM %. Nothing from the handwritten result columns is used except the fly-ash
percentage implied by its columns (20 % for M30/M35/M40, 25 % for M70).
Normal rows: IS 10262 engine (src/engineering.py).  LECA rows: LWAC engine (src/lwac.py).
"""
import csv
import sys

from src.engineering import MixInputs, ScmInput, design_mix
from src.lwac import STATE_SSD, LecaInputs, LightAgg, design_leca_mix

COMMON = dict(cement_type="OPC 43", cement_sg=3.15, exposure="Severe", reinforced=True, msa=20.0,
              aggregate_shape="Crushed angular", fa_zone="II", sg_fa=2.65, sg_ca=2.74,
              abs_fa=1.0, abs_ca=0.5, moisture_mode_fa="SSD", moisture_mode_ca="SSD",
              admixture_type="Superplasticiser, normal (SMF/SNF)", admixture_dose_pct=1.0,
              admixture_sg=1.145)
SCM_SG = {"Fly ash": 2.20, "GGBS": 3.00}
PUMP_CA_REDUCTION = {"ordinary": 10.0, "hsc": 5.0}   # IS 10262 cl. 5.5.2 / 6.2.7 maxima
LECA = dict(sg=1.20, bulk=650.0, abs24=12.0, density=1800.0)   # ASSUMED - supplier data needed

# (label, kind, fck, slump, scm name, scm %)
ROWS = [
    ("M40", "N", 40, 75, None, 0), ("M40", "N", 40, 120, None, 0), ("M70", "N", 70, 120, None, 0),
    ("M40 Fly Ash", "N", 40, 75, "Fly ash", 20), ("M70 Fly Ash", "N", 70, 75, "Fly ash", 25),
    ("M30 (LECA)", "L", 30, 75, None, 0), ("M40 (LECA)", "L", 40, 75, None, 0),
    ("M45 (LECA)", "L", 45, 75, None, 0), ("M35 (LECA)", "L", 35, 75, None, 0),
    ("M30 Fly Ash", "N", 30, 75, "Fly ash", 20), ("M35 Fly Ash", "N", 35, 75, "Fly ash", 20),
    ("M40 GGBS 40% (input sheet)", "N", 40, 75, "GGBS", 40),
]


def run(red=23.0):
    out = []
    for label, kind, fck, slump, scm, pct in ROWS:
        scms = [ScmInput(scm, float(pct), SCM_SG[scm])] if scm else []
        if kind == "N":
            pump = PUMP_CA_REDUCTION["hsc" if fck >= 65 else "ordinary"]
            r = design_mix(MixInputs(fck=fck, slump=slump, scms=scms, admixture_water_reduction_pct=red,
                                     pumpable_ca_reduction_pct=pump, **COMMON))
            row = dict(Grade=label, Slump_mm=slump, fck=fck, Water=r.water_to_add, Cement=r.cement,
                       Fine=r.fa_field, Coarse=r.ca_field, SCM=sum(r.scm_masses.values()),
                       Admix=r.admixture_mass, wcm=r.wcm_final, Density=r.fresh_density,
                       Flags="; ".join(f"{c.status}: {c.name}" for c in r.checks
                                       if c.status in ("FAIL", "REVIEW")))
        else:
            c = COMMON
            r = design_leca_mix(LecaInputs(
                fck=fck, slump=slump, target_fresh_density=LECA["density"], scms=scms, cement_sg=c["cement_sg"],
                coarse=LightAgg("LECA", LECA["sg"], LECA["abs24"], LECA["bulk"], STATE_SSD),
                fine=LightAgg("Sand", c["sg_fa"], c["abs_fa"], None, STATE_SSD),
                admixture_type=c["admixture_type"], admixture_dose_pct=c["admixture_dose_pct"],
                admixture_sg=c["admixture_sg"], admixture_water_reduction_pct=red))
            row = dict(Grade=label, Slump_mm=slump, fck=fck, Water=r.water_to_add, Cement=r.cement,
                       Fine=r.fine_batch, Coarse=r.coarse_batch, SCM=sum(r.scm_masses.values()),
                       Admix=r.admixture_mass, wcm=r.wcm_final, Density=r.fresh_density,
                       Flags="; ".join(f"{k.status}: {k.name}" for k in r.checks if k.status == "FAIL"))
        out.append(row)
    return out


if __name__ == "__main__":
    red = float(sys.argv[1]) if len(sys.argv) > 1 else 23.0
    rows = run(red)
    with open("reference_table_app_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for x in rows:
            w.writerow({k: (round(v, 3) if k == "wcm" else round(v, 2)) if isinstance(v, float) else v
                        for k, v in x.items()})
    for x in rows:
        print(x["Grade"], x["Slump_mm"], *(f"{x[k]:.2f}" for k in ("Water", "Cement", "Fine", "Coarse", "SCM", "Admix", "wcm", "Density")))
        print("    ", x["Flags"])
