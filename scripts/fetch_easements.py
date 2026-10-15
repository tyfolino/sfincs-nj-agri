"""NRCS conservation easement boundaries around Delaware Bay (both shores).

Source: NRCS Stewardship Lands Inventory map service, layer 1 "Easement Boundaries"
(apps.geo.fpac.usda.gov/nrcs-geodata/rest/services/easements/easements/MapServer): ACEP-ALE,
ACEP-WRE, WRP, EWRP, GRP, HFRP, FRPP... Fields: state, county, program, adminfips,
method (how the boundary was mapped), nest_easement_duration, ids. NO enrollment or closing
date, and no agreement number, so timing must come from elsewhere (imagery, NCED / PAD-US).

Queried by envelope BBOX in pages (service max 2000 records), geometry in EPSG:4326.
String fields arrive space-padded to 255 and are stripped.

Writes data/easements/nrcs_easements.gpkg (layer "boundaries") and prints counts by state x
program and, for the study counties, by county x program with area.

Usage:  python scripts/fetch_easements.py
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

import geopandas as gpd
import pandas as pd

from agri_sfincs import config, domain

URL = ("https://apps.geo.fpac.usda.gov/nrcs-geodata/rest/services/easements/easements/"
       "MapServer/1/query")  # fmt: skip
BBOX = (-76.0, 38.4, -74.4, 40.1)  # Delaware Bay, both shores, all of Delaware
OUT = config.EASEMENT_DIR / "nrcs_easements.gpkg"
PAGE = 1000


def query(params: dict) -> dict:
    data = urllib.parse.urlencode({"f": "geojson", **params}).encode()
    with urllib.request.urlopen(urllib.request.Request(URL, data=data), timeout=120) as r:
        return json.load(r)


def fetch(bbox=BBOX) -> gpd.GeoDataFrame:
    base = {"where": "1=1", "geometry": ",".join(map(str, bbox)),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
            "orderByFields": "objectid"}  # fmt: skip
    feats, off = [], 0
    while True:
        d = query({**base, "resultOffset": off, "resultRecordCount": PAGE})
        f = d.get("features", [])
        feats += f
        if len(f) < PAGE:
            break
        off += PAGE
    g = gpd.GeoDataFrame.from_features(feats, crs=4326)
    for c in g.columns:
        if c != "geometry" and pd.api.types.is_string_dtype(g[c]):
            g[c] = g[c].str.strip()
    return g


def main() -> None:
    g = fetch()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    g.to_file(OUT, layer="boundaries", driver="GPKG")
    g["km2"] = g.to_crs(domain.EPSG).area / 1e6
    print(f"wrote {OUT}: {len(g)} polygons")
    print(g.groupby(["state", "program"]).km2.agg(["count", "sum"]).round(2).to_string())
    s = g[g.adminfips.isin(domain.COUNTIES)]
    print("\nstudy counties:")
    print(s.groupby(["county", "program"]).km2.agg(["count", "sum"]).round(3).to_string())


if __name__ == "__main__":
    main()
