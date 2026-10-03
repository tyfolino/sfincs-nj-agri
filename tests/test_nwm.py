"""NWM soil-moisture extraction helpers (scripts/fetch_nwm_soil.py) — no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_nwm_soil as F  # noqa: E402


class TestWindow(unittest.TestCase):
    def test_window_covers_bounds_and_snaps_to_cells(self):
        xc = np.arange(10) * 1000.0 + 500.0  # cells [0,1000), [1000,2000), ...
        yc = np.arange(8) * 1000.0 + 500.0
        ys, xs, g = F.window(xc, yc, (1500.0, 2100.0, 4999.0, 3000.0))
        self.assertEqual((xs.start, xs.stop), (1, 5))
        self.assertEqual((ys.start, ys.stop), (2, 4))
        self.assertEqual((g.x0, g.y0, g.nx, g.ny), (1000.0, 2000.0, 4, 2))
        np.testing.assert_allclose(g.x, xc[1:5])
        np.testing.assert_allclose(g.y, yc[2:4])

    def test_window_clipped_to_grid(self):
        xc = np.arange(4) * 250.0 + 125.0
        ys, xs, _ = F.window(xc, xc, (-1e4, -1e4, 1e4, 1e4))
        self.assertEqual((xs.start, xs.stop, ys.start, ys.stop), (0, 4, 0, 4))


class TestDays(unittest.TestCase):
    def test_00z_belongs_to_previous_day(self):
        t = pd.date_range("2010-01-01 03:00", periods=9, freq="3h")  # .. 01-02 03Z
        d = F.day_label(t)
        self.assertTrue((d[:8] == pd.Timestamp("2010-01-01")).all())
        self.assertEqual(d[8], pd.Timestamp("2010-01-02"))

    def test_224_step_chunks_hold_whole_days(self):
        t = pd.date_range("1979-02-01 03:00", periods=224 * 3, freq="3h")
        d = F.day_label(t)
        for k in range(3):
            self.assertEqual(len(set(d[k * 224 : (k + 1) * 224])), 28)
        self.assertNotEqual(d[223], d[224])

    def test_daily_reduce(self):
        t = pd.date_range("2010-01-01 03:00", periods=16, freq="3h")
        a = np.arange(16, dtype=np.float32).reshape(16, 1)
        a[3] = np.nan
        days, m = F.daily_reduce(a, F.day_label(t), "mean")
        self.assertEqual(len(days), 2)
        self.assertAlmostEqual(float(m[0, 0]), np.mean([0, 1, 2, 4, 5, 6, 7]), places=5)
        self.assertEqual(float(F.daily_reduce(a, F.day_label(t), "max")[1][0, 0]), 7)
        self.assertEqual(float(F.daily_reduce(a, F.day_label(t), "min")[1][1, 0]), 8)
        self.assertEqual(float(F.daily_reduce(a, F.day_label(t), "last")[1][1, 0]), 15)
        allnan = np.full((8, 1), np.nan, np.float32)
        self.assertTrue(np.isnan(F.daily_reduce(allnan, F.day_label(t[:8]), "mean")[1]).all())


class TestAccumulators(unittest.TestCase):
    def test_reset_days_are_quarter_starts(self):
        d = pd.to_datetime(["2010-01-01", "2010-04-01", "2010-04-02", "2010-10-01",
                            "2010-12-01"])  # fmt: skip
        self.assertEqual(F.is_reset_day(d).tolist(), [True, True, False, True, False])

    def test_increment_across_a_reset(self):
        days = pd.date_range("2010-03-30", periods=4)  # 30, 31 Mar, 1, 2 Apr
        eod = np.array([[100.0], [103.0], [2.0], [5.5]])
        inc = F.accum_increment(eod, days)
        self.assertTrue(np.isnan(inc[0, 0]))  # no predecessor, not a reset day
        np.testing.assert_allclose(inc[1:, 0], [3.0, 2.0, 3.5])

    def test_negative_flux_kept(self):  # dew: ACCET may fall
        inc = F.accum_increment(np.array([[1.0], [0.8]]), pd.date_range("2010-01-01", periods=2))
        np.testing.assert_allclose(inc[:, 0], [1.0, -0.2])

    def test_gap_raises(self):
        with self.assertRaises(ValueError):
            F.accum_increment(np.zeros((2, 1)), pd.to_datetime(["2010-01-01", "2010-01-03"]))


class TestWeighting(unittest.TestCase):
    def test_weighted_mean_drops_nan_cells(self):
        v = np.array([[[1.0, 3.0], [np.nan, 10.0]], [[np.nan] * 2] * 2])
        w = np.array([[1.0, 3.0], [5.0, 0.0]])
        out = F.weighted_mean(v, w)
        self.assertAlmostEqual(out[0], (1 * 1 + 3 * 3) / 4)
        self.assertTrue(np.isnan(out[1]))

    def test_share(self):
        v = np.array([0.0, 5.0, np.nan])
        np.testing.assert_array_equal(F.share(v, v > 0), [0.0, 1.0, np.nan])

    def test_nearest_year(self):
        ys = [2008, 2009, 2011, 2012]
        self.assertEqual(F.nearest_year(2002, ys), 2008)
        self.assertEqual(F.nearest_year(2010, ys), 2009)  # tie -> earlier
        self.assertEqual(F.nearest_year(2023, ys), 2012)

    def test_bin_pixels(self):
        g = F.Grid(x0=0.0, y0=0.0, dx=100.0, dy=100.0, nx=2, ny=2)
        xs = np.array([10, 150, 150, 50, 999])
        ys = np.array([10, 10, 10, 150, 10])  # last one outside the grid
        county = np.array([0, 0, 1, 1, 0])
        n = F.bin_pixels(xs, ys, county, g, 2)
        self.assertEqual(n.shape, (2, 2, 2))
        self.assertEqual(n[0, 0, 0], 1)
        self.assertEqual(n[0, 0, 1], 1)
        self.assertEqual(n[1, 0, 1], 1)
        self.assertEqual(n[1, 1, 0], 1)
        self.assertEqual(n.sum(), 4)


if __name__ == "__main__":
    unittest.main()
