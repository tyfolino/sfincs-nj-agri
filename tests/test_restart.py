"""Resume-from-restart plumbing (agri_sfincs.restart) on synthetic run dirs — no network,
no solver."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np

from agri_sfincs import restart as R

INP = """tref                 = 20230815 000000
tstart               = 20230815 000000
tstop                = 20230819 000000
tspinup              = 3600.0
dtmapout             = 86400.0
dtmaxout             = 86400.0
dtrstout             = 86400.0
zsini                = -1.0
infiltration_type    = cnb
"""
DAY = 86400.0


def fortran_records(*payloads: bytes) -> bytes:
    out = b""
    for p in payloads:
        n = len(p).to_bytes(4, "little")
        out += n + p + n
    return out


def rst_bytes(rtype: int = 4, n: int = 3) -> bytes:
    f4 = np.zeros(n, "<f4").tobytes()
    recs = [np.int32(rtype).tobytes()] + [f4] * (R.RST_RECORDS[rtype] - 1)
    return fortran_records(*recs)


def write_map(path: Path, times_s, tmax_s, cum, zs=None, ntmax=None):
    """A tiny SFINCS-like map: time (unlimited) + fixed timemax with float fill."""
    import netCDF4

    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("time", None)
        ds.createDimension("timemax", ntmax or len(tmax_s))
        ds.createDimension("n", 2)
        ds.createVariable("zb", "f4", ("n",))[:] = [1.0, 2.0]
        ds.createVariable("time", "f4", ("time",))[:] = times_s
        z = ds.createVariable("zs", "f4", ("time", "n"))
        z[:] = zs if zs is not None else np.outer(times_s, [1.0, 1.0]) / DAY
        tm = ds.createVariable("timemax", "f4", ("timemax",))
        tm[: len(tmax_s)] = tmax_s
        c = ds.createVariable("cumprcp", "f4", ("timemax", "n"))
        c[: len(tmax_s)] = cum


class TestInp(unittest.TestCase):
    def test_get_set(self):
        self.assertEqual(R.inp_get(INP, "tstart"), "20230815 000000")
        self.assertIsNone(R.inp_get(INP, "rstfile"))
        t = R.inp_set(INP, {"tstart": "20230817 000000", "rstfile": "x.rst"})
        self.assertIn("tstart               = 20230817 000000", t)
        self.assertEqual(R.inp_get(t, "rstfile"), "x.rst")
        self.assertEqual(R.inp_get(t, "zsini"), "-1.0")  # untouched

    def test_resume_inp(self):
        t = R.resume_inp(INP, "sfincs.20230817.000000.rst", datetime(2023, 8, 17))
        self.assertEqual(R.inp_datetime(t, "tstart"), datetime(2023, 8, 17))
        self.assertEqual(R.inp_datetime(t, "tref"), datetime(2023, 8, 15))  # clock kept
        self.assertEqual(R.inp_get(t, "tspinup"), "0.0")  # no second boundary ramp
        self.assertEqual(R.inp_get(t, "rstfile"), "sfincs.20230817.000000.rst")
        self.assertEqual(t.count("tstart"), 1)


class TestRstFiles(unittest.TestCase):
    def test_stamp(self):
        self.assertEqual(R.rst_stamp("sfincs.20230817.000000.rst"), datetime(2023, 8, 17))
        self.assertIsNone(R.rst_stamp("sfincs.20230817.rst"))
        self.assertIsNone(R.rst_stamp("sfincs.20250231.000000.rst"))  # engine's leap-day name

    def test_rst_type(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.rst"
            p.write_bytes(rst_bytes(4))
            self.assertEqual(R.rst_type(p), 4)
            p.write_bytes(rst_bytes(1))
            self.assertEqual(R.rst_type(p), 1)
            p.write_bytes(rst_bytes(4)[:-10])  # killed while writing
            self.assertIsNone(R.rst_type(p))
            p.write_bytes(rst_bytes(4) + b"\0\0")
            self.assertIsNone(R.rst_type(p))
            # a cnb header with one record missing
            p.write_bytes(fortran_records(np.int32(4).tobytes(), b"\0" * 8, b"\0" * 8))
            self.assertIsNone(R.rst_type(p))

    def test_choose_restart(self):
        t0, t1, tref = datetime(2023, 8, 15), datetime(2023, 8, 19), datetime(2023, 8, 15)
        rsts = [(datetime(2023, 8, d), Path(f"r{d}")) for d in (15, 16, 17, 18, 19)]
        rsts.append((datetime(2023, 8, 17, 6), Path("off")))
        ok = lambda p: True  # noqa: E731
        pick = R.choose_restart(rsts, t0, t1, tref, end_s=2.5 * DAY, dtmax=DAY, is_complete=ok)
        self.assertEqual(pick[1], Path("r17"))  # 18 is beyond the written outputs
        pick = R.choose_restart(rsts, t0, t1, tref, end_s=9 * DAY, dtmax=DAY, is_complete=ok)
        self.assertEqual(pick[1], Path("r18"))  # never the one AT tstop, never off-lattice
        bad = lambda p: p != Path("r18")  # noqa: E731
        pick = R.choose_restart(rsts, t0, t1, tref, end_s=9 * DAY, dtmax=DAY, is_complete=bad)
        self.assertEqual(pick[1], Path("r17"))  # incomplete newest -> the one before
        self.assertIsNone(R.choose_restart(rsts, t0, t1, tref, 0.5 * DAY, DAY, ok))
        # prefer a rain-free stamp, but only within the lookback of the newest
        dry = lambda t: t.day == 16  # noqa: E731
        pick = R.choose_restart(rsts, t0, t1, tref, 9 * DAY, DAY, ok, is_dry=dry)
        self.assertEqual(pick[1], Path("r16"))
        pick = R.choose_restart(rsts, t0, t1, tref, 9 * DAY, DAY, ok, is_dry=dry, lookback_s=DAY)
        self.assertEqual(pick[1], Path("r18"))  # r16 is 2 d back: take the newest
        pick = R.choose_restart(rsts, t0, t1, tref, 9 * DAY, DAY, ok, is_dry=lambda t: False)
        self.assertEqual(pick[1], Path("r18"))

    def test_rain_free(self):
        import pandas as pd
        import xarray as xr

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            t = pd.date_range("2023-08-15", periods=10, freq="h")
            p = np.zeros((10, 2, 2), "f4")
            p[4] = 1.0  # the block starting 04:00 rains
            xr.Dataset({"Precipitation": (("time", "y", "x"), p)}, coords={"time": t}).to_netcdf(
                d / "sfincs_netampr.nc")  # fmt: skip
            text = INP + "netamprfile          = sfincs_netampr.nc\n"
            self.assertFalse(R.rain_free(d, text, datetime(2023, 8, 15, 5), hours=3))
            self.assertFalse(R.rain_free(d, text, datetime(2023, 8, 15, 7), hours=3))
            self.assertTrue(R.rain_free(d, text, datetime(2023, 8, 15, 8), hours=3))
            self.assertTrue(R.rain_free(d, text, datetime(2023, 8, 15, 4), hours=3))
            self.assertTrue(R.rain_free(d, INP, datetime(2023, 8, 15, 5)))  # no forcing file


class TestOwnership(unittest.TestCase):
    def test_records(self):
        t = np.arange(0, 5) * DAY
        np.testing.assert_array_equal(R.owned_records(t, 0, 2 * DAY), [0, 1, 2])
        # the later part starts where the earlier one's record at the resume instant was
        np.testing.assert_array_equal(R.owned_records(t, 2 * DAY, None, after_s=2 * DAY), [3, 4])
        np.testing.assert_array_equal(R.owned_records(t, 2 * DAY, None), [2, 3, 4])

    def test_blocks(self):
        tm = np.array([1, 2, 3, R.NC_FLOAT_FILL * 1.001]) * np.array([DAY, DAY, DAY, 1])
        np.testing.assert_array_equal(R.owned_blocks(tm, 0, 2 * DAY, 4 * DAY), [0, 1])
        np.testing.assert_array_equal(R.owned_blocks(tm, 2 * DAY, None, 4 * DAY), [2])

    def test_offset_record(self):
        t = np.array([1, 2, 3]) * DAY
        self.assertEqual(R.offset_record(t, 2 * DAY), 1)
        self.assertIsNone(R.offset_record(t, 0.5 * DAY))


class TestPrepareFinish(unittest.TestCase):
    """A 4-day run killed after day 2 (outputs to 2.5 d), resumed from day 2, finished."""

    def test_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "sfincs.inp").write_text(INP)
            self.assertEqual(R.plan(d).action, "fresh")  # nothing written yet
            for day in (16, 17, 18):
                (d / f"sfincs.201308{day}.000000.rst").write_bytes(rst_bytes())  # wrong year: ignored
            for day in (16, 17):
                (d / f"sfincs.202308{day}.000000.rst").write_bytes(rst_bytes())
            (d / "sfincs.20230818.000000.rst").write_bytes(rst_bytes()[:-3])  # being written
            # segment 0: 0..2 d of map, blocks ending 1 and 2 d (cum 1, 3 mm), 2 more unwritten
            write_map(d / "sfincs_map.nc", [0, DAY, 2 * DAY], [DAY, 2 * DAY],
                      [[1, 1], [3, 3]], ntmax=4)  # fmt: skip
            (d / "sfincs_log.txt").write_text("seg0 log\n")
            pl = R.prepare(d)
            self.assertEqual(pl.action, "resume")
            self.assertEqual(pl.t_resume, datetime(2023, 8, 17))
            self.assertFalse((d / "sfincs_map.nc").exists())
            self.assertEqual(R.inp_get((d / "sfincs.inp").read_text(), "tstart"), "20230817 000000")
            self.assertTrue((d / R.ORIG_INP).is_file())
            # the resumed solve: 2..4 d, its cumprcp restarts at 0 (+2 and +4 mm)
            write_map(d / "sfincs_map.nc", [2 * DAY, 3 * DAY, 4 * DAY], [3 * DAY, 4 * DAY],
                      [[2, 2], [4, 4]], zs=np.full((3, 2), 9.0))  # fmt: skip
            for day in (18, 19):
                (d / f"sfincs.202308{day}.000000.rst").write_bytes(rst_bytes())
            self.assertEqual(R.plan(d).action, "finish")
            rep = R.finish(d)
            self.assertTrue(rep["finished"])
            self.assertEqual(rep["segments"], 1)

            import netCDF4

            with netCDF4.Dataset(d / "sfincs_map.nc") as ds:
                np.testing.assert_allclose(ds["time"][:], np.arange(5) * DAY)
                # record at the resume instant from the EARLIER segment (2.0, not 9.0)
                np.testing.assert_allclose(ds["zs"][:, 0], [0, 1, 2, 9, 9])
                np.testing.assert_allclose(ds["timemax"][:], np.arange(1, 5) * DAY)
                np.testing.assert_allclose(ds["cumprcp"][:, 0], [1, 3, 5, 7])  # offset +3
            self.assertEqual(R.inp_get((d / "sfincs.inp").read_text(), "tstart"), "20230815 000000")
            self.assertFalse((d / R.ORIG_INP).exists())
            self.assertFalse((d / R.SEG_DIR).exists())
            left = sorted(p.name for p in d.glob("sfincs.2023*.rst"))
            self.assertEqual(left, ["sfincs.20230819.000000.rst"])  # the state at tstop
            self.assertIn("seg0 log", (d / "sfincs_log.txt").read_text())

    def test_resumed_segment_killed_before_its_first_record(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "sfincs.inp").write_text(INP)
            write_map(d / "sfincs_map.nc", [0, DAY, 2 * DAY], [DAY, 2 * DAY], [[1, 1], [3, 3]], ntmax=4)
            (d / "sfincs.20230817.000000.rst").write_bytes(rst_bytes())
            self.assertEqual(R.prepare(d).action, "resume")
            (d / "sfincs_map.nc").write_bytes(b"")  # killed while reading its inputs
            pl = R.prepare(d)
            self.assertEqual((pl.action, pl.retire), ("resume", False))
            self.assertEqual(len(R.segments(d)), 1)  # the parked segment survives
            self.assertFalse((d / "sfincs_map.nc").exists())
            self.assertEqual(R.inp_get((d / "sfincs.inp").read_text(), "rstfile"),
                             "sfincs.20230817.000000.rst")  # fmt: skip

    def test_finish_refuses_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "sfincs.inp").write_text(INP)
            write_map(d / "sfincs_map.nc", [0, DAY], [DAY], [[1, 1]], ntmax=4)
            (d / "sfincs.20230816.000000.rst").write_bytes(rst_bytes())
            rep = R.finish(d)
            self.assertFalse(rep["finished"])
            self.assertTrue((d / "sfincs.20230816.000000.rst").exists())

    def test_unreadable_map_means_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "sfincs.inp").write_text(INP)
            (d / "sfincs_map.nc").write_bytes(b"not a netcdf file")
            (d / "sfincs.20230816.000000.rst").write_bytes(rst_bytes())
            self.assertEqual(R.plan(d).action, "fresh")


if __name__ == "__main__":
    unittest.main()
