"""USDA Cropland Data Layer legend: class code -> name, and which codes are cropland.

Codes follow the standard CDL legend (NASS). "Cropland" here = annual and perennial
crops, double crops, fallow/idle cropland, hay, sod and tree/berry crops — what crop
insurance can cover. Grass/Pasture (176) is kept SEPARATE: it is agricultural but
mostly uninsured row-crop-wise, and in NJ it is often lawn-like open land.

``GROUPS`` = the land-cover groups for per-field shares; ``polygon_pixels`` + ``zone_cover``
turn polygons and a CDL year into those shares (scripts/build_sandy_panel.py).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from agri_sfincs import config, domain

# fmt: off
NAMES = {
    0: "Background", 1: "Corn", 2: "Cotton", 3: "Rice", 4: "Sorghum", 5: "Soybeans",
    6: "Sunflower", 10: "Peanuts", 11: "Tobacco", 12: "Sweet Corn", 13: "Pop or Orn Corn",
    14: "Mint", 21: "Barley", 22: "Durum Wheat", 23: "Spring Wheat", 24: "Winter Wheat",
    25: "Other Small Grains", 26: "Dbl Crop WinWht/Soybeans", 27: "Rye", 28: "Oats",
    29: "Millet", 30: "Speltz", 31: "Canola", 32: "Flaxseed", 33: "Safflower",
    34: "Rape Seed", 35: "Mustard", 36: "Alfalfa", 37: "Other Hay/Non Alfalfa",
    38: "Camelina", 39: "Buckwheat", 41: "Sugarbeets", 42: "Dry Beans", 43: "Potatoes",
    44: "Other Crops", 45: "Sugarcane", 46: "Sweet Potatoes", 47: "Misc Vegs & Fruits",
    48: "Watermelons", 49: "Onions", 50: "Cucumbers", 51: "Chick Peas", 52: "Lentils",
    53: "Peas", 54: "Tomatoes", 55: "Caneberries", 56: "Hops", 57: "Herbs",
    58: "Clover/Wildflowers", 59: "Sod/Grass Seed", 60: "Switchgrass",
    61: "Fallow/Idle Cropland", 63: "Forest", 64: "Shrubland", 65: "Barren",
    66: "Cherries", 67: "Peaches", 68: "Apples", 69: "Grapes", 70: "Christmas Trees",
    71: "Other Tree Crops", 72: "Citrus", 74: "Pecans", 75: "Almonds", 76: "Walnuts",
    77: "Pears", 81: "Clouds/No Data", 82: "Developed", 83: "Water", 87: "Wetlands",
    88: "Nonag/Undefined", 92: "Aquaculture", 111: "Open Water",
    112: "Perennial Ice/Snow", 121: "Developed/Open Space",
    122: "Developed/Low Intensity", 123: "Developed/Med Intensity",
    124: "Developed/High Intensity", 131: "Barren", 141: "Deciduous Forest",
    142: "Evergreen Forest", 143: "Mixed Forest", 152: "Shrubland",
    176: "Grass/Pasture", 190: "Woody Wetlands", 195: "Herbaceous Wetlands",
    204: "Pistachios", 205: "Triticale", 206: "Carrots", 207: "Asparagus", 208: "Garlic",
    209: "Cantaloupes", 210: "Prunes", 211: "Olives", 212: "Oranges",
    213: "Honeydew Melons", 214: "Broccoli", 215: "Avocados", 216: "Peppers",
    217: "Pomegranates", 218: "Nectarines", 219: "Greens", 220: "Plums",
    221: "Strawberries", 222: "Squash", 223: "Apricots", 224: "Vetch",
    225: "Dbl Crop WinWht/Corn", 226: "Dbl Crop Oats/Corn", 227: "Lettuce",
    228: "Dbl Crop Triticale/Corn", 229: "Pumpkins", 230: "Dbl Crop Lettuce/Durum Wht",
    231: "Dbl Crop Lettuce/Cantaloupe", 232: "Dbl Crop Lettuce/Cotton",
    233: "Dbl Crop Lettuce/Barley", 234: "Dbl Crop Durum Wht/Sorghum",
    235: "Dbl Crop Barley/Sorghum", 236: "Dbl Crop WinWht/Sorghum",
    237: "Dbl Crop Barley/Corn", 238: "Dbl Crop WinWht/Cotton",
    239: "Dbl Crop Soybeans/Cotton", 240: "Dbl Crop Soybeans/Oats",
    241: "Dbl Crop Corn/Soybeans", 242: "Blueberries", 243: "Cabbage",
    244: "Cauliflower", 245: "Celery", 246: "Radishes", 247: "Turnips",
    248: "Eggplants", 249: "Gourds", 250: "Cranberries", 254: "Dbl Crop Barley/Soybeans",
}
# fmt: on

CROPLAND = frozenset(
    c for c in NAMES if 1 <= c <= 61 or 66 <= c <= 80 or 204 <= c <= 254
)
PASTURE = frozenset({176})
DOUBLE_CROPS = frozenset(c for c, n in NAMES.items() if n.startswith("Dbl Crop"))
#: Sorghum, barley, the wheats, other small grains, rye, oats, millet, speltz, triticale.
SMALL_GRAINS = frozenset({4, 21, 22, 23, 24, 25, 27, 28, 29, 30, 205})

#: Land-cover groups for per-field shares, in column order. The six crop groups split
#: CROPLAND exactly (other_crops = the rest of it); every code in no group is OTHER (barren,
#: aquaculture, background, ...). Pre-2010 legend codes (63/64 forest/shrub, 82 developed,
#: 83 water) sit with their modern twins; 87 (generic wetlands) has no twin and is OTHER.
_CROP_GROUPS = {
    "corn": frozenset({1, 12, 13}),
    "soybeans": frozenset({5}),
    "other_grains": SMALL_GRAINS | DOUBLE_CROPS,
    "hay": frozenset({36, 37}),
    "idle": frozenset({61}),
}
GROUPS = {
    **_CROP_GROUPS,
    "other_crops": CROPLAND - frozenset().union(*_CROP_GROUPS.values()),
    "pasture": PASTURE,
    "herb_wetland": frozenset({195}),
    "woody_wetland": frozenset({190}),
    "forest_shrub": frozenset({63, 64, 141, 142, 143, 152}),
    "developed": frozenset({82, 121, 122, 123, 124}),
    "water": frozenset({83, 111}),
}
OTHER = "other"


def name(code: int) -> str:
    return NAMES.get(int(code), f"class {int(code)}")


def path(year: int, fips: str = domain.STATE_FIPS) -> Path:
    """The CDL GeoTIFF of ``year``: NJ in data/cdl/; other states (Delaware, and Fork 1's) in
    data/floodplain/cdl/ (bulk, scratch; scripts/fetch_cdl.py --fips)."""
    d = config.CDL_DIR if fips == domain.STATE_FIPS else config.FLOODPLAIN_DIR / "cdl"
    return d / f"CDL_{year}_{fips}.tif"


def read(year: int, win, fips: str = domain.STATE_FIPS) -> np.ndarray:
    """The state's CDL ``year`` on the rasterio window ``win`` (every year shares one grid per
    state; checked for NJ and DE), 0 outside the raster."""
    import rasterio

    with rasterio.open(path(year, fips)) as c:
        return c.read(1, window=win, boundless=True, fill_value=0)


CROP_SHARES = [f"share_{k}" for k in ("corn", "soybeans", "other_grains", "hay", "idle", "other_crops")]


def field_years(g, years, fips: str = domain.STATE_FIPS) -> tuple[pd.DataFrame, pd.DataFrame, list[int]]:
    """CDL inside each field (``g.field_id``, polygons) for ``years``, pixel centre in polygon:
    per field (index field_id) n_cdl_px, cdl_px_fallback; per field x year the GROUPS shares,
    cropland (= the six crop groups), dom_code, dom_name. Also the years not on disk. Moved
    here from scripts/build_sandy_panel.py (2026-10-23) so every side builds it one way."""
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.open(path(max(years), fips)) as c:
        gg = g.to_crs(c.crs)
        win = from_bounds(*gg.total_bounds, transform=c.transform).round_offsets().round_lengths()
        tr, shape = c.window_transform(win), (int(win.height), int(win.width))
    zone, flat, fallback = polygon_pixels(gg.geometry, shape, tr)
    n, fid = len(g), g.field_id.values
    rows, missing = [], []
    for y in years:
        if not path(y, fips).exists():
            missing.append(y)
            continue
        t = zone_cover(zone, read(y, win, fips).ravel()[flat], n)
        t.insert(0, "field_id", fid)
        t.insert(1, "year", y)
        t["cropland"] = t[CROP_SHARES].sum(axis=1, min_count=1)
        t["dom_name"] = t.dom_code.map(lambda c: name(c) if c >= 0 else "")
        rows.append(t)
    fy = pd.concat(rows, ignore_index=True)
    fy = fy[[c for c in fy.columns if c not in ("dom_code", "dom_name")] + ["dom_code", "dom_name"]]
    static = pd.DataFrame({"n_cdl_px": rows[0].n_px.values, "cdl_px_fallback": False}, index=fid)
    static.loc[fid[fallback - 1], "cdl_px_fallback"] = True
    return static, fy.drop(columns="n_px"), missing


def polygon_pixels(geoms, shape, transform) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Which pixels of a grid (``shape``, ``transform``) belong to which polygon: pixel CENTRE
    inside (rasterio default; overlaps go to the later polygon). A polygon that holds no
    centre gets the one pixel under its representative point, as
    ``exposure.add_exposure`` does. Returns (``zone``, ``flat``, ``fallback``): 1-based
    polygon number (order of ``geoms``) and flat pixel index, one entry per (polygon, pixel)
    pair, and the polygon numbers that took the fallback pixel (dropped from ``zone`` when
    that pixel is off the grid)."""
    from rasterio.features import rasterize

    geoms = list(geoms)
    lab = np.zeros(shape, dtype="int64")
    for k in range(0, len(geoms), 5000):  # chunks, as exposure.add_exposure
        sub = geoms[k : k + 5000]
        r = rasterize([(g, k + i + 1) for i, g in enumerate(sub)], out_shape=shape,
                      transform=transform, fill=0, dtype="int64")  # fmt: skip
        lab = np.where(r > 0, r, lab)
    flat = np.flatnonzero(lab)
    zone = lab.ravel()[flat]
    miss = np.setdiff1d(np.arange(1, len(geoms) + 1), zone)
    if miss.size:
        pts = [geoms[i - 1].representative_point() for i in miss]
        col = np.floor([(p.x - transform.c) / transform.a for p in pts]).astype(int)
        row = np.floor([(p.y - transform.f) / transform.e for p in pts]).astype(int)
        ok = (row >= 0) & (row < shape[0]) & (col >= 0) & (col < shape[1])
        zone = np.concatenate([zone, miss[ok]])
        flat = np.concatenate([flat, row[ok] * shape[1] + col[ok]])
    return zone, flat, miss


def zone_cover(zone: np.ndarray, code: np.ndarray, n: int, groups=None) -> pd.DataFrame:
    """Per zone 1..``n``: pixel count ``n_px``, the share of its pixels in each group of
    ``groups`` (default ``GROUPS``; columns ``share_<group>``, then ``share_other`` for
    every code in no group) and the dominant class ``dom_code`` (most pixels; ties -> the
    lowest code). ``zone`` and ``code`` are aligned per pixel (``code`` 0..255). A zone with
    no pixel gets n_px 0, NaN shares and dom_code -1."""
    groups = GROUPS if groups is None else groups
    zone = np.asarray(zone, dtype="int64")
    code = np.asarray(code, dtype="int64")
    counts = np.bincount(zone * 256 + code, minlength=(n + 1) * 256).reshape(n + 1, 256)[1:]
    npx = counts.sum(axis=1)
    onehot = np.zeros((256, len(groups) + 1))
    onehot[:, -1] = 1.0
    for j, codes in enumerate(groups.values()):
        idx = [c for c in codes if 0 <= c < 256]
        onehot[idx, :] = 0.0
        onehot[idx, j] = 1.0
    with np.errstate(invalid="ignore", divide="ignore"):
        sh = (counts @ onehot) / npx[:, None]
    out = pd.DataFrame(sh, columns=[f"share_{g}" for g in [*groups, OTHER]],
                       index=pd.RangeIndex(1, n + 1, name="zone"))  # fmt: skip
    out.insert(0, "n_px", npx)
    out["dom_code"] = np.where(npx > 0, counts.argmax(axis=1), -1)
    return out
