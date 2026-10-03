"""Download the USDA Cropland Data Layer for New Jersey, one GeoTIFF per year.

Source: CropScape (nassgeodata.gmu.edu). Its bbox requests timed out on 2026-10-02,
but the state-by-FIPS request answers (slowly) with a link into a server-side cache,
so this asks for the state and clips later. Each file is NJ-wide, 30 m, EPSG:5070
(CONUS Albers), uint8 class codes; the class legend is CDL's standard one.

Alternatives if CropScape is down: Planetary Computer ``usda-cdl`` (COGs, but only
2008-2021 on 2026-10-02), or the NASS national zips (~2 GB per year).

Writes data/cdl/CDL_<year>_34.tif. Existing files are skipped.

Usage:  python scripts/fetch_cdl.py [--years 2008-2025]
"""

from __future__ import annotations

import argparse
import re

import rasterio

from agri_sfincs import config, domain
from agri_sfincs.net import download, get

SERVICE = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile"


def parse_years(s: str) -> list[int]:
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(y) for y in s.split(",")]


def fetch_year(year: int) -> str:
    dest = config.CDL_DIR / f"CDL_{year}_{domain.STATE_FIPS}.tif"
    if dest.exists():
        return f"{year}: have {dest.name}"
    r = get(SERVICE, {"year": year, "fips": domain.STATE_FIPS}, timeout=600)
    m = re.search(r"<returnURL>(.*?)</returnURL>", r.text)
    if not m:
        return f"{year}: NO FILE — service said {r.text[:200]!r}"
    download(m.group(1), dest, timeout=900)
    with rasterio.open(dest) as src:  # prove it is a readable raster, not an HTML error
        info = f"{src.width}x{src.height} {src.crs.to_epsg()} {src.res[0]:.0f} m"
    return f"{year}: wrote {dest.name} ({info})"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", default="2008-2025")
    a = ap.parse_args()
    config.CDL_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    for y in parse_years(a.years):
        try:
            print(fetch_year(y), flush=True)
        except (OSError, RuntimeError, rasterio.errors.RasterioError) as e:
            # requests' exceptions are OSErrors; keep going so one bad year
            # does not cost the rest, and say so at the end.
            print(f"{y}: FAILED {type(e).__name__}: {e}", flush=True)
            failed.append(y)
    if failed:
        raise SystemExit(f"failed years: {failed} — rerun; finished years are skipped")


if __name__ == "__main__":
    main()
