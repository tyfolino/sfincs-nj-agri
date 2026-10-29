"""Land-use panel helpers (agri_sfincs.panel): synthetic tables, no files."""

import unittest

import numpy as np
import pandas as pd

from agri_sfincs import panel


class TestLowCropFields(unittest.TestCase):
    def test_rules(self):
        f = pd.DataFrame({"m_above_mhhw": [0.5, 2.0, 0.5, 0.5], "sandy_share": [0.0, 0.0, np.nan, 0.2]},
                         index=pd.Index([1, 2, 3, 4], name="field_id"))  # fmt: skip
        fy = pd.DataFrame({"field_id": [1, 1, 2, 3, 4, 4], "year": [2008, 2015, 2010, 2010, 2009, 2011],
                           "cropland": [0.6, 0.0, 0.9, 0.9, 0.2, 0.7]})  # fmt: skip
        # 1: low, crop 0.6 (2015 ignored); 2: too high; 3: no Sandy value; 4: crop mean 0.45
        self.assertEqual(panel.low_crop_fields(f, fy).tolist(), [True, False, False, False])


class TestHeightWeights(unittest.TestCase):
    def test_matches_target_mix(self):
        h = pd.Series([0.1, 0.1, 0.6, 0.1, 0.6, 0.6, 2.0])
        ha = pd.Series([1.0, 3.0, 4.0, 2.0, 1.0, 1.0, 5.0])
        t = pd.Series([True, True, True, False, False, False, False])
        c = pd.Series([False, False, False, True, True, True, True])
        w = panel.height_weights(h, ha, t, c)
        self.assertEqual(w[:3].tolist(), [1.0, 3.0, 4.0])  # target keeps its area
        self.assertEqual(w[6], 0.0)  # a bin the target lacks
        bins = np.floor(h / panel.H_BIN)
        share = lambda m: {k: v for k, v in (w[m].groupby(bins[m]).sum() / w[m].sum()).round(9).items() if v}  # noqa: E731
        self.assertEqual(share(c), share(t))  # same area share per bin: 0.5 / 0.5


class TestStormTides(unittest.TestCase):
    def test_seasons(self):
        f = panel.storm_season
        self.assertEqual(f(pd.Timestamp("2024-03-10")), (2024, "nongrow"))
        self.assertEqual(f(pd.Timestamp("2024-04-12")), (2024, "grow"))
        self.assertEqual(f(pd.Timestamp("2025-08-22")), (2025, "grow"))
        self.assertEqual(f(pd.Timestamp("2018-10-27")), (2018, "grow"))
        self.assertEqual(f(pd.Timestamp("2012-12-21")), (2013, "nongrow"))
        self.assertEqual(f(pd.Timestamp("2012-11-01")), (2013, "nongrow"))
        self.assertEqual(f(pd.Timestamp("2016-01-23")), (2016, "nongrow"))

    def test_peaks_merge_within_three_days_and_split_beyond(self):
        t = pd.date_range("2024-03-01", "2024-04-30 23:00", freq="h")
        sj = pd.Series(0.5, index=t)
        sj["2024-03-09 12:00"], sj["2024-03-10 13:00"] = 1.70, 1.73  # one storm, two days
        sj["2024-04-12 01:00"] = 1.744  # a month later: a second storm
        e = panel.storm_tides(sj)
        self.assertEqual(e.day.dt.strftime("%m-%d").tolist(), ["03-10", "04-12"])
        self.assertEqual(e.m.tolist(), [1.73, 1.744])
        self.assertEqual(e.season.tolist(), ["nongrow", "grow"])
        self.assertEqual(e.season_year.tolist(), [2024, 2024])
        self.assertEqual(e.spring.tolist(), [True, True])

    def test_peak_window_is_day_before_to_day_after(self):
        a, b = panel.peak_window(pd.Timestamp("2025-08-22 14:00"))
        self.assertEqual((a, b), (pd.Timestamp("2025-08-21"), pd.Timestamp("2025-08-24")))


if __name__ == "__main__":
    unittest.main()


class TestSwitchExit(unittest.TestCase):
    def test_switched(self):
        m = pd.DataFrame([["corn", "soy", "soy", None]], columns=[2010, 2011, 2012, 2013])
        out = panel.switched(m).iloc[0].tolist()
        self.assertTrue(np.isnan(out[0]) and np.isnan(out[3]))  # no year before / missing
        self.assertEqual(out[1:3], [1.0, 0.0])

    def test_left_cropland(self):
        c = pd.DataFrame([[0.9, 0.2, 0.1, 0.8], [0.9, 0.2, 0.7, 0.1]], columns=[2010, 2011, 2012, 2013])
        out = panel.left_cropland(c)
        self.assertEqual(out[2011].tolist(), [1.0, 0.0])  # field 2 came back in 2012
        self.assertEqual(out[2012].tolist(), [0.0, 0.0])  # field 1 was already out in 2011
        self.assertTrue(out[2010].isna().all() and out[2013].isna().all())  # no t-1 / t+1


class TestQuietEstimate(unittest.TestCase):
    def test_deviations(self):
        v = pd.DataFrame([[1.0, 2.0, 5.0, 3.0, 9.0]], columns=[2008, 2009, 2010, 2011, 2020])
        # quiet 2008, 2009, 2020; window 2 around 2010 keeps 2008 / 2009 (mean 1.5)
        self.assertEqual(panel.deviations(v, 2010, [2008, 2009, 2020], 0, window=2).tolist(), [3.5])
        self.assertEqual(panel.deviations(v, 2010, [2008, 2009, 2020], 1, window=2).tolist(), [1.5])

    def test_estimate(self):
        d = pd.Series([2.0, 4.0, 1.0, np.nan])
        w_t, w_c = pd.Series([1.0, 3.0, 0.0, 0.0]), pd.Series([0.0, 0.0, 1.0, 5.0])
        boot = np.ones((4, 2))
        e = panel.estimate(d, w_t, w_c, boot, scale=1.0)  # (2 + 12) / 4 - 1 (NaN field drops out)
        self.assertEqual(e.tolist(), [2.5, 2.5, 2.5])
