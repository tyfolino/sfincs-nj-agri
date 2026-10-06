"""Split the field units into 120 m cells, so part-field conversions show (a 140 ha LU/LC
polygon that loses only its marsh edge is still "farmed" on average).

Each unit of data/landuse/field_units.gpkg (scripts/build_field_units.py) is inset by
INSET_M (no field-edge pixels), then cut by a CELL_M grid aligned to the Landsat 30 m grid
(corners at 15 m mod 30, so a full cell = 4 x 4 Landsat pixels). Pieces smaller than
MIN_HA are dropped. Each cell keeps its parent's attributes (``unit``, kind, county,
LU/LC codes, period) and gets its own median height above recent MHHW and leveed share
(scripts/farm_wetland_transitions.py: add_exposure).

Writes data/landuse/field_cells.gpkg (EPSG:32618; ``cell`` = 1..N, the raster label for
scripts/landsat_field_stats.py --units field_cells.gpkg --id cell --inset 0 --tag cells).
Usage:  python scripts/build_field_cells.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from agri_sfincs import config
from farm_wetland_transitions import add_exposure

UNITS = config.LANDUSE_DIR / "field_units.gpkg"
OUT = config.LANDUSE_DIR / "field_cells.gpkg"
INSET_M, CELL_M, MIN_HA = 15.0, 120.0, 0.3


def fishnet(bounds, size: float, crs) -> gpd.GeoDataFrame:
    x0, y0, x1, y1 = bounds
    x0 = np.floor((x0 - 15) / size) * size + 15
    y0 = np.floor((y0 - 15) / size) * size + 15
    xs, ys = np.arange(x0, x1 + size, size), np.arange(y0, y1 + size, size)
    return gpd.GeoDataFrame(geometry=[box(x, y, x + size, y + size) for x in xs for y in ys], crs=crs)


def main() -> None:
    u = gpd.read_file(UNITS)
    u["geometry"] = u.geometry.buffer(-INSET_M)
    u = u[~u.geometry.is_empty & u.geometry.notna()]
    net = fishnet(u.total_bounds, CELL_M, u.crs)
    net = net[net.index.isin(gpd.sjoin(net, u[["geometry"]], predicate="intersects").index.unique())]
    c = gpd.overlay(u.drop(columns=["m_above_mhhw", "leveed_share"]), net, how="intersection",
                    keep_geom_type=True)  # fmt: skip
    c["ha"] = c.area / 1e4
    c = c[c.ha >= MIN_HA].reset_index(drop=True)
    c = add_exposure(c)
    c.insert(0, "cell", np.arange(1, len(c) + 1))
    c.to_file(OUT, driver="GPKG")
    print(f"wrote {OUT}: {len(c)} cells from {c.unit.nunique()} units, {c.ha.sum():,.0f} ha")
    print(c.groupby("kind").agg(cells=("cell", "size"), ha=("ha", "sum")).round(0))


if __name__ == "__main__":
    main()
