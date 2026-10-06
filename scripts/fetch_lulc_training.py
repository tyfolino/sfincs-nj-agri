"""Training squares for the multi-class field classifier, from NJDEP LU/LC 2015 = 2020.

NJDEP's photo-interpreters separate what CDL cannot: an active hay field (2100) from an old
field (4410), and marsh from scrub and woods (FINDINGS §24). So the labels are polygons of the
NJDEP Land_Use_2020 layer whose code did NOT change between 2015 and 2020 (LU15 = LU20), at
least MIN_ACRES in size, inside the model domain's bounding box, grouped into CLASSES.

From each polygon, inset by INSET_M, up to PER_POLY 120 m squares (old field: CLASS_OPTS) on the Landsat-aligned grid
(scripts/build_field_cells.py: fishnet) that lie wholly inside are drawn at random, up to
PER_CLASS squares per class. Squares overlapping a NAIP-checked sample are dropped, so the
validation stays independent.

Writes data/landuse/lulc_training_squares.gpkg (EPSG:32618; ``sq`` = 1..N, ``cls``, ``lu``,
``label``). Usage:  python scripts/fetch_lulc_training.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from agri_sfincs import config, domain, region
from build_field_cells import fishnet
from fetch_njlulc import AGOL20, post

OUT = config.LANDUSE_DIR / "lulc_training_squares.gpkg"
MIN_ACRES, INSET_M, CELL_M = 5, 15.0, 120.0
PER_POLY, PER_CLASS, SEED = 3, 800, 20261010
#: old field / scrub comes in small, short-lived polygons: smaller ones, more squares each,
#: and stable over the shorter 2015-2020 span only (as every class)
CLASS_OPTS = {"oldfield": {"min_acres": 1, "per_poly": 8, "cell_m": 90.0}}
CLASSES = {
    "farm": [2100, 2140, 2200],
    "oldfield": [2150, 4410, 4411, 4420, 4430, 4440],
    "marsh": [6111, 6112, 6120, 6141, 6240, 6241],
    "wetwood": [6210, 6220, 6221, 6231, 6232, 6233, 6234, 6251, 6252],
    "forest": [4110, 4120, 4210, 4220, 4230, 4311, 4312, 4321, 4322],
    "developed": [1110, 1120, 1130, 1140, 1150, 1200, 1300, 1400, 1410, 1500, 1600, 1700,
                  1800, 1804, 7500],
    "water": [5100, 5190, 5200, 5300, 5410, 5411, 5412, 6290],
}  # fmt: skip


def fetch_class(codes, bbox, min_acres=MIN_ACRES) -> gpd.GeoDataFrame:
    base = {"where": f"LU15 = LU20 AND ACRES >= {min_acres} AND LU20 IN ({','.join(map(str, codes))})",
            "geometry": ",".join(f"{v:.5f}" for v in bbox), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            "outFields": "LU20,LABEL20,ACRES", "orderByFields": "OBJECTID"}  # fmt: skip
    feats, off = [], 0
    while True:
        d = post(AGOL20, {**base, "resultOffset": off, "resultRecordCount": 1000})
        f = d.get("features", [])
        feats += f
        if len(f) < 1000:
            break
        off += 1000
    return gpd.GeoDataFrame.from_features(feats, crs=4326)


def main() -> None:
    rng = np.random.default_rng(SEED)
    outline = region.load_outline().to_crs(domain.EPSG)
    bbox = tuple(outline.to_crs(4326).total_bounds)
    held = []
    for f in ("spotcheck_samples.csv", "lulc_samples.csv", "exit_samples_cells.csv"):
        p = config.DATA / "imagery" / f
        if p.exists():
            s = pd.read_csv(p)
            held.append(gpd.GeoSeries(gpd.points_from_xy(s.lon, s.lat), crs=4326).to_crs(domain.EPSG).buffer(300))
    held = pd.concat(held).union_all() if held else None
    out = []
    for cls, codes in CLASSES.items():
        o = CLASS_OPTS.get(cls, {})
        g = fetch_class(codes, bbox, o.get("min_acres", MIN_ACRES)).to_crs(domain.EPSG)
        g = g[g.intersects(outline.union_all())]
        g["geometry"] = g.buffer(-INSET_M)
        g = g[~g.geometry.is_empty].reset_index(drop=True)
        net = fishnet(g.total_bounds, o.get("cell_m", CELL_M), g.crs)
        j = gpd.sjoin(net, g[["LU20", "LABEL20", "geometry"]], predicate="within").reset_index(drop=True)
        if held is not None:
            j = j[~j.intersects(held)]
        j = j.sample(frac=1.0, random_state=int(rng.integers(1 << 31)))
        j = j.groupby("index_right").head(o.get("per_poly", PER_POLY)).head(PER_CLASS)
        out.append(gpd.GeoDataFrame({"cls": cls, "lu": j.LU20.astype(int).values,
                                     "label": j.LABEL20.values}, geometry=j.geometry.values,
                                    crs=g.crs))  # fmt: skip
        print(f"{cls:10s} {len(g):6d} polygons -> {len(j)} squares")
    t = pd.concat(out, ignore_index=True)
    t.insert(0, "sq", np.arange(1, len(t) + 1))
    gpd.GeoDataFrame(t, crs=domain.EPSG).to_file(OUT, driver="GPKG")
    print(f"wrote {OUT}: {len(t)} squares")


if __name__ == "__main__":
    main()
