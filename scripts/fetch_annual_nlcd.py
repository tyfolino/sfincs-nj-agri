"""Annual NLCD land cover per year, clipped to a side's ring (agri_sfincs.annual_nlcd), from MRLC's
WMS, in the product's own 30 m grid. Prints the agreement with NLCD 2021 (scripts/fetch_nlcd.py) as a
check that the colours decode to the right classes.

Annual NLCD as single files stayed closed (FINDINGS §4); this WMS was found 2026-11-02.

Writes data/landcover/annual/annual_nlcd_<year>[_de].tif (uint8 classes, 0 = no data, EPSG:5070).
Existing files are skipped.

Usage:  python scripts/fetch_annual_nlcd.py [--side de] [--years 2008 2025]
"""

from __future__ import annotations

import argparse
import io
import time

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from agri_sfincs import annual_nlcd, config, domain, net, region

WMS = "https://dmsdata.cr.usgs.gov/geoserver/mrlc_Land-Cover-Native_conus_year_data/wms"
LAYER = "Land-Cover-Native_conus_year_data"
X0, Y0 = -2415585, 3314805  # a corner of the product's grid
PAD_M = 1000.0
TRIES = 5


def window(side: str) -> tuple[int, int, int, int]:
    """(west, south, east, north), the ring + PAD_M, snapped outward to the product's grid."""
    w, s, e, n = region.load_ring(side).to_crs(domain.EPSG).buffer(PAD_M).to_crs(5070).total_bounds
    return (X0 + 30 * int(np.floor((w - X0) / 30)), Y0 + 30 * int(np.floor((s - Y0) / 30)),
            X0 + 30 * int(np.ceil((e - X0) / 30)), Y0 + 30 * int(np.ceil((n - Y0) / 30)))  # fmt: skip


def fetch(year: int, side: str) -> None:
    out = annual_nlcd.path(year, side)
    if out.exists():
        return
    w, s, e, n = window(side)
    nx, ny = (e - w) // 30, (n - s) // 30
    params = {"service": "WMS", "version": "1.1.1", "request": "GetMap", "layers": LAYER, "styles": "",
              "srs": "EPSG:5070", "bbox": f"{w},{s},{e},{n}", "width": nx, "height": ny,
              "format": "image/geotiff", "time": f"{year}-01-01T00:00:00.000Z"}  # fmt: skip
    for attempt in range(TRIES):  # the service sometimes answers 200 with an error page
        r = net.get(WMS, params=params, timeout=600)
        if r.content[:2] in (b"II", b"MM"):
            break
        print(f"  {year} {side}: not a tiff, try {attempt + 1}: {r.content[:200]!r}", flush=True)
        time.sleep(60)
    else:
        raise RuntimeError(f"{year} {side}: no tiff after {TRIES} tries")
    with rasterio.open(io.BytesIO(r.content)) as src:
        rgb = src.read()
    cls = annual_nlcd.decode(rgb[:3])
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", driver="GTiff", width=nx, height=ny, count=1, dtype="uint8", crs="EPSG:5070",
                       transform=from_origin(w, n, 30, 30), nodata=0, compress="deflate", predictor=2) as dst:  # fmt: skip
        dst.write(cls, 1)
    print(f"{out.name}: {nx}x{ny}, decoded {100 * (cls > 0).mean():.1f}%", flush=True)


def check(side: str) -> None:
    """Share of pixels equal to NLCD 2021, and the 81 / 82 confusion, on the shared grid."""
    with rasterio.open(annual_nlcd.path(2021, side)) as a:
        x, tr, crs = a.read(1), a.transform, a.crs
    y = np.zeros_like(x)
    with rasterio.open(config.LANDCOVER_DIR / f"nlcd_2021{domain.side(side).files}.tif") as b:
        reproject(rasterio.band(b, 1), y, dst_transform=tr, dst_crs=crs, resampling=Resampling.nearest)
    ok = (x > 0) & (y > 0)
    print(f"{side} 2021: {100 * (x[ok] == y[ok]).mean():.1f}% of {ok.sum():,} pixels equal to NLCD 2021; "
          f"class 82 equal {100 * (x[ok & (y == 82)] == 82).mean():.1f}%")  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--side", default="nj", choices=list(domain.SIDES))
    ap.add_argument("--years", nargs=2, type=int, default=[2008, 2025])
    a = ap.parse_args()
    for y in range(a.years[0], a.years[1] + 1):
        fetch(y, a.side)
    check(a.side)


if __name__ == "__main__":
    main()
