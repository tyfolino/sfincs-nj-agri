"""Stage IV 6-h gap filling and grid-axis checks (agri_sfincs.precip) — synthetic, no network."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from agri_sfincs import precip


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


if __name__ == "__main__":
    unittest.main()
