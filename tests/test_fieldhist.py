"""Field history helpers (agri_sfincs.fieldhist) — no network."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from agri_sfincs import fieldhist as fh


class TestExitYear(unittest.TestCase):
    def test_exit(self):
        yrs = list(range(2000, 2010))
        self.assertEqual(fh.exit_year(yrs, [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]), 2004)

    def test_farmed_at_end_or_never(self):
        yrs = list(range(2000, 2006))
        self.assertIsNone(fh.exit_year(yrs, [1, 0, 0, 0, 0, 1]))
        self.assertIsNone(fh.exit_year(yrs, [0] * 6))

    def test_short_run_and_nan(self):
        yrs = list(range(2000, 2008))
        self.assertIsNone(fh.exit_year(yrs, [1, 1, 1, 1, 1, 1, 0, 0]))  # only 2 off years
        # NaN years are skipped: 2003 (farmed), then 0, NaN, 0, 0 -> 3 off years
        self.assertEqual(fh.exit_year(yrs, [1, 1, 1, 1, 0, np.nan, 0, 0]), 2003)


class TestExitEvents(unittest.TestCase):
    def test_window(self):
        f = [1, 1, 1, 0, 0, 0, 0, 0, 1, 1]
        risk, ex = fh.exit_events(range(2000, 2010), f, window=5)
        # years 2000-2004 have a full 5-year look-ahead; 2002 is the exit
        np.testing.assert_array_equal(np.flatnonzero(risk), [0, 1, 2])
        np.testing.assert_array_equal(np.flatnonzero(ex), [2])

    def test_temporary_fallow_is_not_exit(self):
        f = [1, 0, 0, 1, 1, 1, 1]
        risk, ex = fh.exit_events(range(7), f, window=3)
        self.assertFalse(ex.any())
        self.assertTrue(risk[0])

    def test_missing_lookahead(self):
        f = [1, np.nan, np.nan, 0, 0, 0]
        risk, _ = fh.exit_events(range(6), f, window=4)
        self.assertFalse(risk[0])  # only 2 of 4 look-ahead years observed


class TestYearlyFeatures(unittest.TestCase):
    def test_windows_and_clear_filter(self):
        rows = []
        for date, ndvi, n in [("2010-04-15", 0.2, 10), ("2010-07-15", 0.8, 10),
                              ("2010-07-30", 0.6, 10), ("2010-10-15", 0.3, 10),
                              ("2010-08-10", 0.99, 1),  # too few clear pixels
                              ("2010-08-20", -61.3, 10)]:  # NDVI out of range  # fmt: skip
            rows.append({"unit": 5, "date": pd.Timestamp(date), "n": n, "n_valid": 10,
                         "ndvi": ndvi, "mndwi": -0.5, "bsi": 0.0, "swir1": 0.2, "nir": 0.3})  # fmt: skip
        f = fh.yearly_features(pd.DataFrame(rows)).loc[(5, 2010)]
        self.assertAlmostEqual(f.su_ndvi, 0.7)
        self.assertAlmostEqual(f.su_ndvi_max, 0.8)
        self.assertAlmostEqual(f.su_ndvi_min, 0.6)
        self.assertAlmostEqual(f.sp_ndvi_min, 0.2)
        self.assertEqual(f.su_nobs, 2)
        self.assertAlmostEqual(f.fa_ndvi, 0.3)


class TestExitSpotcheckTag(unittest.TestCase):
    def test_cell_tags(self):
        """Both cell tags join exits to the 120 m cells, not the field units (the v2 exits
        of field_classes.py are tagged cells_v2)."""
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import exit_spotcheck

        self.assertTrue(exit_spotcheck.on_cells("cells"))
        self.assertTrue(exit_spotcheck.on_cells("cells_v2"))
        self.assertFalse(exit_spotcheck.on_cells(""))


if __name__ == "__main__":
    unittest.main()
