"""Delaware Land Use/Land Cover transition layers, farmed-before polygons (the NJDEP
counterpart is scripts/fetch_njlulc.py).

Delaware's FirstMap service (PlanningCadastre/DE_LULC, Delaware Modified Anderson codes, 3
digits) has one layer per edition, and the 2017 and 2022 layers carry the previous edition's
code, so each is a transition table:

  2012-2017  DE_LULC/MapServer/3   LULC_CODE2012 -> LULC_CODE2017
  2017-2022  DE_LULC/MapServer/4   LULC_CODE2017 -> LULC_CODE2022

Only polygons whose PREVIOUS code is agriculture (200-299) are kept, statewide (the fields are
clipped to the model domain later, agri_sfincs.fields). Paged by resultOffset (service max 2000).

Writes data/landuse/delulc_<y0>_<y1>.gpkg (EPSG:4326; columns prev, next, label_prev,
label_next, acres, county + the period) and prints counts. Usage:  python scripts/fetch_delulc.py
"""

from __future__ import annotations

import geopandas as gpd

from agri_sfincs import config, net

DE_LULC = "https://enterprise.firstmap.delaware.gov/arcgis/rest/services/PlanningCadastre/DE_LULC/MapServer"
PERIODS = [  # (y0, y1, layer url)
    (2012, 2017, f"{DE_LULC}/3"),
    (2017, 2022, f"{DE_LULC}/4"),
]
PAGE = 1000
M2_PER_ACRE = 4046.8564224


def fetch_period(url: str, p: str, n: str) -> gpd.GeoDataFrame:
    fields = [f"LULC_CODE{p}", f"LULC_CODE{n}", f"LULC_CATEGORY{p}", f"LULC_CATEGORY{n}", "COUNTY"]
    base = {"where": f"LULC_CODE{p} >= 200 AND LULC_CODE{p} < 300", "outSR": 4326,
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
    g = g.rename(columns={f"LULC_CODE{p}": "prev", f"LULC_CODE{n}": "next", f"LULC_CATEGORY{p}": "label_prev",
                          f"LULC_CATEGORY{n}": "label_next", "COUNTY": "county"})  # fmt: skip
    g["acres"] = g.to_crs(5070).area / M2_PER_ACRE
    return g


def main() -> None:
    config.LANDUSE_DIR.mkdir(parents=True, exist_ok=True)
    for y0, y1, url in PERIODS:
        out = config.LANDUSE_DIR / f"delulc_{y0}_{y1}.gpkg"
        if out.exists():
            print(f"{out.name}: exists, skipped")
            continue
        g = fetch_period(url, str(y0), str(y1))
        g["y0"], g["y1"] = y0, y1
        g.to_file(out, driver="GPKG")
        print(f"{out.name}: {len(g)} farmed-before polygons, {g.acres.sum():,.0f} ac, "
              f"{(g.prev != g.next).sum()} changed")


if __name__ == "__main__":
    main()
