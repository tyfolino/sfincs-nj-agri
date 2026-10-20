"""Read whole Landsat C2 L2 scenes of one day from Microsoft Planetary Computer onto a grid.

For single-scene checks (scripts/validate_storm_landsat.py). The 40-year per-field pipeline,
scripts/landsat_field_stats.py, keeps its own threaded copy of the search and token code.

* ``items_on(day, bbox_ll)``: every ``landsat-c2-l2`` item acquired that UTC day over the box.
* ``mosaic(items, bands, tr, shape, crs)``: each band read through a WarpedVRT onto the grid
  (nearest), items in the order given; a pixel keeps the first item with a valid QA there.
"""

from __future__ import annotations

import json
import os
import urllib.request

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/landsat-c2-l2"

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "3")


def _json(url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})  # fmt: skip
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def items_on(day: str, bbox_ll) -> list[dict]:
    """Items acquired on ``day`` (YYYY-MM-DD, UTC) intersecting ``bbox_ll`` (lon/lat), least
    cloudy first."""
    body = {"collections": ["landsat-c2-l2"], "bbox": list(bbox_ll), "limit": 100,
            "datetime": f"{day}T00:00:00Z/{day}T23:59:59Z"}  # fmt: skip
    feats = _json(STAC, body)["features"]
    return sorted(feats, key=lambda f: f["properties"].get("eo:cloud_cover", 100))


def mosaic(items: list[dict], bands: list[str], tr, shape: tuple[int, int], crs: str) -> dict[str, np.ndarray]:
    """{band: uint16 array on the grid} with "qa_pixel" always included; 0 = no data."""
    tok = _json(SAS)["token"]
    bands = list(dict.fromkeys([*bands, "qa_pixel"]))
    out = {b: np.zeros(shape, "uint16") for b in bands}
    for it in items:
        arr = {}
        for b in bands:
            with rasterio.open(f"/vsicurl/{it['assets'][b]['href']}?{tok}") as s, \
                    WarpedVRT(s, crs=crs, transform=tr, width=shape[1], height=shape[0],
                              resampling=Resampling.nearest, src_nodata=s.nodata if s.nodata is not None else 0,
                              nodata=0) as v:  # fmt: skip
                arr[b] = v.read(1)
        qa = arr["qa_pixel"]
        take = (out["qa_pixel"] == 0) & (qa != 0) & ((qa & 1) == 0)
        for b in bands:
            out[b][take] = arr[b][take]
    return out
