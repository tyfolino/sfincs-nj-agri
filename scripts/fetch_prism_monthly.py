"""PRISM monthly precipitation, averaged over each Fork 1 county's cropland.

Source: PRISM Climate Group (Oregon State), the AN81 monthly time series at 4 km
(2.5 arc-minute, NAD83, mm). PRISM retired its old FTP layout and BIL files in 2025;
the current archive is plain HTTPS, one zip per month holding a GeoTIFF:
  https://data.prism.oregonstate.edu/time_series/us/an/4km/ppt/monthly/<YYYY>/prism_ppt_us_25m_<YYYYMM>.zip
(the web service equivalent is https://services.nacse.org/prism/data/get/us/4km/ppt/<YYYYMM>,
which is rate-limited per file and IP, so the archive is used). The zip's .info.txt
gives the dataset type (``an81``...) and creation date. Recent months are provisional
and get re-modelled; re-fetch them with ``--refresh-from``.

County mean over cropland: one static mask, the 2023 CDL (NJ: data/cdl/CDL_2023_34.tif;
other states: data/floodplain/cdl/, scripts/fetch_cdl.py --fips), cropland =
``agri_sfincs.cdl.CROPLAND``. Each 30 m cropland pixel inside a county
(data/fork1/counties.gpkg, scripts/fork1_counties.py) is assigned its PRISM cell
(nearest-neighbour warp of a cell-index grid); a county's monthly value is the
cropland-pixel-weighted mean of its PRISM cells (``agri_sfincs.panel.weighted_county_mean``).
Counties with no CDL cropland fall back to all their pixels (flagged ``weights =
"all land"``).

Writes:
  data/prism/prism_ppt_us_25m_<YYYYMM>.zip      (bulk, scratch)
  data/fork1/prism_weights.csv                  fips, cell, n_px, weights
  data/fork1/prism_county_monthly.csv           fips, year, month, ppt_mm, prism_type

Usage:  python scripts/fetch_prism_monthly.py [--years 2001-2025] [--cdl-year 2023]
                                               [--refresh-from 202501] [--download-only]
"""

from __future__ import annotations

import argparse
import re
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from fetch_cdl import cdl_path
from fetch_rma_col import parse_years
from rasterio import features, warp

from agri_sfincs import cdl, config
from agri_sfincs.net import download
from agri_sfincs.panel import weighted_county_mean

BASE = "https://data.prism.oregonstate.edu/time_series/us/an/4km/ppt/monthly/"
COUNTIES = config.FORK1_DIR / "counties.gpkg"
WEIGHTS = config.FORK1_DIR / "prism_weights.csv"
OUT = config.FORK1_DIR / "prism_county_monthly.csv"


def zip_path(yyyymm: str):
    return config.PRISM_DIR / f"prism_ppt_us_25m_{yyyymm}.zip"


def fetch_month(yyyymm: str, refresh: bool) -> str:
    dest = zip_path(yyyymm)
    if dest.exists() and not refresh:
        return f"{yyyymm}: have"
    download(f"{BASE}{yyyymm[:4]}/{dest.name}", dest)
    with zipfile.ZipFile(dest) as z:  # prove it is a PRISM zip, not an HTML error page
        z.getinfo(dest.name.replace(".zip", ".tif"))
    return f"{yyyymm}: fetched"


def prism_type(yyyymm: str) -> str:
    with zipfile.ZipFile(zip_path(yyyymm)) as z:
        info = z.read(zip_path(yyyymm).name.replace(".zip", ".info.txt")).decode("latin-1")
    m = re.search(r"PRISM_DATASET_TYPE:\s*(\S+)", info)
    return m.group(1) if m else ""


def prism_tif(yyyymm: str) -> str:
    z = zip_path(yyyymm)
    return f"/vsizip/{z}/{z.name.replace('.zip', '.tif')}"


def build_weights(counties: gpd.GeoDataFrame, grid_src: str, cdl_year: int) -> pd.DataFrame:
    """fips x PRISM cell (flat index into the full PRISM grid) -> number of 30 m CDL
    cropland pixels."""
    with rasterio.open(grid_src) as g:
        g_shape, g_tf, g_crs = g.shape, g.transform, g.crs
    cell_index = np.arange(g_shape[0] * g_shape[1], dtype=np.int32).reshape(g_shape)
    crop_codes = np.array(sorted(cdl.CROPLAND), dtype=np.uint8)
    out = []
    for st, cs in counties.groupby("state"):
        path = cdl_path(cdl_year, st)
        if not path.exists():
            raise SystemExit(f"missing {path} — run scripts/fetch_cdl.py --years {cdl_year} --fips {st}")
        with rasterio.open(path) as src:
            land = src.read(1)
            tf, crs, shape = src.transform, src.crs, src.shape
        cs = cs.to_crs(crs)
        cid = features.rasterize(((geom, i + 1) for i, geom in enumerate(cs.geometry)),
                                 out_shape=shape, transform=tf, fill=0, dtype="int32")  # fmt: skip
        cell = np.full(shape, -1, dtype=np.int32)
        warp.reproject(cell_index, cell, src_transform=g_tf, src_crs=g_crs, dst_transform=tf,
                       dst_crs=crs, resampling=warp.Resampling.nearest, src_nodata=-1,
                       dst_nodata=-1)  # fmt: skip
        crop = np.isin(land, crop_codes)
        for label, mask in (("cropland", crop), ("all land", (land > 0) & (land != 111))):
            ok = mask & (cid > 0) & (cell >= 0)
            t = pd.DataFrame({"c": cid[ok], "cell": cell[ok]}).value_counts().rename("n_px")
            t = t.reset_index()
            t["fips"] = cs.fips.to_numpy()[t.c - 1]
            t["weights"] = label
            out.append(t.drop(columns="c"))
        print(f"  weights {st}: {crop.sum():,} cropland px", flush=True)
    w = pd.concat(out, ignore_index=True)
    has_crop = set(w.fips[w.weights == "cropland"])
    w = w[(w.weights == "cropland") | ~w.fips.isin(has_crop)]
    return w[["fips", "cell", "n_px", "weights"]].sort_values(["fips", "cell"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", default="2001-2025")
    ap.add_argument("--cdl-year", type=int, default=2023)
    ap.add_argument("--refresh-from", help="YYYYMM: re-fetch this month and later")
    ap.add_argument("--download-only", action="store_true")
    a = ap.parse_args()
    config.PRISM_DIR.mkdir(parents=True, exist_ok=True)
    months = [f"{y}{m:02d}" for y in parse_years(a.years) for m in range(1, 13)]
    failed = []
    for ym in months:
        try:
            msg = fetch_month(ym, bool(a.refresh_from) and ym >= a.refresh_from)
            if "fetched" in msg:
                print(msg, flush=True)
        except (OSError, KeyError, zipfile.BadZipFile) as e:
            print(f"{ym}: FAILED {type(e).__name__}: {e}", flush=True)
            failed.append(ym)
    if failed:
        raise SystemExit(f"failed months: {failed} — rerun; finished months are skipped")
    if a.download_only:
        return

    counties = gpd.read_file(COUNTIES)
    if WEIGHTS.exists():
        w = pd.read_csv(WEIGHTS, dtype={"fips": str})
    else:
        w = build_weights(counties, prism_tif(months[0]), a.cdl_year)
        w.to_csv(WEIGHTS, index=False)
        print(f"wrote {WEIGHTS} ({w.fips.nunique()} counties, {len(w):,} rows)")
    rows = []
    for ym in months:
        with rasterio.open(prism_tif(ym)) as src:
            v = src.read(1).ravel()
            nod = src.nodata
        val = v[w.cell.to_numpy()].astype(float)
        val[val == nod] = np.nan
        m = weighted_county_mean(w.fips.to_numpy(), w.n_px.to_numpy(float), val)
        t = prism_type(ym)
        rows += [(f, int(ym[:4]), int(ym[4:]), p, t) for f, p in m.items()]
    out = pd.DataFrame(rows, columns=["fips", "year", "month", "ppt_mm", "prism_type"])
    miss = set(counties.fips) - set(out.fips)
    if miss:
        print(f"WARNING: no PRISM value for {sorted(miss)}")
    out.to_csv(OUT, index=False, float_format="%.2f")
    print(f"wrote {OUT} ({out.fips.nunique()} counties x {len(months)} months)")


if __name__ == "__main__":
    main()
