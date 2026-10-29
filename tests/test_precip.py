"""Stage IV 6-h gap filling and grid-axis checks (agri_sfincs.precip) — synthetic, no network."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from agri_sfincs import precip, wind


class TestFill6h(unittest.TestCase):
    def setUp(self):
        self.t = pd.date_range("2003-06-11T01", "2003-06-11T12", freq="h")  # 2 windows
        self.t6 = pd.DatetimeIndex(["2003-06-11T06", "2003-06-11T12"])

    def test_residual_spread_over_missing_hours(self):
        p = np.array([1, np.nan, 2, np.nan, 0, 1, 0, 0, 0, 0, 0, 0], float)[:, None]
        p6 = np.array([[10.0], [0.0]])
        out, fill = precip.fill_from_6h(p, self.t, p6, self.t6)
        np.testing.assert_allclose(out[:6, 0], [1, 3, 2, 3, 0, 1])  # (10 - 4) / 2
        self.assertEqual(list(np.nonzero(fill[:, 0])[0]), [1, 3])
        self.assertAlmostEqual(out[:6].sum(), 10.0)

    def test_negative_residual_fills_zero_and_no_6h_stays_nan(self):
        p = np.array([5, np.nan, 0, 0, 0, 0, np.nan, 0, 0, 0, 0, 0], float)[:, None]
        p6 = np.array([[3.0], [np.nan]])
        out, fill = precip.fill_from_6h(p, self.t, p6, self.t6)
        self.assertEqual(out[1, 0], 0.0)
        self.assertTrue(np.isnan(out[6, 0]) and not fill[6, 0])

    def test_window_of_00z_holds_19_to_00(self):
        t = pd.date_range("2003-06-11T19", "2003-06-12T00", freq="h")
        w = precip.six_hour_windows(np.zeros((6, 1)), t, np.zeros((1, 1)),
                               pd.DatetimeIndex(["2003-06-12T00"]))  # fmt: skip
        self.assertEqual(list(w["end"]), [pd.Timestamp("2003-06-12T00")])
        self.assertEqual(list(w["nh"]), [6])


class TestRegularAxis(unittest.TestCase):
    def test_regular_axis(self):
        X, Y = np.meshgrid(1000.0 + 4762.5 * np.arange(5), -50.0 + 4762.5 * np.arange(3))
        self.assertEqual(precip.regular_axis(X, axis=1, tol=1.0), (1000.0, 4762.5))
        self.assertEqual(precip.regular_axis(Y, axis=0, tol=1.0), (-50.0, 4762.5))
        with self.assertRaises(ValueError):
            precip.regular_axis(X + Y * 0.1, axis=1, tol=1.0)  # rotated


class TestEngineOrigin(unittest.TestCase):
    """A staged rain file as hydromt writes it (centres, y DESCENDING) must, once fixed,
    be read by the engine at the true point (FINDINGS: rain half a cell off before 2026-10-29)."""

    def setUp(self):
        self.xc = 400000.0 + 4000.0 * np.arange(9)
        self.yc = 4330000.0 - 4000.0 * np.arange(7)  # descending, as hydromt writes
        X, Y = np.meshgrid(self.xc, self.yc)
        self.f = lambda x, y: 0.002 * (x - 400000.0) + 0.001 * (y - 4300000.0)  # bilinear is exact
        p = np.stack([self.f(X, Y), 3 * self.f(X, Y)]).astype("f4")
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sfincs_netampr.nc"
        xr.Dataset({"Precipitation": (("time", "y", "x"), p)},
                   coords={"time": [0.0, 60.0], "y": self.yc, "x": self.xc}).to_netcdf(self.path)  # fmt: skip

    def tearDown(self):
        self.tmp.cleanup()

    def sample(self, x, y):
        return wind.engine_sample(self.path, x, y, names=("Precipitation",))[:, 0]

    def test_unfixed_file_is_read_half_a_cell_west_and_north(self):
        x, y = 413000.0, 4318500.0
        np.testing.assert_allclose(self.sample(x, y), [self.f(x - 2000, y + 2000), 3 * self.f(x - 2000, y + 2000)], atol=1e-3)

    def test_fixed_file_is_read_at_the_true_point(self):
        self.assertTrue(precip.to_engine_origin(self.path))
        for x, y in [(413000.0, 4318500.0), (self.xc[3], self.yc[2]), (421234.0, 4311111.0)]:
            np.testing.assert_allclose(self.sample(x, y), [self.f(x, y), 3 * self.f(x, y)], atol=1e-3)

    def test_fix_is_applied_once_and_true_centres_undo_it(self):
        self.assertTrue(precip.to_engine_origin(self.path))
        self.assertFalse(precip.to_engine_origin(self.path))
        with xr.open_dataset(self.path, decode_times=False) as ds:
            self.assertEqual(float(ds.x[0]), self.xc[0] - 2000.0)
            self.assertEqual(float(ds.y[0]), self.yc[0] + 2000.0)
            x, y = precip.true_centres(ds)
            np.testing.assert_array_equal(x, self.xc)
            np.testing.assert_array_equal(y, self.yc)
            np.testing.assert_array_equal(ds.Precipitation.values[0], self.f(*np.meshgrid(self.xc, self.yc)).astype("f4"))


if __name__ == "__main__":
    unittest.main()
