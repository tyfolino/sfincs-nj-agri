"""Marsh branch painting (scripts/paint_branches.py) on a synthetic grid, no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import paint_branches as pb  # noqa: E402


class TestBranchBed(unittest.TestCase):
    """1 m pixels. Marsh at +0.5; the painted main channel is column 0; a 9 m wide branch
    (rows 10-18) joins it; a 120 m wide flat-water body (columns 60-179) with an NHD corridor
    (rows 13-15) across it; a flat pond (rows 40-44) touching nothing."""

    def setUp(self):
        self.bed = np.full((60, 180), 0.5, dtype="float32")
        self.bed[10:19, 1:60] = -1.07  # branch
        self.bed[:, 60:] = -1.07  # wide water
        self.bed[40:45, 20:30] = -1.07  # pond
        self.burned = np.zeros(self.bed.shape, bool)
        self.burned[:, 0] = True
        self.src = np.ones(self.bed.shape, "uint8")
        self.corridor = np.zeros(self.bed.shape, bool)
        self.corridor[13:16, :] = True
        self.mllw = np.full(self.bed.shape, -0.9)

    def run_(self):
        return pb.branch_bed(self.bed, self.src, self.burned, self.corridor, self.mllw,
                             (1.0, 1.0), depth=1.5, slope=0.1, max_hw=40.0)  # fmt: skip

    def test_branch_gets_a_v_capped_at_the_floor(self):
        mask, z = self.run_()
        self.assertTrue(mask[14, 30])
        # centre row of a 9 m branch: 5 m from either bank -> 0.5 m below the flat
        self.assertAlmostEqual(float(z[14, 30]), -1.57, places=2)
        self.assertAlmostEqual(float(z[10, 30]), -1.17, places=2)  # 1 m from the bank
        self.assertTrue((z[mask] >= -0.9 - 1.5 - 1e-6).all())

    def test_never_raises_and_leaves_marsh_and_pond(self):
        mask, z = self.run_()
        self.assertTrue((z <= self.bed + 1e-6).all())
        self.assertFalse(mask[0:5, 1:60].any())  # marsh
        self.assertFalse(mask[40:45, 20:30].any())  # pond: not joined to the burn

    def test_wide_water_only_along_the_corridor(self):
        mask, z = self.run_()
        self.assertFalse(mask[30, 100])  # the wide body's middle
        self.assertFalse(mask[5, 65])  # near its bank, but within max_hw of the wide middle
        self.assertTrue(mask[14, 120])  # the corridor across it
        self.assertAlmostEqual(float(z[14, 120]), -2.4, places=5)  # at the floor


if __name__ == "__main__":
    unittest.main()
