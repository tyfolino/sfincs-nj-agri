"""Per-field, per-scene Landsat statistics, 1984-2025 (Fork 2, step 2.1: when did each field
stop being farmed?).

Units: data/landuse/field_units.gpkg (scripts/build_field_units.py), rasterised on a 30 m
UTM 18N grid aligned to the Landsat grid (pixel corners at 15 m mod 30) after an INWARD
buffer of INSET_M, so only interior pixels count (no field-edge mixing). Units too small for
any interior pixel fall back to their centre-in pixels and are listed in
data/landsat/edge_only_units.csv (treat them as mixed).

Scenes: Landsat Collection 2 Level-2 (TM, ETM+, OLI, OLI-2) from the Microsoft Planetary
Computer STAC (`landsat-c2-l2`), scene cloud cover < MAX_CLOUD %, every WRS-2 path/row that
touches the units. Bands blue, green, red, nir08, swir16 and qa_pixel are read through a
WarpedVRT onto the grid (nearest), then agri_sfincs.landsat gives the clear mask, NDVI, BSI,
MNDWI and per-unit means over clear interior pixels.

Writes one parquet per scene in data/landsat/parts/ (resumable: done scenes are skipped;
data/landsat is a symlink to /scratch), then data/landsat/field_scene_stats.parquet with
columns scene, date, platform, unit, n (clear px), n_valid (non-fill px), ndvi, bsi, mndwi,
nir, swir1. Units with no clear pixel in a scene are left out of that scene.

For the 120 m cells (scripts/build_field_cells.py), which are already inset:
  --units data/landuse/field_cells.gpkg --id cell --inset 0 --tag cells
(the "unit" column of the output then holds the cell id).

Usage:  python scripts/landsat_field_stats.py [--workers 12] [--limit N] [--merge-only]
"""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT

from agri_sfincs import config, domain
from agri_sfincs import landsat as ls
from agri_sfincs.landsat_stac import Token, search

UNITS = config.LANDUSE_DIR / "field_units.gpkg"
PARTS = config.LANDSAT_DIR / "parts"
OUT = config.LANDSAT_DIR / "field_scene_stats.parquet"
MAX_CLOUD, INSET_M, RES = 60, 15.0, 30.0
BANDS = ["blue", "green", "red", "nir08", "swir16", "qa_pixel"]
CRS = f"EPSG:{domain.EPSG}"

os.environ.update({"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MAX_RETRY": "5",
                   "GDAL_HTTP_RETRY_DELAY": "3", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
                   "GDAL_CACHEMAX": "256"})  # fmt: skip


def grid_and_labels(units: gpd.GeoDataFrame, inset_m: float = INSET_M):
    x0, y0, x1, y1 = units.total_bounds
    x0 = np.floor((x0 - 15) / RES) * RES + 15 - RES
    y1 = np.ceil((y1 - 15) / RES) * RES + 15 + RES
    w, h = int(np.ceil((x1 - x0) / RES)) + 2, int(np.ceil((y1 - y0) / RES)) + 2
    tr = from_origin(x0, y1, RES, RES)
    inset = units.geometry.buffer(-inset_m) if inset_m else units.geometry
    shapes = [(g, int(u)) for g, u in zip(inset, units.unit) if not g.is_empty]
    labels = rasterize(shapes, out_shape=(h, w), transform=tr, fill=0, dtype="int32")
    # units too small for an interior pixel fall back to their centre-in pixels (edge_only)
    full = rasterize([(g, int(u)) for g, u in zip(units.geometry, units.unit)], out_shape=(h, w),
                     transform=tr, fill=0, dtype="int32")  # fmt: skip
    has = np.zeros(int(units.unit.max()) + 1, bool)
    has[np.unique(labels)] = True
    fill = (labels == 0) & (full > 0) & ~has[full]
    labels[fill] = full[fill]
    edge_only = np.unique(full[fill])
    if inset_m:
        pd.DataFrame({"unit": edge_only}).to_csv(config.LANDSAT_DIR / "edge_only_units.csv", index=False)
    return tr, (h, w), labels


def do_scene(item, tr, shape, labels, n_units, token: Token, parts=PARTS) -> str:
    sid = item["id"]
    out = parts / f"{sid}.parquet"
    if out.exists():
        return "skip"
    tok = token.get()
    arr = {}
    for b in BANDS:
        href = item["assets"][b]["href"]
        with rasterio.open(f"/vsicurl/{href}?{tok}") as s, \
                WarpedVRT(s, crs=CRS, transform=tr, width=shape[1], height=shape[0],
                          resampling=Resampling.nearest, src_nodata=s.nodata if s.nodata is not None else 0,
                          nodata=0) as v:  # fmt: skip
            arr[b] = v.read(1)
    qa = arr["qa_pixel"]
    valid = (qa != 0) & ((qa & 1) == 0)
    ok = valid & ls.clear(qa)
    sr = {b: ls.reflectance(arr[b]) for b in BANDS[:-1]}
    ix = ls.indices(sr["blue"], sr["green"], sr["red"], sr["nir08"], sr["swir16"])
    stats = ls.field_means(labels, {**ix, "nir": sr["nir08"], "swir1": sr["swir16"]}, ok, n_units)
    n_valid = np.bincount(labels[valid & (labels > 0)], minlength=n_units + 1)
    keep = np.flatnonzero(stats["n"] > 0)
    keep = keep[keep > 0]
    p = item["properties"]
    df = pd.DataFrame({"scene": sid, "date": pd.Timestamp(p["datetime"]).tz_localize(None).normalize(),
                       "platform": p["platform"], "unit": keep.astype("int32"),
                       "n": stats["n"][keep].astype("int32"), "n_valid": n_valid[keep].astype("int32"),
                       **{k: stats[k][keep].astype("float32")
                          for k in ("ndvi", "bsi", "mndwi", "nir", "swir1")}})  # fmt: skip
    tmp = out.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(out)
    return f"{len(df)} units"


def merge(parts_dir=PARTS, out=OUT) -> None:
    parts = sorted(parts_dir.glob("*.parquet"))
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    df.to_parquet(out, index=False)
    print(f"wrote {out}: {len(df):,} rows, {df.scene.nunique()} scenes, {df.unit.nunique()} units, "
          f"{df.date.min():%Y-%m-%d} .. {df.date.max():%Y-%m-%d}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=None, help="first N scenes only (testing)")
    ap.add_argument("--merge-only", action="store_true")
    ap.add_argument("--units", default=str(UNITS), help="polygon layer (default field_units.gpkg)")
    ap.add_argument("--id", default="unit", help="its integer id column (1..N)")
    ap.add_argument("--inset", type=float, default=INSET_M, help="inward buffer, m (0 for cells)")
    ap.add_argument("--tag", default="", help="suffix for parts_<tag>/ and the merged file")
    a = ap.parse_args()
    sfx = f"_{a.tag}" if a.tag else ""
    parts_dir = config.LANDSAT_DIR / f"parts{sfx}"
    out = config.LANDSAT_DIR / f"field_scene_stats{sfx}.parquet"
    if a.merge_only:
        merge(parts_dir, out)
        return
    parts_dir.mkdir(parents=True, exist_ok=True)
    units = gpd.read_file(a.units).to_crs(CRS)
    if a.id != "unit":  # cells carry their parent "unit"; the label is the cell id
        units = units.drop(columns="unit", errors="ignore").rename(columns={a.id: "unit"})
    tr, shape, labels = grid_and_labels(units, a.inset)
    n_units = int(units.unit.max())
    print(f"grid {shape}, {np.unique(labels).size - 1} of {n_units} units have interior pixels")
    items = search(units.to_crs(4326).total_bounds, max_cloud=MAX_CLOUD)
    items.sort(key=lambda f: f["properties"]["datetime"])
    if a.limit:
        items = items[: a.limit]
    print(f"{len(items)} scenes", flush=True)
    token, done, t0 = Token(), 0, time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(do_scene, it, tr, shape, labels, n_units, token, parts_dir): it["id"]
                for it in items}  # fmt: skip
        for f in as_completed(futs):
            done += 1
            try:
                msg = f.result()
            except Exception as e:  # noqa: BLE001 — log and carry on; a rerun retries it
                msg = f"FAILED {type(e).__name__}: {e}"[:200]
            if done % 50 == 0 or msg.startswith("FAILED"):
                print(f"[{done}/{len(items)} {time.time() - t0:.0f}s] {futs[f]}: {msg}", flush=True)
    merge(parts_dir, out)


if __name__ == "__main__":
    main()
