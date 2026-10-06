"""Landsat C2 L2 helpers (agri_sfincs.landsat) — no network."""

from __future__ import annotations

import unittest

import numpy as np

from agri_sfincs import landsat as ls


class TestLandsat(unittest.TestCase):
    def test_clear_bits(self):
        qa = np.array([21824, 1, 2, 8, 16, 32, 64, 128 | 64], dtype="uint16")
        # 21824 = L8 "clear, low confidence" (bits 6, 8, 10, 12, 14): clear
        np.testing.assert_array_equal(ls.clear(qa), [True, False, False, False, False, False,
                                                     True, True])  # fmt: skip

    def test_reflectance(self):
        r = ls.reflectance(np.array([0, 7273, 10909], dtype="uint16"))
        self.assertTrue(np.isnan(r[0]))
        np.testing.assert_allclose(r[1:], [0.0000275 * 7273 - 0.2, 0.0000275 * 10909 - 0.2], atol=1e-6)

    def test_indices(self):
        ix = ls.indices(np.float32(0.05), np.float32(0.08), np.float32(0.05),
                        np.float32(0.45), np.float32(0.20))  # fmt: skip
        self.assertAlmostEqual(float(ix["ndvi"]), 0.8, places=5)  # vegetation
        bare = ls.indices(np.float32(0.10), np.float32(0.12), np.float32(0.18),
                          np.float32(0.22), np.float32(0.32))  # fmt: skip
        self.assertGreater(float(bare["bsi"]), 0)
        self.assertLess(float(bare["ndvi"]), 0.2)
        water = ls.indices(np.float32(0.06), np.float32(0.07), np.float32(0.04),
                           np.float32(0.02), np.float32(0.01))  # fmt: skip
        self.assertGreater(float(water["mndwi"]), 0)

    def test_field_means(self):
        labels = np.array([[0, 1, 1], [2, 2, 2]])
        a = {"x": np.array([[9.0, 1.0, 3.0], [5.0, np.nan, 7.0]])}
        ok = np.array([[True, True, True], [True, True, False]])
        out = ls.field_means(labels, a, ok, n_labels=3)
        np.testing.assert_array_equal(out["n"], [0, 2, 1, 0])
        self.assertAlmostEqual(out["x"][1], 2.0)
        self.assertAlmostEqual(out["x"][2], 5.0)  # NaN and not-ok pixels dropped
        self.assertTrue(np.isnan(out["x"][3]))


if __name__ == "__main__":
    unittest.main()
