"""The farm fields, one set per state: every state land-use polygon farmed in 2012.

2012 is the last edition before the storm years of the panel (Sandy, Oct 2012), so a field that
left farming in 2013-25 is still in the set; a set of 2020 survivors would hide every exit.

* NJ: the previous-edition code of data/landuse/njlulc_2012_2015.gpkg (scripts/fetch_njlulc.py,
  spring 2012 photography), farmed = agri_sfincs.landuse.FARMED. That layer is cut where the
  2015 code differs, so a field that partly left farming by 2015 is two pieces.
* DE: the same from data/landuse/delulc_2012_2017.gpkg (scripts/fetch_delulc.py; Delaware's
  2017 layer carries the 2012 code), farmed = landuse.DE_FARMED, kept where the polygon's
  representative point is inside the DE ring (the bay-draining watersheds, region.load_ring).

``field_id`` is 1..N WITHIN a state: it is the raster label every per-pixel step burns
(agri_sfincs.fieldflood.field_pixels, the CDL and MOTF tables), and each state has its own
model grid. Across states the key is (``state``, ``field_id``); exports spell it "NJ-123".

``load("NJ")`` returns field_id, state, county, ha, behind_levee, lulc2012, lulc2015 (that
layer's next code), lulc2020 (the 2015-2020 layer's next code by largest overlap; blank if not
farmed in 2015), geometry (EPSG:32618). Ids follow the source layer's order, as the Sandy and
storm panels have used since 2026-10-15. ``load("DE")`` has lulc2012, lulc2017, lulc2022
instead (Delaware's editions). ``today`` = the latest edition's code (2020 / 2022).
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from agri_sfincs import config, domain, fieldflood, landuse, region

#: per state: (side, first transition layer, second, its middle edition, its last edition)
EDITIONS = {"NJ": ("nj", "njlulc_2012_2015", "njlulc_2015_2020", 2015, 2020),
            "DE": ("de", "delulc_2012_2017", "delulc_2017_2022", 2017, 2022)}  # fmt: skip


def columns(state: str) -> list[str]:
    _, _, _, mid, last = EDITIONS[state]
    return ["field_id", "state", "county", "ha", "behind_levee", "lulc2012", f"lulc{mid}", f"lulc{last}", "geometry"]


COLUMNS = columns("NJ")


def _load(state: str) -> gpd.GeoDataFrame:
    side, first, second, mid, last = EDITIONS[state]
    g = gpd.read_file(config.LANDUSE_DIR / f"{first}.gpkg").to_crs(domain.EPSG)
    g = g[g.prev.map(landuse.is_farmed)].explode(index_parts=False).reset_index(drop=True)
    if state != "NJ":  # NJ's layer is already clipped to the domain's bbox and three counties
        ring = region.load_ring(side).to_crs(domain.EPSG).geometry.iloc[0]
        g = g[g.representative_point().within(ring)].reset_index(drop=True)
    g = fieldflood.add_county_levee(g[["prev", "next", "geometry"]], side)
    g = g.rename(columns={"prev": "lulc2012", "next": f"lulc{mid}"})
    g["field_id"] = np.arange(1, len(g) + 1)
    g["ha"] = g.area / 1e4
    l2 = gpd.read_file(config.LANDUSE_DIR / f"{second}.gpkg").to_crs(domain.EPSG)[["next", "geometry"]]
    x = gpd.overlay(g[["field_id", "geometry"]], l2, how="intersection", keep_geom_type=True)
    x["a"] = x.area
    best = x.sort_values("a", ascending=False).drop_duplicates("field_id").set_index("field_id")["next"]
    farm_mid = g[f"lulc{mid}"].map(landuse.is_farmed)
    g[f"lulc{last}"] = g.field_id.map(best).where(farm_mid).astype("Int64")
    return g


SOURCES = {"NJ": lambda: _load("NJ"), "DE": lambda: _load("DE")}


def load(state: str = "NJ") -> gpd.GeoDataFrame:
    """The state's 2012 farm fields (see the module docstring)."""
    if state not in SOURCES:
        raise ValueError(f"no field source for {state!r} (have {sorted(SOURCES)})")
    g = SOURCES[state]()
    g["state"] = state
    return g[columns(state)]


def farmed_today(g: gpd.GeoDataFrame) -> np.ndarray:
    """Bool per field: still farmed in the latest edition (NJ 2020, DE 2022), i.e. today's
    farmland for the flood classes (FINDINGS §29). Subset AFTER the per-pixel steps, which need
    every id 1..N."""
    col = "lulc2020" if "lulc2020" in g else "lulc2022"
    return np.array([False if pd.isna(c) else landuse.is_farmed(c) for c in g[col].astype(object)], bool)
