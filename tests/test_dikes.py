"""Dike weirs and gate files (agri_sfincs.dikes) — no network."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from agri_sfincs import dikes


class TestFillNotches(unittest.TestCase):
    def setUp(self):
        self.s = np.arange(0, 1000, 5.0)
        self.z = np.full(self.s.shape, 1.6)

    def test_notch_filled_to_median_and_flagged(self):
        z = self.z.copy()
        z[100:104] = 0.6  # a 20 m gate notch
        crest, notch = dikes.fill_notches(z, self.s)
        self.assertTrue(notch[100:104].all())
        self.assertEqual(int(notch.sum()), 4)
        np.testing.assert_allclose(crest[100:104], 1.6)

    def test_never_lowers(self):
        z = self.z.copy()
        z[50] = 2.5  # a spike stays
        z[150:154] = 0.2
        crest, _ = dikes.fill_notches(z, self.s)
        self.assertTrue((crest >= z).all())
        self.assertEqual(crest[50], 2.5)

    def test_gradual_change_is_not_a_notch(self):
        z = np.linspace(1.0, 2.5, self.s.size)  # 1.5 m over 1 km
        _, notch = dikes.fill_notches(z, self.s)
        self.assertFalse(notch.any())

    def test_nan_ridge_takes_median(self):
        z = self.z.copy()
        z[10] = np.nan
        crest, notch = dikes.fill_notches(z, self.s)
        self.assertTrue(notch[10])
        self.assertAlmostEqual(crest[10], 1.6)


class TestFiles(unittest.TestCase):
    def test_weir_format_and_skip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.weir"
            n = dikes.write_weir(p, [
                ("a", np.array([0.0, 10.0]), np.array([0.0, 0.0]), np.array([1.5, np.nan])),
                ("b", np.array([0.0, 10.0, 20.0]), np.array([5.0, 5.0, 5.0]),
                 np.array([1.0, 1.1, 1.2])),
            ])  # fmt: skip
            lines = p.read_text().splitlines()
        self.assertEqual(n, 3)  # "a" has one finite vertex: skipped
        self.assertEqual(lines[:2], ["b", "3 4"])
        self.assertEqual(lines[2].split(), ["0.0", "5.0", "1.000", "0.60"])

    def test_drn_intake_first(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.drn"
            dikes.write_drn(p, [(1.0, 2.0, 3.0, 4.0)], coef=1.5)
            self.assertEqual(p.read_text().split(), ["1.0", "2.0", "3.0", "4.0", "3", "1.500"])

    def test_ensure_inp_key(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "sfincs.inp").write_text("tref = 1\nweirfile = old.weir\n")
            self.assertFalse(dikes.ensure_inp_key(root, "drnfile", "sfincs.drn"))
            (root / "sfincs.weir").write_text("")
            self.assertTrue(dikes.ensure_inp_key(root, "weirfile", "sfincs.weir"))
            text = (root / "sfincs.inp").read_text()
        self.assertIn("weirfile             = sfincs.weir", text)
        self.assertNotIn("old.weir", text)
        self.assertNotIn("drnfile", text)


class TestScenarios(unittest.TestCase):
    def test_read_weir_roundtrip_and_cap(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.weir"
            dikes.write_weir(p, [("a", np.array([0.0, 10.0, 20.0]), np.zeros(3), np.array([2.0, 1.2, 2.5]))])
            (name, x, y, z), = dikes.read_weir(p)
        self.assertEqual(name, "a")
        np.testing.assert_allclose(z, [2.0, 1.2, 2.5])
        (_, _, _, zc), = dikes.cap_crests([(name, x, y, z)], 1.5)
        np.testing.assert_allclose(zc, [1.5, 1.2, 1.5])  # never raised

    def test_breach(self):
        x = np.arange(0, 100, 5.0)
        z = np.full(x.size, 2.0)
        out = dikes.breach(x, np.zeros_like(x), z, at=10, length_m=20, z_breach=0.8)
        np.testing.assert_array_equal(np.flatnonzero(out < 2.0), [8, 9, 10, 11, 12])
        self.assertTrue((out[8:13] == 0.8).all())


class TestNetworkWalk(unittest.TestCase):
    """build_dike_outlets.walk: along a 3-reach chain A -> B -> C (each 100 m, west to east)."""

    def setUp(self):
        import sys

        import geopandas as gpd
        from shapely.geometry import LineString

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import build_dike_outlets

        self.walk = build_dike_outlets.walk
        self.fl = gpd.GeoDataFrame(
            {"hydroseq": [3.0, 2.0, 1.0], "dnhydroseq": [2.0, 1.0, 0.0]},
            geometry=[LineString([(0, 0), (100, 0)]), LineString([(100, 0), (200, 0)]),
                      LineString([(200, 0), (300, 0)])], crs=32618)  # fmt: skip

    def test_downstream_crosses_reaches_and_stops(self):
        x, _, d = self.walk(self.fl, 3.0, 50.0, down=True, max_m=180.0)
        self.assertAlmostEqual(x[0], 50.0)
        self.assertLessEqual(d.max(), 180.0)
        self.assertGreater(x.max(), 200.0)  # reached reach C
        self.assertTrue(np.all(np.diff(x) > 0))

    def test_upstream_goes_west(self):
        x, _, d = self.walk(self.fl, 1.0, 50.0, down=False, max_m=120.0)
        self.assertAlmostEqual(x[0], 250.0)
        self.assertLess(x.min(), 200.0)  # into reach B
        self.assertTrue(np.all(np.diff(x) < 0))


class TestMergeBed(unittest.TestCase):
    def test_lower_only_and_nodata(self):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from merge_bed_v1 import merge

        nd = -9999.0
        bed = np.array([1.0, 1.0, nd, 2.0], dtype="float32")
        burn = np.array([0.5, 1.5, 0.0, nd], dtype="float32")
        np.testing.assert_array_equal(merge(bed, burn, nd), [0.5, 1.0, nd, 2.0])


if __name__ == "__main__":
    unittest.main()
