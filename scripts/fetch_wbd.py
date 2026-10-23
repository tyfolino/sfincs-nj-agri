"""Download a side's domain HUC12s (NJ: + Gloucester's Great Egg HUC12s, for the coverage
check) from the USGS WBD service and write the ring.

Writes, with <s> = the side's file suffix ("" for NJ, "_de" for Delaware):
  data/region/huc12.gpkg     layer ``domain<s>`` (NJ: the 38, + ``great_egg_gloucester``;
                             DE: the 33)
  data/region/ring<s>.geojson   the dissolved domain, EPSG:32618, one polygon
  data/region/states_cb500k.gpkg      NJ/PA/DE/MD, Census cartographic (shoreline-clipped)
  data/region/model_outline<s>.geojson   the ring minus other states' land (region.py)

Usage:  python scripts/fetch_wbd.py [--side nj|de] [--overwrite]
"""

from __future__ import annotations

import argparse
import io
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import box

from agri_sfincs import config, domain, region
from agri_sfincs.net import arcgis_query, get

WBD_HUC12 = "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/6"
FIELDS = "huc12,name,areasqkm,states"
#: Census cartographic boundary states: clipped to the shoreline, so they are LAND.
CB_STATES = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip"
STATES = {"34": "NJ", "42": "PA", "10": "DE", "24": "MD"}


def fetch_states() -> gpd.GeoDataFrame:
    r = get(CB_STATES, timeout=300)
    with tempfile.TemporaryDirectory() as d:
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(d)
        st = gpd.read_file(next(Path(d).glob("*.shp")))
    return st[st.STATEFP.isin(list(STATES))][["STATEFP", "STUSPS", "geometry"]]


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
    ap.add_argument("--side", default="nj", choices=list(domain.SIDES))
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    sd = domain.side(a.side)
    ring_file = region.ring_file(a.side)
    if ring_file.exists() and not a.overwrite:
        raise SystemExit(f"{ring_file} exists; pass --overwrite")
    config.REGION_DIR.mkdir(parents=True, exist_ok=True)

    dom = fetch(list(sd.huc12))
    for code, name in sd.huc12.items():
        served = dom.loc[dom.huc12 == code, "name"].item()
        if served != name:
            print(f"  ⚠️ {code}: domain.py says {name!r}, WBD now says {served!r}")
    # one layer per side in the shared gpkg: write ours, keep the others
    dom.to_file(region.HUC12_FILE, layer=region.huc12_layer(a.side), driver="GPKG")
    if a.side == "nj":
        egg = fetch(list(domain.GREAT_EGG_GLOUCESTER))
        egg.to_file(region.HUC12_FILE, layer="great_egg_gloucester", driver="GPKG")
    parts = dom
    if sd.bay_huc12:  # the open-bay unit, clipped north (domain.DE_BAY_HUC12)
        bay = fetch([sd.bay_huc12]).to_crs(domain.EPSG)
        x0, y0 = Transformer.from_crs(4326, domain.EPSG, always_xy=True).transform(-76.5, sd.bay_max_lat)
        bay["geometry"] = bay.geometry.intersection(box(x0, y0 - 5e5, x0 + 5e5, y0))
        bay.to_file(region.HUC12_FILE, layer=f"bay{sd.files}", driver="GPKG")
        print(f"  bay unit {sd.bay_huc12} south of {sd.bay_max_lat} N: {bay.area.sum() / 1e6:.0f} km2")
        parts = pd.concat([dom.to_crs(domain.EPSG), bay], ignore_index=True)
    south = config.REGION_DIR / "de_canal_south.geojson"
    if a.side == "de" and south.exists():  # the canal unit south of the canal (split_canal_unit.py)
        cs = gpd.read_file(south).to_crs(domain.EPSG)
        print(f"  {domain.DE_CANAL_HUC12} south of the canal: {cs.area.sum() / 1e6:.0f} km2")
        parts = pd.concat([parts, cs[["huc12", "geometry"]]], ignore_index=True)

    ring = region.dissolve_ring(parts)
    gpd.GeoDataFrame({"name": [f"agri_ring{sd.files}"]}, geometry=[ring], crs=domain.EPSG).to_file(
        ring_file, driver="GeoJSON"
    )
    print(
        f"{len(dom)} domain HUC12s, WBD area {dom.areasqkm.sum():.0f} km2; "
        f"ring {ring.area / 1e6:.0f} km2, {len(ring.exterior.coords)} vertices"
    )
    print(f"wrote {region.HUC12_FILE} and {ring_file}")

    states = fetch_states()
    states.to_file(region.STATES_FILE, driver="GPKG")
    st = states.to_crs(domain.EPSG)
    foreign = st[st.STATEFP.isin(sd.foreign_fips)].geometry.union_all()
    for fp, ab in sd.foreign_fips.items():
        a_km2 = ring.intersection(st[st.STATEFP == fp].geometry.union_all()).area / 1e6
        print(f"  {ab} land inside the ring: {a_km2:.1f} km2 (removed)")
    outline = region.remove_foreign_land(ring, foreign)
    left = ring.difference(foreign).area - outline.area
    gpd.GeoDataFrame({"name": [f"agri_model_outline{sd.files}"]}, geometry=[outline],
                     crs=domain.EPSG).to_file(region.outline_file(a.side), driver="GeoJSON")  # fmt: skip
    print(f"model outline {outline.area / 1e6:.0f} km2 "
          f"(slivers dropped: {left / 1e6:.2f} km2); wrote {region.outline_file(a.side)}")  # fmt: skip


if __name__ == "__main__":
    main()
