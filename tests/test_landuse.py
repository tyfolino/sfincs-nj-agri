"""NJ LU/LC farm -> wetland transition classes (agri_sfincs.landuse) — no network."""

from __future__ import annotations

import unittest

from agri_sfincs import landuse as lu


class TestTransition(unittest.TestCase):
    def test_not_farmed_before_is_none(self):
        self.assertIsNone(lu.transition(6111, 6111))
        self.assertIsNone(lu.transition(2150, 6111))  # abandonment class is not farmed
        self.assertIsNone(lu.transition(None, 2100))

    def test_stays_and_farmed_wetland(self):
        self.assertEqual(lu.transition(2100, 2200), lu.STAYS)
        self.assertEqual(lu.transition(2140, 2140), lu.STAYS)
        self.assertEqual(lu.transition(2100, 2140), lu.TO_FARMED_WET)
        self.assertNotIn(lu.TO_FARMED_WET, lu.WETTING)

    def test_wetting_classes(self):
        self.assertEqual(lu.transition(2100, 2150), lu.TO_FORMER)
        self.assertEqual(lu.transition(2100.0, 6111.0, "SALINE MARSH (LOW MARSH)"), lu.TO_COASTAL)
        self.assertEqual(lu.transition(2140, 6241, "PHRAGMITES DOMINATE COASTAL WETLANDS"),
                         lu.TO_COASTAL)  # fmt: skip
        self.assertEqual(lu.transition(2100, 6210, "DECIDUOUS WOODED WETLANDS"), lu.TO_WETLAND)
        self.assertEqual(lu.transition(2100, 5412, "TIDAL MUD FLAT"), lu.TO_WATER)
        self.assertEqual(lu.transition(2100, 5300), lu.TO_POND)  # dug pond, not drowned
        self.assertNotIn(lu.TO_POND, lu.WETTING)
        for c in (lu.TO_FORMER, lu.TO_COASTAL, lu.TO_WETLAND, lu.TO_WATER):
            self.assertIn(c, lu.WETTING)

    def test_other_majors(self):
        self.assertEqual(lu.transition(2100, 1140), lu.TO_URBAN)
        self.assertEqual(lu.transition(2100, 1750), lu.TO_URBAN)  # managed lawn wetland
        self.assertEqual(lu.transition(2400, 4110), lu.TO_FOREST)
        self.assertEqual(lu.transition(2300, 7400), lu.TO_OTHER)


if __name__ == "__main__":
    unittest.main()
