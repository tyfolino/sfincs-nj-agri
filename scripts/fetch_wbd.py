"""Download the domain HUC12s (+ Gloucester's Great Egg HUC12s, for the coverage check)
from the USGS WBD service and write the ring.

Writes:
  data/region/huc12.gpkg     layer ``domain`` (the 38) and ``great_egg_gloucester``
  data/region/ring.geojson   the dissolved domain, EPSG:32618, one polygon
  data/region/states_cb500k.gpkg      NJ/PA/DE, Census cartographic (shoreline-clipped)
  data/region/model_outline.geojson   the ring minus PA and DE land (region.py)

Usage:  python scripts/fetch_wbd.py [--overwrite]
"""

from __future__ import annotations

import argparse
import io
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd

from agri_sfincs import config, domain, region
from agri_sfincs.net import arcgis_query, get

WBD_HUC12 = "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/6"
FIELDS = "huc12,name,areasqkm,states"
#: Census cartographic boundary states: clipped to the shoreline, so they are LAND.
CB_STATES = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip"
FOREIGN = {"42": "PA", "10": "DE"}


def fetch_states() -> gpd.GeoDataFrame:
    r = get(CB_STATES, timeout=300)
    with tempfile.TemporaryDirectory() as d:
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(d)
        st = gpd.read_file(next(Path(d).glob("*.shp")))
    return st[st.STATEFP.isin([*FOREIGN, domain.STATE_FIPS])][["STATEFP", "STUSPS", "geometry"]]


def fetch(codes: list[str]) -> gpd.GeoDataFrame:
    where = "huc12 IN (" + ",".join(f"'{c}'" for c in codes) + ")"
    gdf = arcgis_query(WBD_HUC12, where, FIELDS)
    gdf.columns = [c.lower() if c != "geometry" else c for c in gdf.columns]
    missing = set(codes) - set(gdf["huc12"])
    if missing:
        raise RuntimeError(f"WBD returned no polygon for {sorted(missing)}")
    if gdf["huc12"].duplicated().any():
        raise RuntimeError("WBD returned duplicate HUC12 rows")
    return gdf.sort_values("huc12").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    if region.HUC12_FILE.exists() and not a.overwrite:
        raise SystemExit(f"{region.HUC12_FILE} exists; pass --overwrite")
    config.REGION_DIR.mkdir(parents=True, exist_ok=True)

    dom = fetch(domain.huc12_codes())
    for code, name in domain.HUC12.items():
        served = dom.loc[dom.huc12 == code, "name"].item()
        if served != name:
            print(f"  ⚠️ {code}: domain.py says {name!r}, WBD now says {served!r}")
    egg = fetch(list(domain.GREAT_EGG_GLOUCESTER))

    if region.HUC12_FILE.exists():
        region.HUC12_FILE.unlink()
    dom.to_file(region.HUC12_FILE, layer="domain", driver="GPKG")
    egg.to_file(region.HUC12_FILE, layer="great_egg_gloucester", driver="GPKG")

    ring = region.dissolve_ring(dom)
    gpd.GeoDataFrame({"name": ["agri_ring"]}, geometry=[ring], crs=domain.EPSG).to_file(
        region.RING_FILE, driver="GeoJSON"
    )
    print(
        f"{len(dom)} domain HUC12s, WBD area {dom.areasqkm.sum():.0f} km2; "
        f"ring {ring.area / 1e6:.0f} km2, {len(ring.exterior.coords)} vertices"
    )
    print(f"wrote {region.HUC12_FILE} and {region.RING_FILE}")

    states = fetch_states()
    states.to_file(region.STATES_FILE, driver="GPKG")
    st = states.to_crs(domain.EPSG)
    foreign = st[st.STATEFP.isin(FOREIGN)].geometry.union_all()
    for fp, ab in FOREIGN.items():
        a_km2 = ring.intersection(st[st.STATEFP == fp].geometry.union_all()).area / 1e6
        print(f"  {ab} land inside the ring: {a_km2:.1f} km2 (removed)")
    outline = region.remove_foreign_land(ring, foreign)
    left = ring.difference(foreign).area - outline.area
    gpd.GeoDataFrame({"name": ["agri_model_outline"]}, geometry=[outline],
                     crs=domain.EPSG).to_file(region.OUTLINE_FILE, driver="GeoJSON")  # fmt: skip
    print(f"model outline {outline.area / 1e6:.0f} km2 "
          f"(slivers dropped: {left / 1e6:.2f} km2); wrote {region.OUTLINE_FILE}")  # fmt: skip


if __name__ == "__main__":
    main()
