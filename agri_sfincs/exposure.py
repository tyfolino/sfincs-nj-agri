"""Tidal exposure on the 30 m CDL grid: recent high water spread over the domain, ground
height, and the "connected low ground" bathtub. Method: FINDINGS §21 (first built by
scripts/bayshore_exposure.py, deleted 2026-10-23, in git); most of the land-change scripts
reuse them.

Delaware (``side="de"``, 2026-10-23): the same on the DE bed (bed_merged_de.tif) and DE CDL,
with high water from the recent records at Reedy Point, Ship John and Lewes plus every
NAVD88-tied CO-OPS datum sheet inside the DE ring (data/channels/de/coops_datums.csv), moved
to the recent epoch by Reedy Point's shift, as NJ's Fortescue and Bivalve sheets are.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import rasterio
import rasterio.warp
import xarray as xr
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from scipy import ndimage
from shapely.geometry import Point

from agri_sfincs import cdl, config, dikes, domain, region, waterlevel
from agri_sfincs.riverbed import coops_datum_navd88

BED = config.ELEV_DIR / "bed_merged.tif"
#: km² of one 30 m CDL pixel.
PX_KM2 = 0.03 * 0.03
#: The forcing gauges minus Cape May (ocean side).
FORCING = [s for s in waterlevel.FORCING if s != domain.CAPE_MAY]
EPOCH_SHEETS = ["8536931", "8535055"]  # Fortescue, Bivalve: 1983-2001 datum sheets
EPOCH_REF = "8551910"  # Reedy Point: has both a sheet and a recent record
LEWES = "8557380"
#: Delaware: the observed gauges nearest its shore (Lewes from its own hourly record)
DE_RECENT = ["8551910", "8537121", LEWES]


def recent_levels(y0=2021, y1=2025) -> pd.DataFrame:
    """Per forcing gauge: MHHW (mean daily max) and median annual max of observed hourly
    levels, m NAVD88, plus lon/lat."""
    rows = []
    with xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc") as ds:
        for s in ds.stations.values:
            w = ds.waterlevel.sel(stations=s).to_series()
            src = ds.source.sel(stations=s).to_series()
            x = w[(w.index.year >= y0) & (w.index.year <= y1) & (src == "obs")]
            d = x.resample("D").max()[x.resample("D").count() >= 20]
            rows.append({"id": str(s), "name": str(ds.name.sel(stations=s).values),
                         "lon": float(ds.lon.sel(stations=s)), "lat": float(ds.lat.sel(stations=s)),
                         "mhhw": d.mean(), "annmax": x.groupby(x.index.year).max().median()})  # fmt: skip
    return pd.DataFrame(rows).set_index("id")


def lewes_levels(y0=2021, y1=2025) -> pd.Series:
    """Lewes MHHW / median annual max (m NAVD88) from its hourly MLLW record and NAVD88 tie,
    as ``recent_levels`` (Lewes is a donor, not a forcing gauge, so not in that file)."""
    h = pd.read_csv(config.GAUGE_DIR / "noaa" / f"{LEWES}_hourly_mllw.csv.gz", parse_dates=["time"]).set_index("time")
    sep, _ = waterlevel.navd_minus_mllw(LEWES)
    x = h.wl_m_mllw[(h.index.year >= y0) & (h.index.year <= y1)].dropna() - sep
    d = x.resample("D").max()[x.resample("D").count() >= 20]
    return pd.Series({"name": "Lewes, DE", "lon": -75.1193, "lat": 38.7828, "mhhw": d.mean(),
                      "annmax": x.groupby(x.index.year).max().median()})  # fmt: skip


def high_water_stations(side: str = "nj") -> pd.DataFrame:
    rec = recent_levels()
    if side != "nj":
        rec.loc[LEWES] = lewes_levels()
    sheets = pd.read_csv(config.channels_dir(side) / "coops_datums.csv", dtype={"id": str}).set_index("id")
    sheet_mhhw = {i: coops_datum_navd88(r, "MHHW") for i, r in sheets.iterrows()}
    shift = rec.loc[EPOCH_REF, "mhhw"] - sheet_mhhw[EPOCH_REF]
    recent = FORCING if side == "nj" else DE_RECENT
    surge = (rec.loc[recent, "annmax"] - rec.loc[recent, "mhhw"]).mean()
    st = rec.loc[recent, ["name", "lon", "lat", "mhhw", "annmax"]].assign(source="2021-25 obs")
    if side == "nj":
        epoch = EPOCH_SHEETS
    else:  # every NAVD88-tied sheet inside the side's ring, not already an observed gauge
        ring = region.load_ring(side).to_crs(4326).union_all()
        epoch = [i for i, r in sheets.iterrows() if np.isfinite(sheet_mhhw[i]) and i not in st.index
                 and ring.contains(Point(r["lon"], r["lat"]))]  # fmt: skip
    for i in epoch:
        st.loc[i] = [sheets.loc[i, "name"], sheets.loc[i, "lon"], sheets.loc[i, "lat"],
                     sheet_mhhw[i] + shift, sheet_mhhw[i] + shift + surge,
                     f"sheet + {shift:.2f} m"]  # fmt: skip
    return st


def idw(st: pd.DataFrame, col: str, x: np.ndarray, y: np.ndarray, crs, p=2.0) -> np.ndarray:
    sx, sy = Transformer.from_crs(4326, crs, always_xy=True).transform(st.lon.values, st.lat.values)
    w = 1.0 / np.maximum(np.hypot(x[..., None] - sx, y[..., None] - sy), 100.0) ** p
    return (w * st[col].values).sum(-1) / w.sum(-1)


def connected_low(zmean, zmax, level, seed) -> tuple[np.ndarray, np.ndarray]:
    low = zmean < level
    lab, _ = ndimage.label(zmax < level)  # 4-connected
    hit = np.unique(lab[seed & (lab > 0)])
    reach = np.isin(lab, hit[hit > 0]) | seed
    return low, low & ndimage.binary_dilation(reach)


def load_grid(side: str = "nj") -> SimpleNamespace:
    """The 30 m CDL window over the side's model domain: ``win``, ``tr``, ``crs``, ``shape``;
    ground ``z_mean`` / ``z_max`` (NaN off the DEM); high water ``hw["mhhw"]`` /
    ``hw["annmax"]`` (IDW, m NAVD88); ``hab`` = z_mean - MHHW."""
    sd = domain.side(side)
    bed = config.ELEV_DIR / f"bed_merged{sd.files}.tif"
    with rasterio.open(cdl.path(2025, sd.state_fips)) as c, rasterio.open(bed) as b:
        bnd = rasterio.warp.transform_bounds(b.crs, c.crs, *b.bounds)
        win = from_bounds(*bnd, transform=c.transform).round_offsets().round_lengths()
        tr, crs = c.window_transform(win), c.crs
        shape = (int(win.height), int(win.width))
        grid = dict(crs=crs, transform=tr, width=shape[1], height=shape[0], nodata=np.nan)
        z = {}
        for k, rs in (("mean", Resampling.average), ("max", Resampling.max)):
            with WarpedVRT(b, resampling=rs, src_nodata=b.nodata, dtype="float32", **grid) as v:
                z[k] = v.read(1)
    st = high_water_stations(side)
    xs = tr.c + tr.a * (np.arange(0, shape[1], 20) + 0.5)
    ys = tr.f + tr.e * (np.arange(0, shape[0], 20) + 0.5)
    coarse = {k: idw(st, k, *np.meshgrid(xs, ys), crs) for k in ("mhhw", "annmax")}
    hw = {k: np.kron(v, np.ones((20, 20)))[: shape[0], : shape[1]] for k, v in coarse.items()}
    return SimpleNamespace(win=win, tr=tr, crs=crs, shape=shape, grid=grid, z_mean=z["mean"],
                           z_max=z["max"], hw=hw, hab=z["mean"] - hw["mhhw"], stations=st)  # fmt: skip


def add_exposure(g, side: str = "nj"):
    """``g`` (polygons) plus ``m_above_mhhw`` (median height above recent MHHW) and
    ``leveed_share``, on the 30 m grid of ``load_grid`` (FINDINGS §21)."""
    G = load_grid(side)
    gg = g.to_crs(G.crs)
    lab = np.zeros(G.shape, dtype="int64")
    # rasterize in chunks keyed by row number + 1 (small polygons may miss every cell centre)
    for k in range(0, len(gg), 5000):
        sub = gg.iloc[k : k + 5000]
        r = rasterize([(geom, i + 1) for i, geom in zip(range(k, k + len(sub)), sub.geometry)],
                      out_shape=G.shape, transform=G.tr, fill=0, dtype="int64")  # fmt: skip
        lab = np.where(r > 0, r, lab)
    lev = dikes.leveed_areas(G.crs, side)
    leveed = rasterize([(x, 1) for x in lev.geometry], out_shape=G.shape, transform=G.tr,
                       fill=0, dtype="uint8")  # fmt: skip
    ok = (lab > 0) & np.isfinite(G.hab)
    df = pd.DataFrame({"i": lab[ok] - 1, "hab": G.hab[ok], "lev": leveed[ok]})
    agg = df.groupby("i").agg(hab_p50=("hab", "median"), leveed=("lev", "mean"))
    g = g.copy()
    g["m_above_mhhw"] = agg.hab_p50.reindex(range(len(g))).values
    g["leveed_share"] = agg.leveed.reindex(range(len(g))).values
    # polygons that hit no cell centre: sample the grid at a representative point
    miss = g.m_above_mhhw.isna()
    if miss.any():
        pts = gg.loc[miss].representative_point()
        rr = ((pts.y - G.tr.f) / G.tr.e).astype(int).clip(0, G.shape[0] - 1)
        cc = ((pts.x - G.tr.c) / G.tr.a).astype(int).clip(0, G.shape[1] - 1)
        g.loc[miss, "m_above_mhhw"] = G.hab[rr.values, cc.values]
        g.loc[miss, "leveed_share"] = leveed[rr.values, cc.values]
    return g
