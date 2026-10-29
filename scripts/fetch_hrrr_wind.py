"""HRRR hourly 10 m wind over the bay and both shores, earth-relative, one NetCDF per window.

⚠️ Runs in the SEPARATE grib env (eccodes), like fetch_mrms.py, so it imports nothing
from ``agri_sfincs``:

    /cache/home/tpj8/agri-micromamba/envs/grib/bin/python scripts/fetch_hrrr_wind.py \
        --start 2018-10-13T00 --end 2018-11-04T00 --out data/wind/hrrr/hrrr_wind_storm2018oct.nc

Source: NOAA HRRR on AWS (noaa-hrrr-bdp-pds, NOAA Open Data Dissemination; from
2014-07-30), the 3 km CONUS analysis ``wrfsfcf00`` of each hourly cycle. When an
analysis is missing, the previous cycle's 1 h forecast (``f01``) stands in; the count
of each goes in the attributes. Only ``UGRD`` / ``VGRD`` at 10 m are downloaded (HTTP
range from the ``.idx``; they are adjacent messages, ~2.5 MB an hour).

Why HRRR (2026-10-29): ERA5's ~28 km cells are part land over a 15-40 km wide bay and
read ~30% low against the bay lights (reports/era5_wind.md); HRRR's 3 km grid has the
bay as water.

🔴 HRRR u / v are GRID-relative (``uvRelativeToGrid`` = 1) on a Lambert conformal grid.
They are rotated to east / north here (``earth_relative``: angle = sin(Latin1) x
(lon - LoV), the tangent-cone constant; the same rotation as wgrib2 -new_grid_winds
earth and WRF's cosalpha / sinalpha). ~14 deg at the bay.

Box (N, W, S, E): ``BOX``, the same as fetch_era5_wind.BOX; the crop is the index window
of every grid point inside it.

Writes ``--out``: ``u10``, ``v10`` (m/s, earth-relative, the vector the air moves TOWARD)
on ``time`` (UTC, valid time) x ``y`` x ``x`` (crop rows south -> north, as in the GRIB),
2-D ``latitude`` / ``longitude``, and the projection in the attributes (``LoV``,
``Latin1``, ``Latin2``, ``Dx``) for agri_sfincs.wind to recover the regular grid.

Usage: see above; ``--workers`` parallel downloads (default 8).
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xarray as xr

#: [North, West, South, East], degrees (= fetch_era5_wind.BOX).
BOX = [40.25, -76.0, 38.5, -74.5]
AWS = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{c:%Y%m%d}/conus/hrrr.t{c:%H}z.wrfsfcf{f:02d}.grib2"
FIELDS = ("UGRD:10 m above ground", "VGRD:10 m above ground")

_session = requests.Session()
_session.headers["User-Agent"] = "sfincs-nj-agri (research; Rutgers ag flood-loss study)"


def _get(url: str, headers: dict | None = None, retries: int = 5) -> bytes:
    delay = 5.0
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, headers=headers or {}, timeout=120)
            if r.status_code in (200, 206):
                return r.content
            if r.status_code in (403, 404):
                raise FileNotFoundError(url)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"giving up on {url}")


def byte_range(idx: str, fields=FIELDS) -> tuple[int, int | None]:
    """(first byte, last byte or None = to the end) spanning ``fields``, which must be
    adjacent messages in the ``.idx`` text."""
    lines = [ln.split(":") for ln in idx.strip().splitlines()]
    hit = [k for k, ln in enumerate(lines) if ":".join(ln[3:5]) in fields]
    if len(hit) != len(fields) or hit[-1] - hit[0] != len(fields) - 1:
        raise ValueError(f"fields {fields} not found together in the index")
    start = int(lines[hit[0]][1])
    end = int(lines[hit[-1] + 1][1]) - 1 if hit[-1] + 1 < len(lines) else None
    return start, end


def earth_relative(u, v, lon, lov: float, latin1: float):
    """Grid-relative (u, v) on a tangent Lambert conformal grid -> east / north.
    ``lon``, ``lov`` in degrees (either sign convention)."""
    d = (np.asarray(lon) - lov + 180.0) % 360.0 - 180.0
    a = np.radians(np.sin(np.radians(latin1)) * d)
    c, s = np.cos(a), np.sin(a)
    return c * u + s * v, -s * u + c * v


def crop_window(lat: np.ndarray, lon: np.ndarray, box=BOX) -> tuple[slice, slice]:
    """Row / column slices of the smallest index window holding every point in ``box``."""
    n, w, s, e = box
    lon = np.where(lon > 180, lon - 360, lon)
    inside = (lat >= s) & (lat <= n) & (lon >= w) & (lon <= e)
    r, c = np.where(inside)
    return slice(r.min(), r.max() + 1), slice(c.min(), c.max() + 1)


def decode(raw: bytes) -> dict:
    """The two messages in ``raw``, cropped to ``BOX`` (a full CONUS hour with its lat / lon
    is ~60 MB; a storm window holds ~530 of them): earth-relative ``u`` / ``v``, ``lat`` /
    ``lon`` (-180..180), the grid keys and the crop."""
    import eccodes

    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(raw)
        path = f.name
    out = {}
    try:
        with open(path, "rb") as fh:
            while (h := eccodes.codes_grib_new_from_file(fh)) is not None:
                try:
                    ni, nj = eccodes.codes_get(h, "Nx"), eccodes.codes_get(h, "Ny")
                    name = eccodes.codes_get(h, "shortName")  # 10u / 10v
                    out[name] = eccodes.codes_get_values(h).reshape(nj, ni)
                    if "grid" not in out:
                        out["grid"] = {k: eccodes.codes_get(h, k) for k in (
                            "LoVInDegrees", "Latin1InDegrees", "Latin2InDegrees", "DxInMetres",
                            "uvRelativeToGrid", "latitudeOfFirstGridPointInDegrees",
                            "longitudeOfFirstGridPointInDegrees")}  # fmt: skip
                        out["lat"] = eccodes.codes_get_array(h, "latitudes").reshape(nj, ni)
                        out["lon"] = eccodes.codes_get_array(h, "longitudes").reshape(nj, ni)
                finally:
                    eccodes.codes_release(h)
    finally:
        os.unlink(path)
    if set(out) < {"10u", "10v"}:
        raise ValueError(f"expected 10u and 10v, got {sorted(out)}")
    g = out["grid"]
    if g["uvRelativeToGrid"] != 1:
        raise RuntimeError(f"expected grid-relative winds, got {g}")
    rs, cs = crop_window(out["lat"], out["lon"])
    lon = out["lon"][rs, cs]
    lon = np.where(lon > 180, lon - 360, lon)
    u, v = earth_relative(out["10u"][rs, cs], out["10v"][rs, cs], lon, g["LoVInDegrees"], g["Latin1InDegrees"])
    return {"u": u.astype("f4"), "v": v.astype("f4"), "lat": out["lat"][rs, cs], "lon": lon,
            "grid": g, "crop": (rs.start, rs.stop, cs.start, cs.stop)}


def fetch_hour(t: pd.Timestamp) -> tuple[dict | None, str]:
    """The decoded fields valid at ``t``: the t analysis, else the t-1 h cycle's f01."""
    for cycle, fh, tag in ((t, 0, "f00"), (t - pd.Timedelta("1h"), 1, "f01")):
        url = AWS.format(c=cycle, f=fh)
        try:
            a, b = byte_range(_get(url + ".idx").decode())
            raw = _get(url, {"Range": f"bytes={a}-{'' if b is None else b}"})
            return decode(raw), tag
        except (FileNotFoundError, ValueError):
            continue
    return None, "missing"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", required=True, help="first valid time, UTC")
    ap.add_argument("--end", required=True, help="last valid time, UTC")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    times = pd.date_range(a.start, a.end, freq="h")
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} exists")
    out.parent.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(a.workers) as ex:
        got = list(ex.map(fetch_hour, times))
    first = next(g for g, _ in got if g is not None)
    grid, lat, lon = first["grid"], first["lat"], first["lon"]
    u = np.full((len(times),) + lat.shape, np.nan, "f4")
    v = np.full_like(u, np.nan)
    for k, (g, _) in enumerate(got):
        if g is None:
            continue
        if g["grid"] != grid or g["crop"] != first["crop"]:
            raise RuntimeError(f"HRRR grid changed at {times[k]}")
        u[k], v[k] = g["u"], g["v"]
    r0, r1, c0, c1 = first["crop"]
    tags = pd.Series([t for _, t in got]).value_counts().to_dict()
    ds = xr.Dataset(
        {"u10": (("time", "y", "x"), u, {"units": "m s-1", "long_name": "10 m eastward wind (earth-relative)"}),
         "v10": (("time", "y", "x"), v, {"units": "m s-1", "long_name": "10 m northward wind (earth-relative)"})},
        coords={"time": times, "latitude": (("y", "x"), lat), "longitude": (("y", "x"), lon)},
        attrs={"title": "HRRR 10 m wind, earth-relative, clipped to the bay",
               "source": "NOAA HRRR, AWS noaa-hrrr-bdp-pds, wrfsfcf00 (f01 of the previous cycle if missing)",
               "source_example": AWS.format(c=times[0], f=0),
               "hours": str(tags), "missing_hours": int(tags.get("missing", 0)),
               "LoV": float(grid["LoVInDegrees"]), "Latin1": float(grid["Latin1InDegrees"]),
               "Latin2": float(grid["Latin2InDegrees"]), "Dx": float(grid["DxInMetres"]),
               "crop_rows": f"{r0}:{r1}", "crop_cols": f"{c0}:{c1}",
               "box_NWSE": str(BOX)},
    )  # fmt: skip
    enc = {k: {"zlib": True, "complevel": 4} for k in ("u10", "v10")}
    tmp = out.with_suffix(".nc.part")
    ds.to_netcdf(tmp, encoding=enc)
    tmp.replace(out)
    print(f"wrote {out}: {u.shape}, hours {tags}")


if __name__ == "__main__":
    main()
