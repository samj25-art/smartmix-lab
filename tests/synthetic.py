"""SYNTHETIC data used ONLY by the automated tests to exercise the pipeline offline.

It is NOT the UCI dataset, it is never used by the app, and metrics obtained from it say
nothing about real concrete.
"""
import numpy as np
import pandas as pd

from src import constants as C


def make_synthetic(n=1030, seed=0):
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({
        "cement": rng.uniform(100, 540, n), "slag": rng.choice([0, 0, rng.uniform(20, 340)], n) * rng.random(n),
        "fly_ash": rng.uniform(0, 200, n) * (rng.random(n) > .5), "water": rng.uniform(120, 247, n),
        "superplasticizer": rng.uniform(0, 30, n) * (rng.random(n) > .3),
        "coarse_agg": rng.uniform(800, 1145, n), "fine_agg": rng.uniform(590, 992, n),
        "age": rng.choice([3, 7, 14, 28, 56, 90, 180, 365], n).astype(float)})
    binder = d.cement + d.slag + d.fly_ash
    wb = d.water / binder
    d["strength"] = (60 * np.exp(-2.2 * wb) * np.log(d.age + 1) / np.log(29) + 0.15 * d.superplasticizer
                     + rng.normal(0, 3, n)).clip(2, 85)
    d = pd.concat([d, d.iloc[:20]], ignore_index=True)       # include duplicate rows on purpose
    return d[C.FEATURES + [C.TARGET]]


def uci_style_headers(df):
    names = ["Cement (component 1)(kg in a m^3 mixture)", "Blast Furnace Slag (component 2)(kg in a m^3 mixture)",
             "Fly Ash (component 3)(kg in a m^3 mixture)", "Water  (component 4)(kg in a m^3 mixture)",
             "Superplasticizer (component 5)(kg in a m^3 mixture)",
             "Coarse Aggregate  (component 6)(kg in a m^3 mixture)",
             "Fine Aggregate (component 7)(kg in a m^3 mixture)", "Age (day)",
             "Concrete compressive strength(MPa, megapascals) "]
    out = df.copy()
    out.columns = names
    return out
