"""Forcing inputs: water-level gap filling, SSURGO ksat averaging, and the bed merges
(build_bed.py, merge_bed.py) — synthetic, no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from agri_sfincs import waterlevel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_ssurgo  # noqa: E402


class TestFillGaps(unittest.TestCase):
    def setUp(self):
        self.idx = pd.date_range("2020-01-01", periods=6, freq="h")
        self.stations = set(waterlevel.FORCING) | {
            d for v in waterlevel.DONORS.values() for d in v
        }

    def _series(self, values):
        return pd.Series(values, index=self.idx, dtype="float64")

    def test_obs_kept_gap_filled_from_first_donor_with_data(self):
        pred = {s: self._series([1.0] * 6) for s in self.stations}
        obs = {s: self._series([1.2] * 6) for s in self.stations}  # residual +0.2
        sjs = "8537121"
        first, second = waterlevel.DONORS[sjs][:2]
        obs[sjs] = self._series([1.5, np.nan, np.nan, 1.5, 1.5, 1.5])
        obs[first] = self._series([1.2, np.nan, 1.3, 1.2, 1.2, 1.2])  # missing at t1
        lv, src = waterlevel.fill_gaps(obs, pred, self.idx)
        self.assertEqual(lv[sjs].iloc[0], 1.5)
        self.assertEqual(src[sjs].iloc[0], "obs")
        # t1: first donor missing -> second donor's residual (+0.2)
        self.assertAlmostEqual(lv[sjs].iloc[1], 1.2)
        self.assertEqual(src[sjs].iloc[1], second)
        # t2: first donor present, residual +0.3
        self.assertAlmostEqual(lv[sjs].iloc[2], 1.3)
        self.assertEqual(src[sjs].iloc[2], first)

    def test_unfillable_hour_stays_missing_and_flagged(self):
        pred = {s: self._series([1.0] * 6) for s in self.stations}
        obs = {s: self._series([np.nan] * 6) for s in self.stations}
        lv, src = waterlevel.fill_gaps(obs, pred, self.idx)
        self.assertTrue(lv.isna().all().all())
        self.assertTrue((src == "").all().all())


class TestHarmonicKsat(unittest.TestCase):
    def test_restrictive_layer_dominates(self):
        hz = pd.DataFrame({"hzdept_r": [0, 50], "hzdepb_r": [50, 150],
                           "ksat_r": [100.0, 1.0]})  # fmt: skip
        # Window 0-100: 50 cm at 100 + 50 cm at 1 -> 100 / (0.5 + 50) = 1.98
        self.assertAlmostEqual(fetch_ssurgo.harmonic_ksat(hz), 100 / 50.5, places=6)

    def test_missing_ksat_horizons_skipped_and_empty_is_nan(self):
        hz = pd.DataFrame({"hzdept_r": [0, 30], "hzdepb_r": [30, 80],
                           "ksat_r": [np.nan, 10.0]})  # fmt: skip
        self.assertAlmostEqual(fetch_ssurgo.harmonic_ksat(hz), 10.0)
        empty = pd.DataFrame({"hzdept_r": [120], "hzdepb_r": [200], "ksat_r": [5.0]})
        self.assertTrue(np.isnan(fetch_ssurgo.harmonic_ksat(empty)))

    def test_drained_codes_drop_the_d(self):
        hsg = pd.Series(["A/D", "B/D", "C/D", "B", "D", ""])
        self.assertEqual(fetch_ssurgo.hsg_codes(hsg, drained=False).tolist(),
                         [2, 7, 8, 6, 3, 4])  # fmt: skip
        self.assertEqual(fetch_ssurgo.hsg_codes(hsg, drained=True).tolist(),
                         [1, 6, 5, 6, 3, 4])  # fmt: skip


class TestBedMerge(unittest.TestCase):
    """The bed rules: lidar wins, CUDEM only deepens low (tidal) pixels, never raises,
    never touches inland lake surfaces; NoData falls through in order."""

    def test_rules(self):
        import build_bed

        nan = np.nan
        lidar = np.array([[7.56, -0.43, -0.99, nan, nan, nan, 0.8]], dtype="float32")
        cudem = np.array([[-0.20, 0.17, -6.47, -5.0, nan, nan, 0.0]], dtype="float32")
        dep3 = np.array([[nan, nan, nan, nan, 30.0, nan, nan]], dtype="float32")
        gmrt = np.array([[nan, nan, nan, nan, nan, -3.0, nan]], dtype="float32")
        bed, src = build_bed.merge_tile(lidar, {3: cudem, 4: dep3, 5: gmrt})
        np.testing.assert_allclose(bed[0], [7.56, -0.43, -6.47, -5.0, 30.0, -3.0, 0.0],
                                   rtol=0, atol=1e-6)  # fmt: skip
        # lake keeps lidar surface; Greenwich not raised; Bivalve deepened; 0.8 -> 0.0
        # is the documented residual risk (a 0-filled creek between DEEPER_M and LOW_M).
        self.assertEqual(src[0].tolist(), [1, 1, 2, 3, 4, 5, 2])


class TestMergeBedV1(unittest.TestCase):
    """merge_bed.py: the river-bed burn only ever lowers the bed; NoData passes through."""

    def test_lower_only_and_nodata(self):
        from merge_bed import merge

        nd = -9999.0
        bed = np.array([1.0, 1.0, nd, 2.0], dtype="float32")
        burn = np.array([0.5, 1.5, 0.0, nd], dtype="float32")
        np.testing.assert_array_equal(merge(bed, burn, nd), [0.5, 1.0, nd, 2.0])


if __name__ == "__main__":
    unittest.main()
