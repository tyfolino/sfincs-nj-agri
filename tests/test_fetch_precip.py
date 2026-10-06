"""Stage IV / MRMS clip helpers (scripts/fetch_precip_hourly.py) — no network.

fetch_precip_hourly needs eccodes, which only the grib env has, so these tests are
skipped in the shared env. Run them there (this file imports nothing from agri_sfincs):

    cd tests && /cache/home/tpj8/agri-micromamba/envs/grib/bin/python -m unittest test_fetch_precip
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import fetch_precip_hourly as F  # noqa: E402
except ImportError as e:  # the shared env has no eccodes
    F, WHY = None, str(e)


@unittest.skipIf(F is None, "grib env only")
class TestFetchClip(unittest.TestCase):
    def test_mrms_window_matches_the_event_files(self):
        rs, cs, lat, lon = F.mrms_window()
        self.assertEqual((len(lat), len(lon)), (96, 84))
        self.assertEqual((lat[0], lat[-1], lon[0], lon[-1]), (39.935, 38.985, -75.635, -74.805))

    def test_stage4_window_pads_bbox(self):
        lat, lon = np.meshgrid(np.arange(38.0, 41.0, 0.05), np.arange(-76.5, -74.0, 0.05),
                               indexing="ij")  # fmt: skip
        rs, cs = F.stage4_window(lat, lon, pad=0.06)
        w, s, e, n = F.BBOX
        sub_lat, sub_lon = lat[rs, cs], lon[rs, cs]
        self.assertLess(sub_lat.min(), s)
        self.assertGreater(sub_lat.max(), n)
        self.assertLess(sub_lon.min(), w)
        self.assertGreater(sub_lon.max(), e)
        self.assertGreaterEqual(sub_lat.min(), s - 0.06 - 1e-9)

    def test_year_and_month_parts(self):
        t = F.year_hours(2023)
        self.assertEqual((t[0], t[-1], len(t)),
                         (pd.Timestamp("2023-01-01T01"), pd.Timestamp("2024-01-01T00"), 8760))  # fmt: skip
        g = F.month_groups(t)
        self.assertEqual(len(g["2023-01"]), 744)
        self.assertEqual(g["2023-12"][-1], pd.Timestamp("2024-01-01T00"))

    def test_mrms_sources_around_the_switch(self):
        c = F.candidates("mrms", pd.Timestamp("2020-10-14T05"))
        self.assertEqual([k for k, _ in c], [1, 2, 0])
        c = F.candidates("mrms", pd.Timestamp("2020-10-13T23"))
        self.assertEqual([k for k, _ in c], [0, 2])

    def test_stage4_url_is_the_hour_end(self):
        u = F.candidates("stage4", pd.Timestamp("2002-01-01T00"))[0][1]
        self.assertTrue(u.endswith("/2002/01/01/stage4/ST4.2002010100.01h.grib"), u)


if __name__ == "__main__":
    unittest.main()
