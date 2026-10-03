"""The domain ring and the analysis regions, built from the HUC12 and county layers.

Two different polygons, on purpose:

* the **ring** is the union of the domain HUC12s — drainage divides on land, and the
  NJ/DE state line in the river and bay (the frontal HUC12s run out to it). The
  seaward water-level line is drawn inside it later (step 2), so the ring is the
  outer limit of the model, not its mask;
* the **model outline** is the ring minus Pennsylvania and Delaware LAND. North of about
  Bridgeport the WBD "frontal Delaware River" HUC12s cross the river and take in PA land
  (Marcus Hook / Chester heights, 25-120 m; 81 km2), and 22 km2 of DE land rides along
  near New Castle (measured 2026-10-02). The river and bay water stay in;
* the **analysis cells** are ring x county: what the loss data can be compared with.
"""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon

from agri_sfincs import config, domain

HUC12_FILE = config.REGION_DIR / "huc12.gpkg"
COUNTIES_FILE = config.REGION_DIR / "counties.gpkg"
RING_FILE = config.REGION_DIR / "ring.geojson"
OUTLINE_FILE = config.REGION_DIR / "model_outline.geojson"
STATES_FILE = config.REGION_DIR / "states_cb500k.gpkg"  # NJ/PA/DE, shoreline-clipped

#: HUC12 polygons share edges but WBD vertices do not always coincide exactly; a
#: dissolve leaves sliver gaps that become false interior holes. Close them with a
#: tiny buffer out-and-back (metres, in the UTM CRS).
_SLIVER_M = 1.0
#: Interior rings smaller than this are slivers, not real enclaves.
_MIN_HOLE_M2 = 1.0e4


def dissolve_ring(huc12: gpd.GeoDataFrame) -> Polygon:
    """Union of the HUC12 polygons as ONE polygon in ``domain.EPSG``, slivers closed.

    Raises if the union is not a single polygon (a missing HUC12 would split it) or
    if it keeps a real interior hole (a HUC12 surrounded by the domain but left out).
    """
    g = huc12.to_crs(domain.EPSG).geometry
    u = g.buffer(_SLIVER_M).union_all().buffer(-_SLIVER_M)
    if isinstance(u, MultiPolygon):
        parts = sorted(u.geoms, key=lambda p: p.area, reverse=True)
        # Specks from the buffer round trip are not real parts.
        real = [p for p in parts if p.area > _MIN_HOLE_M2]
        if len(real) > 1:
            raise ValueError(
                f"ring is {len(real)} separate polygons (areas km2: "
                f"{[round(p.area / 1e6, 2) for p in real]}) — is a HUC12 missing?"
            )
        u = real[0]
    holes = [r for r in u.interiors if Polygon(r).area > _MIN_HOLE_M2]
    if holes:
        raise ValueError(
            f"ring has {len(holes)} interior hole(s) (km2: "
            f"{[round(Polygon(r).area / 1e6, 2) for r in holes]}) — an enclave HUC12?"
        )
    return Polygon(u.exterior)


def remove_foreign_land(ring: Polygon, foreign_land) -> Polygon:
    """``ring`` minus ``foreign_land`` (a geometry in the same CRS), keeping the largest
    part. Anything else left over is a sliver cut off by the subtraction; it is dropped
    and its area reported by the caller via the returned polygon's area."""
    out = ring.difference(foreign_land)
    if isinstance(out, MultiPolygon):
        out = max(out.geoms, key=lambda p: p.area)
    return out


def load_huc12() -> gpd.GeoDataFrame:
    return gpd.read_file(HUC12_FILE)


def load_counties() -> gpd.GeoDataFrame:
    return gpd.read_file(COUNTIES_FILE)


def load_ring() -> gpd.GeoDataFrame:
    return gpd.read_file(RING_FILE)


def load_outline() -> gpd.GeoDataFrame:
    """The MODEL outline (ring minus PA/DE land). Use this, not the ring, to build."""
    return gpd.read_file(OUTLINE_FILE)
