"""Field units for the satellite farm history (Fork 2, step 2.1).

From data/landuse/farm_wetland_transitions.gpkg (scripts/farm_wetland_transitions.py):
  farmed2012    NJDEP LU/LC polygons farmed in 2012 (the 2012-15 layer's previous code):
                ALL on ground below MHHW + 3 m, plus N_UPLAND drawn at random from higher
                ground (the comparison: does low ground leave farming faster than upland?)
  conv_pre2012  every polygon that left farming for wetland, water, forest or "other" in
                1995-2012 (not development), so Landsat can date the early wave
plus
  marsh_ref     N_MARSH disks (60 m radius) in stable marsh: CDL herbaceous wetland (195)
                in all of 2008-25, ground below MHHW + 0.5 m, inside the study counties.
                These are calibration references for "never farmed".

Covariates are carried over: m_above_mhhw (median, §21 surface), leveed_share, county, the
LU/LC codes and transition class.

Writes data/landuse/field_units.gpkg (EPSG:32618; ``unit`` = 1..N, the raster label used by
scripts/landsat_field_stats.py). Usage:  python scripts/build_field_units.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer

from agri_sfincs import cdl, config, domain, exposure, landuse, region

SRC = config.LANDUSE_DIR / "farm_wetland_transitions.gpkg"
OUT = config.LANDUSE_DIR / "field_units.gpkg"
N_UPLAND, N_MARSH, SEED = 2500, 200, 20261007
KEEP = ["kind", "county", "prev", "next", "label_next", "cls", "y0", "y1", "ha",
        "m_above_mhhw", "leveed_share", "geometry"]  # fmt: skip


def marsh_refs(n: int, rng) -> gpd.GeoDataFrame:
    G = exposure.load_grid()
    stable = np.ones(G.shape, bool)
    for y in range(2008, 2026):
        stable &= cdl.read(y, G.win) == 195
    cand = np.flatnonzero(stable & np.isfinite(G.hab) & (G.hab < 0.5))
    pick = rng.choice(cand, size=min(4 * n, cand.size), replace=False)
    r, c = np.unravel_index(pick, G.shape)
    x, y = G.tr.c + G.tr.a * (c + 0.5), G.tr.f + G.tr.e * (r + 0.5)
    ux, uy = Transformer.from_crs(G.crs, domain.EPSG, always_xy=True).transform(x, y)
    pts = gpd.GeoDataFrame({"m_above_mhhw": G.hab[r, c]},
                           geometry=gpd.points_from_xy(ux, uy), crs=domain.EPSG)  # fmt: skip
    keep = []  # thin to >= 300 m apart
    for i, p in enumerate(pts.geometry):
        if all(p.distance(pts.geometry.iloc[j]) >= 300 for j in keep):
            keep.append(i)
        if len(keep) == n:
            break
    d = pts.iloc[keep].copy()
    d["geometry"] = d.buffer(60)
    d["kind"], d["cls"], d["leveed_share"] = "marsh_ref", "marsh", 0.0
    d["ha"] = d.area / 1e4
    return d


def main() -> None:
    rng = np.random.default_rng(SEED)
    g = gpd.read_file(SRC)
    f12 = g[g.y0 == 2012].copy()
    low, up = f12[f12.m_above_mhhw < 3.0], f12[~(f12.m_above_mhhw < 3.0)]
    up = up.iloc[rng.choice(len(up), size=min(N_UPLAND, len(up)), replace=False)]
    farmed = pd.concat([low, up]).assign(kind="farmed2012")
    early = g[(g.y0 < 2012) & ~g.cls.isin([landuse.STAYS, landuse.TO_URBAN, landuse.TO_POND,
                                           landuse.TO_FARMED_WET])].assign(kind="conv_pre2012")  # fmt: skip
    m = marsh_refs(N_MARSH, rng)
    cty = region.load_counties().to_crs(domain.EPSG)
    cty = cty[cty.fips.isin(domain.COUNTIES)]
    m["county"] = gpd.sjoin(m.set_geometry(m.centroid), cty[["name", "geometry"]], how="left",
                            predicate="within")["name"].values  # fmt: skip
    u = pd.concat([farmed, early, m], ignore_index=True)
    u = gpd.GeoDataFrame(u[[c for c in KEEP if c in u.columns]], geometry="geometry", crs=domain.EPSG)
    u.insert(0, "unit", np.arange(1, len(u) + 1))
    u.to_file(OUT, driver="GPKG")
    print(f"wrote {OUT}: {len(u)} units")
    print(u.groupby("kind").agg(n=("unit", "size"), ha=("ha", "sum"),
                                low=("m_above_mhhw", lambda s: int((s < 1.5).sum()))).round(0))  # fmt: skip


if __name__ == "__main__":
    main()
