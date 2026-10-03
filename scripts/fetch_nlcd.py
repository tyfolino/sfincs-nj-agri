"""NLCD 2021 land cover (the last "classic" NLCD release, CONUS), clipped to the ring.

Source: MRLC's GeoServer WCS 2.0.1, coverage ``mrlc_download__NLCD_2021_Land_Cover_L48``,
asked for just the domain window in its native CONUS Albers (EPSG:5070) 30 m grid.

Why not Annual NLCD (checked 2026-10-02): the per-year COGs on the MRLC S3 bucket
answer 403 for 1985-2022 and 2024, and the 2023 object is a 42-byte placeholder TIFF;
the WCS offers only Annual-NLCD change summaries. One static land cover is all the
model needs (roughness and curve numbers); crop type by year comes from CDL.

Classes are the standard NLCD legend (11 water ... 95 emergent herbaceous wetlands),
which hydromt_sfincs' ``lulc/NLCD_HSG.csv`` (curve numbers) and bight's
``data/roughness/NLCD_CONUS_mapping.csv`` (Manning's n) are keyed on.

Writes data/landcover/nlcd_2021.tif (uint8, EPSG:5070, 30 m, ring bbox + 1 km).

Usage:  python scripts/fetch_nlcd.py [--overwrite]
"""

from __future__ import annotations

import argparse

import numpy as np
import rasterio

from agri_sfincs import config, domain, region
from agri_sfincs.net import download

WCS = "https://www.mrlc.gov/geoserver/ows"
COVERAGE = "mrlc_download__NLCD_2021_Land_Cover_L48"
PAD_M = 1000.0
OUT = config.DATA / "landcover" / "nlcd_2021.tif"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    if OUT.exists() and not a.overwrite:
        raise SystemExit(f"{OUT} exists; pass --overwrite")
    ring = region.load_ring()
    w, s, e, n = ring.to_crs(domain.EPSG).buffer(PAD_M).to_crs(5070).total_bounds
    # Snap outward to the NLCD 30 m grid (its origin is a multiple of 15 m off 0).
    w, s = np.floor(w / 30) * 30 - 15, np.floor(s / 30) * 30 - 15
    e, n = np.ceil(e / 30) * 30 + 15, np.ceil(n / 30) * 30 + 15
    url = (
        f"{WCS}?service=WCS&version=2.0.1&request=GetCoverage&coverageId={COVERAGE}"
        f"&format=image/geotiff&subset=X({w:.0f},{e:.0f})&subset=Y({s:.0f},{n:.0f})"
    )
    download(url, OUT, timeout=900)
    with rasterio.open(OUT) as src:
        arr = src.read(1)
        crs, res = src.crs, src.res
    if arr.size < 1000 or res != (30.0, 30.0):
        raise RuntimeError(f"unexpected NLCD response: shape {arr.shape}, res {res}")
    v, c = np.unique(arr, return_counts=True)
    print(f"wrote {OUT} {arr.shape[1]}x{arr.shape[0]} {crs} {res}")
    print("km2 by class:", dict(zip(v.tolist(), (c * 900 / 1e6).round(1).tolist())))


if __name__ == "__main__":
    main()
