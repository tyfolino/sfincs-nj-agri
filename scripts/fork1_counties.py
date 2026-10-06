"""County polygons for the Fork 1 states, each flagged coastal plain or not.

Fork 1 (plan compressed-humming-eclipse.md) pools county x month crop-insurance losses
across NJ, DE, MD, VA and NC. This writes the county frame every other Fork 1 script
uses:

* polygons: Census TIGERweb State_County layer 1 (``STATE`` in the list), simplified to
  ~50 m in CONUS Albers (EPSG:5070; enough for 30 m CDL masks and 4 km PRISM weights);
  VA independent cities are their own "counties", as in RMA's county codes;
* ``eco_l3``/``eco_l3_name``: the EPA Level III ecoregion (EPA ORD MapServer,
  "Level III Ecoregion Polygons", one multipart polygon per ecoregion) holding the
  county's representative point;
* ``coastal_plain``: that ecoregion is 63 Middle Atlantic Coastal Plain, 65
  Southeastern Plains or 84 Atlantic Coastal Pine Barrens (the NJ Pine Barrens);
  a centroid rule, so a county that straddles the Fall Line goes by its middle.

Writes data/fork1/counties.gpkg (fips, state, state_abbr, name, area_km2, eco_l3,
eco_l3_name, coastal_plain; EPSG:5070).

Usage:  python scripts/fork1_counties.py [--states NJ,DE,MD,VA,NC] [--overwrite]
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import pandas as pd
from fetch_rma_col import parse_states

from agri_sfincs import config
from agri_sfincs.net import arcgis_query

TIGER_COUNTIES = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/"
    "MapServer/1"
)
EPA_L3 = (
    "https://geodata.epa.gov/arcgis/rest/services/ORD/"
    "USEPA_Ecoregions_Level_III_and_IV/MapServer/11"
)
#: Level III ecoregions counted as Atlantic coastal plain.
COASTAL_PLAIN_L3 = {"63", "65", "84"}
OUT = config.FORK1_DIR / "counties.gpkg"
SIMPLIFY_M = 50.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--states", help="comma list of abbreviations (default: NJ,DE,MD,VA,NC)")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    if OUT.exists() and not a.overwrite:
        raise SystemExit(f"{OUT} exists; pass --overwrite")
    states = parse_states(a.states)
    abbr_of = {c: ab for ab, c in states.items()}
    codes = ",".join(f"'{c}'" for c in states.values())
    gdf = arcgis_query(TIGER_COUNTIES, f"STATE IN ({codes})", "STATE,COUNTY,NAME",
                       page_size=25)  # fmt: skip
    gdf["fips"] = gdf.STATE + gdf.COUNTY
    gdf["state"] = gdf.STATE
    gdf["state_abbr"] = gdf.STATE.map(abbr_of)
    gdf["name"] = gdf.NAME
    gdf = gdf[["fips", "state", "state_abbr", "name", "geometry"]].to_crs(5070)
    gdf = gdf.dissolve("fips", as_index=False, aggfunc="first")  # multipart counties
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_M)
    gdf["area_km2"] = gdf.geometry.area / 1e6

    # One multipart polygon per ecoregion (its STATE_NAME is just the first state), so
    # select by the counties' bounding box, not by state name.
    bbox = tuple(gdf.to_crs(4326).total_bounds)
    eco = arcgis_query(EPA_L3, "1=1", "US_L3CODE,US_L3NAME", bbox=bbox, page_size=2).to_crs(5070)
    pts = gpd.GeoDataFrame(gdf[["fips"]], geometry=gdf.geometry.representative_point(),
                           crs=gdf.crs)  # fmt: skip
    j = gpd.sjoin(pts, eco[["US_L3CODE", "US_L3NAME", "geometry"]], how="left",
                  predicate="within").drop_duplicates("fips")  # fmt: skip
    # A representative point on a coastline sliver can miss every polygon; take the nearest.
    miss = j.US_L3CODE.isna()
    if miss.any():
        near = gpd.sjoin_nearest(pts[pts.fips.isin(j.fips[miss])],
                                 eco[["US_L3CODE", "US_L3NAME", "geometry"]]).drop_duplicates("fips")  # fmt: skip
        j = pd.concat([j[~miss], near])
    j = j.set_index("fips")
    gdf["eco_l3"] = gdf.fips.map(j.US_L3CODE).astype(str)
    gdf["eco_l3_name"] = gdf.fips.map(j.US_L3NAME)
    gdf["coastal_plain"] = gdf.eco_l3.isin(COASTAL_PLAIN_L3)
    gdf = gdf.sort_values("fips").reset_index(drop=True)
    config.FORK1_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT, driver="GPKG")
    by = gdf.groupby("state_abbr").agg(n=("fips", "size"), coastal=("coastal_plain", "sum"))
    print(f"wrote {OUT} ({len(gdf)} counties)\n{by}")


if __name__ == "__main__":
    main()
