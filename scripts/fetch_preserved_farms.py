"""NJ Farmland Preservation Program (SADC) preserved farms in the domain's three counties.

Source: SADC's public NJFPP_Preserved_Farms feature service on ArcGIS Online
(services.arcgis.com/gzSkSfQGxyX6dicF/.../NJFPP_Preserved_Farms/FeatureServer/0): farms preserved
by the SADC and its partners since 1983, current configuration. Fields include SADC_ID, PROGRAM,
ACRE_EASEMENT, DATE_CLOSED, FED_MONEY_USED_FLAG and NRCS_ID_. NO price paid. Polygons are
"approximate ... for planning purposes" (service metadata).

Queried by COUNTY in pages (service max 2000 records), geometry in EPSG:4326.

Writes data/easements/njfpp_preserved_farms.gpkg (layer "farms") and prints counts and
easement acres by county x program.

Usage:  python scripts/fetch_preserved_farms.py
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

import geopandas as gpd
import pandas as pd

from agri_sfincs import config, domain

URL = ("https://services.arcgis.com/gzSkSfQGxyX6dicF/arcgis/rest/services/NJFPP_Preserved_Farms/"
       "FeatureServer/0/query")  # fmt: skip
OUT = config.EASEMENT_DIR / "njfpp_preserved_farms.gpkg"
PAGE = 1000


def query(params: dict) -> dict:
    data = urllib.parse.urlencode({"f": "geojson", **params}).encode()
    with urllib.request.urlopen(urllib.request.Request(URL, data=data), timeout=120) as r:
        return json.load(r)


def fetch() -> gpd.GeoDataFrame:
    names = ",".join(f"'{n.upper()}'" for n in domain.COUNTIES.values())
    base = {"where": f"UPPER(COUNTY) IN ({names})", "outSR": 4326, "outFields": "*",
            "orderByFields": "OBJECTID"}  # fmt: skip
    feats, off = [], 0
    while True:
        f = query({**base, "resultOffset": off, "resultRecordCount": PAGE}).get("features", [])
        feats += f
        if len(f) < PAGE:
            break
        off += PAGE
    g = gpd.GeoDataFrame.from_features(feats, crs=4326)
    if "DATE_CLOSED" in g:  # epoch milliseconds
        g["DATE_CLOSED"] = pd.to_datetime(g["DATE_CLOSED"], unit="ms", errors="coerce")
    return g


def main() -> None:
    g = fetch()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    g.to_file(OUT, layer="farms", driver="GPKG")
    print(f"wrote {OUT}: {len(g)} polygons")
    print(g.groupby(["COUNTY", "PROGRAM"]).ACRE_EASEMENT.agg(["count", "sum"]).round(0).to_string())


if __name__ == "__main__":
    main()
