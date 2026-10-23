"""Dams, levees and related structures inside the ring, plus NJDEP's head-of-tide line
and NHD waterbodies (lakes need real water levels; the DEM shows them as flat beds).

Sources (all queried by the ring's lon/lat bbox, then clipped to the ring + 1 km):
  NID   USACE National Inventory of Dams (points; heights, spillway, storage; NO crest
        elevation — that comes from the DEM in step 2)
  NLD   USACE National Levee Database: alignment lines, leveed areas, closure
        structures, pipe gates, pipes, pump stations
  NJDEP Features/Hydrography: Head of Tide (2), Waterbody 2015 (NHD) (33)

What came back, 2026-10-02: NLD DOES hold the bayshore meadow banks / salt-hay dikes
(~113 km of alignment: Jones Island Road, Sayres Neck, Port Norris, Locust Island
"Thorofare Meadow Bank Company", Hancocks Bridge ...; mostly private sponsors) plus
PSEG's Artificial Island levee and the Gibbstown/Repauno industrial levees. NLD pipe
gates (13) are the only tide-gate-like records. The ring+1km clip also catches a few
PA-side lines (Tinicum / John Heinz refuge). NJDEP's waterbody LEVELELEV field is
EMPTY for every lake here, so lake levels must come from the DEM or the dam heights.

Delaware (``--side de``): NID and NLD, and since NLD holds almost none of its banks (2
alignments, 1 leveed area in the DE ring), USFWS NWI wetlands with the "h" special modifier
(diked / impounded: the refuge pools, diked marsh, mill ponds) as ``nwi_impounded``.

Writes data/structures/structures.gpkg (Delaware: structures_de.gpkg), one layer per source (EPSG:4326), and prints counts. Layers that come back empty
are written as empty and SAID so.

Usage:  python scripts/fetch_structures.py [--side nj|de] [--overwrite]
"""

from __future__ import annotations

import argparse

import geopandas as gpd

from agri_sfincs import config, domain, region
from agri_sfincs.net import arcgis_query

USACE = "https://geospatial.sec.usace.army.mil/dls/rest/services"
NJDEP = "https://mapsdep.nj.gov/arcgis/rest/services/Features"
LAYERS = {
    "nid_dams": f"{USACE}/NID/National_Inventory_of_Dams_Public_Service/FeatureServer/0",
    "nld_alignment": f"{USACE}/NLD/Public/FeatureServer/7",
    "nld_leveed_areas": f"{USACE}/NLD/Public/FeatureServer/16",
    "nld_closures": f"{USACE}/NLD/Public/FeatureServer/10",
    "nld_pipe_gates": f"{USACE}/NLD/Public/FeatureServer/6",
    "nld_pipes": f"{USACE}/NLD/Public/FeatureServer/8",
    "nld_pump_stations": f"{USACE}/NLD/Public/FeatureServer/4",
    "njdep_head_of_tide": f"{NJDEP}/Hydrography/MapServer/2",
    "njdep_waterbody_2015": f"{NJDEP}/Hydrography/MapServer/33",
    "nwi_impounded": "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0",
}
#: layers fetched for one side only
ONLY_SIDE = {"njdep_head_of_tide": "nj", "njdep_waterbody_2015": "nj", "nwi_impounded": "de"}
#: Per-layer query options. The waterbody layer holds 9,157 features in the bbox,
#: mostly marsh and tiny ponds, and a full page of its polygons times out. Keep
#: lakes/ponds (FTYPE 390) and reservoirs (436) of 1 ha or more, in small pages.
OPTIONS = {
    "njdep_waterbody_2015": {
        "where": "FTYPE IN (390, 436) AND AREASQKM >= 0.01",
        "page_size": 200,
    },
    "nwi_impounded": {"where": "ATTRIBUTE LIKE '%h'", "page_size": 500},
}
CLIP_PAD_M = 1000.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--only", nargs="*", help="fetch just these layers")
    ap.add_argument("--side", default="nj", choices=list(domain.SIDES))
    a = ap.parse_args()
    OUT = config.structures_file(a.side)
    if OUT.exists() and not (a.overwrite or a.only):
        raise SystemExit(f"{OUT} exists; pass --overwrite (or --only LAYER ...)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists() and not a.only:
        OUT.unlink()

    ring = region.load_ring(a.side)
    bbox = tuple(ring.to_crs(4326).total_bounds)
    clip = ring.to_crs(domain.EPSG).buffer(CLIP_PAD_M).to_crs(4326)
    for name, url in LAYERS.items():
        if a.only and name not in a.only:
            continue
        if ONLY_SIDE.get(name, a.side) != a.side:
            continue
        gdf = arcgis_query(url, bbox=bbox, **OPTIONS.get(name, {}))
        n_box = len(gdf)
        if n_box:
            gdf = gpd.clip(gdf, clip)
        gdf.to_file(OUT, layer=name, driver="GPKG")
        print(f"  {name:22s} {n_box:5d} in bbox -> {len(gdf):5d} in ring+1km", flush=True)

    dams = gpd.read_file(OUT, layer="nid_dams")
    if len(dams):
        cols = [c for c in ("NIDID", "NAME", "RIVER_OR_STREAM", "NID_HEIGHT",
                            "HYDRAULIC_HEIGHT", "NORMAL_STORAGE", "SURFACE_AREA",
                            "DRAINAGE_AREA", "SPILLWAY_TYPE", "SPILLWAY_WIDTH")
                if c in dams.columns]  # fmt: skip
        big = dams.sort_values("SURFACE_AREA", ascending=False)[cols].head(25)
        print("\nLargest dams by surface area:\n" + big.to_string(index=False))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
