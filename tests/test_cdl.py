"""CDL groups and per-polygon cover shares (agri_sfincs.cdl) — synthetic, no rasters."""

import unittest

import numpy as np
from rasterio.transform import from_origin
from shapely.geometry import box

from agri_sfincs import cdl


class TestGroups(unittest.TestCase):
    def test_crop_groups_split_cropland(self):
        crop = ["corn", "soybeans", "other_grains", "hay", "idle", "other_crops"]
        union = frozenset().union(*(cdl.GROUPS[g] for g in crop))
        self.assertEqual(union, cdl.CROPLAND)
        self.assertEqual(sum(len(cdl.GROUPS[g]) for g in crop), len(cdl.CROPLAND))

    def test_groups_disjoint_and_placed(self):
        seen = set()
        for codes in cdl.GROUPS.values():
            self.assertFalse(seen & codes)
            seen |= codes
        self.assertIn(225, cdl.GROUPS["other_grains"])  # dbl crop WinWht/Corn
        self.assertIn(24, cdl.GROUPS["other_grains"])
        self.assertIn(242, cdl.GROUPS["other_crops"])  # blueberries
        self.assertIn(176, cdl.GROUPS["pasture"])
        self.assertNotIn(131, seen)  # barren -> other


class TestZoneCover(unittest.TestCase):
    def test_shares_and_dominant(self):
        groups = {"corn": {1}, "soy": {5}}
        zone = np.array([1, 1, 1, 1, 2, 2, 2])
        code = np.array([1, 1, 5, 131, 5, 1, 131])
        t = cdl.zone_cover(zone, code, n=3, groups=groups)
        self.assertEqual(list(t.columns), ["n_px", "share_corn", "share_soy", "share_other", "dom_code"])
        self.assertEqual(t.loc[1, "n_px"], 4)
        self.assertAlmostEqual(t.loc[1, "share_corn"], 0.5)
        self.assertAlmostEqual(t.loc[1, "share_other"], 0.25)
        self.assertEqual(t.loc[1, "dom_code"], 1)
        self.assertEqual(t.loc[2, "dom_code"], 1)  # three-way tie -> lowest code
        self.assertEqual(t.loc[3, "n_px"], 0)  # no pixel
        self.assertTrue(np.isnan(t.loc[3, "share_corn"]))
        self.assertEqual(t.loc[3, "dom_code"], -1)
        rows = t.loc[[1, 2], ["share_corn", "share_soy", "share_other"]].sum(axis=1)
        np.testing.assert_allclose(rows, 1.0)


class TestPolygonPixels(unittest.TestCase):
    def test_centres_and_fallback(self):
        tr = from_origin(0, 40, 10, 10)  # 4 x 4 grid of 10 m pixels
        geoms = [box(0, 20, 20, 40),  # top-left 2 x 2 pixels
                 box(31, 1, 34, 4)]  # tiny, holds no centre: bottom-right pixel by fallback
        zone, flat, fallback = cdl.polygon_pixels(geoms, (4, 4), tr)
        got = sorted(zip(zone.tolist(), flat.tolist()))
        self.assertEqual(got, [(1, 0), (1, 1), (1, 4), (1, 5), (2, 15)])
        self.assertEqual(fallback.tolist(), [2])


if __name__ == "__main__":
    unittest.main()
