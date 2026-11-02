"""Read Sentinel-2 L2A scenes of one day from Microsoft Planetary Computer onto a grid, for
single-scene water checks (scripts/validate_storm_landsat.py). Same shape as landsat_stac.

``water`` returns (clear, mndwi) from green (B03, 10 m) and SWIR (B11, 20 m), read nearest on the
caller's grid. Clear = the scene classification (SCL) is none of NO_CLEAR.
"""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from agri_sfincs.landsat_stac import STAC, _json

SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
#: No data, saturated, cloud shadow, cloud medium / high, cirrus, snow. Dark pixels (2) stay: water
#: is often classed so.
NO_CLEAR = (0, 1, 3, 8, 9, 10, 11)
#: From processing baseline 04.00 (January 2022) L2A digital numbers carry this offset.
OFFSET_FROM, DN_OFFSET = 4.0, 1000.0


def items_on(day: str, bbox_ll) -> list[dict]:
    """Items acquired on ``day`` (YYYY-MM-DD, UTC) over ``bbox_ll``, least cloudy first."""
    body = {"collections": ["sentinel-2-l2a"], "bbox": list(bbox_ll), "limit": 100,
            "datetime": f"{day}T00:00:00Z/{day}T23:59:59Z"}  # fmt: skip
    feats = _json(STAC, body)["features"]
    return sorted(feats, key=lambda f: f["properties"].get("eo:cloud_cover", 100))


def reflectance(dn: np.ndarray, baseline: float) -> np.ndarray:
    """Surface reflectance; NaN where the digital number is 0 (no data)."""
    off = DN_OFFSET if baseline >= OFFSET_FROM else 0.0
    dn = np.asarray(dn, "float32")
    return np.where(dn > 0, (dn - off) / 10000.0, np.nan).astype("float32")


def clear(scl: np.ndarray) -> np.ndarray:
    return ~np.isin(scl, NO_CLEAR)


def water(items: list[dict], tr, shape: tuple[int, int], crs: str) -> tuple[np.ndarray, np.ndarray]:
    """(clear, mndwi) on the grid; a pixel keeps the first item that sees it clear."""
    tok = _json(SAS)["token"]
    ok = np.zeros(shape, bool)
    out = np.full(shape, np.nan, "float32")
    for it in items:
        arr = {}
        for b in ("B03", "B11", "SCL"):
            with rasterio.open(f"/vsicurl/{it['assets'][b]['href']}?{tok}") as s, \
                    WarpedVRT(s, crs=crs, transform=tr, width=shape[1], height=shape[0],
                              resampling=Resampling.nearest, src_nodata=0, nodata=0) as v:  # fmt: skip
                arr[b] = v.read(1)
        base = float(it["properties"]["s2:processing_baseline"])
        g, s_ = reflectance(arr["B03"], base), reflectance(arr["B11"], base)
        with np.errstate(divide="ignore", invalid="ignore"):
            m = (g - s_) / (g + s_)
        take = ~ok & clear(arr["SCL"]) & np.isfinite(m)
        out[take], ok[take] = m[take], True
    return ok, out
