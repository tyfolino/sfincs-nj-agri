"""Per-field flood class rules (agri_sfincs.fieldflood) — pure, no runs."""

import math
import unittest

from agri_sfincs import fieldflood as ff


class TestFirstLevel(unittest.TestCase):
    def test_lowest_level_over_share(self):
        self.assertEqual(ff.first_level([0.0, 0.05, 0.2, 0.9]), 0.6)

    def test_none_and_missing_runs(self):
        self.assertTrue(math.isnan(ff.first_level([0.0, 0.0, 0.09, 0.0])))
        self.assertEqual(ff.first_level([float("nan"), 0.5, 0.5, 0.5]), 0.3)


class TestClassify(unittest.TestCase):
    def test_today(self):
        self.assertEqual(ff.classify(0.0, 0.0, True), "flooded today")
        self.assertEqual(ff.classify(0.6, 0.0, True), "dike-dependent today")

    def test_dike_dependent_later(self):
        self.assertEqual(ff.classify(1.0, 0.3, True), "dike-dependent +0.3 m")
        self.assertEqual(ff.classify(math.nan, 0.6, True), "dike-dependent +0.6 m")

    def test_overtopped_vs_exposed(self):
        self.assertEqual(ff.classify(0.6, 0.6, True), "overtopped +0.6 m")
        self.assertEqual(ff.classify(0.6, 0.6, False), "exposed +0.6 m")
        # removing the dikes left it drier: the as-built level decides
        self.assertEqual(ff.classify(0.3, 1.0, True), "overtopped +0.3 m")
        self.assertEqual(ff.classify(0.3, math.nan, False), "exposed +0.3 m")

    def test_safe_and_order(self):
        self.assertEqual(ff.classify(math.nan, math.nan, False), ff.SAFE)
        order = ff.class_order()
        for w, wo, b in [(0.0, 0.0, 1), (0.3, 0.0, 1), (1.0, 0.3, 0), (0.6, 0.6, 1), (0.6, 0.6, 0)]:
            self.assertIn(ff.classify(w, wo, bool(b)), order)
        self.assertEqual(order[0], "flooded today")
        self.assertEqual(order[-1], ff.SAFE)


class TestLongestRun(unittest.TestCase):
    def test_runs(self):
        self.assertEqual(ff.longest_run([]), 0)
        self.assertEqual(ff.longest_run([False, False]), 0)
        self.assertEqual(ff.longest_run([True, True, False, True, True, True, False]), 3)
        self.assertEqual(ff.longest_run([True] * 31), 31)


if __name__ == "__main__":
    unittest.main()
