"""Annual NLCD land cover (USGS / MRLC, Collection 1, 30 m, CONUS, 1985 on), a second reading of
which fields are farmed: one product over all years, so it has neither CDL's 2024 change nor its
2011 spike. It reads agriculture as 81 (pasture / hay) + 82 (cultivated crops), without crop type.

The WMS serves the classes as colours, so ``decode`` maps them back (scripts/fetch_annual_nlcd.py
writes the classes). ``field_shares`` is per field x year, pixel centre in polygon as CDL.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from agri_sfincs import cdl, config, domain

#: Class -> colour of the WMS's default style.
PALETTE = {11: (70, 107, 159), 12: (209, 222, 248), 21: (222, 197, 197), 22: (217, 146, 130), 23: (235, 0, 0),
           24: (171, 0, 0), 31: (179, 172, 159), 41: (104, 171, 95), 42: (28, 95, 44), 43: (181, 197, 143),
           52: (204, 184, 121), 71: (223, 223, 194), 81: (220, 217, 57), 82: (171, 108, 40), 90: (184, 217, 235),
           95: (108, 159, 184)}  # fmt: skip
AG = (81, 82)
#: A field needs this many 30 m pixels: below it one pixel moves the share past the 50% line.
MIN_PX = 5


def _key(r, g, b):
    return (np.asarray(r, "int64") << 16) + (np.asarray(g, "int64") << 8) + np.asarray(b, "int64")


def decode(rgb: np.ndarray) -> np.ndarray:
    """(3, h, w) colours -> (h, w) classes, uint8; any other colour (outside the data) is 0."""
    keys = np.array(sorted(_key(*c) for c in PALETTE.values()))
    cls = {int(_key(*c)): k for k, c in PALETTE.items()}
    vals = np.array([cls[int(k)] for k in keys], "uint8")
    v = _key(rgb[0], rgb[1], rgb[2])
    i = np.searchsorted(keys, v).clip(0, len(keys) - 1)
    return np.where(keys[i] == v, vals[i], 0).astype("uint8")


def path(year: int, side: str = "nj") -> Path:
    return config.LANDCOVER_DIR / "annual" / f"annual_nlcd_{year}{domain.side(side).files}.tif"


def field_shares(g, years, side: str = "nj") -> pd.DataFrame:
    """field_id, year, nlcd_ag (share of the field's pixels in AG; NaN under MIN_PX pixels, or where
    every pixel is outside the data) for ``g.field_id`` polygons."""
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.open(path(max(years), side)) as src:
        gg = g.to_crs(src.crs)
        win = from_bounds(*gg.total_bounds, transform=src.transform).round_offsets().round_lengths()
        tr, shape = src.window_transform(win), (int(win.height), int(win.width))
    zone, flat, _ = cdl.polygon_pixels(gg.geometry, shape, tr)
    n, rows = len(g), []
    for y in years:
        with rasterio.open(path(y, side)) as src:
            c = src.read(1, window=win, boundless=True, fill_value=0).ravel()[flat]
        have = np.bincount(zone, weights=c > 0, minlength=n + 1)[1:]
        ag = np.bincount(zone, weights=np.isin(c, AG), minlength=n + 1)[1:]
        with np.errstate(invalid="ignore", divide="ignore"):
            share = np.where(have >= MIN_PX, ag / have, np.nan)
        rows.append(pd.DataFrame({"field_id": g.field_id.values, "year": y, "nlcd_ag": share}))
    return pd.concat(rows, ignore_index=True)
