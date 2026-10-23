"""The part of WBD HUC12 020402050705 ("Chesapeake and Delaware Canal-Frontal Delaware River")
SOUTH of the C&D Canal, for the Delaware side (the canal is its north edge; user, 2026-10-23).

Most of the unit is Delaware land south of the canal (between the canal and Augustine Creek)
plus its river frontage down to Port Penn; leaving the whole unit out cut ~67 km2 of DE land
and a strip of river out of the model, and the river edge of that notch became a forced
boundary. The canal is found in the DE bed (data/elevation/bed_merged_de.tif): water deeper
than DEEP_M inland of the river shore (west of SHORE_LON), the dredged ship channel and the
Delaware City branch. The unit minus that water (+ BUFFER_DEG) splits into pieces; the
largest whose representative point is south of the canal (SOUTH_OF_LAT) is kept.

Writes data/region/de_canal_south.geojson (EPSG:4326, tracked), which scripts/fetch_wbd.py
--side de adds to the DE ring. Needs bed_merged_de.tif (scripts/build_bed.py --side de),
whose extent (the DE outline bbox + 1 km) already holds the whole unit.
Usage:  python scripts/split_canal_unit.py
"""

from __future__ import annotations

import geopandas as gpd
import rasterio
import shapely
from rasterio.features import shapes
from rasterio.windows import from_bounds
from shapely.geometry import box, shape

from agri_sfincs import config, domain
from agri_sfincs.net import arcgis_query

WBD_HUC12 = "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/6"
DEEP_M = -3.0
SHORE_LON = -75.578
BUFFER_DEG = 0.0005
SOUTH_OF_LAT = 39.55
DECIMATE = 4
OUT = config.REGION_DIR / "de_canal_south.geojson"


def main() -> None:
    unit = arcgis_query(WBD_HUC12, f"huc12='{domain.DE_CANAL_HUC12}'", "huc12,name").geometry.iloc[0]
    with rasterio.open(config.ELEV_DIR / "bed_merged_de.tif") as s:
        w = from_bounds(*unit.bounds, transform=s.transform).round_offsets().round_lengths()
        shape_ = (int(w.height) // DECIMATE, int(w.width) // DECIMATE)
        a = s.read(1, window=w, out_shape=shape_)
        tr = s.window_transform(w) * s.window_transform(w).scale(w.width / shape_[1], w.height / shape_[0])
    deep = (a < DEEP_M) & (a > -9000)
    water = shapely.union_all([shape(g) for g, v in shapes(deep.astype("uint8"), transform=tr) if v == 1])
    canal = water.intersection(unit).intersection(box(-76.5, 39.0, SHORE_LON, 40.0))
    parts = list(getattr(unit.difference(canal.buffer(BUFFER_DEG)), "geoms", []))
    south = [p for p in parts if p.representative_point().y < SOUTH_OF_LAT]
    if not south:
        raise RuntimeError("no piece of the unit south of the canal: check DEEP_M / SHORE_LON")
    keep = max(south, key=lambda p: p.area)
    g = gpd.GeoDataFrame({"huc12": [domain.DE_CANAL_HUC12], "part": ["south of the canal"]},
                         geometry=[keep], crs=4326)  # fmt: skip
    g.to_file(OUT, driver="GeoJSON")
    km2 = g.to_crs(domain.EPSG).area.iloc[0] / 1e6
    print(f"unit split into {len(parts)} pieces; kept {km2:.1f} km2 south of the canal -> {OUT}")


if __name__ == "__main__":
    main()
