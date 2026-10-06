"""Event windows, focus periods and precipitation-forcing helpers — no network, no model."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from agri_sfincs import events as E
from agri_sfincs import precip as P


class TestFocus(unittest.TestCase):
    def test_periods(self):
        T = pd.Timestamp
        self.assertEqual(E.focus_period("2023-09"), (T("2023-09-01"), T("2023-10-01")))
        self.assertEqual(E.focus_period("2023"), (T("2023-01-01"), T("2024-01-01")))
        self.assertEqual(E.focus_period("2023-11/2024-02"), (T("2023-11-01"), T("2024-03-01")))

    def test_legacy_events_unchanged(self):
        ev = E.EVENTS["sep2023"]
        self.assertEqual((ev.tstart, ev.tstop, ev.precip), ("2023-08-15 00:00:00",
                         "2023-10-01 00:00:00", "mrms_2023_09"))  # fmt: skip
        self.assertEqual(ev.focus_months(), ["2023-09"])
        self.assertEqual(ev.dtmapout, 3600.0)
        days = pd.date_range("2023-08-31", "2023-10-01", freq="D")
        f = ev.in_focus(days)
        self.assertEqual(int(f.sum()), 30)
        self.assertFalse(f[0])  # Aug 31
        self.assertTrue(f[-2])  # Sep 30
        self.assertFalse(f[-1])  # Oct 1

    def test_year_events(self):
        y = E.EVENTS["y2023"]
        self.assertEqual((y.tstart, y.tstop), ("2022-12-01 00:00:00", "2024-01-01 00:00:00"))
        self.assertEqual(y.precip, "mrms")
        self.assertEqual(len(y.focus_months()), 12)
        self.assertEqual(y.dtmapout, E.DAY_S)
        self.assertEqual(E.EVENTS["y2015"].precip, "stage4")  # its December is pre-MRMS
        self.assertEqual(E.EVENTS["y2016"].precip, "mrms")
        self.assertEqual(E.EVENTS["y2025"].tstop, "2025-12-31 00:00:00")  # gauges end
        for ev in E.EVENTS.values():  # every window is whole days (restart lattice)
            dt = pd.Timestamp(ev.tstop) - pd.Timestamp(ev.tstart)
            self.assertEqual(dt % pd.Timedelta(days=1), pd.Timedelta(0), ev.name)

    def test_year_spinup_outside_focus(self):
        y = E.EVENTS["y2023"]
        self.assertFalse(y.in_focus(["2022-12-31"])[0])
        self.assertTrue(y.in_focus(["2023-01-01", "2023-12-31"]).all())


class TestPrecipHelpers(unittest.TestCase):
    def test_window_hours(self):
        h = P.window_hours("2022-12-01", "2024-01-01")
        self.assertEqual(h[0], pd.Timestamp("2022-12-01 00:00"))
        self.assertEqual(h[-1], pd.Timestamp("2024-01-01 00:00"))
        self.assertEqual(len(h), (365 + 31) * 24 + 1)

    def test_file_years(self):
        # the hour ending 2023-01-01T00 lives in the 2022 file
        self.assertEqual(P.file_years(pd.DatetimeIndex(["2023-01-01 00:00"])), [2022])
        self.assertEqual(P.file_years(P.window_hours("2022-12-01", "2024-01-01")), [2022, 2023])

    def test_nearest_index(self):
        c = np.array([10.0, 20.0, 30.0])
        np.testing.assert_array_equal(P.nearest_index(c, np.array([4.0, 14.9, 15.1, 34.9, 35.1])),
                                      [-1, 0, 1, 2, -1])  # fmt: skip

    def test_catalog_entry(self):
        y = P.catalog_entry("mrms_y2023", "precip/forcing/mrms_y2023.nc", "mrms", "EPSG:4326",
                            "2022-12-01", "2024-01-01")  # fmt: skip
        self.assertTrue(P.catalog_has(y, "mrms_y2023"))
        self.assertFalse(P.catalog_has(y, "mrms_y20"))
        self.assertIn("crs: 4326", y)
        s4 = P.catalog_entry("stage4_y2003", "x.nc", "stage4", "+proj=stere", "2002-12-01", "2004-01-01")
        self.assertNotIn("crs:", s4)  # in the file: hydromt cannot serialise HRAP's CRS
        import yaml

        doc = yaml.safe_load(y + s4)
        self.assertEqual(doc["mrms_y2023"]["driver"]["name"], "raster_xarray")
        self.assertEqual(doc["mrms_y2023"]["metadata"]["crs"], 4326)


if __name__ == "__main__":
    unittest.main()
