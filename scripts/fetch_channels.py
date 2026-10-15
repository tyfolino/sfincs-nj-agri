"""Inputs for the river-bed burn (FINDINGS §11): chart soundings, flowlines, gauge
cross-sections and tidal datums. Network only; ``build_riverbeds.py`` reads the cache.

    python scripts/fetch_channels.py [enc] [nhd] [usgs] [datums] [ehydro] [--overwrite]

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
        in the ring bbox -> ``nhdplus_hr.gpkg``.
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
import os
import warnings
import xml.etree.ElementTree as ET
import zipfile

import geopandas as gpd
import pandas as pd
import shapely

from agri_sfincs import config, domain, region, usgs_ogc
from agri_sfincs.net import arcgis_query, download, get

OUT = config.CHANNELS_DIR
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
PAD_M = 1000.0


def _ring_bbox() -> tuple[float, float, float, float]:
    return tuple(region.load_ring().to_crs(4326).total_bounds)


def _ring_pad():
    return region.load_ring().to_crs(domain.EPSG).buffer(PAD_M).to_crs(4326).union_all()


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
    ring = region.load_ring().to_crs(4326).union_all()
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
def fetch_nhd(overwrite: bool) -> None:
    out = OUT / "nhdplus_hr.gpkg"
    if out.exists() and not overwrite:
        print(f"{out} exists; skipping (--overwrite to refetch)")
        return
    bbox, pad = _ring_bbox(), _ring_pad()
    parts = {
        "flowline": (3, f"totdasqkm >= {MIN_DA_KM2}", FLOW_FIELDS, 1000),
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
    names = sorted({v["ehydro"] for v in domain.TIDAL_REACHES.values() if v.get("ehydro")})
    where = "sdsfeaturename IN (" + ", ".join(f"'{n}'" for n in names) + ")"
    g = arcgis_query(EHYDRO_INDEX, where=where,
                     out_fields="surveyjobidpk,sdsfeaturename,surveydatestart,surveytype,sourcedatalocation")  # fmt: skip
    g = g[g["surveyjobidpk"].fillna("").str.startswith(("MA_", "SA_"))].copy()
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
    ap.add_argument("stages", nargs="*", default=["enc", "nhd", "usgs", "datums", "ehydro"])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for st in a.stages:
        print(f"== {st}")
        {"enc": fetch_enc, "nhd": fetch_nhd, "usgs": fetch_usgs, "datums": fetch_datums,
         "ehydro": fetch_ehydro}[st](a.overwrite)


if __name__ == "__main__":
    main()
