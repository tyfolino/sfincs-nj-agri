"""scripts/hay_lag_test.py: the two-way fixed-effects fit recovers a planted lag effect and
ignores field and county-year levels; zero-weight rows (an undrawn watershed) drop out.
Synthetic tables, no files, no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hay_lag_test as H


def panel_table(n: int = 200, years=range(2012, 2024), effect: float = 3.0, seed: int = 0) -> pd.DataFrame:
    """Fields with their own hay level, a county-year shock and +effect at lag 2 only."""
    rng = np.random.default_rng(seed)
    yrs = np.array(list(years))
    field = np.repeat(np.arange(n), len(yrs))
    year = np.tile(yrs, n)
    county = np.repeat(rng.integers(0, 3, n), len(yrs))
    d = pd.DataFrame({"field": field.astype(str), "year": year, "cty_year": [f"{c}-{y}" for c, y in zip(county, year)]})
    for k in H.LAGS:
        d[H.lag_name(k)] = rng.integers(0, 2, len(d)).astype(float)
    d["F 1-3"] = d[["lag 1", "lag 2", "lag 3"]].sum(axis=1)
    shock = {c: rng.normal(0, 5) for c in d.cty_year.unique()}
    level = rng.normal(10, 4, n)[field]
    for o in H.OUTCOMES:
        d[o] = level + d.cty_year.map(shock) + rng.normal(0, 0.1, len(d))
    d["hay"] += effect * d["lag 2"]
    return d


class FitTest(unittest.TestCase):
    def setUp(self):
        self.d = panel_table()
        self.groups = [pd.factorize(self.d.field)[0], pd.factorize(self.d.cty_year)[0]]

    def test_recovers_planted_lag(self):
        b = H.fit(self.d, self.groups, np.ones(len(self.d)))["lags"]
        hay = dict(zip(H.SPECS["lags"], b[list(H.OUTCOMES).index("hay")]))
        self.assertAlmostEqual(hay["lag 2"], 3.0, delta=0.05)
        for k, v in hay.items():
            if k != "lag 2":
                self.assertAlmostEqual(v, 0.0, delta=0.05, msg=k)
        corn = b[list(H.OUTCOMES).index("corn")]
        np.testing.assert_allclose(corn, 0.0, atol=0.05)

    def test_zero_weight_rows_drop_out(self):
        w = np.ones(len(self.d))
        drop = self.d.field.astype(int) < 50
        bad = self.d.copy()
        bad.loc[drop, "hay"] += 100 * bad.loc[drop, "lag 0"]  # would show at lag 0 if counted
        b_all = H.fit(bad, self.groups, w)["lags"]
        b_kept = H.fit(bad, self.groups, np.where(drop, 0.0, w))["lags"]
        i, j = list(H.OUTCOMES).index("hay"), H.SPECS["lags"].index("lag 0")
        self.assertGreater(b_all[i, j], 10)
        self.assertAlmostEqual(b_kept[i, j], 0.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
