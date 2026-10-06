"""Open-water evaporation forcing (agri_sfincs.evap) — synthetic, no network."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from agri_sfincs import evap


def _pet(days, value=4.0):
    """A 3 x 3 gridMET-like daily ETo field around the domain (lat ascending)."""
    lat = np.array([39.0, 39.5, 40.0])
    lon = np.array([-75.6, -75.2, -74.8])
    return xr.DataArray(
        np.full((len(days), 3, 3), value, dtype="float32"),
        coords={"time": pd.DatetimeIndex(days), "lat": lat, "lon": lon},
        dims=("time", "lat", "lon"), name="pet",
    )  # fmt: skip


def _precip(times):
    """A 2 x 3 UTM 18N precip grid (mm/h, hour starting at time), y descending."""
    x = np.array([480_000.0, 481_000.0, 482_000.0])
    y = np.array([4_370_000.0, 4_369_000.0])
    p = np.zeros((len(times), 2, 3), dtype="float32")
    return xr.DataArray(p, coords={"time": times, "y": y, "x": x},
                        dims=("time", "y", "x"), name="Precipitation")  # fmt: skip


class TestSolar(unittest.TestCase):
    def test_noon_and_midnight(self):
        lon, lat = evap.SUN_LONLAT
        # Local solar noon at -75.2 E is ~17:01 UTC; midnight ~05 UTC.
        s = evap.sin_solar_elevation(pd.DatetimeIndex(["2023-06-21T17:00", "2023-06-21T05:00"]), lon, lat)  # fmt: skip
        self.assertAlmostEqual(np.degrees(np.arcsin(s[0])), 90 - 39.45 + 23.44, delta=0.7)
        self.assertLess(s[1], 0)
        s_dec = evap.sin_solar_elevation(pd.DatetimeIndex(["2023-12-21T17:00"]), lon, lat)
        self.assertAlmostEqual(np.degrees(np.arcsin(s_dec[0])), 90 - 39.45 - 23.44, delta=0.7)

    def test_gridmet_day_starts_at_07z(self):
        d = evap.gridmet_day(pd.DatetimeIndex(["2023-09-15T06:00", "2023-09-15T07:00"]))
        self.assertEqual(list(d), [pd.Timestamp("2023-09-14"), pd.Timestamp("2023-09-15")])


class TestWeights(unittest.TestCase):
    def test_daylight_weights_sum_to_one_per_day(self):
        t = pd.date_range("2023-09-14T07:00", "2023-09-17T06:00", freq="h")
        for shape in ("daylight", "uniform"):
            w = evap.hourly_weights(t, shape=shape)
            s = pd.Series(w, index=evap.gridmet_day(t)).groupby(level=0).sum()
            np.testing.assert_allclose(s.values, 1.0, atol=1e-9)
        w = evap.hourly_weights(t)
        self.assertTrue((w >= 0).all())
        night = (t.hour >= 2) & (t.hour <= 8)  # 22-04 EDT
        self.assertEqual(float(w[night].sum()), 0.0)

    def test_clipped_window_keeps_hourly_rate(self):
        t = pd.date_range("2023-09-14T07:00", "2023-09-15T06:00", freq="h")
        full = evap.hourly_weights(t)
        part = evap.hourly_weights(t[10:16])
        np.testing.assert_allclose(part, full[10:16])

    def test_bad_shape(self):
        with self.assertRaises(ValueError):
            evap.hourly_weights(pd.date_range("2023-09-14", periods=3, freq="h"), shape="x")


class TestNetPrecip(unittest.TestCase):
    def test_dry_hours_keeps_rain_series(self):
        p = np.array([0.0, 0.2, 5.0, 0.0])
        e = np.array([0.3, 0.3, 0.3, 0.0])
        np.testing.assert_allclose(evap.net_precip(p, e, buffer=0), [-0.3, 0.2, 5.0, 0.0])
        np.testing.assert_allclose(evap.net_precip(p, e, mode="subtract"), p - e)
        # cnb treats prcp <= 0 as "not raining" (sfincs_infiltration.f90:737): the
        # positive part, which is all cnb sees, must be untouched in dry_hours mode.
        n = evap.net_precip(p, e)
        np.testing.assert_allclose(np.clip(n, 0, None), p)

    def test_buffer_keeps_minus_e_away_from_rain(self):
        p = np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0])
        e = np.full(6, 0.4)
        np.testing.assert_allclose(evap.net_precip(p, e), [-0.4, 0.0, 1.0, 0.0, -0.4, -0.4])
        np.testing.assert_allclose(evap.net_precip(p, e, buffer=2)[:5], [0, 0, 1, 0, 0])
        # Grid: one raining node -> its 3 x 3 x 3 neighbourhood gets no -E.
        g = np.zeros((3, 5, 5))
        g[1, 2, 2] = 2.0
        n = evap.net_precip(g, np.ones_like(g))
        self.assertTrue((n[:, 1:4, 1:4] >= 0).all())
        self.assertEqual(float(n[1, 2, 2]), 2.0)
        self.assertEqual(float(n[1, 0, 0]), -1.0)
        self.assertEqual(int((n < 0).sum()), g.size - 27)

    def test_dataarray(self):
        p = xr.DataArray([0.0, 1.0], dims="time")
        e = xr.DataArray([0.5, 0.5], dims="time")
        np.testing.assert_allclose(evap.net_precip(p, e, buffer=0).values, [-0.5, 1.0])
        np.testing.assert_allclose(evap.net_precip(p, e).values, [0.0, 1.0])
        with self.assertRaises(ValueError):
            evap.net_precip(p, e, mode="nope")


class TestOnGrid(unittest.TestCase):
    def setUp(self):
        self.t = pd.date_range("2023-09-14T07:00", "2023-09-16T06:00", freq="h")
        self.pet = _pet(["2023-09-14", "2023-09-15"], value=4.0)

    def test_daily_total_is_kc_times_pet(self):
        p = _precip(self.t)
        e = evap.evap_on_grid(p, pet=self.pet, kc=1.05)
        self.assertEqual(e.dims, ("time", "y", "x"))
        daily = e.isel(y=0, x=0).to_series().groupby(evap.gridmet_day(self.t)).sum()
        np.testing.assert_allclose(daily.values, 4.0 * 1.05, rtol=1e-5)

    def test_missing_pet_day_raises(self):
        p = _precip(self.t)
        with self.assertRaises(ValueError):
            evap.evap_on_grid(p, pet=self.pet.isel(time=[0]))

    def test_precip_minus_evap_keeps_rain(self):
        p = _precip(self.t)
        p[20, 0, 1] = 3.0
        out = evap.precip_minus_evap(p, pet=self.pet)
        self.assertEqual(float(out[20, 0, 1]), 3.0)
        self.assertLess(float(out[17 - 7 + 0, 0, 0]), 0)  # ~noon, dry
        self.assertIn(evap.STAMP, out.attrs)
        self.assertEqual(out.name, "Precipitation")

    def test_apply_to_run_rewrites_once(self):
        p = _precip(self.t)
        ds = p.to_dataset()
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            ds.to_netcdf(run / "sfincs_netampr.nc",
                         encoding={"time": {"units": "minutes since 2023-09-14"}})  # fmt: skip
            info = evap.apply_to_run(run, pet=self.pet)
            self.assertAlmostEqual(info["mean_E_mm_per_day_applied"], 4.2, places=3)
            with xr.open_dataset(run / "sfincs_netampr.nc") as out:
                self.assertEqual(out["Precipitation"].dtype, np.float32)
                self.assertEqual(out["time"].encoding["units"], "minutes since 2023-09-14")
                self.assertEqual(out["Precipitation"].dims, ("time", "y", "x"))
            with self.assertRaises(RuntimeError):
                evap.apply_to_run(run, pet=self.pet)


if __name__ == "__main__":
    unittest.main()
