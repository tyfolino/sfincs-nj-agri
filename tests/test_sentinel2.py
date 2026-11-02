import unittest

import numpy as np

from agri_sfincs import sentinel2


class TestSentinel2(unittest.TestCase):
    def test_offset_only_from_baseline_4(self):
        self.assertAlmostEqual(float(sentinel2.reflectance(np.array([2000]), 5.10)[0]), 0.1, places=5)
        self.assertAlmostEqual(float(sentinel2.reflectance(np.array([2000]), 3.00)[0]), 0.2, places=5)
        self.assertTrue(np.isnan(sentinel2.reflectance(np.array([0]), 5.10)[0]))

    def test_clear_keeps_water_and_dark(self):
        self.assertEqual(sentinel2.clear(np.array([2, 4, 6, 3, 9])).tolist(), [True, True, True, False, False])


if __name__ == "__main__":
    unittest.main()
