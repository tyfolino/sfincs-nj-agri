"""River-bed burn: datum conversion, profiles, hydraulic geometry, never-raise — no network."""

from __future__ import annotations

import math
import unittest

import numpy as np

from agri_sfincs import riverbed as rb

# CO-OPS datum sheets (feet on station datum), as served 2026-10-03.
BIVALVE = {"MHHW": 2.82, "MHW": 2.39, "MSL": -0.32, "MTL": -0.43, "MLW": -3.26,
           "MLLW": -3.45, "NAVD88": -0.04}  # fmt: skip
LEWES = {"MHHW": 7.43, "MHW": 7.01, "MSL": 5.01, "MTL": 4.98, "MLW": 2.94, "MLLW": 2.78,
         "NAVD88": 5.41}  # fmt: skip


class TestDatums(unittest.TestCase):
    def test_datum_sheet_to_navd88(self):
        self.assertAlmostEqual(rb.coops_datum_navd88(BIVALVE), (-3.45 + 0.04) * 0.3048, 6)
        self.assertAlmostEqual(rb.coops_datum_navd88(BIVALVE, "MTL"), (-0.43 + 0.04) * 0.3048, 6)
        # Reedy Point: NAVD88 - MLLW = 0.905 m, as FINDINGS §6
        reedy = {"MLLW": 1.35, "NAVD88": 4.32}
        self.assertAlmostEqual(-rb.coops_datum_navd88(reedy), 0.905, 3)

    def test_no_navd88_tie_is_nan(self):
        self.assertTrue(math.isnan(rb.coops_datum_navd88({"MLLW": 2.0, "NAVD88": None})))
        self.assertTrue(math.isnan(rb.coops_datum_navd88({"MLLW": 2.0})))

    def test_subordinate_ratio(self):
        # ratio 1 reproduces the reference's own MLLW if MTL is the reference's (to the
        # sheet's 0.01 ft rounding: MTL is (MHW + MLW) / 2 rounded)
        mtl = rb.coops_datum_navd88(LEWES, "MTL")
        self.assertAlmostEqual(rb.subordinate_mllw_navd88(LEWES, "R", 1.0, 1.0, mtl),
                               rb.coops_datum_navd88(LEWES), 2)  # fmt: skip
        # Millville: 1.21 x Lewes, MTL borrowed from Bivalve
        m = rb.subordinate_mllw_navd88(LEWES, "R", 1.21, 1.21, -0.119)
        expect = -0.119 - 0.5 * 1.21 * ((7.01 - 2.78) + (2.94 - 2.78)) * 0.3048
        self.assertAlmostEqual(m, expect, 6)
        self.assertLess(m, -0.119)  # MLLW is below MTL

    def test_subordinate_additive_and_unknown(self):
        m = rb.subordinate_mllw_navd88(LEWES, "A", 0.5, -0.1, 0.0)
        self.assertAlmostEqual(m, -0.5 * ((4.23 + 0.5) + (0.16 - 0.1)) * 0.3048, 6)
        with self.assertRaises(ValueError):
            rb.subordinate_mllw_navd88(LEWES, "X", 1.0, 1.0, 0.0)

    def test_chart_depth_to_navd88(self):
        z = rb.chart_to_navd88([0.0, 2.0, -0.5], -0.9)
        np.testing.assert_allclose(z, [-0.9, -2.9, -0.4])
        # depth below MLLW is down-positive: deeper sounding -> lower bed
        self.assertLess(rb.chart_to_navd88(3.0, -1.0), rb.chart_to_navd88(1.0, -1.0))

    def test_depare_depth(self):
        self.assertAlmostEqual(rb.depare_depth([0.0], [1.8]), 0.9)
        self.assertAlmostEqual(rb.depare_depth([-1.8, 0.0], [0.0, 1.8]), 0.9)  # drying ignored
        self.assertAlmostEqual(rb.depare_depth([0.0, 1.8], [1.8, 9.1]), 1.8)  # deep class: lower bound
        self.assertAlmostEqual(rb.depare_depth([-1.6], [1.8]), 0.9)  # negative DRVAL1 floored
        self.assertTrue(math.isnan(rb.depare_depth([-1.8], [0.0])))
        self.assertTrue(math.isnan(rb.depare_depth([], [])))
        # user 2026-10-05: shallow classes take 1.2 m, clipped to the interval
        self.assertAlmostEqual(rb.depare_depth([0.0], [1.8], shallow_m=1.2), 1.2)
        self.assertAlmostEqual(rb.depare_depth([0.0], [1.0], shallow_m=1.2), 1.0)
        self.assertAlmostEqual(rb.depare_depth([0.0, 1.8], [1.8, 9.1], shallow_m=1.2), 1.8)
        self.assertAlmostEqual(rb.depare_depth([0.0, 0.0], [1.8, 5.4], shallow_m=1.2), 1.2)  # coarse 0-5.4


class TestProfiles(unittest.TestCase):
    def test_running_median(self):
        s = np.array([0, 10, 20, 30, 100.0])
        z = np.array([1, 2, 30, 4, 5.0])
        out = rb.running_median(s, z, np.array([10.0, 60.0, 100.0]), 10.0)
        self.assertEqual(out[0], 2.0)  # median of 1, 2, 30
        self.assertTrue(np.isnan(out[1]))
        self.assertEqual(out[2], 5.0)
        out = rb.running_median(s, z, np.array([10.0, 100.0]), 10.0, min_n=3)
        self.assertEqual(out[0], 2.0)
        self.assertTrue(np.isnan(out[1]))  # one sample < min_n
        # widened to the 3 nearest samples within max_half
        out = rb.running_median(s, z, np.array([100.0]), 10.0, min_n=3, max_half=80.0)
        self.assertEqual(out[0], 5.0)  # median of 4, 5, 30 (s = 30, 100, 20)
        out = rb.running_median(s, z, np.array([100.0]), 10.0, min_n=3, max_half=60.0)
        self.assertTrue(np.isnan(out[0]))

    def test_fill_interior_does_not_extrapolate(self):
        g = np.arange(6.0)
        p = np.array([np.nan, 1.0, np.nan, np.nan, 4.0, np.nan])
        out = rb.fill_interior(g, p)
        np.testing.assert_allclose(out[1:5], [1, 2, 3, 4])
        self.assertTrue(np.isnan(out[0]) and np.isnan(out[5]))

    def test_taper(self):
        t = rb.taper([0.0, 500.0, 1000.0, 1500.0, 2000.0], 1000.0, -0.4, 1000.0)
        np.testing.assert_allclose(t, [0.0, -0.2, -0.4, -0.2, 0.0])
        self.assertEqual(rb.taper([5000.0], 1000.0, -0.4, 1000.0)[0], 0.0)

    def test_monotone_downstream(self):
        z = np.array([5.0, 6.0, np.nan, 4.0, 4.5, 3.0])
        out = rb.monotone_downstream(z)
        np.testing.assert_allclose(out[[0, 1, 3, 4, 5]], [5, 5, 4, 4, 3])
        self.assertTrue(np.isnan(out[2]))
        d = np.diff(out[np.isfinite(out)])
        self.assertTrue((d <= 0).all())


class TestHydraulicGeometry(unittest.TestCase):
    def test_gauge_mean_depth_units_and_band(self):
        q = np.arange(1, 101, dtype=float)  # ft3/s
        w = np.full(100, 10.0)  # ft
        a = np.where((q >= 25.75) & (q <= 75.25), 20.0, 999.0)  # only the band is 2 ft deep
        r = rb.gauge_mean_depth(q, w, a)
        self.assertEqual(r["n"], 100)
        self.assertEqual(r["n_band"], 50)
        self.assertAlmostEqual(r["depth_m"], 2.0 * 0.3048, 6)
        self.assertAlmostEqual(r["width_m"], 10.0 * 0.3048, 6)

    def test_gauge_mean_depth_drops_bad_rows(self):
        r = rb.gauge_mean_depth([0, np.nan, 5, 5], [10, 10, 0, 10], [5, 5, 5, 5])
        self.assertEqual(r["n"], 1)
        self.assertEqual(rb.gauge_mean_depth([], [], [])["n"], 0)
        self.assertEqual(rb.gauge_mean_depth([1, 9], [10, 10], [5, 5])["n_band"], 0)

    def test_power_law_roundtrip(self):
        x = np.array([5.0, 20, 80, 300])
        a, b = rb.power_law_fit(x, 0.3 * x**0.25)
        self.assertAlmostEqual(a, 0.3, 6)
        self.assertAlmostEqual(b, 0.25, 6)
        with self.assertRaises(ValueError):
            rb.power_law_fit([1.0], [1.0])

    def test_interp_log_da(self):
        v = rb.interp_log_da([10.0, 1000.0], [1.0, 3.0], [1.0, 10.0, 100.0, 1000.0, 1e5])
        np.testing.assert_allclose(v, [1, 1, 2, 3, 3])  # 100 is half-way in log
        np.testing.assert_allclose(rb.interp_log_da([50.0], [0.7], [1.0, 1e4]), [0.7, 0.7])


class TestPickSurvey(unittest.TestCase):
    def test_most_recent_full_survey(self):
        dates = ["2023-03-16", "2026-03-02", "2021-07-21"]
        # the 2026 survey covers only the entrance: the full 2023 one wins
        self.assertEqual(rb.pick_survey(dates, [33.0, 3.0, 13.0]), 0)
        # all similar: the newest wins
        self.assertEqual(rb.pick_survey(dates, [6.0, 5.9, 6.0]), 1)
        self.assertEqual(rb.pick_survey(dates, [0.0, 0.0, 0.0]), -1)
        self.assertEqual(rb.pick_survey([], []), -1)


class TestNeverRaise(unittest.TestCase):
    def test_only_lowers(self):
        bed = np.array([1.0, 1.0, np.nan, -3.0, 0.5])
        burn = np.array([0.0, 2.0, -1.0, -2.0, np.nan])
        out = rb.never_raise(bed, burn)
        np.testing.assert_allclose(out[0], 0.0)
        self.assertTrue(np.isnan(out[1:]).all())
        merged = np.fmin(bed, out)
        ok = np.isfinite(bed)
        self.assertTrue((merged[ok] <= bed[ok]).all())

    def test_min_drop(self):
        out = rb.never_raise([1.0, 1.0], [0.95, 0.5], min_drop=0.1)
        self.assertTrue(np.isnan(out[0]))
        self.assertEqual(out[1], 0.5)


class TestV2Sources(unittest.TestCase):
    def test_parse_a93(self):
        lon, lat, d = rb.parse_a93("H10027   39798841 -75420869   1260711\r\n")
        self.assertAlmostEqual(lat, 39.798841)
        self.assertAlmostEqual(lon, -75.420869)
        self.assertAlmostEqual(d, 12.6)
        self.assertIsNone(rb.parse_a93("H10027   39798841 -75420869 999990711"))

    def test_csb_depth(self):
        # 4.0 m below a transducer 0.5 m down, sea 1.2 m above MLLW: bed 3.3 m below MLLW
        self.assertAlmostEqual(float(rb.csb_depth_mllw(4.0, 1.2, 0.5)), 3.3)

    def test_stated_floor(self):
        grid = np.arange(0.0, 500.0, 100.0)  # head (0) to mouth (400)
        mllw = np.full(5, -0.9)
        prof = np.array([0.0, -1.0, -2.0, -5.0, -3.0])
        out = rb.stated_floor(prof, mllw, grid, 200.0, 2.13)
        np.testing.assert_allclose(out, [0.0, -1.0, -3.03, -5.0, -3.03])  # never raised


if __name__ == "__main__":
    unittest.main()
