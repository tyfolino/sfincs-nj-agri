"""agri_sfincs.waterlevel.match_highs: synthetic series, no files."""

import unittest

import numpy as np
import pandas as pd

from agri_sfincs import waterlevel


class TestMatchHighs(unittest.TestCase):
    def test_pairs_each_high(self):
        t = pd.date_range("2020-01-01", periods=24 * 10 * 2, freq="6min")  # 2 days at 6 min
        hours = (t - t[0]) / pd.Timedelta("1h")
        obs = pd.Series(np.cos(2 * np.pi * hours / 12.42), index=t)  # highs at 0 h (edge), 12.42 h, 24.84 h ...
        model = pd.Series(0.9 * np.cos(2 * np.pi * (hours - 1) / 12.42), index=t)
        d = waterlevel.match_highs(obs, model)
        self.assertEqual(len(d), 3)  # interior highs only (find_peaks skips the first sample)
        self.assertTrue(np.allclose(d.obs_m, 1.0, atol=1e-3))
        self.assertTrue(np.allclose(d.diff_m, -0.1, atol=1e-3))  # model peaks 0.9, 1 h late (inside the 3 h window)

    def test_no_model_near(self):
        t = pd.date_range("2020-01-01", periods=400, freq="6min")
        obs = pd.Series(np.sin(np.arange(400) / 30.0), index=t)
        model = pd.Series([0.0], index=[pd.Timestamp("2021-01-01")])
        self.assertTrue(waterlevel.match_highs(obs, model).empty)


if __name__ == "__main__":
    unittest.main()
