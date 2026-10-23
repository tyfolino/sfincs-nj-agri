"""agri_sfincs.fields: the per-state field set's pure pieces."""

from __future__ import annotations

import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from agri_sfincs import fields


class TestFields(unittest.TestCase):
    def test_farmed_2020_handles_blanks(self):
        g = gpd.GeoDataFrame({"lulc2020": pd.array([2100, 1110, pd.NA, 2140], dtype="Int64")},
                             geometry=[box(0, 0, 1, 1)] * 4, crs=32618)  # fmt: skip
        self.assertEqual(fields.farmed_today(g).tolist(), [True, False, False, True])

    def test_unknown_state(self):
        with self.assertRaises(ValueError):
            fields.load("XX")


if __name__ == "__main__":
    unittest.main()
