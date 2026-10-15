"""Tidal exposure on the 30 m CDL grid: recent high water spread over the domain, ground
height, and the "connected low ground" bathtub. Method: scripts/bayshore_exposure.py
(FINDINGS §21), which first built these; most of the land-change scripts reuse them.
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

from agri_sfincs import cdl, config, dikes, domain, waterlevel
from agri_sfincs.riverbed import coops_datum_navd88

BED = config.ELEV_DIR / "bed_merged.tif"
#: km² of one 30 m CDL pixel.
PX_KM2 = 0.03 * 0.03
#: The forcing gauges minus Cape May (ocean side).
FORCING = [s for s in waterlevel.FORCING if s != domain.CAPE_MAY]
EPOCH_SHEETS = ["8536931", "8535055"]  # Fortescue, Bivalve: 1983-2001 datum sheets
EPOCH_REF = "8551910"  # Reedy Point: has both a sheet and a recent record


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


def high_water_stations() -> pd.DataFrame:
    rec = recent_levels()
    sheets = pd.read_csv(config.CHANNELS_DIR / "coops_datums.csv", dtype={"id": str}).set_index("id")
    sheet_mhhw = {i: coops_datum_navd88(r, "MHHW") for i, r in sheets.iterrows()}
    shift = rec.loc[EPOCH_REF, "mhhw"] - sheet_mhhw[EPOCH_REF]
    surge = (rec.loc[FORCING, "annmax"] - rec.loc[FORCING, "mhhw"]).mean()
    st = rec.loc[FORCING, ["name", "lon", "lat", "mhhw", "annmax"]].assign(source="2021-25 obs")
    for i in EPOCH_SHEETS:
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


def load_grid() -> SimpleNamespace:
    """The 30 m CDL window over the model domain: ``win``, ``tr``, ``crs``, ``shape``; ground
    ``z_mean`` / ``z_max`` (NaN off the DEM); high water ``hw["mhhw"]`` / ``hw["annmax"]``
    (IDW, m NAVD88); ``hab`` = z_mean - MHHW."""
    with rasterio.open(cdl.path(2025)) as c, rasterio.open(BED) as b:
        bnd = rasterio.warp.transform_bounds(b.crs, c.crs, *b.bounds)
        win = from_bounds(*bnd, transform=c.transform).round_offsets().round_lengths()
        tr, crs = c.window_transform(win), c.crs
        shape = (int(win.height), int(win.width))
        grid = dict(crs=crs, transform=tr, width=shape[1], height=shape[0], nodata=np.nan)
        z = {}
        for k, rs in (("mean", Resampling.average), ("max", Resampling.max)):
            with WarpedVRT(b, resampling=rs, src_nodata=b.nodata, dtype="float32", **grid) as v:
                z[k] = v.read(1)
    st = high_water_stations()
    xs = tr.c + tr.a * (np.arange(0, shape[1], 20) + 0.5)
    ys = tr.f + tr.e * (np.arange(0, shape[0], 20) + 0.5)
    coarse = {k: idw(st, k, *np.meshgrid(xs, ys), crs) for k in ("mhhw", "annmax")}
    hw = {k: np.kron(v, np.ones((20, 20)))[: shape[0], : shape[1]] for k, v in coarse.items()}
    return SimpleNamespace(win=win, tr=tr, crs=crs, shape=shape, grid=grid, z_mean=z["mean"],
                           z_max=z["max"], hw=hw, hab=z["mean"] - hw["mhhw"], stations=st)  # fmt: skip


def add_exposure(g):
    """``g`` (polygons) plus ``m_above_mhhw`` (median height above recent MHHW) and
    ``leveed_share``, on the 30 m grid of ``load_grid`` (FINDINGS §21)."""
    G = load_grid()
    gg = g.to_crs(G.crs)
    lab = np.zeros(G.shape, dtype="int64")
    # rasterize in chunks keyed by row number + 1 (small polygons may miss every cell centre)
    for k in range(0, len(gg), 5000):
        sub = gg.iloc[k : k + 5000]
        r = rasterize([(geom, i + 1) for i, geom in zip(range(k, k + len(sub)), sub.geometry)],
                      out_shape=G.shape, transform=G.tr, fill=0, dtype="int64")  # fmt: skip
        lab = np.where(r > 0, r, lab)
    lev = dikes.leveed_areas(G.crs)
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
