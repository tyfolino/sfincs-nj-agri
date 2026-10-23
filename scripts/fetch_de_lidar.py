"""Delaware's statewide lidar DEM (USGS 3DEP 1 m, project DE_Statewide_B23, hydro-flattened,
NAVD88) on the NJ lidar's grid spacing, over the DE model outline + 1 km: the DE side's tier 1
in scripts/build_bed.py (the counterpart of the NJ 10 ft lidar).

Why not CUDEM: CUDEM holds inland lakes as flat ~0 m "beds" (bight FINDINGS §54a; Silver Lake,
Killen Pond, Noxontown Pond are all in this domain). The lidar carries their water surface.

The 1 m tiles are COGs with overviews (2, 4, 8 ... m), so they are not downloaded: gdalwarp
reads the overview nearest the target spacing over HTTP (/vsicurl), average resampling, onto
EPSG:4326 at the NJ lidar's 3.505e-5 deg (~3.9 m x 3.0 m). Tiles are listed by the TNM API
(products over the outline's bbox, title containing ``PROJECT``).

Writes config.DATA_BULK/elevation/de_lidar_b23.tif (float32, m NAVD88, nodata -9999, tiled,
deflate) + the tile list de_lidar_b23_tiles.txt beside it, and the catalog line to add.
Usage:  python scripts/fetch_de_lidar.py [--overwrite]
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
from pathlib import Path

import pyproj
import rasterio

from agri_sfincs import config, domain, region
from agri_sfincs.net import get

TNM = "https://tnmaccess.nationalmap.gov/api/v1/products"
DATASET = "Digital Elevation Model (DEM) 1 meter"
PROJECT = "DE_Statewide_B23"
NJ_LIDAR = config.BIGHT_DATA / "elevation_v4/nj_10ft_dem_v4.tif"  # its lattice is copied
PAD_M = 1000.0
OUT = config.DATA_BULK / "elevation" / "de_lidar_b23.tif"
BIN = Path(sys.executable).parent  # the env's gdalbuildvrt / gdalwarp (batch jobs have no env PATH)


def tiles(bbox) -> list[str]:
    j = get(TNM, {"datasets": DATASET, "bbox": ",".join(f"{v:.4f}" for v in bbox), "max": 1000,
                  "outputFormat": "JSON"}, timeout=300).json()  # fmt: skip
    urls = sorted({i["downloadURL"] for i in j.get("items", []) if PROJECT in i.get("title", "")})
    if not urls:
        raise RuntimeError(f"TNM listed no {PROJECT} tiles over {bbox}")
    return urls


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    if OUT.exists() and not a.overwrite:
        raise SystemExit(f"{OUT} exists; pass --overwrite")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    outline = region.load_outline("de").to_crs(domain.EPSG).buffer(PAD_M).to_crs(4326)
    w, s, e, n = outline.total_bounds
    urls = tiles((w, s, e, n))
    lst = OUT.with_name("de_lidar_b23_tiles.txt")
    lst.write_text("\n".join(f"/vsicurl/{u}" for u in urls) + "\n")
    print(f"{len(urls)} {PROJECT} tiles over {w:.3f},{s:.3f},{e:.3f},{n:.3f}")
    vrt = OUT.with_suffix(".src.vrt")
    env = dict(os.environ, PROJ_DATA=pyproj.datadir.get_data_dir(), GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
               CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MAX_RETRY="8", GDAL_HTTP_RETRY_DELAY="5",
               GDAL_CACHEMAX="1024")  # fmt: skip
    subprocess.run([str(BIN / "gdalbuildvrt"), "-overwrite", "-input_file_list", str(lst), str(vrt)], check=True, env=env)
    # snap the target box to the NJ lidar's lattice so the two beds share pixel edges
    with rasterio.open(NJ_LIDAR) as nj:
        res, c0, f0 = nj.transform.a, nj.transform.c, nj.transform.f
    x0, x1 = c0 + res * math.floor((w - c0) / res), c0 + res * math.ceil((e - c0) / res)
    y1, y0 = f0 - res * math.floor((f0 - n) / res), f0 - res * math.ceil((f0 - s) / res)
    subprocess.run([str(BIN / "gdalwarp"), "-overwrite", "-t_srs", "EPSG:4326", "-tr", repr(res), repr(res),
                    "-te", repr(x0), repr(y0), repr(x1), repr(y1), "-r", "average",
                    "-dstnodata", "-9999", "-ot", "Float32", "-multi", "-wo", "NUM_THREADS=4",
                    "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=3", "-co", "BIGTIFF=YES",
                    str(vrt), str(OUT)], check=True, env=env)  # fmt: skip
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
