"""Per county, the fixed share of cropland in the FEMA 1% floodplain (and a relief proxy).

Fork 1 identifies "does flooding add damage beyond rain" from counties that differ in a
FIXED flood-prone cropland share. This computes that share for every county in
data/fork1/counties.gpkg (scripts/fork1_counties.py).

Sources (all public, fetched once and cached on scratch under data/floodplain/):
* **FEMA NFHL** (hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer):
  layer 28 S_FLD_HAZ_AR "Flood Hazard Zones" with ``SFHA_TF = 'T'`` (zones A, AE, AH,
  AO, AR, A99, V, VE: the 1% annual-chance Special Flood Hazard Area), queried per state
  by DFIRM_ID prefix, generalized to ~10 m (``maxAllowableOffset``);
  layer 0 "NFHL Availability" (the footprint of digital FIRM data), for coverage;
  layer 3 S_FIRM_PAN, the newest/oldest panel effective date per DFIRM, for map vintage.
  The service resets connections now and then; ``agri_sfincs.net.get`` retries.
* **Cropland:** the 2023 CDL (scripts/fetch_cdl.py --fips), cropland =
  ``agri_sfincs.cdl.CROPLAND``, 30 m, EPSG:5070. Static: one year for the whole panel.
* **Relief proxy** ("low-lying", a cheap HAND stand-in): USGS 3DEP elevation
  (elevation.nationalmap.gov ImageServer exportImage) at 90 m on a grid aligned with
  the CDL (3 x 3 CDL pixels per DEM cell); relative elevation = DEM minus the lowest
  DEM value within 1 km (``agri_sfincs.panel.relative_elevation``); NoData (open water
  offshore) counts as 0 m. ``share_low2m`` = cropland < 2 m above that local low,
  ``share_low1m`` likewise. It marks valley bottoms AND broad flats, so it is a
  robustness variant, not a floodplain map.

Per county (``agri_sfincs.panel.cropland_shares``):
  crop_km2         cropland area
  nfhl_coverage    share of cropland inside the NFHL availability footprint
  share_sfha       cropland in the 1% SFHA / all cropland
  share_low1m/2m   relief proxy shares
  share_flood      the share Fork 1 uses: share_sfha where nfhl_coverage >= 0.9, else
                   share_low2m x mean(share_sfha)/mean(share_low2m) of the well-covered
                   counties (coastal plain and upland separately)
  share_source     "nfhl", "fallback: low-relief x k (coverage 0.xx)" or "no cropland"
  dfirm_ids, eff_date_max, eff_date_min   FIRM databases touching the county and their
                   panel effective-date range (newest/oldest), for vintage

Writes:
  data/floodplain/nfhl_sfha_<ST>.gpkg, nfhl_availability.gpkg, dem90/<fips>.tif (bulk)
  data/fork1/flood_prone_share.csv

Usage:  python scripts/flood_prone_share.py [--cdl-year 2023] [--coverage-min 0.9]
"""

from __future__ import annotations

import argparse
import json
import math

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from fetch_cdl import cdl_path
from rasterio import features
from rasterio.io import MemoryFile
from rasterio.windows import Window

from agri_sfincs import cdl, config
from agri_sfincs.net import get
from agri_sfincs.panel import cropland_shares, relative_elevation

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
DEM = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
COUNTIES = config.FORK1_DIR / "counties.gpkg"
OUT = config.FORK1_DIR / "flood_prone_share.csv"
FP = config.FLOODPLAIN_DIR
DEM_FACTOR = 3  # 90 m DEM cell = 3 x 3 CDL pixels
PAD_PX = 36  # >= 1 km of 30 m pixels, a multiple of DEM_FACTOR
LOW_RADIUS_M = 1000.0


def query_geojson(layer_url: str, params: dict, page: int = 1000) -> gpd.GeoDataFrame:
    """All features of an ArcGIS layer as EPSG:4326, paged by resultOffset (ordered by
    OBJECTID so pages do not overlap)."""
    frames, off = [], 0
    while True:
        p = {"outSR": 4326, "f": "geojson", "returnGeometry": "true", "orderByFields": "OBJECTID",
             "resultOffset": off, "resultRecordCount": page} | params  # fmt: skip
        j = get(f"{layer_url}/query", p, timeout=600).json()
        if "error" in j:
            raise RuntimeError(f"{layer_url}: {j['error']}")
        feats = j.get("features", [])
        if feats:
            frames.append(gpd.GeoDataFrame.from_features(feats, crs=4326))
        more = j.get("exceededTransferLimit") or j.get("properties", {}).get("exceededTransferLimit")
        if not feats or not more:
            break
        off += len(feats)
        if off % 10000 < page:
            print(f"    {off:,} features", flush=True)
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326)


def fetch_sfha(state: str, abbr: str) -> gpd.GeoDataFrame:
    dest = FP / f"nfhl_sfha_{abbr}.gpkg"
    if not dest.exists():
        print(f"  NFHL SFHA {abbr} ...", flush=True)
        g = query_geojson(f"{NFHL}/28", {
            "where": f"SFHA_TF = 'T' AND DFIRM_ID LIKE '{state}%'",
            "outFields": "DFIRM_ID,FLD_ZONE", "maxAllowableOffset": 1e-4, "geometryPrecision": 6})  # fmt: skip
        g = g[g.geometry.notna() & ~g.geometry.is_empty]
        g.to_crs(5070).to_file(dest, driver="GPKG")
        print(f"  wrote {dest.name} ({len(g):,} polygons)", flush=True)
    return gpd.read_file(dest)


def fetch_availability(bbox) -> gpd.GeoDataFrame:
    dest = FP / "nfhl_availability.gpkg"
    if not dest.exists():
        g = query_geojson(f"{NFHL}/0", {
            "where": "1=1", "outFields": "STUDY_ID", "maxAllowableOffset": 5e-4,
            "geometry": ",".join(f"{v:.4f}" for v in bbox), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"}, page=200)  # fmt: skip
        g.to_crs(5070).to_file(dest, driver="GPKG")
        print(f"  wrote {dest.name} ({len(g):,} polygons)", flush=True)
    return gpd.read_file(dest)


def panel_dates(state: str) -> pd.DataFrame:
    """DFIRM_ID -> newest / oldest FIRM panel effective date (S_FIRM_PAN)."""
    stats = [{"statisticType": t, "onStatisticField": "EFF_DATE", "outStatisticFieldName": n}
             for t, n in (("max", "eff_max"), ("min", "eff_min"))]  # fmt: skip
    j = get(f"{NFHL}/3/query", {"where": f"DFIRM_ID LIKE '{state}%'", "f": "json",
                                "outStatistics": json.dumps(stats),
                                "groupByFieldsForStatistics": "DFIRM_ID"}, timeout=300).json()  # fmt: skip
    d = pd.DataFrame([f["attributes"] for f in j.get("features", [])])
    if d.empty:
        return pd.DataFrame(columns=["DFIRM_ID", "eff_max", "eff_min"])
    for c in ("eff_max", "eff_min"):
        t = pd.to_datetime(d[c], unit="ms")
        d[c] = t.where(t.dt.year < 2100).dt.date  # 9999-09-09 is FEMA's "no date"
    return d


def fetch_dem(fips: str, bounds, shape) -> np.ndarray:
    """3DEP elevation (m) on ``shape`` cells exactly covering ``bounds`` (EPSG:5070)."""
    dest = FP / "dem90" / f"{fips}.tif"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = get(DEM, {"bbox": ",".join(f"{v:.1f}" for v in bounds), "bboxSR": 5070,
                      "imageSR": 5070, "size": f"{shape[1]},{shape[0]}", "format": "tiff",
                      "pixelType": "F32", "interpolation": "RSP_BilinearInterpolation",
                      "f": "image"}, timeout=600)  # fmt: skip
        with MemoryFile(r.content) as mf, mf.open() as src:  # proves it is a raster
            if src.shape != tuple(shape):
                raise RuntimeError(f"DEM {fips}: got {src.shape}, asked {shape}")
        part = dest.with_suffix(".tif.part")
        part.write_bytes(r.content)
        part.rename(dest)
    with rasterio.open(dest) as src:
        z = src.read(1).astype("float64")
        nod = src.nodata
    bad = ~np.isfinite(z) | (z < -500) | ((z == nod) if nod is not None else False)
    z[bad] = 0.0  # open water offshore: sea level
    return z


def county_row(c, src, sfha, avail) -> dict:
    """Shares for one county from the state's CDL ``src``."""
    w0, s0, e0, n0 = c.geometry.bounds
    inv = ~src.transform
    col0, row0 = inv * (w0, n0)
    col1, row1 = inv * (e0, s0)
    col0, row0 = math.floor(col0) - PAD_PX, math.floor(row0) - PAD_PX
    ncol = math.ceil(col1) + PAD_PX - col0
    nrow = math.ceil(row1) + PAD_PX - row0
    ncol += -ncol % DEM_FACTOR
    nrow += -nrow % DEM_FACTOR
    win = Window(col0, row0, ncol, nrow)
    land = src.read(1, window=win, boundless=True, fill_value=0)
    tf = src.window_transform(win)
    shape = land.shape
    bounds = rasterio.windows.bounds(win, src.transform)

    def mask(gdf) -> np.ndarray:
        sub = gdf.iloc[gdf.sindex.query(c.geometry, predicate="intersects")]
        if not len(sub):
            return np.zeros(shape, bool)
        return features.rasterize(((g, 1) for g in sub.geometry), out_shape=shape,
                                  transform=tf, fill=0, dtype="uint8").astype(bool)  # fmt: skip

    in_county = features.rasterize([(c.geometry, 1)], out_shape=shape, transform=tf,
                                   fill=0, dtype="uint8").astype(bool)  # fmt: skip
    dem = fetch_dem(c.fips, bounds, (nrow // DEM_FACTOR, ncol // DEM_FACTOR))
    rel = relative_elevation(dem, LOW_RADIUS_M / (30.0 * DEM_FACTOR))
    rel30 = np.repeat(np.repeat(rel, DEM_FACTOR, axis=0), DEM_FACTOR, axis=1)
    zones = {"sfha": mask(sfha), "avail": mask(avail), "low1m": rel30 < 1.0, "low2m": rel30 < 2.0}
    sub = sfha.iloc[sfha.sindex.query(c.geometry, predicate="intersects")]
    r = cropland_shares(land, in_county, zones, cdl.CROPLAND)
    return {"fips": c.fips, "crop_km2": r.pop("n_crop") * 9e-4, **r,
            "dfirm_ids": ";".join(sorted(set(sub.DFIRM_ID)))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cdl-year", type=int, default=2023)
    ap.add_argument("--coverage-min", type=float, default=0.9)
    a = ap.parse_args()
    FP.mkdir(parents=True, exist_ok=True)
    counties = gpd.read_file(COUNTIES)
    avail = fetch_availability(tuple(counties.to_crs(4326).total_bounds))
    rows, dates = [], []
    for st, cs in counties.groupby("state"):
        abbr = cs.state_abbr.iloc[0]
        sfha = fetch_sfha(st, abbr)
        dates.append(panel_dates(st))
        with rasterio.open(cdl_path(a.cdl_year, st)) as src:
            cs = cs.to_crs(src.crs)
            for c in cs.itertuples():
                rows.append(county_row(c, src, sfha, avail))
        print(f"  {abbr}: {len(cs)} counties done", flush=True)
    d = pd.DataFrame(rows).rename(columns={"share_avail": "nfhl_coverage"})
    dt = pd.concat(dates).set_index("DFIRM_ID")
    ids = d.dfirm_ids.str.split(";")
    def span(col, fn):
        v = dt[col].dropna()
        return [fn((v[i] for i in L if i in v.index), default=None) for L in ids]

    d["eff_date_max"] = span("eff_max", max)
    d["eff_date_min"] = span("eff_min", min)
    d = counties[["fips", "state_abbr", "name", "coastal_plain"]].merge(d, on="fips")
    good = d.nfhl_coverage >= a.coverage_min
    # Fallback in SFHA units: scale the relief share by the SFHA/relief ratio of
    # well-covered counties of the same physiography.
    d["share_flood"] = d.share_sfha.where(good)
    d["share_source"] = np.where(good, "nfhl", "")
    for cp in (True, False):
        ref = d[good & (d.coastal_plain == cp) & (d.crop_km2 > 1)]
        k = ref.share_sfha.mean() / ref.share_low2m.mean() if len(ref) else np.nan
        m = ~good & (d.coastal_plain == cp)
        d.loc[m, "share_flood"] = (d.share_low2m[m] * k).clip(upper=1.0)
        d.loc[m, "share_source"] = [f"fallback: low-relief x {k:.2f} (coverage {v:.2f})"
                                    for v in d.nfhl_coverage[m]]  # fmt: skip
    d.loc[~(d.crop_km2 > 0), "share_source"] = "no cropland"
    d.to_csv(OUT, index=False, float_format="%.5g")
    print(f"wrote {OUT} ({len(d)} counties; {int((~good).sum())} on the fallback)")
    print(d.groupby(["state_abbr", "coastal_plain"])[["share_sfha", "share_low2m", "nfhl_coverage"]]
          .median().round(3))  # fmt: skip


if __name__ == "__main__":
    main()
