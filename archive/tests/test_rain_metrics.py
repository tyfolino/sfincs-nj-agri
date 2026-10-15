"""Rain metrics helpers (archive/scripts/rain_metrics.py) — synthetic, no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rain_metrics as R  # noqa: E402

import cropweights  # noqa: E402


class TestLocalMonths(unittest.TestCase):
    def test_summer_hour_goes_by_its_local_start(self):
        # Hour ending 04Z Jul 1 = 23-24 EDT Jun 30; ending 05Z = 00-01 EDT Jul 1.
        t = pd.DatetimeIndex(["2023-07-01T04", "2023-07-01T05"])
        ls = R.local_hour_start(t)
        self.assertEqual(list(ls.month), [6, 7])
        self.assertEqual(ls[1], pd.Timestamp("2023-07-01T00"))

    def test_winter_offset_is_five_hours(self):
        t = pd.DatetimeIndex(["2023-01-01T05", "2023-01-01T06"])
        ls = R.local_hour_start(t)
        self.assertEqual(list(zip(ls.year, ls.month)), [(2022, 12), (2023, 1)])
        ids = R.month_index(ls)
        self.assertEqual(list(ids), [2022 * 12 + 11, 2023 * 12])

    def test_local_month_lengths(self):
        ids = [2023 * 12 + m - 1 for m in (1, 3, 11)] + [2024 * 12 + 1]
        self.assertEqual(list(R.local_month_hours(ids)), [744, 743, 721, 696])

    def test_local_day_lengths(self):
        d = pd.DatetimeIndex(["2023-03-12", "2023-11-05", "2023-07-01"])
        self.assertEqual(list(R.local_day_hours(d)), [23, 25, 24])

    def test_every_hour_lands_in_one_local_day(self):
        t = pd.date_range("2023-03-12T01", "2023-03-13T12", freq="h")  # spring forward
        days = R.local_hour_start(t).normalize()
        n = pd.Series(1, index=days).groupby(level=0).size()
        self.assertEqual(n[pd.Timestamp("2023-03-12")], 23)


class TestWindowMax(unittest.TestCase):
    def test_windows_stay_inside_groups(self):
        x = np.array([1, 2, 3, 10, 0, 0, 5], float)
        g = np.array([0, 0, 0, 1, 1, 1, 1])
        ids, m = R.window_max(x, 2, g)
        self.assertEqual(list(ids), [0, 1])
        # Group 0: 1+2, 2+3 -> 5. Group 1: 10+0, 0+0, 0+5 -> 10 (3+10 crosses groups).
        np.testing.assert_allclose(m, [5, 10])

    def test_k1_is_the_max_and_short_groups_are_nan(self):
        x = np.array([4, 1, 7], float)
        g = np.array([0, 0, 1])
        np.testing.assert_allclose(R.window_max(x, 1, g)[1], [4, 7])
        np.testing.assert_allclose(R.window_max(x, 2, g)[1], [5, np.nan])

    def test_nan_counts_as_zero_and_2d(self):
        x = np.array([[1, np.nan], [np.nan, 2], [3, 2]])
        g = np.zeros(3, int)
        np.testing.assert_allclose(R.window_max(x, 2, g)[1], [[3, 4]])

    def test_matches_brute_force(self):
        rng = np.random.default_rng(1)
        x = rng.gamma(0.3, 2.0, 500)
        g = np.repeat(np.arange(5), [80, 120, 100, 150, 50])
        for k in (1, 3, 24, 48):
            want = []
            for gi in range(5):
                v = x[g == gi]
                want.append(max(v[i : i + k].sum() for i in range(len(v) - k + 1)))
            np.testing.assert_allclose(R.window_max(x, k, g)[1], want)

    def test_unsorted_groups_rejected(self):
        with self.assertRaises(ValueError):
            R.window_max(np.ones(3), 1, np.array([1, 0, 1]))


class TestWeighting(unittest.TestCase):
    def test_matches_nwm_weighted_mean(self):
        rng = np.random.default_rng(2)
        v = rng.random((6, 3, 4))
        v[0, 1, 2] = v[3] = np.nan  # one NaN cell; one all-NaN step
        w = rng.integers(0, 5, (3, 4)).astype(float)
        mean, nan_frac = R.weighted_means(v.reshape(6, -1), w.reshape(-1, 1))
        np.testing.assert_allclose(mean[:, 0], cropweights.weighted_mean(v, w), equal_nan=True)
        self.assertTrue(np.isnan(mean[3, 0]))
        self.assertAlmostEqual(nan_frac[3, 0], 1.0)
        self.assertAlmostEqual(nan_frac[0, 0], w[1, 2] / w.sum())
        self.assertEqual(nan_frac[1, 0], 0.0)

    def test_two_counties(self):
        p = np.array([[1.0, 3.0, 10.0]])
        w = np.array([[1, 0], [1, 0], [0, 2]], float)
        mean, _ = R.weighted_means(p, w)
        np.testing.assert_allclose(mean, [[2.0, 10.0]])

    def test_mrms_grid_bins_pixels_to_the_cell_holding_them(self):
        lat = np.round(39.935 - np.arange(3) * 0.01, 3)  # files run north -> south
        lon = np.round(-75.635 + np.arange(4) * 0.01, 3)
        ds = xr.Dataset(coords={"lat": ("y", lat), "lon": ("x", lon)})
        g, tr, flip = R.product_grid("mrms", ds)
        self.assertIsNone(tr)
        self.assertTrue(flip)
        self.assertAlmostEqual(g.x0, -75.64)
        self.assertAlmostEqual(g.y0, 39.91)
        # A pixel at (-75.6251, 39.9349) is in cell (lon -75.625, lat 39.935): top row.
        n = cropweights.bin_pixels([-75.6251], [39.9349], [0], g, 1)
        self.assertEqual(n[0, 2, 1], 1)  # ascending y: the north row is the last

    def test_cdl_year_rule(self):
        years = [y for y in range(2008, 2026) if y not in cropweights.SKIP_CDL]
        self.assertEqual(cropweights.nearest_year(2003, years), 2008)
        self.assertEqual(cropweights.nearest_year(2010, years), 2009)
        self.assertEqual(cropweights.nearest_year(2025, years), 2025)


class TestAntecedent(unittest.TestCase):
    def setUp(self):
        idx = pd.date_range("2020-01-01", "2020-03-31", freq="D")
        self.d = pd.Series(1.0, index=idx)
        self.d["2020-01-31"] = 5.0

    def test_windows_end_the_day_before_the_month(self):
        s = pd.DatetimeIndex(["2020-02-01", "2020-03-01"])
        np.testing.assert_allclose(R.antecedent(self.d, s, 7), [11.0, 7.0])
        np.testing.assert_allclose(R.antecedent(self.d, s, 30), [34.0, 34.0])  # leap Feb + Jan 31

    def test_window_before_the_record_is_nan(self):
        s = pd.DatetimeIndex(["2020-01-01", "2020-01-08", "2020-01-09"])
        np.testing.assert_allclose(R.antecedent(self.d, s, 7), [np.nan, 7.0, 7.0])
        np.testing.assert_allclose(R.antecedent(self.d, s[:1], 7), [np.nan])

    def test_day_without_data_makes_it_nan(self):
        d = self.d.copy()
        d["2020-02-25"] = np.nan
        s = pd.DatetimeIndex(["2020-03-01"])
        self.assertTrue(np.isnan(R.antecedent(d, s, 7)[0]))
        self.assertEqual(R.antecedent(d, s, 4)[0], 4.0)


if __name__ == "__main__":
    unittest.main()
