"""agri_sfincs.waterlevel: match_highs and the chain boundary (FINDINGS §41); synthetic series, no files."""

import unittest

import numpy as np
import pandas as pd

from agri_sfincs import domain, waterlevel


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


def tide(index, lag_h=0.0, amp=1.0):
    hours = (index - pd.Timestamp("2020-01-01")) / pd.Timedelta("1h")
    return pd.Series(amp * np.cos(2 * np.pi * (np.asarray(hours) - lag_h) / 12.42), index=index)


class TestChainBoundary(unittest.TestCase):
    def test_chain_is_the_gauges_plus_virtual(self):
        virtual = {s["id"] for s in domain.VIRTUAL_STATIONS}
        self.assertEqual(set(waterlevel.CHAIN), set(waterlevel.FORCING) | virtual)
        self.assertEqual(set(waterlevel.VIRTUAL_DONOR), virtual)
        self.assertEqual(len(waterlevel.CHAIN_LAG_H), len(waterlevel.CHAIN) - 1)

    def test_chain_pair(self):
        gx, gy = [0.0, 10.0, 20.0], [0.0, 0.0, 0.0]
        self.assertEqual(waterlevel.chain_pair(2.5, 0.0, gx, gy), (0, 0.25))
        i, w = waterlevel.chain_pair(17.0, 0.0, gx, gy)
        self.assertEqual(i, 1)
        self.assertAlmostEqual(w, 0.7)
        self.assertEqual(waterlevel.chain_pair(-5.0, 0.0, gx, gy), (0, 0.25))  # beyond the end: inverse distance, as SFINCS

    def test_lag_blend_keeps_range(self):
        t = pd.date_range("2020-01-01", periods=24 * 10 * 3, freq="6min")
        a, b = tide(t), tide(t, lag_h=1.3)
        mid = waterlevel.lag_blend(a, b, 0.5, 1.3, t[20:-20])
        naive = 0.5 * a + 0.5 * b
        self.assertAlmostEqual(np.nanmax(mid), 1.0, places=2)
        self.assertLess(naive.max(), 0.95)  # cos(pi * 1.3 / 12.42) = 0.95
        # the blend sits at the midpoint's phase: peak 0.65 h after a's
        self.assertTrue(np.allclose(mid, tide(t[20:-20], lag_h=0.65), atol=1e-3))

    def test_chain_boundary_ends_are_the_gauges(self):
        t = pd.date_range("2020-01-01", periods=48, freq="h")
        lv = pd.DataFrame({s: tide(t, lag_h=sum(waterlevel.CHAIN_LAG_H[:k]), amp=1 + 0.1 * k)
                           for k, s in enumerate(waterlevel.CHAIN)})
        gx = np.arange(len(waterlevel.CHAIN)) * 10.0
        idx = pd.date_range("2020-01-01 06:00", "2020-01-02 06:00", freq="6min")
        zs, names = waterlevel.chain_boundary(lv, [0.0, gx[-1]], [0.0, 0.0], gx, np.zeros_like(gx), idx)
        self.assertTrue(np.allclose(zs[0], tide(idx, amp=1.0), atol=0.01))
        self.assertTrue(np.allclose(zs[1], tide(idx, sum(waterlevel.CHAIN_LAG_H), amp=1.6), atol=0.01))
        self.assertTrue(names[0].startswith(waterlevel.CHAIN[0]))


class TestFillVirtual(unittest.TestCase):
    def test_prediction_plus_donor_residual(self):
        idx = pd.date_range("2020-01-01", periods=4, freq="h")
        pred = {s: pd.Series([1.0, 2.0, 3.0, 4.0], index=idx) for s in
                set(waterlevel.VIRTUAL_DONOR) | set(waterlevel.VIRTUAL_DONOR.values())}
        levels = pd.DataFrame({d: pred[d] + [0.1, 0.2, np.nan, 0.3] for d in set(waterlevel.VIRTUAL_DONOR.values())})
        lv, src = waterlevel.fill_virtual(pred, levels, idx)
        for st, d in waterlevel.VIRTUAL_DONOR.items():
            self.assertTrue(np.allclose(lv[st], [1.1, 2.2, np.nan, 4.3], equal_nan=True))
            self.assertEqual(list(src[st]), [f"virtual:{d}"] * 2 + [""] + [f"virtual:{d}"])


if __name__ == "__main__":
    unittest.main()
