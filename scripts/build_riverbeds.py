"""Burn river beds (FINDINGS §11): a raster of river-bed elevations on the bed grid,
to be MERGED into ``bed_merged.tif`` by a later step (never stacked on top of it).

    python scripts/build_riverbeds.py [--da-min 10] [--min-width 10] [--no-raster]

Inputs (``scripts/fetch_channels.py``, data/channels/): NOAA ENC soundings and depth
areas, NHDPlus HR flowlines / StreamRiver areas / lakes, USGS channel measurements,
CO-OPS tidal datums; and data/elevation/bed_merged.tif + bed_source.tif,
data/structures/structures.gpkg (NJDEP head of tide).

Rules (user, 2026-10-02, revised 2026-10-05; this mirrors nj_bight_sfincs
``build_riverbeds_v4.py``):

TIDAL reaches (``domain.TIDAL_REACHES``): the NHDPlus HR main path from the NJDEP
head-of-tide point down to the first Delaware River/Bay flowline, cut where it runs
into open water (the last run of bed_source 3 = lidar NoData); open-water pixels
(bed_source 3: CUDEM's surveyed bed) are never painted. Every value is a function
of distance ALONG the centreline (bight lesson: 2-D interpolation of sparse soundings
leaks across meanders), painted flat across the channel. Sources, in precedence:
  * eHydro     USACE condition surveys (data/channels/ehydro/, ft below MLLW 1983-2001,
               NJ State Plane ft — checked in each survey's metadata) on the reaches
               with an ``ehydro`` channel (Maurice, Salem): per reach the MOST RECENT
               survey covering >= ``EHYDRO_COVER_FRAC`` of the best survey's length;
               running median +-``EHYDRO_WINDOW_M``, linear inside the surveyed span.
               It REPLACES the chart there (user, 2026-10-05).             src code 6
  * soundings  ENC SOUNDG inside the painted channel (+ ``SOUNDING_TOL_M``), depth below
               MLLW -> NAVD88 with the local MLLW (below), running median over
               +-``TIDAL_WINDOW_M`` of >= ``TIDAL_MIN_N`` soundings (else the 3 nearest
               within ``TIDAL_MAX_HALF_M``), linear between.
                                                                          src code 1
  * chart area where no sounding reaches (most of every creek: the ENC carries only
               "0-1.8 m" depth areas above the mouths), the midpoint of the deepest S-57
               DEPARE interval the centreline crosses within 50 (else 150) m of the
               station (``TAIL_MLLW_M`` = 1.2 m below MLLW for the 0-1.8 m class; a
               deeper class gives its lower bound, the depth the chart guarantees).
                                                                          src code 2
  * uncharted  above the last chart depth area (Stow, Oldmans, Raccoon ... are charted
               only near their mouths): ``TAIL_MLLW_M`` (1.2 m) below MLLW. src code 3
  * MLLW in NAVD88 along the reach: CO-OPS datum sheets where they carry NAVD88
    (Bivalve, Fortescue, Reedy Point, Marcus Hook, Philadelphia, Lewes) and the
    tide-prediction SUBORDINATE stations on the reach (Millville, Mauricetown, Greenwich
    Pier, Salem, Quinton, ...), whose MLLW = MTL - (MHW'+MLW')/2 from their ratios to the
    reference station, with MTL borrowed from the nearest NAVD88-tied station. VDatum's
    API has no answer on any of these creeks (412 / -999999). Interpolated along the
    centreline; held constant beyond the end nodes.
  * channel    NHDPlus HR StreamRiver areas the centreline crosses, within
               ``TIDAL_MAX_HALFWIDTH_M``, plus a minimum strip of half-width
               max(width(DA), ``--min-width``)/2 so narrow upper reaches stay connected.

NON-TIDAL streams: every NHDPlus HR network flowline with drainage area >= ``--da-min``
km2 that drains to a head-of-tide point (its HoT flowline is cut at the point), minor
divergences excluded, grouped by level path (one river = one profile).
  * surface    the bed_merged (lidar, hydro-flattened: the WATER SURFACE) low decile of a
               +-15 m cross-section every 10 m, per +-25 m bin, running median over
               +-``SURF_SMOOTH_M``, then made non-increasing downstream (water does not
               run uphill: a bridge deck or bank pixel cannot lift the line).
  * depth      USGS channel measurements: mean depth = area / width, median over the
               site's own p25-p75 measured-flow band (bight's Trenton rule). A power law
               depth = a DA^b over all sites in the ring with >= ``MIN_MEAS`` measurements
               in that band, and, on a level path that carries gauges, the gauge/law
               ratio interpolated in log(DA) between them (held beyond).
                                                  src 4 (gauged path), src 5 (law only)
  * anchors    at ``ANCHOR_SITES`` only (Pitman, Swedesboro: their lidar surface reads
               ~0.4 m above the measured stage) the bed is tied to the gauge: NAVD88
               gauge datum + median stage at the band's measurements - mean depth, the
               correction tapering to 0 over +-``ANCHOR_TAPER_M``.        src code 7
  * low water  stations whose lidar surface is below ``NT_SURFACE_MIN_M`` (1 m NAVD88:
               tidal elevations behind a head-of-tide point, likely tide-gated meadow,
               ~66 km) are NOT burned (user, 2026-10-05: handled separately).
  * width      the same, for the painted strip (median width in the band), floored at
               ``--min-width`` (the model's subgrid pixel is 10 m: a narrower strip is
               averaged away), capped at ``NT_MAX_HALFWIDTH_M``; StreamRiver areas the
               path crosses are painted too.
  * lakes      NHDPlus HR LakePond/Reservoir polygons are NOT painted: a flat lake bed is
               the separate fake-lake-bed problem (Union Lake, Sunset Lake ...).

NEVER RAISE: a pixel is written only where the burn is below bed_merged; where two
profiles overlap, the deeper wins. bed_merged.tif is read, never written.

Outputs:
  data/elevation/riverbed_burn.tif     float32 m NAVD88, the bed grid (EPSG:4326, lidar
                                       grid), NoData -9999 where nothing is burned
  data/elevation/riverbed_source.tif   uint8 codes 1-7 above, 0 = not burned
  data/elevation/river_table.csv       one row per tidal reach / non-tidal level path
  data/elevation/riverbed_profiles.csv every profile station (for review / plots)
  data/elevation/riverbed_soundings.csv the ENC soundings each tidal profile used
  data/channels/ehydro/coverage.csv    every survey's coverage of its reach (the pick)
  data/channels/gauge_geometry.csv     per-site mean depth / width / flow band
  data/channels/tidal_datum_nodes.csv  MLLW in NAVD88 at every CO-OPS node used
  data/channels/gauge_anchors.csv      the two anchored gauges' datum, stage, depth, bed
"""

from __future__ import annotations

import argparse
import re
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
import shapely.ops
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds

from agri_sfincs import config, domain, region, riverbed

warnings.filterwarnings("ignore", message=".*geographic CRS.*")

CH = config.CHANNELS_DIR
ELEV = config.ELEV_DIR
EPSG = domain.EPSG
NODATA = -9999.0

HOT_SNAP_M = 100.0  # a head-of-tide point counts if a flowline is this close
TIDAL_STEP_M = 25.0
TIDAL_WINDOW_M = 500.0  # running median of soundings (bight: 300 m) ...
TIDAL_MIN_N = 3  # ... over at least this many: a thinner window takes the 3 nearest ...
TIDAL_MAX_HALF_M = 1500.0  # ... if they lie within this; else interpolated between
TIDAL_SMOOTH_M = 150.0  # final smoothing of the combined tidal profile
TIDAL_MAX_HALFWIDTH_M = 300.0  # bight: the tidal Raritan is ~600 m wide
SOUNDING_TOL_M = 25.0  # soundings this far outside the painted channel still count
DEPARE_RADIUS_M = (50.0, 150.0)  # look for chart depth areas this far from a station
DATUM_NODE_MAX_M = 2000.0  # CO-OPS nodes this close to a tidal centreline are used
MOUTH_GAP = 4  # stations of non-open-water allowed inside the final open-water run
#: ... and a reach also ends where the water across it (between charted land, ENC
#: LNDARE, along the normal to the centreline) first gets wider than this: the creek
#: has run out into the Delaware. NHDPlus carries each creek's flowline out to the
#: Delaware's mid-river artificial path, and on the upper Delaware the lidar covers that
#: water (src 1/2), so the open-water rule alone let Mantua Creek pick up -12 m
#: ship-channel soundings off Paulsboro.
MOUTH_WIDTH_M = 1000.0
WIDTH_PROBE_M = np.arange(5.0, 1505.0, 10.0)

END_TOL_M = 0.5  # a point projecting within this of a line end is "past the end"
NT_STEP_M = 10.0
NT_OFFSETS_M = np.array([-15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0])
SURF_BIN_M = 25.0  # +- along-channel bin of the cross-section samples
SURF_PCT = 10.0
SURF_SMOOTH_M = 100.0
NT_MAX_HALFWIDTH_M = 60.0
MIN_MEAS = 5  # channel measurements in the p25-p75 band for a site to count
GAUGE_SNAP_M = 75.0  # a gauge anchors a level path only within this distance
LAKE_MIN_KM2 = 0.01  # NHD lakes/reservoirs >= 1 ha are not painted

SRC_NAMES = {1: "tidal: ENC soundings", 2: "tidal: ENC depth area",
             3: "tidal: uncharted, 1.2 m below MLLW",
             4: "non-tidal: surface - gauge depth", 5: "non-tidal: surface - DA law depth",
             6: "tidal: USACE eHydro survey", 7: "non-tidal: anchored to gauge stage"}  # fmt: skip
#: Uncharted tidal reaches and the chart's "0-1.8 m" depth class: this depth below MLLW
#: (user, 2026-10-05: bight's value; the 0.9 m midpoint read ~0.8 m shallow against the
#: 2023 Maurice survey).
TAIL_MLLW_M = 1.2
EHYDRO_DIR = CH / "ehydro"
EHYDRO_WINDOW_M = 150.0
EHYDRO_MIN_N = 3
EHYDRO_COVER_FRAC = 0.9
#: Non-tidal stations whose lidar surface is below this (m NAVD88) are not burned.
NT_SURFACE_MIN_M = 1.0
#: Gauges whose measured stage overrides the lidar surface (user, 2026-10-05), and the
#: distance over which the correction tapers back to the lidar rule.
ANCHOR_SITES = {"01475001": "Mantua Creek at Pitman", "01477120": "Raccoon Creek near Swedesboro"}
ANCHOR_TAPER_M = 1500.0
ANCHOR_SINCE = "2007"  # stage records (and gauge datums) from the 2007 gage-height series


# ── inputs ────────────────────────────────────────────────────────────────────
def load_flowlines() -> gpd.GeoDataFrame:
    f = gpd.read_file(CH / "nhdplus_hr.gpkg", layer="flowline").to_crs(EPSG)
    f["geometry"] = shapely.force_2d(f.geometry.values)
    for k in ("hydroseq", "dnhydroseq", "levelpathi"):
        f[k] = f[k].astype("int64")
    return f.set_index("hydroseq", drop=False)


class Grid:
    """The bed grid (bed_merged.tif): transforms and windowed reads."""

    def __init__(self):
        self.bed = rasterio.open(ELEV / "bed_merged.tif")
        self.src = rasterio.open(ELEV / "bed_source.tif")
        self.T = self.bed.transform
        self.W, self.H = self.bed.width, self.bed.height
        self.to_ll = Transformer.from_crs(EPSG, self.bed.crs, always_xy=True)
        self.to_utm = Transformer.from_crs(self.bed.crs, EPSG, always_xy=True)

    def sample(self, x, y, which="bed") -> np.ndarray:
        """Nearest-pixel values at UTM points (NaN off-grid / NoData)."""
        x, y = np.asarray(x, dtype="float64"), np.asarray(y, dtype="float64")
        out = np.full(x.shape, np.nan)
        if x.size == 0:
            return out
        lon, lat = self.to_ll.transform(x, y)
        c, r = ~self.T * (np.asarray(lon), np.asarray(lat))
        r, c = np.floor(r).astype(int), np.floor(c).astype(int)
        ok = (r >= 0) & (r < self.H) & (c >= 0) & (c < self.W)
        if not ok.any():
            return out
        r0, r1, c0, c1 = r[ok].min(), r[ok].max() + 1, c[ok].min(), c[ok].max() + 1
        ds = self.bed if which == "bed" else self.src
        a = ds.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype("float64")
        if ds.nodata is not None:
            a[a == ds.nodata] = np.nan
        out[ok] = a[r[ok] - r0, c[ok] - c0]
        return out


# ── tidal datums ──────────────────────────────────────────────────────────────
def datum_nodes() -> gpd.GeoDataFrame:
    """MLLW (m NAVD88) at every CO-OPS node: NAVD88-tied datum sheets, and subordinate
    stations through ``riverbed.subordinate_mllw_navd88``."""
    d = pd.read_csv(CH / "coops_datums.csv", dtype={"id": str})
    o = pd.read_csv(CH / "coops_offsets.csv", dtype={"id": str, "ref": str})
    d["mllw_navd88_m"] = [riverbed.coops_datum_navd88(r) for r in d.to_dict("records")]
    d["mtl_navd88_m"] = [riverbed.coops_datum_navd88(r, "MTL") for r in d.to_dict("records")]
    tied = d[np.isfinite(d["mllw_navd88_m"])].copy()
    tied["kind"] = "datum sheet (NAVD88 tie)"
    tg = gpd.GeoDataFrame(tied, geometry=gpd.points_from_xy(tied.lon, tied.lat), crs=4326).to_crs(EPSG)
    refs = d.set_index("id")
    rows = []
    for r in o.itertuples():
        if r.ref not in refs.index or r.id in set(tied["id"]):
            continue
        p = gpd.GeoSeries([shapely.Point(r.lon, r.lat)], crs=4326).to_crs(EPSG).iloc[0]
        k = tg.distance(p).idxmin()
        mllw = riverbed.subordinate_mllw_navd88(refs.loc[r.ref].to_dict(), r.type, r.h_high,
                                                r.h_low, tg.loc[k, "mtl_navd88_m"])  # fmt: skip
        rows.append({"id": r.id, "name": r.name, "lon": r.lon, "lat": r.lat,
                     "mllw_navd88_m": mllw, "mtl_navd88_m": tg.loc[k, "mtl_navd88_m"],
                     "kind": f"subordinate ({r.type} {r.h_high}/{r.h_low} x {r.ref}; "
                             f"MTL from {tg.loc[k, 'id']})"})  # fmt: skip
    sub = pd.DataFrame(rows)
    allp = pd.concat([tied[["id", "name", "lon", "lat", "mllw_navd88_m", "mtl_navd88_m", "kind"]], sub],
                     ignore_index=True)  # fmt: skip
    return gpd.GeoDataFrame(allp, geometry=gpd.points_from_xy(allp.lon, allp.lat), crs=4326).to_crs(EPSG)


def mllw_along(line, nodes: gpd.GeoDataFrame, grid: np.ndarray) -> tuple[np.ndarray, list[str]]:
    near = nodes[nodes.distance(line) <= DATUM_NODE_MAX_M]
    if near.empty:
        near = nodes.loc[[nodes.distance(line).idxmin()]]
    s = shapely.line_locate_point(line, near.geometry.values)
    o = np.argsort(s)
    return np.interp(grid, s[o], near["mllw_navd88_m"].values[o]), list(near["id"].values[o])


# ── eHydro ────────────────────────────────────────────────────────────────────
US_FT = 1200.0 / 3937.0
_EH_META = {"Vertical Reference Datum": r"MLLW", "Tidal Epoch": r"1983-2001",
            "Projected Coordinate Units": r"US Survey Foot", "Horizontal Zone": r"NJ"}  # fmt: skip
_eh_cache: dict[tuple[str, bool], tuple] = {}


def ehydro_points(sid: str, full: bool = True):
    """(x, y, depth_m) of an eHydro survey in UTM; depth m below MLLW (1983-2001).
    The survey's metadata must say MLLW / 1983-2001 / US Survey Foot / NJ State Plane
    (EPSG 3424), else this raises. ``full``: the multibeam ``*_FULL.XYZ`` if present."""
    key = (sid, full)
    if key in _eh_cache:
        return _eh_cache[key]
    d = EHYDRO_DIR / sid
    files = {f.name.upper(): f for f in d.iterdir()}
    xml = files.get(f"{sid}.XML")
    txt = xml.read_text(errors="ignore") if xml else ""
    for k, v in _EH_META.items():
        if not re.search(rf"{k}:\s*{v}", txt):
            raise ValueError(f"{sid}: metadata does not say '{k}: {v}'")
    f = files.get(f"{sid}_FULL.XYZ") if full else None
    f = f or files[f"{sid}.XYZ"]
    a = pd.read_csv(f, sep=r"\s+", header=None, usecols=[0, 1, 2]).to_numpy(dtype="float64")
    if np.median(a[:, 2]) <= 0:
        raise ValueError(f"{sid}: depths are not positive-down")
    x, y = Transformer.from_crs(3424, EPSG, always_xy=True).transform(a[:, 0], a[:, 1])
    _eh_cache[key] = (np.asarray(x), np.asarray(y), a[:, 2] * US_FT)
    return _eh_cache[key]


def ehydro_profile(channel: str, line, chan, grid, mllw):
    """The eHydro bed profile of one reach: (profile, survey id, coverage rows)."""
    idx = pd.read_csv(EHYDRO_DIR / "index.csv", parse_dates=["date"])
    idx = idx[(idx["channel"] == channel) & idx["downloaded"]].reset_index(drop=True)

    def prof_of(sid, full):
        x, y, dep = ehydro_points(sid, full)
        pts = shapely.points(x, y)
        m = shapely.dwithin(chan, pts, SOUNDING_TOL_M)
        st = shapely.line_locate_point(line, pts[m])
        inner = (st > END_TOL_M) & (st < line.length - END_TOL_M)
        st, d = st[inner], dep[m][inner]
        z = riverbed.chart_to_navd88(d, np.interp(st, grid, mllw))
        return riverbed.running_median(st, z, grid, EHYDRO_WINDOW_M, EHYDRO_MIN_N), int(st.size)

    cov = []
    for r in idx.itertuples():
        p, n = prof_of(r.id, full=False)
        cov.append({"channel": channel, "id": r.id, "date": r.date.date(), "type": r.type, "points": n,
                    "coverage_km": float(np.isfinite(p).sum() * (grid[1] - grid[0]) / 1e3)})  # fmt: skip
    k = riverbed.pick_survey(idx["date"].values, [c["coverage_km"] for c in cov], EHYDRO_COVER_FRAC)
    for i, c in enumerate(cov):
        c["picked"] = i == k
    if k < 0:
        return np.full(grid.shape, np.nan), "", cov
    sid = idx.loc[k, "id"]
    p, n = prof_of(sid, full=True)
    cov[k]["points_used"] = n
    return riverbed.fill_interior(grid, p), sid, cov


# ── geometry helpers ──────────────────────────────────────────────────────────
def hot_points(flow: gpd.GeoDataFrame) -> dict[int, float]:
    """{hydroseq: station (m) of the most upstream head-of-tide point on it}."""
    h = gpd.read_file(config.STRUCTURES, layer="njdep_head_of_tide").to_crs(EPSG)
    main = flow[flow["divergence"] != 2]
    out: dict[int, float] = {}
    for p in h.geometry:
        d = main.distance(p)
        if d.min() > HOT_SNAP_M:
            continue
        k = int(d.idxmin())
        s = float(shapely.line_locate_point(main.loc[k, "geometry"], p))
        out[k] = min(out.get(k, np.inf), s)
    return out


def downstream_path(flow, start: int) -> list[int]:
    path, cur = [], start
    while cur in flow.index and len(path) < 5000:
        name = flow.loc[cur, "gnis_name"]
        if isinstance(name, str) and name.startswith("Delaware"):
            break
        path.append(cur)
        cur = int(flow.loc[cur, "dnhydroseq"])
    return path


def chain(flow, ids: list[int], cut: dict[int, tuple[float, float]] | None = None):
    """Concatenate flowlines (in flow order) into LineStrings, breaking at gaps > 1 m.
    ``cut`` = {hydroseq: (from_m, to_m)} keeps only that part of a flowline. Returns
    [(line, [(start_station, hydroseq), ...])]."""
    pieces, coords, marks = [], [], []
    for h in ids:
        g = flow.loc[h, "geometry"]
        if cut and h in cut:
            g = shapely.ops.substring(g, *cut[h])
            if g.length < 1.0:
                continue
        c = list(g.coords)
        if coords and shapely.Point(coords[-1]).distance(shapely.Point(c[0])) > 1.0:
            pieces.append((shapely.LineString(coords), marks))
            coords, marks = [], []
        s0 = shapely.LineString(coords).length if len(coords) >= 2 else 0.0
        marks.append((s0, h))
        coords += c if not coords else c[1:]
    if len(coords) >= 2:
        pieces.append((shapely.LineString(coords), marks))
    return pieces


def water_width(line, grid, land) -> np.ndarray:
    """Open-water width (m) across ``line`` at each station: distance to charted land
    along the normal on each side, each capped at ``WIDTH_PROBE_M`` max."""
    cx, cy, nx, ny = normals(line, grid)
    out = np.zeros(grid.shape)
    for sign in (-1.0, 1.0):
        xs = cx[:, None] + sign * nx[:, None] * WIDTH_PROBE_M
        ys = cy[:, None] + sign * ny[:, None] * WIDTH_PROBE_M
        hit = shapely.contains_xy(land, xs, ys)  # (stations, probes)
        first = np.where(hit.any(axis=1), WIDTH_PROBE_M[np.argmax(hit, axis=1)], WIDTH_PROBE_M[-1] + 5.0)
        out += first
    return out


def da_along(flow, marks, grid) -> np.ndarray:
    s0 = np.array([m[0] for m in marks])
    da = flow.loc[[m[1] for m in marks], "totdasqkm"].values.astype("float64")
    k = np.clip(np.searchsorted(s0, grid, side="right") - 1, 0, len(s0) - 1)
    return da[k]


def normals(line, grid):
    c = shapely.line_interpolate_point(line, grid)
    a = shapely.line_interpolate_point(line, np.clip(grid - 5.0, 0, line.length))
    b = shapely.line_interpolate_point(line, np.clip(grid + 5.0, 0, line.length))
    tx, ty = shapely.get_x(b) - shapely.get_x(a), shapely.get_y(b) - shapely.get_y(a)
    tn = np.hypot(tx, ty)
    tn[tn == 0] = 1.0
    return shapely.get_x(c), shapely.get_y(c), -ty / tn, tx / tn


# ── hydraulic geometry ────────────────────────────────────────────────────────
def gauge_geometry(flow) -> pd.DataFrame:
    cm = pd.read_csv(CH / "usgs_channel_measurements.csv", dtype={"site": str}, low_memory=False)
    sites = pd.read_csv(CH / "usgs_sites.csv", dtype={"site": str}).set_index("site")
    for u, k in (("ft^3/s", "channel_flow_unit"), ("ft", "channel_width_unit"), ("ft^2", "channel_area_unit")):
        bad = cm[k].notna() & (cm[k] != u)
        if bad.any():
            raise ValueError(f"channel-measurements: {k} not {u} in {bad.sum()} rows")
    ring = region.load_ring().to_crs(4326).union_all()
    rows = []
    for s, g in cm.groupby("site"):
        if s not in sites.index:
            continue
        r = riverbed.gauge_mean_depth(g["channel_flow"], g["channel_width"], g["channel_area"])
        if r.get("n_band", 0) < MIN_MEAS:
            continue
        st = sites.loc[s]
        rows.append({"site": s, "name": st["name"], "site_type": st["site_type"], "lon": st["lon"],
                     "lat": st["lat"], "da_km2": st["drainage_area_mi2"] * 2.589988,
                     "in_ring": ring.contains(shapely.Point(st["lon"], st["lat"])),
                     "first": str(g["time"].min())[:4], "last": str(g["time"].max())[:4], **r})  # fmt: skip
    gg = pd.DataFrame(rows)
    gg = gg[gg["in_ring"] & np.isfinite(gg["da_km2"]) & (gg["da_km2"] > 0)].copy()
    # snap to the network for the level path (non-tidal use only)
    pts = gpd.GeoSeries(gpd.points_from_xy(gg.lon, gg.lat), crs=4326).to_crs(EPSG)
    main = flow[flow["divergence"] != 2]
    lp, dist, fda = [], [], []
    for p, da in zip(pts, gg["da_km2"]):
        d = main.distance(p)
        cand = d[d <= GAUGE_SNAP_M].index
        if len(cand):  # the nearby flowline whose drainage area matches best
            k = min(cand, key=lambda h: abs(np.log(main.loc[h, "totdasqkm"] / da)))
        else:
            k = d.idxmin()
        lp.append(int(main.loc[k, "levelpathi"]))
        dist.append(float(d[k]))
        fda.append(float(main.loc[k, "totdasqkm"]))
    gg["levelpathi"], gg["snap_m"], gg["nhd_da_km2"] = lp, dist, fda
    gg["x"], gg["y"] = shapely.get_x(pts.values), shapely.get_y(pts.values)
    # a site anchors its level path only if it sits on it (snap and drainage area agree)
    ratio = gg["nhd_da_km2"] / gg["da_km2"]
    gg["on_path"] = (gg["snap_m"] <= GAUGE_SNAP_M) & (ratio > 0.67) & (ratio < 1.5)
    return gg.sort_values("da_km2").reset_index(drop=True)


# ── painting ──────────────────────────────────────────────────────────────────
def paint(G: Grid, line, grid, prof, hw, code, extra=None, exclude=None, skip_src=()):
    """Pixels of the bed grid to burn for one profile: (flat index, z, code).
    A pixel is in if it lies within ``hw(station)`` of the centreline, or inside
    ``extra`` (UTM), and not inside ``exclude``; its value is the profile at its
    station (flat across the channel) and its code that of the nearest station
    (``code``: an int, or one per station). Pixels whose bed_source code is in
    ``skip_src`` are left alone."""
    ok = np.isfinite(prof)
    if ok.sum() < 2:
        return None
    zone = line.buffer(float(np.nanmax(hw)))
    if extra is not None and not extra.is_empty:
        zone = zone.union(extra)
    if exclude is not None and not exclude.is_empty:
        zone = zone.difference(exclude)
    if zone.is_empty:
        return None
    reg_ll = shapely.ops.transform(lambda x, y: G.to_ll.transform(x, y), zone)
    win = from_bounds(*reg_ll.bounds, transform=G.T).round_offsets().round_lengths()
    win = win.intersection(Window(0, 0, G.W, G.H))
    if win.width < 1 or win.height < 1:
        return None
    wt = rasterio.windows.transform(win, G.T)
    m = geometry_mask([reg_ll], (int(win.height), int(win.width)), wt, invert=True)
    rr, cc = np.nonzero(m)
    if rr.size == 0:
        return None
    lon = wt.c + (cc + 0.5) * wt.a
    lat = wt.f + (rr + 0.5) * wt.e
    x, y = G.to_utm.transform(lon, lat)
    pts = shapely.points(x, y)
    st = shapely.line_locate_point(line, pts)
    dd = shapely.distance(line, pts)
    keep = dd <= np.interp(st, grid, hw)
    if extra is not None and not extra.is_empty:
        keep |= shapely.contains_xy(extra, x, y)
    keep &= (st >= grid[ok][0]) & (st <= grid[ok][-1])
    # nothing beyond the ends: a pixel that projects onto an end point lies past the
    # head of tide or out in the water the reach runs into (the Delaware, for a creek)
    keep &= (st > END_TOL_M) & (st < line.length - END_TOL_M)
    if skip_src:
        sw = G.src.read(1, window=win)
        keep &= ~np.isin(sw[rr, cc], list(skip_src))
    # a NaN station is a gap (e.g. a non-tidal stretch left unburned): never bridged
    j = np.clip(np.searchsorted(grid, st), 0, len(grid) - 1)
    keep &= ok[j] & ok[np.clip(j - 1, 0, len(grid) - 1)]
    if not keep.any():
        return None
    z = np.interp(st[keep], grid[ok], prof[ok])
    flat = (rr[keep] + int(win.row_off)).astype("int64") * G.W + (cc[keep] + int(win.col_off))
    codes = np.broadcast_to(np.asarray(code, dtype="uint8"), grid.shape)
    k = np.clip(np.searchsorted(grid, st[keep]), 0, len(grid) - 1)
    return flat, z.astype("float32"), codes[k].copy()


# ── tidal reaches ─────────────────────────────────────────────────────────────
def tidal_reach(name, spec, flow, G, nodes, enc_s, enc_a, areas, law, land):
    head = gpd.GeoSeries([shapely.Point(spec["head"])], crs=4326).to_crs(EPSG).iloc[0]
    main = flow[flow["divergence"] != 2]
    k = int(main.distance(head).idxmin())
    path = downstream_path(flow, k)
    s_head = float(shapely.line_locate_point(flow.loc[k, "geometry"], head))
    pieces = chain(flow, path, cut={k: (s_head, flow.loc[k, "geometry"].length)})
    line, marks = max(pieces, key=lambda p: p[0].length)
    # the mouth: the start of the final open-water run (bed_source 3), small gaps allowed
    g0 = np.arange(0.0, line.length, TIDAL_STEP_M)
    q = shapely.line_interpolate_point(line, g0)
    src = G.sample(shapely.get_x(q), shapely.get_y(q), which="src")
    i = len(src)
    gap = 0
    for j in range(len(src) - 1, -1, -1):
        if src[j] == 3:
            i, gap = j, 0
        else:
            gap += 1
            if gap > MOUTH_GAP:
                break
    mouth = g0[i] if i < len(src) else line.length
    width = water_width(line, g0, land)
    wide = width > MOUTH_WIDTH_M
    if wide.any():
        mouth = min(mouth, g0[np.argmax(wide)])
    line = shapely.ops.substring(line, 0.0, mouth)
    grid = np.arange(0.0, line.length + TIDAL_STEP_M / 2, TIDAL_STEP_M)
    da = da_along(flow, marks, grid)
    mllw, node_ids = mllw_along(line, nodes, grid)
    width = np.clip(riverbed.power_law(da, *law["width"]), MIN_WIDTH, None)
    hw = np.minimum(width / 2.0, TIDAL_MAX_HALFWIDTH_M)
    a = areas[areas.intersects(line.buffer(10.0))]
    chan_extra = shapely.union_all(a.geometry.values).intersection(line.buffer(TIDAL_MAX_HALFWIDTH_M)) if len(a) else shapely.Polygon()
    chan = line.buffer(1.0).union(chan_extra) if not chan_extra.is_empty else line.buffer(MIN_WIDTH / 2)
    # soundings inside the channel
    near = enc_s[shapely.dwithin(chan, enc_s.geometry.values, SOUNDING_TOL_M)]
    s_all = shapely.line_locate_point(line, near.geometry.values)
    inner = (s_all > END_TOL_M) & (s_all < line.length - END_TOL_M)  # not past either end
    near, s_snd = near[inner], s_all[inner]
    z_snd = riverbed.chart_to_navd88(near["depth_m"].values, np.interp(s_snd, grid, mllw))
    p_snd = riverbed.fill_interior(grid, riverbed.running_median(s_snd, z_snd, grid, TIDAL_WINDOW_M, TIDAL_MIN_N,
                                                                       TIDAL_MAX_HALF_M))
    # USACE eHydro survey: replaces the chart where it reaches
    p_eh, eh_sid, eh_cov = np.full(grid.shape, np.nan), "", []
    if spec.get("ehydro"):
        p_eh, eh_sid, eh_cov = ehydro_profile(spec["ehydro"], line, chan, grid, mllw)
    p_snd = np.where(np.isfinite(p_eh), np.nan, p_snd)
    # chart depth areas elsewhere
    cx, cy, _, _ = normals(line, grid)
    d_area = np.full(grid.shape, np.nan)
    sidx = enc_a.sindex
    for j in np.nonzero(~np.isfinite(p_snd) & ~np.isfinite(p_eh))[0]:
        p = shapely.Point(cx[j], cy[j])
        for rad in DEPARE_RADIUS_M:  # chart areas the centreline itself runs through
            hit = sidx.query(p.buffer(rad).intersection(line.buffer(1.0)), predicate="intersects")
            if hit.size:
                d_area[j] = riverbed.depare_depth(enc_a["DRVAL1"].values[hit], enc_a["DRVAL2"].values[hit],
                                                  shallow_m=TAIL_MLLW_M)
                break
    p_area = mllw - d_area
    p_tail = mllw - TAIL_MLLW_M
    code = np.select([np.isfinite(p_eh), np.isfinite(p_snd), np.isfinite(p_area)], [6, 1, 2], 3)
    comb = np.select([np.isfinite(p_eh), np.isfinite(p_snd), np.isfinite(p_area)], [p_eh, p_snd, p_area], p_tail)
    prof = riverbed.running_median(grid, comb, grid, TIDAL_SMOOTH_M)
    prof[~np.isfinite(comb)] = np.nan
    prof = riverbed.fill_interior(grid, prof)
    bed_cl = G.sample(cx, cy)
    # open water (bed_source 3: lidar NoData -> CUDEM's surveyed bed) is never painted:
    # the burn is for channels the lidar paved over. It also keeps the Delaware itself
    # out, which NHDPlus HR draws as ONE StreamRiver polygon with its tidal creeks.
    p = paint(G, line, grid, prof, hw, code, extra=chan_extra, skip_src=(3,))
    out = [p] if p is not None else []
    prof_df = pd.DataFrame({"reach": name, "kind": "tidal", "station_m": grid, "da_km2": da,
                            "mllw_navd88_m": mllw, "chart_depth_area_m": d_area,
                            "soundings_bed_m": p_snd, "ehydro_bed_m": p_eh, "bed_profile_m": prof, "src": code,
                            "bed_merged_cl_m": bed_cl, "x": cx, "y": cy})  # fmt: skip
    row = {"reach": name, "kind": "tidal", "river": spec["river"], "length_km": line.length / 1e3,
           "levelpathi": int(flow.loc[k, "levelpathi"]),
           "da_km2_max": float(np.nanmax(da)), "n_soundings": int(len(near)),
           "soundings_to_km": float(s_snd.min() / 1e3) if len(near) else np.nan,
           "ehydro_survey": eh_sid, "km_ehydro": float((code == 6).sum() * TIDAL_STEP_M / 1e3),
           "km_soundings": float((code == 1).sum() * TIDAL_STEP_M / 1e3),
           "km_chart_area": float((code == 2).sum() * TIDAL_STEP_M / 1e3),
           "km_uncharted": float((code == 3).sum() * TIDAL_STEP_M / 1e3),
           "mllw_navd88_m": f"{mllw[0]:+.2f} head .. {mllw[-1]:+.2f} mouth",
           "datum_nodes": " ".join(node_ids), "channel_area_km2": chan.area / 1e6,
           "bed_p50_m": float(np.nanmedian(prof)), "bed_min_m": float(np.nanmin(prof)),
           "bed_max_m": float(np.nanmax(prof)), "note": spec.get("note", "")}  # fmt: skip
    used = pd.DataFrame({"reach": name, "station_m": s_snd, "depth_below_mllw_m": near["depth_m"].values,
                         "z_navd88_m": z_snd, "cell": near["cell"].values})  # fmt: skip
    return line, out, prof_df, row, path, used, eh_cov


# ── non-tidal streams ─────────────────────────────────────────────────────────
def nontidal_ids(flow, hot: dict[int, float], da_min: float, tidal: set[int]) -> dict[int, int]:
    """{hydroseq: hydroseq of the HoT flowline it drains to} for flowlines with
    DA >= da_min, not minor divergences, that drain to a head-of-tide point. Flowlines
    on a tidal reach's path (``tidal``) are never non-tidal, and a HoT point that
    snapped onto one (a tributary's point near its confluence) is ignored."""
    hot = {h: s for h, s in hot.items() if h not in tidal}
    sel = flow[(flow["divergence"] != 2) & (flow["totdasqkm"] >= da_min) & ~flow.index.isin(list(tidal))]
    memo: dict[int, int | None] = {}
    for h in sel.index:
        seen, cur, res = [], int(h), None
        while True:
            if cur in memo:
                res = memo[cur]
                break
            seen.append(cur)
            if cur in hot:
                res = cur
                break
            if cur not in flow.index:
                break
            cur = int(flow.loc[cur, "dnhydroseq"])
        for s in seen:
            memo[s] = res
    return {h: memo[h] for h in sel.index if memo.get(h) is not None}


def anchor_targets(gauges: pd.DataFrame) -> pd.DataFrame:
    """Bed (m NAVD88) at each ``ANCHOR_SITES`` gauge = gauge datum (must be NAVD88) +
    median gage height of its discharge measurements in the p25-p75 flow band since
    ``ANCHOR_SINCE`` - the gauge's mean depth (the same band)."""
    sites = pd.read_csv(CH / "usgs_sites.csv", dtype={"site": str}).set_index("site")
    fm = pd.read_csv(CH / "usgs_gage_heights.csv", dtype={"site": str}, low_memory=False)
    cm = pd.read_csv(CH / "usgs_channel_measurements.csv", dtype={"site": str}, low_memory=False)
    rows = []
    for s, name in ANCHOR_SITES.items():
        st = sites.loc[s]
        if st["altitude_datum"] != "NAVD88":
            raise ValueError(f"{s} {name}: gauge datum is {st['altitude_datum']}, not NAVD88")
        f = fm[(fm["site"] == s) & (fm["unit_of_measure"] == "ft") & (fm["time"] >= ANCHOR_SINCE)]
        c = cm[cm["site"] == s].dropna(subset=["channel_flow"])
        q = c["channel_flow"].values
        band = c[(q >= np.percentile(q, 25)) & (q <= np.percentile(q, 75))]
        j = f.merge(band[["field_visit_id"]], on="field_visit_id")
        g = gauges.set_index("site").loc[s]
        datum = st["altitude_ft"] * riverbed.FT
        stage = float(j["value"].median()) * riverbed.FT
        rows.append({"site": s, "name": name, "datum_navd88_m": datum, "stage_p50_m": stage,
                     "n_stage": len(j), "depth_m": g["depth_m"], "bed_navd88_m": datum + stage - g["depth_m"],
                     "levelpathi": g["levelpathi"], "x": g["x"], "y": g["y"]})  # fmt: skip
    return pd.DataFrame(rows)


def nontidal_path(lp, ids, flow, G, hot, law, gauges, lakes, areas, anchors):
    ids = sorted(ids, key=lambda h: -flow.loc[h, "hydroseq"])  # upstream first
    cut = {h: (0.0, hot[h]) for h in ids if h in hot}
    out_rows, prof_rows, paints = [], [], []
    for pi, (line, marks) in enumerate(chain(flow, ids, cut=cut)):
        if line.length < 3 * NT_STEP_M:
            continue
        grid = np.arange(0.0, line.length + NT_STEP_M / 2, NT_STEP_M)
        da = da_along(flow, marks, grid)
        cx, cy, nx, ny = normals(line, grid)
        xs = (cx[:, None] + nx[:, None] * NT_OFFSETS_M).ravel()
        ys = (cy[:, None] + ny[:, None] * NT_OFFSETS_M).ravel()
        ss = np.repeat(grid, len(NT_OFFSETS_M))
        zs = G.sample(xs, ys)
        okz = np.isfinite(zs)
        o = np.argsort(ss[okz])
        s_ok, z_ok = ss[okz][o], zs[okz][o]
        lo = np.searchsorted(s_ok, grid - SURF_BIN_M)
        hi = np.searchsorted(s_ok, grid + SURF_BIN_M, side="right")
        raw = np.array([np.percentile(z_ok[a:b], SURF_PCT) if b - a >= 3 else np.nan for a, b in zip(lo, hi)])
        surf = riverbed.monotone_downstream(riverbed.running_median(grid, raw, grid, SURF_SMOOTH_M))
        g_here = gauges[(gauges["levelpathi"] == lp) & gauges["on_path"]]
        base_d = riverbed.power_law(da, *law["depth"])
        base_w = riverbed.power_law(da, *law["width"])
        if len(g_here):
            rd = g_here["depth_m"].values / riverbed.power_law(g_here["da_km2"].values, *law["depth"])
            rw = g_here["width_m"].values / riverbed.power_law(g_here["da_km2"].values, *law["width"])
            depth = base_d * riverbed.interp_log_da(g_here["da_km2"].values, rd, da)
            width = base_w * riverbed.interp_log_da(g_here["da_km2"].values, rw, da)
            code = 4
        else:
            depth, width, code = base_d, base_w, 5
        hw = np.clip(np.maximum(width, MIN_WIDTH) / 2.0, None, NT_MAX_HALFWIDTH_M)
        prof = surf - depth
        codes = np.full(grid.shape, code)
        anchored = []
        for a in anchors[anchors["levelpathi"] == lp].itertuples():
            pt = shapely.Point(a.x, a.y)
            if line.distance(pt) > 100.0:
                continue
            s_g = float(line.project(pt))
            delta = a.bed_navd88_m - float(np.interp(s_g, grid, prof))
            prof = prof + riverbed.taper(grid, s_g, delta, ANCHOR_TAPER_M)
            codes[np.abs(grid - s_g) < ANCHOR_TAPER_M] = 7
            anchored.append(f"{a.site} {delta:+.2f} m")
        low = surf < NT_SURFACE_MIN_M  # tidal elevations behind a head of tide: not burned
        prof[low] = np.nan
        a = areas[areas.intersects(line.buffer(5.0))]
        extra = (shapely.union_all(a.geometry.values).intersection(line.buffer(NT_MAX_HALFWIDTH_M))
                 if len(a) else None)  # fmt: skip
        lk = lakes[lakes.intersects(line.buffer(NT_MAX_HALFWIDTH_M))]
        excl = shapely.union_all(lk.geometry.values) if len(lk) else None
        p = paint(G, line, grid, prof, hw, codes, extra=extra, exclude=excl)
        if p is not None:
            paints.append(p)
        in_lake = (shapely.contains_xy(excl, cx, cy) if excl is not None else np.zeros(grid.shape, bool))
        names = flow.loc[[m[1] for m in marks], "gnis_name"].dropna()
        nm = names.mode().iloc[0] if len(names) else ""
        rid = f"lp{lp}" + (f"_{pi}" if pi else "")
        prof_rows.append(pd.DataFrame({"reach": rid, "kind": "non-tidal", "station_m": grid, "da_km2": da,
                                       "surface_raw_m": raw, "surface_m": surf, "depth_m": depth,
                                       "width_m": width, "bed_profile_m": prof, "src": codes,
                                       "in_lake": in_lake, "x": cx, "y": cy}))  # fmt: skip
        out_rows.append({"reach": rid, "kind": "non-tidal", "river": nm, "length_km": line.length / 1e3,
                         "da_km2_min": float(da.min()), "da_km2_max": float(da.max()),
                         "gauges": " ".join(g_here["site"]), "depth_m": f"{depth.min():.2f}..{depth.max():.2f}",
                         "width_m": f"{width.min():.1f}..{width.max():.1f}",
                         "km_in_lakes": float(in_lake.sum() * NT_STEP_M / 1e3),
                         "km_low_surface_unburned": float(low.sum() * NT_STEP_M / 1e3),
                         "anchored": "; ".join(anchored),
                         "surface_drop_m": float(np.nanmax(surf) - np.nanmin(surf)) if np.isfinite(surf).any() else np.nan,
                         "bed_p50_m": float(np.nanmedian(prof)) if np.isfinite(prof).any() else np.nan,
                         "src": code, "line": line})  # fmt: skip
    return out_rows, prof_rows, paints


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    global MIN_WIDTH
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--da-min", type=float, default=10.0, help="non-tidal: min drainage area km2")
    ap.add_argument("--min-width", type=float, default=10.0, help="painted strip floor, m")
    ap.add_argument("--no-raster", action="store_true", help="tables/profiles only")
    a = ap.parse_args()
    MIN_WIDTH = a.min_width

    flow = load_flowlines()
    G = Grid()
    hot = hot_points(flow)
    print(f"head of tide: {len(hot)} flowlines carry an NJDEP point within {HOT_SNAP_M:.0f} m")

    gauges = gauge_geometry(flow)
    gauges.to_csv(CH / "gauge_geometry.csv", index=False)
    stream = gauges[gauges["site_type"].fillna("").str.contains("Stream")]
    law = {"depth": riverbed.power_law_fit(stream["da_km2"], stream["depth_m"]),
           "width": riverbed.power_law_fit(stream["da_km2"], stream["width_m"])}  # fmt: skip
    print(f"gauges: {len(gauges)} sites with >= {MIN_MEAS} measurements in their p25-p75 flow band; "
          f"depth = {law['depth'][0]:.3f} DA^{law['depth'][1]:.3f}, "
          f"width = {law['width'][0]:.2f} DA^{law['width'][1]:.3f} (m, km2)")  # fmt: skip

    nodes = datum_nodes()
    nodes.drop(columns="geometry").to_csv(CH / "tidal_datum_nodes.csv", index=False)
    enc_s = gpd.read_file(CH / "enc_ring.gpkg", layer="SOUNDG").to_crs(EPSG)
    enc_a = gpd.read_file(CH / "enc_ring.gpkg", layer="DEPARE").to_crs(EPSG)
    enc_a = enc_a[enc_a.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].reset_index(drop=True)
    areas = gpd.read_file(CH / "nhdplus_hr.gpkg", layer="area").to_crs(EPSG)
    land = shapely.union_all(gpd.read_file(CH / "enc_ring.gpkg", layer="LNDARE").to_crs(EPSG).geometry.values)
    shapely.prepare(land)
    lakes = gpd.read_file(CH / "nhdplus_hr.gpkg", layer="waterbody").to_crs(EPSG)
    lakes = lakes[lakes["areasqkm"] >= LAKE_MIN_KM2]

    rows, profs, paints, lines, tidal, snd_used, eh_cov = [], [], [], {}, set(), [], []
    for name, spec in domain.TIDAL_REACHES.items():
        line, p, prof_df, row, path, used, cov = tidal_reach(name, spec, flow, G, nodes, enc_s, enc_a, areas, law, land)
        tidal |= set(path[1:])  # the head flowline keeps its non-tidal upper part
        lines[name] = line
        snd_used.append(used)
        eh_cov += [dict(c, reach=name) for c in cov]
        rows.append(row)
        profs.append(prof_df)
        paints += p
        print(f"  tidal {name:10s} {row['length_km']:5.1f} km, eHydro {row['ehydro_survey'] or '-'} "
              f"({row['km_ehydro']:.1f} km), {row['n_soundings']:4d} soundings "
              f"({row['km_soundings']:.1f} km), chart areas {row['km_chart_area']:.1f} km, "
              f"uncharted {row['km_uncharted']:.1f} km, MLLW "
              f"{row['mllw_navd88_m']}, bed p50 {row['bed_p50_m']:+.2f}")  # fmt: skip

    anchors = anchor_targets(gauges)
    anchors.to_csv(CH / "gauge_anchors.csv", index=False, float_format="%.3f")
    for r in anchors.itertuples():
        print(f"  anchor {r.site} {r.name}: datum {r.datum_navd88_m:+.2f} + stage {r.stage_p50_m:.2f} "
              f"(n {r.n_stage}) - depth {r.depth_m:.2f} = bed {r.bed_navd88_m:+.2f} m NAVD88")
    nt = nontidal_ids(flow, hot, a.da_min, tidal)
    by_lp: dict[int, list[int]] = {}
    for h in nt:
        by_lp.setdefault(int(flow.loc[h, "levelpathi"]), []).append(h)
    print(f"non-tidal: {len(nt)} flowlines >= {a.da_min} km2 above a head of tide, {len(by_lp)} level paths")
    nt_lines = []
    for lp, ids in by_lp.items():
        r, p, pt = nontidal_path(lp, ids, flow, G, hot, law, gauges, lakes, areas, anchors)
        for rr in r:
            nt_lines.append({"reach": rr["reach"], "river": rr["river"], "geometry": rr.pop("line")})
        rows += r
        profs += p
        paints += pt

    pd.concat(snd_used, ignore_index=True).to_csv(ELEV / "riverbed_soundings.csv", index=False, float_format="%.3f")
    pd.DataFrame(eh_cov).to_csv(EHYDRO_DIR / "coverage.csv", index=False, float_format="%.2f")
    table = pd.DataFrame(rows)
    table.to_csv(ELEV / "river_table.csv", index=False)
    pd.concat(profs, ignore_index=True).to_csv(ELEV / "riverbed_profiles.csv", index=False, float_format="%.3f")
    gl = gpd.GeoDataFrame(
        [{"reach": k, "river": domain.TIDAL_REACHES[k]["river"], "kind": "tidal", "geometry": v} for k, v in lines.items()]
        + [dict(d, kind="non-tidal") for d in nt_lines], crs=EPSG)  # fmt: skip
    gl.to_file(ELEV / "riverbed_centrelines.gpkg", driver="GPKG")
    print(f"wrote {ELEV / 'river_table.csv'} ({len(table)} rows), riverbed_profiles.csv, riverbed_centrelines.gpkg")
    if a.no_raster:
        return

    flat = np.concatenate([p[0] for p in paints])
    z = np.concatenate([p[1] for p in paints])
    code = np.concatenate([p[2] for p in paints])
    o = np.lexsort((z, flat))  # by pixel, deepest first
    flat, z, code = flat[o], z[o], code[o]
    first = np.r_[True, flat[1:] != flat[:-1]]
    flat, z, code = flat[first], z[first], code[first]
    print(f"painting {flat.size:,} pixels; reading bed_merged ...", flush=True)
    bed = G.bed.read(1).astype("float32")
    bed[bed == G.bed.nodata] = np.nan
    b = bed.ravel()[flat]
    burn = riverbed.never_raise(b, z)
    keep = np.isfinite(burn)
    print(f"  {keep.sum():,} of {flat.size:,} lower the bed (the rest are already deeper)")
    out = np.full(bed.shape, NODATA, dtype="float32")
    srcr = np.zeros(bed.shape, dtype="uint8")
    out.ravel()[flat[keep]] = burn[keep]
    srcr.ravel()[flat[keep]] = code[keep]
    del bed
    prof = G.bed.profile.copy()
    prof.update(dtype="float32", nodata=NODATA, compress="deflate", predictor=3, tiled=True,
                blockxsize=512, blockysize=512, BIGTIFF="YES")  # fmt: skip
    with rasterio.open(ELEV / "riverbed_burn.tif", "w", **prof) as d:
        d.write(out, 1)
        d.update_tags(note="river-bed burn, m NAVD88; merge as min(bed_merged, burn); "
                           "scripts/build_riverbeds.py", **{f"src_{k}": v for k, v in SRC_NAMES.items()})  # fmt: skip
    prof.update(dtype="uint8", nodata=0, predictor=2)
    with rasterio.open(ELEV / "riverbed_source.tif", "w", **prof) as d:
        d.write(srcr, 1)
        d.update_tags(**{f"src_{k}": v for k, v in SRC_NAMES.items()})
    lower = b[keep] - burn[keep]
    px_area = abs(G.T.a * G.T.e) * (111_320 * np.cos(np.radians(39.45))) * 110_574
    for c, n in SRC_NAMES.items():
        m = code[keep] == c
        if m.any():
            print(f"  src {c} {n:36s} {m.sum() * px_area / 1e6:7.2f} km2, lowered by "
                  f"p50 {np.median(lower[m]):.2f} m (p90 {np.percentile(lower[m], 90):.2f})")
    print(f"wrote {ELEV / 'riverbed_burn.tif'} and riverbed_source.tif")


MIN_WIDTH = 10.0

if __name__ == "__main__":
    main()
