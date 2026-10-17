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
