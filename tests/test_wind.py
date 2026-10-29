"""Wind forcing grid and the engine's corner convention (agri_sfincs.wind) — synthetic, no network."""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from agri_sfincs import wind


class TestGrid(unittest.TestCase):
    def test_centres_overhang_the_model_by_pad_cells(self):
        xc, yc = wind.grid_centres((1000.0, 2000.0, 31000.0, 12000.0), res=5000.0, pad=3)
        self.assertTrue(np.all(np.diff(xc) == 5000.0) and np.all(np.diff(yc) == 5000.0))
        self.assertLessEqual(xc[0] - 2.5 * 5000.0, 1000.0 - 2 * 5000.0)  # > 1 cell outside
        self.assertGreaterEqual(xc[-1] + 2.5 * 5000.0, 31000.0 + 2 * 5000.0)
        self.assertLessEqual(yc[0] - 2.5 * 5000.0, 2000.0 - 2 * 5000.0)
        self.assertGreaterEqual(yc[-1] + 2.5 * 5000.0, 12000.0 + 2 * 5000.0)


class TestEngineConvention(unittest.TestCase):
    """What the engine reads back from the written file must be the field at the true point."""

    def setUp(self):
        self.xc = 400000.0 + 5000.0 * np.arange(8)
        self.yc = 4300000.0 + 5000.0 * np.arange(6)
        X, Y = np.meshgrid(self.xc, self.yc)
        self.f = lambda x, y: 0.001 * (x - 400000.0) + 0.0005 * (y - 4300000.0)  # linear: bilinear is exact
        self.u = np.stack([self.f(X, Y), 2 * self.f(X, Y)]).astype("f4")
        self.v = -self.u
        self.times = pd.DatetimeIndex(["2023-06-01 00:00", "2023-06-01 01:00"])
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / wind.FILE
        wind.write_file(self.path, self.times, self.xc, self.yc, self.u, self.v, "2023-06-01", 32618, {})

    def tearDown(self):
        self.tmp.cleanup()

    def test_engine_reads_true_field(self):
        for x, y in [(412345.0, 4311111.0), (self.xc[2], self.yc[3]), (426000.0, 4318000.0)]:
            got = wind.engine_sample(self.path, x, y)
            np.testing.assert_allclose(got[:, 0], [self.f(x, y), 2 * self.f(x, y)], atol=1e-4)
            np.testing.assert_allclose(got[:, 1], [-self.f(x, y), -2 * self.f(x, y)], atol=1e-4)

    def test_written_coordinates_are_corners_and_time_is_fews_minutes(self):
        with xr.open_dataset(self.path, decode_times=False) as ds:
            self.assertEqual(float(ds.x[0]), self.xc[0] - 2500.0)
            self.assertEqual(float(ds.y[0]), self.yc[0] - 2500.0)
            self.assertEqual(ds.time.attrs["units"], "minutes since 2023-06-01 00:00:00")
            self.assertEqual(list(ds.time.values), [0.0, 60.0])
            self.assertEqual(ds["eastward_wind"].dims, ("time", "y", "x"))

    def test_centres_written_would_be_half_a_cell_off(self):
        """The trap the convention avoids: a file holding CENTRES is read 2.5 km W and S."""
        bad = Path(self.tmp.name) / "centres.nc"
        wind.write_file(bad, self.times, self.xc + 2500.0, self.yc + 2500.0, self.u, self.v, "2023-06-01", 32618, {})
        x, y = 412345.0, 4311111.0
        self.assertAlmostEqual(float(wind.engine_sample(bad, x, y)[0, 0]), self.f(x - 2500.0, y - 2500.0), places=4)


class TestRegrid(unittest.TestCase):
    def test_uniform_field_and_components_kept_apart(self):
        lat, lon = np.arange(40.0, 38.4, -0.25), np.arange(-76.0, -74.4, 0.25)
        t = pd.date_range("2023-06-01", periods=2, freq="h")
        ds = xr.Dataset({"u10": (("time", "latitude", "longitude"), np.full((2, lat.size, lon.size), 3.0)),
                         "v10": (("time", "latitude", "longitude"), np.full((2, lat.size, lon.size), -4.0))},
                        coords={"time": t, "latitude": lat, "longitude": lon})  # fmt: skip
        xc, yc = wind.grid_centres((470000.0, 4340000.0, 490000.0, 4360000.0))
        u, v = wind.regrid(ds, xc, yc, 32618)
        self.assertEqual(u.shape, (2, yc.size, xc.size))
        np.testing.assert_allclose(u, 3.0, rtol=1e-6)
        np.testing.assert_allclose(v, -4.0, rtol=1e-6)

    def test_outside_the_era5_box_raises(self):
        lat, lon = np.array([39.5, 39.25]), np.array([-75.5, -75.25])
        ds = xr.Dataset({k: (("time", "latitude", "longitude"), np.ones((1, 2, 2))) for k in ("u10", "v10")},
                        coords={"time": pd.date_range("2023-06-01", periods=1), "latitude": lat, "longitude": lon})  # fmt: skip
        xc, yc = wind.grid_centres((470000.0, 4340000.0, 490000.0, 4380000.0))
        with self.assertRaises(ValueError):
            wind.regrid(ds, xc, yc, 32618)


class TestHrrr(unittest.TestCase):
    """A synthetic HRRR window file on its Lambert conformal grid, read the way load_hrrr does."""

    def make(self, gap_hours=()):
        from pyproj import Transformer

        attrs = {"LoV": 262.5, "Latin1": 38.5, "Latin2": 38.5, "Dx": 3000.0}
        proj = wind.HRRR_PROJ.format(**attrs)
        x0, y0 = Transformer.from_crs("EPSG:4326", proj, always_xy=True).transform(-76.2, 38.3)
        x, y = x0 + 3000.0 * np.arange(60), y0 + 3000.0 * np.arange(80)
        X, Y = np.meshgrid(x, y)
        lon, lat = Transformer.from_crs(proj, "EPSG:4326", always_xy=True).transform(X, Y)
        t = pd.date_range("2018-10-27", periods=6, freq="h")
        u = np.stack([0.001 * (X - x0) + k for k in range(6)]).astype("f4")  # linear in x
        u[list(gap_hours)] = np.nan
        ds = xr.Dataset({"u10": (("time", "y", "x"), u), "v10": (("time", "y", "x"), -u)},
                        coords={"time": t, "latitude": (("y", "x"), lat), "longitude": (("y", "x"), lon)},
                        attrs=attrs)  # fmt: skip
        return ds, x, y, proj, x0

    def test_axes_recovered_from_lat_lon(self):
        ds, x, y, _, _ = self.make()
        xa, ya, _ = wind.hrrr_axes(ds)
        np.testing.assert_allclose(xa, x, atol=0.01)
        np.testing.assert_allclose(ya, y, atol=0.01)

    def test_load_fills_short_gaps_and_regrids_exactly(self):
        from pyproj import Transformer

        ds, _, _, proj, x0 = self.make(gap_hours=(2, 3))
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "hrrr").mkdir()
            ds.to_netcdf(Path(d) / "hrrr" / "hrrr_wind_test.nc")
            with unittest.mock.patch.object(wind.config, "WIND_DIR", Path(d)):
                got = wind.load("hrrr", "2018-10-27 01:00", "2018-10-27 05:00")
        self.assertEqual(got.attrs["filled_hours"], 2)
        xc, yc = wind.grid_centres((470000.0, 4340000.0, 490000.0, 4360000.0))
        u, v = wind.regrid(got, xc, yc, 32618)
        px, _ = Transformer.from_crs(32618, proj, always_xy=True).transform(*np.meshgrid(xc, yc))
        for k, hour in enumerate(range(1, 6)):
            np.testing.assert_allclose(u[k], 0.001 * (px - x0) + hour, atol=2e-3)
        np.testing.assert_allclose(v, -u)

    def test_long_gap_raises(self):
        ds, *_ = self.make(gap_hours=(1, 2, 3, 4))
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "hrrr").mkdir()
            ds.to_netcdf(Path(d) / "hrrr" / "hrrr_wind_test.nc")
            with unittest.mock.patch.object(wind.config, "WIND_DIR", Path(d)), self.assertRaises(ValueError):
                wind.load("hrrr", "2018-10-27 00:00", "2018-10-27 05:00")


if __name__ == "__main__":
    unittest.main()
