"""Fork 1: RMA state split, cropland shares, FE-PPML/logit and sandwich SEs — synthetic
data only, no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from rasterio import features
from rasterio.transform import from_origin
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_rma_col  # noqa: E402
import fork1_panel  # noqa: E402

from agri_sfincs import config  # noqa: E402
from agri_sfincs import panel as pn  # noqa: E402


def _col_line(state: str, county: str, indemnity: str = "100") -> str:
    f = ["2020", state, "XX", county, "Some County", "0081", "Soybeans", "90", "APH", "A",
         "H", "31", "Excess Moisture", "6", "JUN", "2020", "1", "1", "10", "0", "1000",
         "50", "20", "30", "0", "0", "0", "5", indemnity, ".1"]  # fmt: skip
    return "|".join(f) + "\n"


class TestRmaStates(unittest.TestCase):
    def test_split_keeps_requested_states_only(self):
        lines = [_col_line("34", "033"), _col_line("10", "001"), "\n",
                 _col_line("42", "001"), _col_line("37", "095", "7")]  # fmt: skip
        keep, n = fetch_rma_col.split_states(lines, ["34", "37"], len(fetch_rma_col.COLUMNS))
        self.assertEqual(n, 4)  # the blank line is not a record
        self.assertEqual(sorted(keep), ["34", "37"])
        self.assertEqual([r[0] for r in keep["34"]], ["34033"])
        self.assertEqual(keep["37"][0][0], "37095")
        self.assertEqual(keep["37"][0][1 + fetch_rma_col.COLUMNS.index("indemnity")], "7")

    def test_wrong_field_count_raises(self):
        with self.assertRaisesRegex(RuntimeError, "layout"):
            fetch_rma_col.split_states(["2020|34|NJ\n"], ["34"], len(fetch_rma_col.COLUMNS))

    def test_paths_keep_nj_where_it_was(self):
        self.assertEqual(fetch_rma_col.state_csv("colsom", 2020, "NJ"),
                         config.RMA_DIR / "colsom_2020_NJ.csv")  # fmt: skip
        self.assertEqual(fetch_rma_col.state_csv("sobcov", 2020, "VA"),
                         config.RMA_STATES_DIR / "sobcov_2020_VA.csv")  # fmt: skip

    def test_parse_states(self):
        self.assertEqual(list(fetch_rma_col.parse_states(None)), ["NJ", "DE", "MD", "VA", "NC"])
        self.assertEqual(fetch_rma_col.parse_states("nj, nc"), {"NJ": "34", "NC": "37"})
        with self.assertRaises(SystemExit):
            fetch_rma_col.parse_states("PA")


class TestShares(unittest.TestCase):
    def test_share_on_synthetic_polygon(self):
        # 100 x 100 cells of 30 m; left half corn (1), right half forest (141);
        # a floodplain polygon covering columns 30-59, all rows.
        tf = from_origin(0, 3000, 30, 30)
        land = np.full((100, 100), 141, np.uint8)
        land[:, :50] = 1
        zone = features.rasterize([(box(900, 0, 1800, 3000), 1)], out_shape=land.shape,
                                  transform=tf, dtype="uint8").astype(bool)  # fmt: skip
        county = np.ones_like(zone)
        county[:20] = False  # the top 20 rows are another county
        r = pn.cropland_shares(land, county, {"fp": zone}, {1, 5})
        self.assertEqual(r["n_crop"], 80 * 50)
        self.assertAlmostEqual(r["share_fp"], 20 / 50)  # cols 30-49 of crop cols 0-49

    def test_no_cropland_is_nan(self):
        r = pn.cropland_shares(np.zeros((3, 3)), np.ones((3, 3), bool), {"a": np.ones((3, 3))}, {1})
        self.assertEqual(r["n_crop"], 0)
        self.assertTrue(np.isnan(r["share_a"]))

    def test_relative_elevation_valley(self):
        x = np.abs(np.arange(-10, 11, dtype=float))
        dem = np.tile(x, (5, 1))  # a V valley, floor at column 10
        rel = pn.relative_elevation(dem, 3)
        self.assertEqual(rel[2, 10], 0.0)
        self.assertEqual(rel[2, 12], 2.0)  # floor within 3 cells
        self.assertEqual(rel[2, 0], 3.0)  # floor out of reach: height above local low

    def test_weighted_county_mean_skips_nan(self):
        m = pn.weighted_county_mean(["a", "a", "b", "c"], [1, 3, 2, 1], [10, np.nan, 4, np.nan])
        self.assertEqual(m["a"], 10)
        self.assertEqual(m["b"], 4)
        self.assertTrue(np.isnan(m["c"]))


def _panel(seed=0, C=120, Y=15, M=12, b=(0.5, 1.5)):
    rng = np.random.default_rng(seed)
    c, yr, m = (a.ravel() for a in np.meshgrid(np.arange(C), np.arange(Y), np.arange(M), indexing="ij"))
    share = rng.uniform(0, 0.4, C)[c]
    P = rng.gamma(4, 25, len(c)) / 100
    eta = (rng.normal(0, 1, C)[c] + rng.normal(0, 0.5, M)[m] + rng.normal(0, 0.5, Y)[yr]
           + b[0] * P + b[1] * P * share)  # fmt: skip
    L = np.exp(rng.normal(3, 1, C))[c]
    return rng, c, yr, m, np.column_stack([P, P * share]), eta, L


class TestFeGlm(unittest.TestCase):
    def test_demean_equals_dummy_regression(self):
        rng = np.random.default_rng(3)
        n = 300
        g1, g2 = rng.integers(0, 7, n), rng.integers(0, 5, n)
        w = rng.uniform(0.5, 2, n)
        x = rng.normal(size=n) + g1 * 0.3
        D = np.column_stack([np.eye(7)[g1], np.eye(5)[g2][:, 1:]])
        sw = np.sqrt(w)
        coef = np.linalg.lstsq(D * sw[:, None], x * sw, rcond=None)[0]
        np.testing.assert_allclose(pn.demean(x, [g1, g2], w), x - D @ coef, atol=1e-8)

    def test_ppml_recovers_coefficients_with_fe_and_offset(self):
        rng, c, yr, m, X, eta, L = _panel()
        mu = L * np.exp(eta)
        # overdispersed, zero-heavy "dollars": compound Poisson-gamma
        k = rng.poisson(mu / 50)
        y = np.array([rng.gamma(2.0, 25.0, kk).sum() for kk in k])
        r = pn.fit_fe_glm(y, X, [c, m, yr], c, offset=np.log(L))
        self.assertTrue(r["converged"])
        np.testing.assert_allclose(r["beta"], [0.5, 1.5], atol=4 * r["se"].max())
        self.assertLess(abs(r["beta"][1] - 1.5), 0.3)

    def test_all_zero_county_dropped(self):
        rng, c, yr, m, X, eta, L = _panel(C=30)
        y = rng.poisson(np.exp(eta)).astype(float)
        y[c == 0] = 0.0
        r = pn.fit_fe_glm(y, X, [c, m, yr], c)
        self.assertFalse(r["keep"][c == 0].any())
        self.assertEqual(r["n_clusters"], 29)

    def test_logit_recovers_coefficients(self):
        rng, c, yr, m, X, eta, L = _panel(seed=1, C=200, Y=20, b=(0.8, 2.0))
        p = 1 / (1 + np.exp(-(eta - 1.0)))
        y = (rng.uniform(size=len(p)) < p).astype(float)
        r = pn.fit_fe_glm(y, X, [c, m, yr], c, family="logit")
        np.testing.assert_allclose(r["beta"], [0.8, 2.0], atol=3.5 * r["se"].max())

    def test_cluster_se_matches_sampling_spread(self):
        # County-level shocks shared across months make naive SEs too small; the
        # clustered SE must track the Monte Carlo spread of the estimates.
        est, ses = [], []
        for s in range(40):
            rng, c, yr, m, X, eta, L = _panel(seed=100 + s, C=60, Y=8)
            shock = rng.normal(0, 0.4, (60, 8))[c, yr]  # county-year shocks
            y = rng.poisson(np.exp(eta + shock)).astype(float)
            r = pn.fit_fe_glm(y, X, [c, m, yr], c)
            est.append(r["beta"][1])
            ses.append(r["se"][1])
        ratio = np.mean(ses) / np.std(est)
        self.assertGreater(ratio, 0.7)
        self.assertLess(ratio, 1.4)

    def test_two_way_with_singleton_second_way_equals_one_way(self):
        # V(county, obs) = V(county) + V(obs) - V(county x obs) = V(county)
        rng, c, yr, m, X, eta, L = _panel(seed=5, C=40, Y=6)
        y = rng.poisson(np.exp(eta)).astype(float)
        r = pn.fit_fe_glm(y, X, [c, m, yr], c)
        u = y[r["keep"]] - r["mu"]
        cc = c[r["keep"]]
        obs = np.arange(len(cc))
        V1 = pn.cluster_vcov(r["Xt"], r["w"], u, cc)
        V2 = pn.cluster_vcov(r["Xt"], r["w"], u, [cc, obs])
        # the G/(G-1) factors of the obs-level terms cancel exactly
        np.testing.assert_allclose(V2, V1, rtol=1e-8)


class TestPanelHelpers(unittest.TestCase):
    def test_exposure_wheat_fall_uses_next_commodity_year(self):
        liab = pd.DataFrame({"fips": "34033", "commodity_code": ["0011", "0011", "0081"],
                             "commodity_year": [2020, 2021, 2020], "liability": [10.0, 20.0, 5.0]})  # fmt: skip
        e = fork1_panel.exposure(liab).set_index(["year", "month"])
        self.assertEqual(e.loc[(2020, 6), "liability"], 15.0)  # wheat cy2020 + soy cy2020
        self.assertEqual(e.loc[(2020, 10), "liability"], 25.0)  # wheat cy2021 + soy cy2020
        self.assertEqual(e.loc[(2020, 10), "liability_row"], 25.0)

    def test_mde80_interpolates(self):
        pw = pd.DataFrame({"b2_true": [0.0, 1.0, 2.0, 3.0], "power": [0.05, 0.3, 0.7, 0.9]})
        self.assertAlmostEqual(fork1_panel.mde80(pw, "power"), 2.5)


if __name__ == "__main__":
    unittest.main()
