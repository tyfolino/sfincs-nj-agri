"""Stage IV and MRMS hourly QPE, clipped to the three study counties: one NetCDF per year.

⚠️ Runs in the SEPARATE grib env (eccodes), like fetch_mrms.py, so it imports nothing
from ``agri_sfincs``:

    G=/cache/home/tpj8/agri-micromamba/envs/grib/bin/python
    $G scripts/fetch_precip_hourly.py --product stage4 --years 2002-2025 --workers 10
    $G scripts/fetch_precip_hourly.py --product mrms   --years 2015-2025 --workers 10
    $G scripts/fetch_precip_hourly.py --product stage4_6h --years 2002-2025 --workers 6

Sources (probed 2026-10-03):
  stage4  NCEP Stage IV hourly multi-sensor (RFC radar + gauge) analysis, from the Iowa
          Environmental Mesonet archive, complete 2002 -> today:
            https://mesonet.agron.iastate.edu/archive/data/YYYY/MM/DD/stage4/
            ST4.YYYYMMDDHH.01h.grib   (also .06h / .24h, not used)
          GRIB1 until ~2019, GRIB2 after, SAME 1121 x 881 HRAP polar-stereographic grid
          (~4.76 km; lat_ts 60N, lon_0 105W). Iowa State's *mtarchive* host has NO
          stage4/ directory (404); NCAR EOL ds21.093 / RDA ds507.5 were not needed.
          The file hour is the END of the accumulation (GRIB step 0-1 from HH-1).
          Missing cells are a GRIB bitmap -> NaN.
          The HOURLY mosaic has whole hours with nothing over NJ although the file
          exists (MARFC's hourly field absent: 2003-06 alone has 160 such hours), while
          the 6-h files (ST4.YYYYMMDDHH.06h.grib, HH = 00/06/12/18, GRIB1 headers say
          "18-24 h from 12Z the day before" for 12Z) are complete there; product
          ``stage4_6h`` fetches them so rain_metrics.py can fill those hours. IEM has
          NO 6-h files for nearly all of 2006, 2009-01..09 and a third of 2002 (the
          hourly gaps there are small). 4 hourly files are unreadable (2002 x3,
          2022-05-11T07). NCAR GDEX d507005 gave an empty listing; not pursued.
  mrms    MRMS hourly gauge-corrected QPE, as fetch_mrms.py (URLs, BBOX and the switch
          date are imported from it): Iowa State mtarchive GaugeCorr_QPE_01H before
          2020-10-14T00 (first file 2015-05-06T20; nothing earlier), AWS noaa-mrms-pds
          MultiSensor_QPE_01H_Pass2 from then. AWS Pass2 actually starts 2020-10-14T20
          and Iowa State GaugeCorr stops 2020-10-14T12, so missing hours fall back to
          Iowa State's own Pass2 copy (from 2020-10-13T19), then GaugeCorr; ``source``
          records which one each hour is. 0.01 deg grid; the file time is the END of
          the hour; -3 ("no coverage") -> NaN.

Clip: fetch_mrms.BBOX (model outline + 5 km), which also holds all three WHOLE counties
(Gloucester's Great Egg Harbor part included: county bounds -75.564..-74.852 E,
39.056..39.888 N vs BBOX -75.64..-74.80, 38.98..39.94). MRMS: the 96 x 84 cells
whose centres lie inside it (same cells as data/precip/mrms_2023-09.nc). Stage IV: the
rectangle of HRAP cells whose centres lie inside BBOX + 0.06 deg (one cell), so every
county point sits in a kept cell. Raw CONUS files are streamed and never kept.

Writes data/precip/<product>/<product>_<year>.nc:
  precip(time, y, x)  float32 mm accumulated over the hour (6 h for stage4_6h) ENDING at
                      ``time`` (UTC); the year holds those ending <year>-01-01T01 ..
                      <year+1>-01-01T00
  lat, lon            cell centres (1-D for MRMS, 2-D (y, x) for Stage IV)
  status(time)        0 ok, 1 file absent (404), 3 unreadable / wrong grid or time,
                      4 before the product exists (not requested)
  n_nan(time)         NaN cells in the clip that hour (= all cells unless status 0)
  source(time)        MRMS only: 0 GaugeCorr (Iowa State), 1 Pass2 (AWS), 2 Pass2
                      (Iowa State), -1 none
Resumable: finished months are kept as data/precip/<product>/parts/YYYY-MM.npz; a
month with transient failures (status 2) is retried on the next run, only those hours.
A year file is assembled once its 12 months are free of status 2; then its parts are
deleted. Existing year files are skipped.
"""

from __future__ import annotations

import argparse
import gzip
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import eccodes
import numpy as np
import pandas as pd
import requests
import xarray as xr

import fetch_mrms  # same directory, same env

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "precip"
BBOX = fetch_mrms.BBOX  # w, s, e, n
UA = "sfincs-nj-agri (research; Rutgers ag flood-loss study)"

STAGE4 = ("https://mesonet.agron.iastate.edu/archive/data/{t:%Y/%m/%d}/stage4/"
          "ST4.{t:%Y%m%d%H}.01h.grib")  # fmt: skip
#: A GRIB2 Stage IV file that defines the HRAP grid (lat/lon of every cell).
STAGE4_REF = pd.Timestamp("2023-09-29T12")
STAGE4_PAD = 0.06  # deg: one HRAP cell
STAGE4_SHAPE = (881, 1121)  # Nj, Ni
STAGE4_PROJ4 = "+proj=stere +lat_0=90 +lat_ts=60 +lon_0=-105 +x_0=0 +y_0=0 +R=6371200 +units=m"
#: First hour-ending time each product has (earlier hours: status 4, not requested).
FIRST = {"stage4": pd.Timestamp("2002-01-01T00"), "stage4_6h": pd.Timestamp("2002-01-01T00"),
         "mrms": pd.Timestamp("2015-05-06T00")}
#: Accumulation length (h) of each product's files.
STEP_H = {"stage4": 1, "stage4_6h": 6, "mrms": 1}

OK, ABSENT, FAILED, BAD, BEFORE = 0, 1, 2, 3, 4

_session: requests.Session | None = None


def _sess() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = UA
    return _session


#: MRMS sources, by code (stored per hour as ``source``).
MRMS_SOURCES = {
    0: fetch_mrms.IASTATE,  # GaugeCorr_QPE_01H, Iowa State
    1: fetch_mrms.AWS,  # MultiSensor_QPE_01H_Pass2, AWS
    2: ("https://mtarchive.geol.iastate.edu/{t:%Y/%m/%d}/mrms/ncep/MultiSensor_QPE_01H_Pass2/"
        "MultiSensor_QPE_01H_Pass2_00.00_{t:%Y%m%d-%H}0000.grib2.gz"),  # Pass2, Iowa State
}
STAGE4_SOURCE = 9


def candidates(product: str, t: pd.Timestamp) -> list[tuple[int, str]]:
    """(source code, URL) to try in order for the hour ending at ``t``. MRMS: the
    fetch_mrms.py choice first; then, for the hours around the switch that one source
    lacks (AWS Pass2 starts 2020-10-14T20, Iowa State GaugeCorr ends 2020-10-14T12),
    Iowa State's Pass2 copy, then GaugeCorr."""
    if product == "stage4":
        return [(STAGE4_SOURCE, STAGE4.format(t=t))]
    if product == "stage4_6h":
        return [(STAGE4_SOURCE, STAGE4.format(t=t).replace(".01h.", ".06h."))]
    order = [1, 2, 0] if t >= fetch_mrms.PASS2_START else [0, 2]
    return [(k, MRMS_SOURCES[k].format(t=t)) for k in order]


def get(url: str, retries: int = 6) -> bytes | None:
    """Body of ``url``; None on 404. Retries 429/5xx/connection errors with backoff and
    raises after ``retries``."""
    delay = 5.0
    for attempt in range(retries + 1):
        try:
            r = _sess().get(url, timeout=120)
            if r.status_code == 200:
                return r.content
            if r.status_code in (403, 404):  # S3 answers 403 for a missing key
                return None
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:  # incl. ChunkedEncodingError mid-body
            err = type(e).__name__
        if attempt == retries:
            raise RuntimeError(f"{url}: {err}")
        time.sleep(delay)
        delay = min(delay * 2, 300.0)
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------- grids + decoding


def decode(raw: bytes):
    """(values (Nj, Ni) float64 with NaN for missing, header dict) of one GRIB message."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    h = eccodes.codes_new_from_message(raw)
    try:
        eccodes.codes_set(h, "missingValue", 1.0e20)
        hd = {k: eccodes.codes_get(h, k) for k in
              ("edition", "Ni", "Nj", "latitudeOfFirstGridPointInDegrees",
               "longitudeOfFirstGridPointInDegrees", "validityDate", "validityTime",
               "dataDate", "dataTime", "startStep", "endStep")}  # fmt: skip
        v = eccodes.codes_get_values(h).reshape(hd["Nj"], hd["Ni"])
    finally:
        eccodes.codes_release(h)
    v[v >= 1.0e19] = np.nan
    return v, hd


def _hhmm(t: pd.Timestamp) -> tuple[int, int]:
    return int(f"{t:%Y%m%d}"), t.hour * 100


def mrms_window():
    """(row slice, col slice, lat, lon) of the MRMS CONUS grid inside BBOX: rows run
    north -> south from 54.995, cols west -> east from -129.995, 0.01 deg."""
    w, s, e, n = BBOX
    lat0, lon0, d = 54.995, -129.995, 0.01
    j0, j1 = int(np.ceil(round((lat0 - n) / d, 6))), int(np.floor(round((lat0 - s) / d, 6))) + 1
    i0, i1 = int(np.ceil(round((w - lon0) / d, 6))), int(np.floor(round((e - lon0) / d, 6))) + 1
    lat = np.round(lat0 - np.arange(j0, j1) * d, 3)
    lon = np.round(lon0 + np.arange(i0, i1) * d, 3)
    return slice(j0, j1), slice(i0, i1), lat, lon


def stage4_window(lat2d: np.ndarray, lon2d: np.ndarray, pad: float = STAGE4_PAD):
    """(row slice, col slice) of the smallest rectangle holding every cell whose centre
    lies inside BBOX + ``pad``."""
    w, s, e, n = BBOX
    lon2d = np.where(lon2d > 180, lon2d - 360, lon2d)
    inside = (lon2d >= w - pad) & (lon2d <= e + pad) & (lat2d >= s - pad) & (lat2d <= n + pad)
    rows, cols = np.nonzero(inside)
    if not len(rows):
        raise RuntimeError("BBOX is outside the Stage IV grid")
    return slice(rows.min(), rows.max() + 1), slice(cols.min(), cols.max() + 1)


def stage4_grid():
    """Lat/lon (Nj, Ni) of the Stage IV HRAP grid, from the reference GRIB2 file."""
    raw = get(STAGE4.format(t=STAGE4_REF))
    h = eccodes.codes_new_from_message(raw)
    try:
        nj, ni = eccodes.codes_get(h, "Nj"), eccodes.codes_get(h, "Ni")
        lat = eccodes.codes_get_array(h, "latitudes").reshape(nj, ni)
        lon = eccodes.codes_get_array(h, "longitudes").reshape(nj, ni)
    finally:
        eccodes.codes_release(h)
    if (nj, ni) != STAGE4_SHAPE:
        raise RuntimeError(f"Stage IV reference grid is {nj} x {ni}")
    return lat, np.where(lon > 180, lon - 360, lon)


def check_header(product: str, hd: dict, t: pd.Timestamp) -> str | None:
    """Why this message is not the expected hour on the expected grid, or None."""
    if product.startswith("stage4"):
        if (hd["Nj"], hd["Ni"]) != STAGE4_SHAPE:
            return f"grid {hd['Nj']}x{hd['Ni']}"
        lat1, lon1 = hd["latitudeOfFirstGridPointInDegrees"], hd["longitudeOfFirstGridPointInDegrees"]
        # GRIB1 headers before ~2012 round lon1 to 240.983 instead of 240.977: same grid.
        if abs(lat1 - 23.117) > 0.01 or abs((lon1 % 360) - 240.977) > 0.01:
            return f"first point {lat1},{lon1}"
        # GRIB1 6-h files say e.g. "18-24 h from 12Z yesterday": check the span only.
        span = hd["endStep"] - hd["startStep"]
        if (hd["validityDate"], hd["validityTime"]) != _hhmm(t) or span != STEP_H[product]:
            return f"valid {hd['validityDate']} {hd['validityTime']} span {span} h"
    else:
        if (hd["Nj"], hd["Ni"]) != (3500, 7000):
            return f"grid {hd['Nj']}x{hd['Ni']}"
        if abs(hd["latitudeOfFirstGridPointInDegrees"] - 54.995) > 1e-3:
            return "first point"
        # MRMS stamps the hour's END as its reference time.
        if (hd["dataDate"], hd["dataTime"]) != _hhmm(t):
            return f"time {hd['dataDate']} {hd['dataTime']}"
    return None


_WIN: dict = {}


def _init(product: str, win) -> None:
    global _session
    _session = None  # never share the parent's pooled connections across fork
    _WIN["product"], _WIN["win"] = product, win


def fetch_hour(t: pd.Timestamp):
    """(status, source code, clipped float32 array or None, note) for the hour ending
    at ``t``: the first candidate that exists and decodes."""
    product, (rs, cs) = _WIN["product"], _WIN["win"]
    result = (ABSENT, -1, None, "")
    for src, url in candidates(product, t):
        try:
            raw = get(url)
        except RuntimeError as e:
            result = (FAILED, src, None, str(e))  # transient: retried next run
            continue
        if raw is None:
            continue
        try:
            v, hd = decode(raw)
        except Exception as e:  # noqa: BLE001 — a corrupt file is data, not a crash
            result = (BAD, src, None, f"{url}: {type(e).__name__}: {e}")
            continue
        why = check_header(product, hd, t)
        if why:
            result = (BAD, src, None, f"{url}: {why}")
            continue
        out = v[rs, cs].astype(np.float32)
        out[out < 0] = np.nan  # MRMS -3 = no coverage
        return OK, src, out, ""
    return result


# ---------------------------------------------------------------- months + years


def year_hours(year: int, step_h: int = 1) -> pd.DatetimeIndex:
    """Accumulation-ending times of a year file: <year>-01-01T01 .. <year+1>-01-01T00
    (for 6-h files: those ending at 00, 06, 12, 18Z)."""
    t = pd.date_range(f"{year}-01-01T01", f"{year + 1}-01-01T00", freq="h")
    return t[t.hour % step_h == 0]


def month_groups(times: pd.DatetimeIndex) -> dict[str, pd.DatetimeIndex]:
    """Split hour-ending times by the UTC month of the hour's START (the part files)."""
    key = (times - pd.Timedelta("1h")).strftime("%Y-%m")
    return {k: times[key == k] for k in pd.unique(key)}


def do_month(product, key, times, shape, ex, part_dir: Path) -> np.ndarray:
    """Fetch (or complete) one month part; returns its status array."""
    part = part_dir / f"{key}.npz"
    if part.exists():
        z = np.load(part)
        arr, status, source = z["precip"], z["status"], z["source"]
        todo = np.nonzero(status == FAILED)[0]
        if len(status) != len(times) or arr.shape[1:] != shape:
            raise RuntimeError(f"{part} does not match this month/clip — delete it")
        if not len(todo):
            return status
    else:
        arr = np.full((len(times), *shape), np.nan, np.float32)
        status = np.full(len(times), FAILED, np.int8)
        source = np.full(len(times), -1, np.int8)
        todo = np.arange(len(times))
    before = times[todo] < FIRST[product]
    status[todo[before]] = BEFORE
    todo = todo[~before]
    t0 = time.time()
    notes = []
    for k, (st, src, a, note) in zip(todo, ex.map(fetch_hour, times[todo], chunksize=4)):
        status[k], source[k] = st, src
        if a is not None:
            arr[k] = a
        if note and st != ABSENT:
            notes.append(note)
    tmp = part.with_name(part.name + ".tmp.npz")
    np.savez(tmp, precip=arr, status=status, source=source, time=times.values)
    tmp.rename(part)
    c = np.bincount(status, minlength=5)
    print(f"{product} {key}: {len(todo)} fetched in {time.time() - t0:.0f} s; ok {c[OK]} "
          f"absent {c[ABSENT]} failed {c[FAILED]} bad {c[BAD]} before {c[BEFORE]}",
          flush=True)  # fmt: skip
    for n in notes[:5]:
        print(f"    {n}", flush=True)
    return status


def assemble(product, year, coords, part_dir: Path, dest: Path) -> None:
    times = year_hours(year, STEP_H[product])
    parts = [np.load(part_dir / f"{k}.npz") for k in month_groups(times)]
    arr = np.concatenate([p["precip"] for p in parts])
    status = np.concatenate([p["status"] for p in parts])
    source = np.concatenate([p["source"] for p in parts])
    n_nan = np.isnan(arr).reshape(len(times), -1).sum(axis=1).astype(np.int32)
    dims = ("time", "y", "x")
    data = {"precip": (dims, arr, {"units": "mm",
                                   "long_name": f"{STEP_H[product]}-h accumulation ending at time (UTC)"}),
            "status": ("time", status, {"flag_values": "0 1 3 4",
                                        "flag_meanings": "ok absent unreadable before_product"}),
            "n_nan": ("time", n_nan, {"long_name": "NaN cells in the clip this hour"})}  # fmt: skip
    attrs = {"product": product, "bbox_wsen": str(BBOX), "made_by": "scripts/fetch_precip_hourly.py",
             "time": f"END of the {STEP_H[product]}-h accumulation, UTC"}  # fmt: skip
    if product == "mrms":
        data["source"] = ("time", source,
                          {"flag_meanings": "-1 none, 0 GaugeCorr_QPE_01H (Iowa State "
                                            "mtarchive), 1 MultiSensor_QPE_01H_Pass2 (AWS), "
                                            "2 MultiSensor_QPE_01H_Pass2 (Iowa State)"})  # fmt: skip
        c = {"lat": ("y", coords["lat"]), "lon": ("x", coords["lon"])}
        attrs["source_urls"] = f"{fetch_mrms.IASTATE} | {fetch_mrms.AWS}"
    else:
        c = {"lat": (("y", "x"), coords["lat"]), "lon": (("y", "x"), coords["lon"]),
             "hrap_j": ("y", coords["j"]), "hrap_i": ("x", coords["i"])}  # fmt: skip
        attrs |= {"source_urls": STAGE4, "crs_proj4": STAGE4_PROJ4,
                  "grid": "HRAP 1121x881 polar stereographic, ~4762.5 m; hrap_j/i index the "
                          "full grid (row 0 = south)"}  # fmt: skip
    ds = xr.Dataset(data, coords={"time": times, **c}, attrs=attrs)
    tmp = dest.with_name(dest.name + ".tmp")
    enc = {"precip": {"zlib": True, "complevel": 4, "shuffle": True},
           "status": {"zlib": True}, "n_nan": {"zlib": True}}  # fmt: skip
    ds.to_netcdf(tmp, encoding=enc)
    tmp.rename(dest)
    for k in month_groups(times):
        (part_dir / f"{k}.npz").unlink()
    c = np.bincount(status, minlength=5)
    print(f"{product} {year}: wrote {dest.name}; hours ok {c[OK]} absent {c[ABSENT]} "
          f"bad {c[BAD]} before {c[BEFORE]}; NaN cell-hours in ok hours "
          f"{int(n_nan[status == OK].sum())}", flush=True)  # fmt: skip


def parse_years(s: str) -> list[int]:
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(y) for y in s.split(",")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--product", choices=list(STEP_H), required=True)
    ap.add_argument("--years", required=True, help="e.g. 2002-2025 or 2023,2021")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--start", help="testing: only hours ending from this time ...")
    ap.add_argument("--end", help="... to this one (parts_test/ only, no year file)")
    a = ap.parse_args()
    out_dir = OUT / a.product
    part_dir = out_dir / ("parts_test" if a.start else "parts")
    part_dir.mkdir(parents=True, exist_ok=True)

    if a.product == "mrms":
        rs, cs, lat, lon = mrms_window()
        coords = {"lat": lat, "lon": lon}
    else:
        lat2d, lon2d = stage4_grid()
        rs, cs = stage4_window(lat2d, lon2d)
        coords = {"lat": lat2d[rs, cs], "lon": lon2d[rs, cs],
                  "j": np.arange(rs.start, rs.stop), "i": np.arange(cs.start, cs.stop)}  # fmt: skip
    shape = (rs.stop - rs.start, cs.stop - cs.start)
    print(f"{a.product}: clip rows {rs.start}:{rs.stop} cols {cs.start}:{cs.stop} "
          f"= {shape}", flush=True)  # fmt: skip

    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.product, (rs, cs))) as ex:
        for year in parse_years(a.years):
            dest = out_dir / f"{a.product}_{year}.nc"
            if dest.exists() and not a.start:
                print(f"{a.product} {year}: have {dest.name}", flush=True)
                continue
            times = year_hours(year, STEP_H[a.product])
            if a.start:
                times = times[(times >= pd.Timestamp(a.start)) & (times <= pd.Timestamp(a.end))]
            if not len(times):
                continue
            ok = True
            for key, ts in month_groups(times).items():
                st = do_month(a.product, key, ts, shape, ex, part_dir)
                ok &= not (st == FAILED).any()
            if a.start:
                continue
            if ok:
                assemble(a.product, year, coords, part_dir, dest)
            else:
                print(f"{a.product} {year}: transient failures left — rerun to retry them",
                      flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
