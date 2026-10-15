"""NJDEP Land Use/Land Cover transition layers over the model domain, farmed-before polygons.

Each NJDEP edition layer carries the previous edition's code, so one layer = one period:

  1995-2002  mapsdep Land_lu/MapServer/11   LU95 -> LU02
  2002-2007  mapsdep Land_lu/MapServer/7    LU02 -> LU07
  2007-2012  mapsdep Land_lu/MapServer/0    LU07 -> LU12
  2012-2015  mapsdep Land_lu/MapServer/13   LU12 -> LU15
  2015-2020  NJDEP AGOL Land_Use_2020/FeatureServer/5   LU15 -> LU20

Only polygons whose PREVIOUS code is agriculture (2000-2999) are kept (both the ones that
changed and the controls that stayed farmed), inside the model domain's bounding box.
Paged by resultOffset (service max 2000).

Writes data/landuse/njlulc_<y0>_<y1>.gpkg (EPSG:4326; columns prev, next, label_prev,
label_next, acres + the period) and prints counts. Usage:  python scripts/fetch_njlulc.py
"""

from __future__ import annotations

import geopandas as gpd

from agri_sfincs import config, landuse, net, region

MAPSDEP = "https://mapsdep.nj.gov/arcgis/rest/services/Features/Land_lu/MapServer"
PERIODS = [  # (y0, y1, layer url, previous suffix, next suffix)
    (1995, 2002, f"{MAPSDEP}/11", "95", "02"),
    (2002, 2007, f"{MAPSDEP}/7", "02", "07"),
    (2007, 2012, f"{MAPSDEP}/0", "07", "12"),
    (2012, 2015, f"{MAPSDEP}/13", "12", "15"),
    (2015, 2020, landuse.LULC2020_URL, "15", "20"),
]
PAGE = 1000


def fetch_period(url: str, p: str, n: str, bbox) -> gpd.GeoDataFrame:
    fields = [f"LU{p}", f"LU{n}", f"LABEL{p}", f"LABEL{n}", "ACRES"]
    base = {"where": f"LU{p} >= 2000 AND LU{p} < 3000",
            "geometry": ",".join(f"{v:.5f}" for v in bbox), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            "outFields": ",".join(fields), "orderByFields": "OBJECTID"}  # fmt: skip
    feats, off = [], 0
    while True:
        d = net.arcgis_form_query(url, {**base, "resultOffset": off, "resultRecordCount": PAGE})
        f = d.get("features", [])
        feats += f
        if len(f) < PAGE:
            break
        off += PAGE
    g = gpd.GeoDataFrame.from_features(feats, crs=4326)
    return g.rename(columns={f"LU{p}": "prev", f"LU{n}": "next", f"LABEL{p}": "label_prev",
                             f"LABEL{n}": "label_next", "ACRES": "acres"})  # fmt: skip


def main() -> None:
    config.LANDUSE_DIR.mkdir(parents=True, exist_ok=True)
    bbox = tuple(region.load_outline().to_crs(4326).total_bounds)
    for y0, y1, url, p, n in PERIODS:
        out = config.LANDUSE_DIR / f"njlulc_{y0}_{y1}.gpkg"
        if out.exists():
            print(f"{out.name}: exists, skipped")
            continue
        g = fetch_period(url, p, n, bbox)
        g["y0"], g["y1"] = y0, y1
        g.to_file(out, driver="GPKG")
        print(f"{out.name}: {len(g)} farmed-before polygons, {g.acres.sum():,.0f} ac, "
              f"{(g.prev != g.next).sum()} changed")


if __name__ == "__main__":
    main()
