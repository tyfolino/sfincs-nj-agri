"""HRRR fetch helpers (scripts/fetch_hrrr_wind.py) — no network.

fetch_hrrr_wind decodes with eccodes, which only the grib env has, but these helpers are
pure numpy, so the tests run in either env:

    cd tests && /cache/home/tpj8/agri-micromamba/envs/grib/bin/python -m unittest test_fetch_hrrr
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import fetch_hrrr_wind as F  # noqa: E402
except ImportError as e:  # requests / xarray missing
    F, WHY = None, str(e)

IDX = """69:41000000:d=2018102712:TMP:2 m above ground:anl:
70:41500000:d=2018102712:DPT:2 m above ground:anl:
71:42296624:d=2018102712:UGRD:10 m above ground:anl:
72:43560850:d=2018102712:VGRD:10 m above ground:anl:
73:44800000:d=2018102712:WIND:10 m above ground:anl:
"""


@unittest.skipIf(F is None, "needs requests + xarray")
class TestFetchHrrr(unittest.TestCase):
    def test_byte_range_spans_both_messages(self):
        self.assertEqual(F.byte_range(IDX), (42296624, 44799999))

    def test_byte_range_last_message_is_open_ended(self):
        self.assertEqual(F.byte_range("\n".join(IDX.splitlines()[:4])), (42296624, None))

    def test_byte_range_missing_field_raises(self):
        with self.assertRaises(ValueError):
            F.byte_range("\n".join(IDX.splitlines()[:3]))

    def test_no_rotation_on_the_central_meridian(self):
        u, v = F.earth_relative(np.array([3.0]), np.array([-4.0]), np.array([-97.5]), 262.5, 38.5)
        np.testing.assert_allclose([u[0], v[0]], [3.0, -4.0], atol=1e-12)

    def test_rotation_at_the_bay_keeps_speed_and_turns_by_the_cone_angle(self):
        """At -75.4 E grid north points ~13.8 deg east of true north (cone sin 38.5 x 22.1 deg):
        a wind blowing along grid north blows toward ~13.8 deg true."""
        lon = -75.4
        ang = np.sin(np.radians(38.5)) * (lon + 97.5)
        u, v = F.earth_relative(np.array([0.0]), np.array([10.0]), np.array([lon]), 262.5, 38.5)
        self.assertAlmostEqual(float(np.hypot(u, v)[0]), 10.0, places=9)
        self.assertAlmostEqual(float(np.degrees(np.arctan2(u, v))[0]), ang, places=9)
        self.assertAlmostEqual(ang, 13.76, places=1)

    def test_crop_window_covers_the_box(self):
        lat, lon = np.meshgrid(np.arange(38.0, 41.0, 0.05), np.arange(-77.0, -74.0, 0.05), indexing="ij")
        rs, cs = F.crop_window(lat, lon + 360.0)  # GRIB longitudes are 0..360
        n, w, s, e = F.BOX
        sub_lat, sub_lon = lat[rs, cs], lon[rs, cs]
        self.assertTrue(sub_lat.min() >= s and sub_lat.max() <= n)
        self.assertTrue(sub_lon.min() >= w and sub_lon.max() <= e)
        self.assertAlmostEqual(sub_lat.min(), s, delta=0.05)
        self.assertAlmostEqual(sub_lon.max(), e, delta=0.05)


if __name__ == "__main__":
    unittest.main()
