"""MRMS hourly gauge-corrected QPE over the model, clipped and stacked into one NetCDF.

⚠️ Runs in the SEPARATE grib env, not the shared sfincs env (which has no GRIB driver
and must not be installed into):

    /cache/home/tpj8/agri-micromamba/envs/grib/bin/python scripts/fetch_mrms.py \
        --start 2023-08-15T01 --end 2023-10-01T00 --out data/precip/mrms_2023-09.nc

so it imports nothing from ``agri_sfincs``.

Products (by the hour's date):
  >= 2020-10-14  AWS noaa-mrms-pds  CONUS/MultiSensor_QPE_01H_Pass2_00.00   (Pass 2:
                 the gauge-corrected, ~1 h latency product)
  <  2020-10-14  Iowa State mtarchive  mrms/ncep/GaugeCorr_QPE_01H  (mid-2015 on)

Each file is one hour's accumulation (mm) ENDING at its timestamp, on the 0.01 deg
MRMS grid. Negative values are MRMS "no coverage" flags (-3) and become NaN.

Output (``--out``): precip(time, lat, lon) float32 mm accumulated over the hour ENDING
at ``time`` (UTC); attrs record product, source URLs and the NaN count. ``tests/``
check that ``BBOX`` covers the model outline.

Usage: see above; ``--workers`` parallel downloads (default 8).
"""

from __future__ import annotations

import argparse
import gzip
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xarray as xr

#: Model outline + 5 km, lon/lat (agri_sfincs.region.load_outline, 2026-10-02),
#: rounded outward to the 0.01 deg MRMS grid.
# w, s, e, n. = agri_sfincs.domain.RAIN_BBOX: this script runs in the grib env, which cannot
# import the package (no pyproj); tests/test_rain_metrics.py checks the two agree.
BBOX = (-75.64, 38.98, -74.80, 39.94)
PASS2_START = pd.Timestamp("2020-10-14T00")
AWS = (
    "https://noaa-mrms-pds.s3.amazonaws.com/CONUS/MultiSensor_QPE_01H_Pass2_00.00/"
    "{t:%Y%m%d}/MRMS_MultiSensor_QPE_01H_Pass2_00.00_{t:%Y%m%d-%H}0000.grib2.gz"
)
IASTATE = (
    "https://mtarchive.geol.iastate.edu/{t:%Y/%m/%d}/mrms/ncep/GaugeCorr_QPE_01H/"
    "GaugeCorr_QPE_01H_00.00_{t:%Y%m%d-%H}0000.grib2.gz"
)

_session = requests.Session()
_session.headers["User-Agent"] = "sfincs-nj-agri (research; Rutgers ag flood-loss study)"


def url_for(t: pd.Timestamp) -> str:
    return (AWS if t >= PASS2_START else IASTATE).format(t=t)


def _get(url: str, retries: int = 5) -> bytes:
    delay = 5.0
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, timeout=120)
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                raise FileNotFoundError(url)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"giving up on {url}")


def read_hour(t: pd.Timestamp) -> np.ndarray:
    """One hour's field clipped to BBOX, (lat descending, lon ascending)."""
    raw = gzip.decompress(_get(url_for(t)))
    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(raw)
        path = f.name
    try:
        ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
        da = ds[next(iter(ds.data_vars))]
        lon = da.longitude.values
        lon = np.where(lon > 180, lon - 360, lon)
        da = da.assign_coords(longitude=lon)
        w, s, e, n = BBOX
        sub = da.sel(latitude=slice(n + 1e-6, s - 1e-6), longitude=slice(w - 1e-6, e + 1e-6))
        out = sub.values.astype("float32")
        grid = (sub.latitude.values, sub.longitude.values)
        ds.close()
    finally:
        os.unlink(path)
    out[out < 0] = np.nan
    return out, grid


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", required=True, help="first hour-ending time, UTC")
    ap.add_argument("--end", required=True, help="last hour-ending time, UTC")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    times = pd.date_range(a.start, a.end, freq="h")
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} exists")
    out.parent.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(read_hour, times))
    grids = {(g[0].tobytes(), g[1].tobytes()) for _, g in results}
    if len(grids) != 1:
        raise RuntimeError("MRMS grid changed inside the window")
    lat, lon = results[0][1]
    arr = np.stack([r[0] for r in results])
    da = xr.DataArray(
        arr, dims=("time", "lat", "lon"),
        coords={"time": times, "lat": lat, "lon": lon}, name="precip",
        attrs={"units": "mm", "long_name": "1-h accumulation ending at time (UTC)"},
    )  # fmt: skip
    products = sorted({"Pass2 (AWS)" if t >= PASS2_START else "GaugeCorr (IAState)"
                       for t in times})  # fmt: skip
    ds = da.to_dataset()
    ds.attrs = {
        "title": "MRMS hourly gauge-corrected QPE, clipped to the agri model",
        "products": ", ".join(products),
        "source_example": url_for(times[0]),
        "nan_cells": int(np.isnan(arr).sum()),
        "bbox_wsen": str(BBOX),
    }
    ds.to_netcdf(out, encoding={"precip": {"zlib": True, "complevel": 4}})
    basin_mean = np.nanmean(arr, axis=(1, 2))
    print(f"wrote {out}: {arr.shape} {products}; NaN cells {ds.attrs['nan_cells']}; "
          f"bbox-mean total {basin_mean.sum():.0f} mm, max hour {np.nanmax(arr):.1f} mm")  # fmt: skip


if __name__ == "__main__":
    main()
