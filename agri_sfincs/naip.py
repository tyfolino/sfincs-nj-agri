"""NAIP aerial imagery from Microsoft Planetary Computer: find the image of a year over a
point (STAC search) and cut an RGB chip from it (signed URL, read over /vsicurl/). Used by the
imagery / LU/LC / exit spot-checks (scripts/*_spotcheck.py)."""

from __future__ import annotations

import json
import os
import urllib.request

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/naip"

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")


def http_json(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})  # fmt: skip
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def naip_item(lon, lat, year) -> str | None:
    """HREF of the NAIP image covering (lon, lat) flown in ``year`` (None if none)."""
    d = http_json(STAC, {"collections": ["naip"], "limit": 50,
                         "intersects": {"type": "Point", "coordinates": [lon, lat]},
                         "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z"})  # fmt: skip
    f = d.get("features", [])
    return f[0]["assets"]["image"]["href"] if f else None


def chip(href, token, lon, lat, half=120, res=1.0) -> np.ndarray:
    """RGB at ``res`` m, a 2*``half`` m square centred on (lon, lat), in UTM 18N."""
    utm = "EPSG:26918"
    x, y = Transformer.from_crs(4326, utm, always_xy=True).transform(lon, lat)
    n = int(2 * half / res)
    tr = rasterio.transform.from_origin(x - half, y + half, res, res)
    with rasterio.open(f"/vsicurl/{href}?{token}") as s, \
            WarpedVRT(s, crs=utm, transform=tr, width=n, height=n,
                      resampling=Resampling.bilinear) as v:  # fmt: skip
        return np.moveaxis(v.read([1, 2, 3]), 0, -1)
