"""Inputs for the river-bed burn (FINDINGS §11): chart soundings, flowlines, gauge
cross-sections and tidal datums. Network only; ``build_riverbeds.py`` reads the cache.

    python scripts/fetch_channels.py [enc] [nhd] [usgs] [datums] [ehydro] [nos] [csb] [--side de] [--overwrite]

Delaware (``--side de``): the same stages over the DE ring, into data/channels/de/ (NOS
surveys stay shared in data/channels/nos/).

Stages (all by default), everything under ``data/channels/`` (gitignored):

enc     NOAA ENC cells (charts.noaa.gov, S-57). The product catalog ``ENCProdCat.xml``
        holds every cell's coverage polygon; every ACTIVE cell whose coverage meets the
        ring is downloaded (``enc/raw/``), and its SOUNDG / DEPARE / DEPCNT / DRGARE /
        LNDARE (land, for the tidal-reach mouths) features inside the ring + 1 km go to ``enc_ring.gpkg`` (EPSG:4326; soundings
        are split into points, ``depth_m`` = metres below the cell's sounding datum, with
        the cell name, compilation scale and SDAT code). The shared env's GDAL has the
        S57 driver; updates (.001 ...) are applied.
nhd     NHDPlus HR (hydro.nationalmap.gov NHDPlus_HR MapServer): network flowlines with
        ``totdasqkm`` >= ``MIN_DA_KM2`` (layer 3) and NHDArea StreamRiver polygons
        (layer 8, ftype 460) and NHDWaterbody lakes/reservoirs (layer 9, ftype 390/436)
        in the ring bbox -> ``nhdplus_hr.gpkg``. With ``--nhd-gdb`` (the map service timed out
        over Delaware, 504, 2026-10-23) the same layers and columns come from the staged
        NHDPlus HR HU4 0204 file geodatabase (``NHD_GDB``, downloaded once to
        config.DATA_BULK/nhdplus/): NHDFlowline + NHDPlusFlowlineVAA + NHDPlusEROMMA (qama).
usgs    Every USGS ``channel-measurements`` row in the ring bbox (all sites, incl. the
        miscellaneous-measurement ones), the ``field-measurements`` mean gage height of
        the same field visits at the continuous stream gauges, and monitoring-location
        metadata (drainage area, gauge datum altitude) -> ``usgs_channel_measurements.csv``,
        ``usgs_gage_heights.csv``, ``usgs_sites.csv``.
ehydro  USACE eHydro (Philadelphia District) surveys of every channel named in
        ``domain.TIDAL_REACHES[...]["ehydro"]`` (Maurice River, Salem River): the survey
        index (``ehydro/index.csv``: id, date, type, bbox) from the eHydro_Survey_Data
        FeatureServer, and every survey ZIP, unpacked to ``ehydro/<id>/``. User,
        2026-10-05: where a survey exists it REPLACES the ENC soundings;
        build_riverbeds.py picks the survey per reach.
nos     NCEI NOS hydrographic surveys named in ``domain.TIDAL_REACHES[...]["nos"]`` (HYD93
        XYZ, data.ngdc.noaa.gov .../nos/coast/<range>/<id>/GEODAS/<id>.a93.gz) -> ``nos/``.
        Fetched by hand for e9 (2026-10-20); a stage since the v2 beds (2026-10-23).
csb     NCEI crowdsourced bathymetry (CSB, IHO DCDB): the tracks (gis.ngdc.noaa.gov csb
        MapServer) that cross each tidal reach's channel (``riverbed_centrelines.gpkg``,
        kind "tidal", buffered ``CSB_HALF_M``; so build_riverbeds.py must have run once),
        their point files from the public S3 bucket, kept inside the buffer, then reduced
        to MLLW: depth + ``CSB_DRAFT_M`` (the transducer sits ~0.3-1 m down) - the observed
        6-min water level (MLLW) at the CO-OPS gauge nearest the reach's mouth at the
        sounding's time (``CSB_TIDE``). The tide in a creek lags and differs from the bay
        gauge's by ~0.1-0.3 m, which the running median partly averages out. Soundings with
        no gauge record within 30 min are dropped -> ``csb/<reach>.csv`` (lon, lat,
        depth_mllw_m, depth_raw_m, wl_mllw_m, station, time_utc, provider, platform, track).
        Method: nj_bight_sfincs logs/cohansey_sources_2026-10-22/csb_tide_reduce.py.
datums  NOAA CO-OPS: datums of every station with published datums in the ring bbox
        (+ the three tide-prediction reference stations) and tide-prediction offsets
        of every subordinate station -> ``coops_datums.csv``, ``coops_offsets.csv``.
        VDatum is NOT used: its API answers 412 (or -999999) on every tributary point
        tried here (Bivalve, Greenwich, Hancocks Bridge, Salem, Millville, Bridgeton),
        as bight found on the tidal Delaware (bight FINDINGS 54g).

The ENC sounding reader and the channel-measurement depth rule follow nj_bight_sfincs
``scripts/build_riverbeds_v4.py`` (``_enc_points``) and ``build_inland_water_v4.py``
(``gauge_mean_depth``); copied, not imported.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import warnings
import xml.etree.ElementTree as ET
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from agri_sfincs import config, domain, region, riverbed, usgs_ogc
from agri_sfincs.net import arcgis_form_query, arcgis_query, download, get

OUT = config.CHANNELS_DIR
SIDE = "nj"
ENC_CATALOG = "https://www.charts.noaa.gov/ENCs/ENCProdCat.xml"
ENC_LAYERS = ("SOUNDG", "DEPARE", "DEPCNT", "DRGARE", "LNDARE")
NHDPLUS = "https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer"
MIN_DA_KM2 = 5.0
FLOW_FIELDS = (
    "nhdplusid,gnis_name,ftype,fcode,totdasqkm,hydroseq,dnhydroseq,levelpathi,"
    "terminalpa,streamorde,pathlength,lengthkm,divergence,startflag,qama"
)
COOPS = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi"
EHYDRO = "https://ehydroprod.blob.core.usgovcloudapi.net/ehydro-surveys/CENAP/{sid}.ZIP"
EHYDRO_INDEX = (
    "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/eHydro_Survey_Data/FeatureServer/0"
)
#: Tide-prediction reference stations the subordinate stations here are tied to.
COOPS_REFS = ("8557380", "8551910", "8545240")
NOS_URL = "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/{rng}/{sid}/GEODAS/{sid}.a93.gz"
CSB_TRACKS = "https://gis.ngdc.noaa.gov/arcgis/rest/services/csb/MapServer/1"
CSB_POINTS = "https://noaa-dcdb-bathymetry-pds.s3.amazonaws.com/csb/csv/{y}/{m}/{d}/{stem}_pointData.csv"
COOPS_DATA = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
CSB_HALF_M = 150.0
CSB_DRAFT_M = 0.5
#: CO-OPS gauges with observed water levels that a reach's CSB soundings may be reduced with
CSB_TIDE = ("8545240", "8540433", "8551910", "8537121", "8557380")
PAD_M = 1000.0


def _reaches() -> dict:
    return domain.side(SIDE).tidal_reaches


def _ring_bbox() -> tuple[float, float, float, float]:
    return tuple(region.load_ring(SIDE).to_crs(4326).total_bounds)


def _ring_pad():
    return region.load_ring(SIDE).to_crs(domain.EPSG).buffer(PAD_M).to_crs(4326).union_all()


# ── ENC ───────────────────────────────────────────────────────────────────────
def enc_cells(catalog: str, ring) -> pd.DataFrame:
    """Active ENC cells whose catalog coverage polygon meets ``ring`` (lon/lat)."""
    rows = []
    for c in ET.parse(catalog).getroot().iter("cell"):
        if c.findtext("status") != "Active":
            continue
        polys = []
        for p in c.iter("panel"):
            v = [(float(x.findtext("long")), float(x.findtext("lat"))) for x in p.iter("vertex")]
            if len(v) >= 3:
                polys.append(shapely.Polygon(v).buffer(0))
        if not polys:
            continue
        cov = shapely.union_all(polys)
        if cov.intersects(ring):
            rows.append({"cell": c.findtext("name"), "scale": int(c.findtext("cscale")),
                         "title": c.findtext("lname"), "issued": c.findtext("isdt"),
                         "edition": c.findtext("edtn"), "update": c.findtext("updn"),
                         "url": c.findtext("zipfile_location"),
                         "ring_share": cov.intersection(ring).area / ring.area})  # fmt: skip
    return pd.DataFrame(rows).sort_values(["scale", "cell"], ascending=[False, True])


def _dsid(path) -> dict:
    """SDAT / VDAT / DUNI of an S-57 cell (its DSID record)."""
    import pyogrio

    d = pyogrio.read_dataframe(path, layer="DSID", read_geometry=False)
    return {k: int(d[f"DSPM_{k}"].iloc[0]) for k in ("SDAT", "VDAT", "DUNI")}


def fetch_enc(overwrite: bool) -> None:
    import pyogrio

    os.environ["OGR_S57_OPTIONS"] = (
        "SPLIT_MULTIPOINT=ON,ADD_SOUNDG_DEPTH=ON,UPDATES=APPLY,RETURN_PRIMITIVES=OFF"
    )
    warnings.filterwarnings("ignore")
    enc = OUT / "enc"
    cat = enc / "ENCProdCat.xml"
    if overwrite or not cat.exists():
        download(ENC_CATALOG, cat)
    ring = region.load_ring(SIDE).to_crs(4326).union_all()
    cells = enc_cells(cat, ring)
    cells.to_csv(enc / "cells.csv", index=False)
    print(f"{len(cells)} active ENC cells meet the ring")
    pad = _ring_pad()
    frames: dict[str, list] = {k: [] for k in ENC_LAYERS}
    for c in cells.itertuples():
        z = enc / "raw" / f"{c.cell}.zip"
        if overwrite or not z.exists():
            download(c.url, z)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(enc / "raw")
        s57 = enc / "raw" / "ENC_ROOT" / c.cell / f"{c.cell}.000"
        meta = _dsid(s57)
        if meta["DUNI"] != 1:
            raise ValueError(f"{c.cell}: depth units code {meta['DUNI']} (1 = metres)")
        layers = {n for n, _ in pyogrio.list_layers(s57)}
        for lay in ENC_LAYERS:
            if lay not in layers:
                continue
            g = gpd.read_file(s57, layer=lay, engine="pyogrio")
            g = g[g.geometry.notna() & g.geometry.intersects(pad)].copy()
            if not len(g):
                continue
            if lay == "SOUNDG":
                g["depth_m"] = g.geometry.z
                g["geometry"] = shapely.force_2d(g.geometry.values)
            keep = [k for k in ("depth_m", "DRVAL1", "DRVAL2", "VALDCO", "QUASOU",
                                "TECSOU", "SORDAT", "SORIND", "OBJNAM") if k in g]  # fmt: skip
            g = g[keep + ["geometry"]].copy()
            g["cell"], g["scale"], g["sdat"] = c.cell, c.scale, meta["SDAT"]
            frames[lay].append(g)
    out = OUT / "enc_ring.gpkg"
    if out.exists():
        out.unlink()
    for lay, fr in frames.items():
        g = gpd.GeoDataFrame(pd.concat(fr, ignore_index=True), crs=4326)
        for k in g.columns:
            if g[k].dtype == object and k != "geometry":
                g[k] = g[k].astype(str)
        if lay == "LNDARE":  # points / lines are islets and piers; keep polygons
            g = g[g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        g.to_file(out, layer=lay, driver="GPKG")
        print(f"  {lay}: {len(g)} features in the ring + {PAD_M:.0f} m "
              f"(SDAT codes {sorted(g['sdat'].unique())})")  # fmt: skip
    print(f"wrote {out}")


# ── NHDPlus HR ────────────────────────────────────────────────────────────────
NHD_GDB_URL = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/NHDPlusHR/Beta/GDB/NHDPLUS_H_0204_HU4_GDB.zip"
NHD_GDB = config.DATA_BULK / "nhdplus" / "NHDPLUS_H_0204_HU4_GDB.gdb"
NHD_FROM_GDB = False


def nhd_from_gdb(bbox) -> dict[str, gpd.GeoDataFrame]:
    """flowline / area / waterbody as fetch_nhd's service query returns them, from the GDB."""
    import pyogrio

    if not NHD_GDB.exists():
        z = NHD_GDB.with_suffix(".zip")
        download(NHD_GDB_URL, z, timeout=1800)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(NHD_GDB.parent)
    rd = lambda layer, **k: pyogrio.read_dataframe(NHD_GDB, layer=layer, **k)  # noqa: E731
    fl = rd("NHDFlowline", bbox=bbox, columns=["NHDPlusID", "GNIS_Name", "FType", "FCode", "LengthKM"])
    vaa = rd("NHDPlusFlowlineVAA", read_geometry=False,
             columns=["NHDPlusID", "TotDASqKm", "HydroSeq", "DnHydroSeq", "LevelPathI", "TerminalPa",
                      "StreamOrde", "PathLength", "Divergence", "StartFlag"])  # fmt: skip
    erom = rd("NHDPlusEROMMA", read_geometry=False, columns=["NHDPlusID", "QAMA"])
    fl = fl.merge(vaa, on="NHDPlusID").merge(erom, on="NHDPlusID", how="left")
    fl.columns = [c.lower() if c != "geometry" else c for c in fl.columns]
    fl = fl[fl.totdasqkm >= MIN_DA_KM2].to_crs(4326)
    fl["geometry"] = shapely.force_2d(shapely.line_merge(fl.geometry.values))
    fl = fl[fl.geometry.geom_type == "LineString"]
    for k in ("nhdplusid", "hydroseq", "dnhydroseq", "levelpathi", "terminalpa", "streamorde", "divergence",
              "startflag", "ftype", "fcode"):  # fmt: skip
        fl[k] = fl[k].astype("int64")
    out = {"flowline": fl[[c.strip() for c in FLOW_FIELDS.split(",")] + ["geometry"]]}
    for name, layer, types in (("area", "NHDArea", (460,)), ("waterbody", "NHDWaterbody", (390, 436))):
        g = rd(layer, bbox=bbox, columns=["NHDPlusID", "GNIS_Name", "FType", "FCode", "AreaSqKm"])
        g.columns = [c.lower() if c != "geometry" else c for c in g.columns]
        g = g[g.ftype.isin(types)].to_crs(4326)
        g["geometry"] = shapely.force_2d(g.geometry.values)
        out[name] = g
    return out


def fetch_nhd(overwrite: bool) -> None:
    out = OUT / "nhdplus_hr.gpkg"
    if out.exists() and not overwrite:
        print(f"{out} exists; skipping (--overwrite to refetch)")
        return
    bbox, pad = _ring_bbox(), _ring_pad()
    if NHD_FROM_GDB:
        if out.exists():
            out.unlink()
        for name, g in nhd_from_gdb(bbox).items():
            g = g[g.intersects(pad)]
            g.to_file(out, layer=name, driver="GPKG")
            print(f"  NHDPlus HR (GDB) {name}: {len(g)} features in the ring + {PAD_M:.0f} m")
        print(f"wrote {out}")
        return
    parts = {
        "flowline": (3, f"totdasqkm >= {MIN_DA_KM2}", FLOW_FIELDS, 250),  # 1000 timed out (504) over DE
        "area": (8, "ftype = 460", "nhdplusid,gnis_name,ftype,fcode,areasqkm", 200),
        "waterbody": (9, "ftype IN (390, 436)", "nhdplusid,gnis_name,ftype,fcode,areasqkm", 200),
    }  # fmt: skip
    if out.exists():
        out.unlink()
    for name, (layer, where, fields, page) in parts.items():
        g = arcgis_query(f"{NHDPLUS}/{layer}", where=where, out_fields=fields,
                         bbox=bbox, page_size=page)  # fmt: skip
        g = g[g.intersects(pad)]
        g.to_file(out, layer=name, driver="GPKG")
        print(f"  NHDPlus HR {name}: {len(g)} features in the ring + {PAD_M:.0f} m")
    print(f"wrote {out}")


# ── USGS ──────────────────────────────────────────────────────────────────────
def fetch_usgs(overwrite: bool) -> None:
    f_cm = OUT / "usgs_channel_measurements.csv"
    if overwrite or not f_cm.exists():
        rows = usgs_ogc.items("channel-measurements", bbox=",".join(f"{v:.4f}" for v in _ring_bbox()))
        cm = pd.DataFrame(rows)
        cm["site"] = cm["monitoring_location_id"].str.removeprefix("USGS-")
        cm.to_csv(f_cm, index=False)
        print(f"  channel-measurements: {len(cm)} rows at {cm['site'].nunique()} sites (bbox)")
    cm = pd.read_csv(f_cm, dtype={"site": str})
    bbox = ",".join(f"{v:.4f}" for v in _ring_bbox())
    # ONE bbox call each: anonymous access is rate-limited per IP, and a per-site loop
    # over ~200 measurement sites ran into OVER_RATE_LIMIT (2026-10-03).
    f_sites = OUT / "usgs_sites.csv"
    if overwrite or not f_sites.exists():
        recs = []
        for p in usgs_ogc.items("monitoring-locations", bbox=bbox):
            recs.append({"site": str(p.get("id", "")).removeprefix("USGS-"),
                         "name": p.get("monitoring_location_name"),
                         "site_type": p.get("site_type"), "lon": p.get("lon"),
                         "lat": p.get("lat"), "drainage_area_mi2": p.get("drainage_area"),
                         "altitude_ft": p.get("altitude"),
                         "altitude_datum": p.get("vertical_datum"),
                         "altitude_accuracy_ft": p.get("altitude_accuracy")})  # fmt: skip
        sites = pd.DataFrame(recs)
        sites = sites[sites["site"].isin(set(cm["site"]))]
        sites.to_csv(f_sites, index=False)
        print(f"  monitoring-locations: {len(sites)} sites with channel measurements")
    sites = pd.read_csv(f_sites, dtype={"site": str})
    f_gh = OUT / "usgs_gage_heights.csv"
    if overwrite or not f_gh.exists():
        r = usgs_ogc.items("field-measurements", bbox=bbox, parameter_code="00065")
        gh = pd.DataFrame(r)
        gh["site"] = gh["monitoring_location_id"].str.removeprefix("USGS-")
        gh.to_csv(f_gh, index=False)
        print(f"  field-measurements 00065: {len(gh)} rows at {gh['site'].nunique()} sites")
    print(f"  {len(sites)} sites; gage heights cached in {f_gh.name}")


# ── eHydro ────────────────────────────────────────────────────────────────────
def fetch_ehydro(overwrite: bool) -> None:
    names = sorted({v["ehydro"] for v in _reaches().values() if v.get("ehydro")})
    prefixes = tuple(sorted({v["ehydro_prefix"] for v in _reaches().values() if v.get("ehydro_prefix")}))
    where = "sdsfeaturename IN (" + ", ".join(f"'{n}'" for n in names) + ")"
    g = arcgis_query(EHYDRO_INDEX, where=where,
                     out_fields="surveyjobidpk,sdsfeaturename,surveydatestart,surveytype,sourcedatalocation")  # fmt: skip
    g = g[g["surveyjobidpk"].fillna("").str.startswith(prefixes)].copy()
    g["date"] = pd.to_datetime(g["surveydatestart"], unit="ms").dt.date
    b = g.geometry.bounds
    idx = pd.DataFrame({"id": g["surveyjobidpk"], "channel": g["sdsfeaturename"], "date": g["date"],
                        "type": g["surveytype"], "url": g["sourcedatalocation"], "west": b.minx, "south": b.miny, "east": b.maxx,
                        "north": b.maxy}).sort_values(["channel", "date"])  # fmt: skip
    (OUT / "ehydro").mkdir(parents=True, exist_ok=True)
    got = []
    for sid, url in zip(idx["id"], idx["url"]):
        z = OUT / "ehydro" / f"{sid}.ZIP"
        try:  # the index's own URL: newer blobs are named CENAP_DIS_<id>.ZIP
            if overwrite or not z.exists():
                download(url if isinstance(url, str) and url else EHYDRO.format(sid=sid), z)
        except Exception as e:  # noqa: BLE001 — some indexed surveys have no blob (404)
            print(f"    {sid}: {type(e).__name__} {str(e)[:80]}")
            got.append(False)
            continue
        if not (OUT / "ehydro" / sid).exists() or overwrite:
            with zipfile.ZipFile(z) as zf:
                zf.extractall(OUT / "ehydro" / sid)
        got.append(True)
    idx["downloaded"] = got
    idx.to_csv(OUT / "ehydro" / "index.csv", index=False)
    print(f"  eHydro: {sum(got)} of {len(idx)} surveys of {names} -> {OUT / 'ehydro'}")


# ── NOS hydrographic surveys ──────────────────────────────────────────────────
def nos_range(sid: str) -> str:
    """NCEI's folder of 2000 surveys holding ``sid``: H10027 -> H10001-H12000."""
    n = int(sid[1:])
    lo = (n - 1) // 2000 * 2000 + 1
    return f"{sid[0]}{lo:05d}-{sid[0]}{lo + 1999:05d}"


def fetch_nos(overwrite: bool) -> None:
    ids = sorted({sid for v in _reaches().values() for sid, _ in v.get("nos", [])})
    for sid in ids:
        dest = config.CHANNELS_DIR / "nos" / f"{sid}.a93.gz"
        if dest.exists() and not overwrite:
            print(f"  {sid}: have")
            continue
        download(NOS_URL.format(rng=nos_range(sid), sid=sid), dest)
        print(f"  {sid}: wrote {dest}")


# ── crowdsourced bathymetry ───────────────────────────────────────────────────
def csb_tracks(poly_ll) -> list[str]:
    """Names of the CSB track files whose line crosses ``poly_ll`` (lon/lat polygon)."""
    rings = [[list(c) for c in poly_ll.exterior.coords]]
    params = {"geometry": json.dumps({"rings": rings, "spatialReference": {"wkid": 4326}}),
              "geometryType": "esriGeometryPolygon", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
              "outFields": "NAME", "returnGeometry": "false", "f": "json"}  # fmt: skip
    j = arcgis_form_query(CSB_TRACKS, params)
    if "error" in j:
        raise RuntimeError(f"CSB track query: {j['error']}")
    return sorted({f["attributes"]["NAME"] for f in j.get("features", [])})


def csb_track_points(name: str) -> pd.DataFrame:
    stem = name.removesuffix(".tar.gz")
    url = CSB_POINTS.format(y=stem[:4], m=stem[4:6], d=stem[6:8], stem=stem)
    r = get(url, timeout=600)
    return pd.read_csv(io.StringIO(r.text), usecols=["LON", "LAT", "DEPTH", "TIME", "PLATFORM_NAME", "PROVIDER"])


def coops_6min(station: str, month: pd.Timestamp, cache) -> pd.Series:
    """Observed 6-min water level (m above MLLW, UTC) for one calendar month, cached."""
    f = cache / f"{station}_{month:%Y%m}.csv"
    if not f.exists():
        end = month + pd.offsets.MonthEnd(0)
        j = get(COOPS_DATA, {"product": "water_level", "station": station, "datum": "MLLW", "units": "metric",
                             "time_zone": "gmt", "format": "json", "application": "sfincs-nj-agri",
                             "begin_date": f"{month:%Y%m%d}", "end_date": f"{end:%Y%m%d} 23:54"}).json()  # fmt: skip
        d = pd.DataFrame(j.get("data", []), columns=["t", "v"])
        d.to_csv(f, index=False)
    d = pd.read_csv(f)
    s = pd.to_numeric(d["v"], errors="coerce")
    s.index = pd.to_datetime(d["t"], utc=True)
    return s.dropna()


def fetch_csb(overwrite: bool) -> None:
    cl_f = config.ELEV_DIR / f"riverbed_centrelines{domain.side(SIDE).files}.gpkg"
    if not cl_f.exists():
        raise FileNotFoundError(f"{cl_f}: run build_riverbeds.py once first")
    cl = gpd.read_file(cl_f)
    cl = cl[cl.kind == "tidal"].to_crs(domain.EPSG)
    st = pd.DataFrame(domain.NOAA_STATIONS).set_index("id").loc[list(CSB_TIDE)]
    st_xy = gpd.GeoSeries(gpd.points_from_xy(st.lon, st.lat), index=st.index, crs=4326).to_crs(domain.EPSG)
    (OUT / "csb" / "tide").mkdir(parents=True, exist_ok=True)
    cache: dict[str, pd.DataFrame] = {}
    for r in cl.itertuples():
        dest = OUT / "csb" / f"{r.reach}.csv"
        if dest.exists() and not overwrite:
            print(f"  {r.reach}: have")
            continue
        buf = r.geometry.buffer(CSB_HALF_M)
        buf_ll = gpd.GeoSeries([buf.simplify(25.0)], crs=domain.EPSG).to_crs(4326).iloc[0]
        if buf_ll.geom_type != "Polygon":
            buf_ll = max(buf_ll.geoms, key=lambda g: g.area)
        names = csb_tracks(buf_ll)
        mouth = shapely.Point(r.geometry.coords[-1])
        station = st_xy.distance(mouth).idxmin()
        rows = []
        for nm in names:
            if nm not in cache:
                try:
                    cache[nm] = csb_track_points(nm)
                except Exception as e:  # noqa: BLE001 — a few indexed tracks have no point file
                    print(f"    {nm}: {type(e).__name__} {str(e)[:80]}")
                    cache[nm] = pd.DataFrame(columns=["LON", "LAT", "DEPTH", "TIME", "PLATFORM_NAME", "PROVIDER"])
            p = cache[nm]
            if p.empty:
                continue
            xy = gpd.GeoSeries(gpd.points_from_xy(p.LON, p.LAT), crs=4326).to_crs(domain.EPSG)
            inside = shapely.contains_xy(buf, xy.x.values, xy.y.values)
            if inside.any():
                rows.append(p[inside].assign(track=nm))
        if not rows:
            print(f"  {r.reach}: {len(names)} tracks, no soundings in the channel")
            continue
        d = pd.concat(rows, ignore_index=True)
        d["t"] = pd.to_datetime(d.TIME, utc=True, errors="coerce")
        d = d[d.t.notna() & (d.DEPTH > 0)]
        wl = pd.concat([coops_6min(station, m, OUT / "csb" / "tide")
                        for m in sorted({t.tz_localize(None).to_period("M").to_timestamp() for t in d.t})])  # fmt: skip
        wl = wl[~wl.index.duplicated()].sort_index()
        j = np.searchsorted(wl.index.values, d.t.values)
        jl, jr = np.clip(j - 1, 0, len(wl) - 1), np.clip(j, 0, len(wl) - 1)
        gap = np.minimum(np.abs(d.t.values - wl.index.values[jl]), np.abs(wl.index.values[jr] - d.t.values))
        d["wl_mllw_m"] = np.interp(d.t.values.astype("int64"), wl.index.values.astype("int64"), wl.values)
        d = d[gap <= np.timedelta64(30, "m")]
        d["depth_mllw_m"] = riverbed.csb_depth_mllw(d.DEPTH, d.wl_mllw_m, CSB_DRAFT_M)
        out = pd.DataFrame({"lon": d.LON, "lat": d.LAT, "depth_mllw_m": d.depth_mllw_m.round(3),
                            "depth_raw_m": d.DEPTH, "wl_mllw_m": d.wl_mllw_m.round(3), "station": station,
                            "time_utc": d.t, "provider": d.PROVIDER, "platform": d.PLATFORM_NAME,
                            "track": d.track})  # fmt: skip
        out.to_csv(dest, index=False)
        print(f"  {r.reach}: {len(names)} tracks, {len(out)} soundings in the channel "
              f"({out.track.nunique()} tracks, {out.time_utc.min():%Y}-{out.time_utc.max():%Y}), tide {station}, "
              f"depth below MLLW p50 {out.depth_mllw_m.median():.1f} m")  # fmt: skip


# ── CO-OPS datums ─────────────────────────────────────────────────────────────
def fetch_datums(overwrite: bool) -> None:
    f_d, f_o = OUT / "coops_datums.csv", OUT / "coops_offsets.csv"
    if f_d.exists() and f_o.exists() and not overwrite:
        print(f"{f_d.name}, {f_o.name} exist; skipping")
        return
    w, s, e, n = _ring_bbox()
    inbox = lambda st: w - 0.05 <= st["lng"] <= e + 0.05 and s - 0.05 <= st["lat"] <= n + 0.05  # noqa: E731
    with_datums = {st["id"]: st for st in get(f"{COOPS}/stations.json", {"type": "datums"}).json()["stations"]}
    pred = get(f"{COOPS}/stations.json", {"type": "tidepredictions"}).json()["stations"]
    want = {k for k, st in with_datums.items() if inbox(st)} | set(COOPS_REFS)
    drows = []
    for sid in sorted(want):
        st = with_datums[sid]
        d = get(f"{COOPS}/stations/{sid}/datums.json").json()
        if d.get("units") != "feet":
            raise ValueError(f"{sid}: datums in {d.get('units')}")
        vals = {x["name"]: x["value"] for x in d.get("datums") or []}
        drows.append({"id": sid, "name": st["name"], "lon": st["lng"], "lat": st["lat"],
                      "epoch": d.get("epoch"),
                      **{k: vals.get(k) for k in ("MHHW", "MHW", "MSL", "MTL", "MLW", "MLLW", "NAVD88")}})  # fmt: skip
    pd.DataFrame(drows).to_csv(f_d, index=False)
    orows = []
    for st in pred:
        if st.get("type") != "S" or not inbox(st):
            continue
        o = get(f"{COOPS}/stations/{st['id']}/tidepredoffsets.json").json()
        orows.append({"id": st["id"], "name": st["name"], "lon": st["lng"], "lat": st["lat"],
                      "ref": o.get("refStationId"), "type": o.get("heightAdjustedType"),
                      "h_high": o.get("heightOffsetHighTide"),
                      "h_low": o.get("heightOffsetLowTide")})  # fmt: skip
    pd.DataFrame(orows).to_csv(f_o, index=False)
    print(f"  CO-OPS: {len(drows)} stations with datums (feet, station datum), "
          f"{len(orows)} subordinate offsets -> {f_d.name}, {f_o.name}")  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stages", nargs="*", default=["enc", "nhd", "usgs", "datums", "ehydro", "nos"])
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--side", default="nj", choices=list(domain.SIDES))
    ap.add_argument("--nhd-gdb", action="store_true", help="nhd stage from the staged NHDPlus HR GDB")
    a = ap.parse_args()
    global OUT, SIDE, NHD_FROM_GDB
    OUT, SIDE, NHD_FROM_GDB = config.channels_dir(a.side), a.side, a.nhd_gdb
    OUT.mkdir(parents=True, exist_ok=True)
    for st in a.stages:
        print(f"== {st}")
        {"enc": fetch_enc, "nhd": fetch_nhd, "usgs": fetch_usgs, "datums": fetch_datums,
         "ehydro": fetch_ehydro, "nos": fetch_nos, "csb": fetch_csb}[st](a.overwrite)


if __name__ == "__main__":
    main()
