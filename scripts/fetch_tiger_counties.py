"""Download New Jersey county boundaries (Census TIGERweb) to data/region/counties.gpkg.

Columns: ``fips`` (5-digit), ``name`` (e.g. "Salem"), geometry (EPSG:4326).

Usage:  python scripts/fetch_tiger_counties.py [--overwrite]
"""

from __future__ import annotations

import argparse

from agri_sfincs import config, domain, region
from agri_sfincs.net import arcgis_query

TIGER_COUNTIES = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/"
    "MapServer/1"
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    if region.COUNTIES_FILE.exists() and not a.overwrite:
        raise SystemExit(f"{region.COUNTIES_FILE} exists; pass --overwrite")
    config.REGION_DIR.mkdir(parents=True, exist_ok=True)

    gdf = arcgis_query(TIGER_COUNTIES, f"STATE='{domain.STATE_FIPS}'", "STATE,COUNTY,NAME")
    gdf["fips"] = gdf["STATE"] + gdf["COUNTY"]
    gdf["name"] = gdf["NAME"].str.replace(" County", "", regex=False)
    gdf = gdf[["fips", "name", "geometry"]].sort_values("fips").reset_index(drop=True)
    if len(gdf) != 21:
        raise RuntimeError(f"expected NJ's 21 counties, got {len(gdf)}")
    for fips, name in {**domain.COUNTIES, **domain.COUNTIES_FRINGE}.items():
        if gdf.loc[gdf.fips == fips, "name"].tolist() != [name]:
            raise RuntimeError(f"county {fips} is not {name!r} in TIGER")
    gdf.to_file(region.COUNTIES_FILE, driver="GPKG")
    print(f"wrote {region.COUNTIES_FILE} ({len(gdf)} counties)")


if __name__ == "__main__":
    main()
