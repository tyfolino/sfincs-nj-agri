"""Water levels at the NOAA forcing gauges: NAVD88 conversion and gap filling.

Forcing gauges (user, 2026-10-02), upstream to the bay mouth:
    Philadelphia -> Marcus Hook -> Reedy Point -> Ship John Shoal -> Cape May
Gap filling: predicted tide at the gap station + the NON-TIDAL RESIDUAL (observed -
predicted) of a donor gauge, donors tried in order, hour by hour. Every filled hour
is flagged. Residuals change along the estuary (lag, amplification), so this is a
gap-filler for a mostly pluvial question, not a surge model.

Datum: everything is downloaded in MLLW (every station serves it) and shifted by
NAVD88 - MLLW. Stations with a CO-OPS NAVD88 tie use it; MLLW-only stations (Ship
John Shoal) take the transfer bight uses (nj_bight_sfincs
scripts/download_noaa_sandy_wl.py ``navd_minus_mllw``):
    NAVD88 - MLLW = (MSL - MLLW)_station + mean over neighbours of (NAVD88 - MSL)
which is uncertain by about 0.1 m at Ship John Shoal.

Virtual gauges (FINDINGS §41): Fortescue and Bidwell Creek entrance have harmonic
predictions but no observations; ``fill_virtual`` gives them predicted tide + a donor's
residual, so the boundary along the Cumberland shore is not Cape May's smaller tide.
``chain_boundary`` builds the boundary itself: one point per ~1 km of boundary, each a
LAG-AWARE blend of its two neighbours on CHAIN (agri_sfincs.events.setup_event).

``match_highs`` pairs every observed high tide at a gauge with the model's highest level
near it (scripts/validate_sandy.py, scripts/validate_storm_gauges.py); ``match_extremes``
does highs or lows where the 6-min record is complete around them; ``usgs_event_series``
reads a fetched gauge series (scripts/fetch_usgs_event.py) in m; ``his_series`` a run's
observation points; ``gauge_series`` one point, read from the channel cell under it
(``channel_series``) where the point itself sits on a bank cell.
"""

from __future__ import annotations

import pandas as pd

from agri_sfincs.net import get

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
MDAPI = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations"

#: Forcing gauges, upstream to mouth.
FORCING = ["8545240", "8540433", "8551910", "8537121", "8536110"]
#: Donors for residual transfer, nearest first. Lewes fills Cape May (both at the
#: mouth); everything inside the estuary leans on Reedy Point, the most complete
#: interior gauge.
DONORS = {
    "8545240": ["8540433", "8551910"],
    "8540433": ["8545240", "8551910"],
    "8551910": ["8540433", "8537121", "8545240"],
    "8537121": ["8551910", "8536110", "8557380"],
    "8536110": ["8557380", "8537121"],
    "8557380": ["8536110", "8537121"],  # Lewes: written for the DE chain (2026-10-23)
    "8555889": ["8557380", "8536110"],  # Brandywine Shoal: the DE rail (2026-10-29)
}
#: Gauges gap-filled and written to the forcing file besides FORCING: Lewes ends the DE chain,
#: Brandywine Shoal is its lower-bay point (2013 has no record: filled from Lewes).
EXTRA = ["8557380", "8555889"]


#: Virtual gauges (domain.VIRTUAL_STATIONS) -> donor of the non-tidal residual: level = own
#: predicted tide + the donor's (filled level - predicted tide).
VIRTUAL_DONOR = {"8536931": "8537121", "8536581": "8536110", "8554399": "8537121"}

#: The water-level boundary chain, bay mouth to Philadelphia (FINDINGS §41), and the tide's
#: travel time from each point to the next (h; lag of peak correlation between 2023 hourly
#: predictions, cubic to 6 min). Blending two neighbours ~1.3 h apart without moving them to
#: a common phase first loses ~6-8% of range midway.
CHAIN = ["8536110", "8536581", "8536931", "8537121", "8551910", "8540433", "8545240"]
CHAIN_LAG_H = [0.5, 0.4, 0.5, 1.2, 1.3, 1.2]
#: Per side. NJ's chain runs along the NJ shore (Bidwell 1.73, Fortescue 1.78 m mean range),
#: whose tide is bigger than mid-bay's; the first DE pass reused it on the state line and the
#: DE shore got ~15-20% too much tide (FINDINGS §46). The DE rail (2026-10-29) runs Lewes (1.24)
#: -> Brandywine Shoal (mid lower bay, 1.49) -> Mahon River entrance (DE shore, 1.62, virtual)
#: -> Ship John Shoal (mid-bay, 1.70) and then NJ's chain up-river. Lags as above (2023
#: predictions): 0.2, 0.9, 0.3 h.
CHAINS = {"nj": (CHAIN, CHAIN_LAG_H),
          "de": (["8557380", "8555889", "8554399", *CHAIN[3:]], [0.2, 0.9, 0.3, *CHAIN_LAG_H[3:]])}


def chain_pair(x: float, y: float, gx, gy) -> tuple[int, float]:
    """For a boundary point (x, y): (i, w) such that the point lies between chain points i and
    i + 1 at fraction w (0 at i, 1 at i + 1). The pair is the nearest chain point and the
    nearer of its two chain neighbours; w is SFINCS's inverse-distance weight."""
    import numpy as np

    d = np.hypot(np.asarray(gx) - x, np.asarray(gy) - y)
    n = int(np.argmin(d))
    nb = [i for i in (n - 1, n + 1) if 0 <= i < len(d)]
    m = min(nb, key=lambda i: d[i])
    a, b = min(n, m), max(n, m)
    return a, float(d[a] / (d[a] + d[b]))


def lag_blend(a: pd.Series, b: pd.Series, w: float, lag_h: float, index: pd.DatetimeIndex):
    """(1 - w) a(t - w lag) + w b(t + (1 - w) lag) on ``index``: ``b``'s tide arrives ``lag_h``
    after ``a``'s, and both are moved to the phase of a point at fraction ``w`` before they
    are weighted. Linear in time between the series' samples; NaN outside them."""
    import numpy as np

    lag = pd.Timedelta(hours=lag_h)
    ns = lambda i: pd.DatetimeIndex(i).as_unit("ns").asi8  # noqa: E731
    at = lambda s, t: np.interp(ns(t), ns(s.index), s.to_numpy(float), left=np.nan, right=np.nan)  # noqa: E731
    return (1 - w) * at(a, index - w * lag) + w * at(b, index + (1 - w) * lag)


def chain_boundary(levels: pd.DataFrame, x, y, gx, gy, index: pd.DatetimeIndex,
                   chain=CHAIN, lags=CHAIN_LAG_H) -> tuple[pd.DataFrame, list[str]]:  # fmt: skip
    """Water level at each boundary point (x[k], y[k]) on ``index``: the lag-aware blend of its
    two ``chain`` neighbours (default CHAIN; a side's from CHAINS). ``levels``: one column per
    chain id (hourly is fine: it is taken to 6 min by cubic interpolation first); gx, gy: the
    chain points' coordinates, same CRS as x, y. Returns (levels, one label per point
    "<id a>-<id b>:<w>")."""
    import numpy as np

    fine = levels[list(chain)].resample("6min").interpolate("cubic")
    cols, names = [], []
    for xk, yk in zip(x, y):
        i, w = chain_pair(xk, yk, gx, gy)
        cols.append(lag_blend(fine[chain[i]], fine[chain[i + 1]], w, lags[i], index))
        names.append(f"{chain[i]}-{chain[i + 1]}:{w:.2f}")
    return pd.DataFrame(np.array(cols).T, index=index), names


def datums(station: str) -> dict[str, float]:
    """CO-OPS tidal datums for a station, metres on station datum."""
    j = get(f"{MDAPI}/{station}/datums.json", {"units": "metric"}).json()
    return {d["name"]: float(d["value"]) for d in j.get("datums") or []}


def navd_minus_mllw(station: str, navd_from: list[str] | None = None,
                    own_tie: bool = True) -> tuple[float, str]:  # fmt: skip
    """(NAVD88 - MLLW in m, how it was obtained) — see the module docstring. ``own_tie=False``
    transfers from ``navd_from`` even if the station has a NAVD88 tie of its own."""
    own = datums(station)
    if "NAVD88" in own and own_tie:
        return own["NAVD88"] - own["MLLW"], "CO-OPS NAVD88 tie"
    if not navd_from:
        raise ValueError(f"{station} has no NAVD88 tie and no navd_from neighbours")
    seps = {n: (d := datums(n))["NAVD88"] - d["MSL"] for n in navd_from}
    sep = sum(seps.values()) / len(seps)
    how = f"transfer: MSL-MLLW {own['MSL'] - own['MLLW']:.3f} + NAVD88-MSL {sep:+.3f} from {seps}"
    return own["MSL"] - own["MLLW"] + sep, how


def predictions_year(station: str, year: int) -> pd.Series:
    """Hourly predicted tide (MLLW, m, UTC) for one calendar year."""
    params = {
        "product": "predictions", "application": "sfincs-nj-agri",
        "begin_date": f"{year}0101", "end_date": f"{year}1231 23:00",
        "datum": "MLLW", "station": station, "time_zone": "gmt",
        "units": "metric", "interval": "h", "format": "json",
    }  # fmt: skip
    j = get(API, params, timeout=120).json()
    if "predictions" not in j:
        raise RuntimeError(f"no predictions for {station} {year}: {j}")
    df = pd.DataFrame(j["predictions"])
    s = pd.to_numeric(df["v"])
    s.index = pd.to_datetime(df["t"])
    return s


def fill_gaps(
    obs: dict[str, pd.Series], pred: dict[str, pd.Series], index: pd.DatetimeIndex, stations=None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gap-fill every FORCING station (or ``stations``) on ``index``. Donors lend their RAW
    residual (obs - pred), never a filled one, so the set filled cannot change any station.

    obs/pred: station -> hourly series on the SAME datum per station (MLLW here).
    Returns (levels, source): levels[station] filled where possible; source[station]
    = "obs", or the donor id whose residual filled the hour, or "" if still missing.
    """
    resid = {s: (obs[s] - pred[s]).reindex(index) for s in obs if s in pred}
    levels, source = {}, {}
    for st in FORCING if stations is None else stations:
        o = obs[st].reindex(index)
        src = pd.Series("", index=index, dtype=object)
        src[o.notna()] = "obs"
        out = o.copy()
        p = pred[st].reindex(index)
        for d in DONORS[st]:
            need = out.isna() & p.notna() & resid[d].notna()
            out[need] = p[need] + resid[d][need]
            src[need] = d
        levels[st], source[st] = out, src
    return pd.DataFrame(levels), pd.DataFrame(source)


def fill_virtual(pred: dict[str, pd.Series], levels: pd.DataFrame,
                 index: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:  # fmt: skip
    """Every VIRTUAL_DONOR station on ``index``: its predicted tide + the donor's non-tidal
    residual (``levels`` = fill_gaps output, so a filled donor hour counts). Same datum
    convention as fill_gaps (each station's own MLLW). source = "virtual:<donor>" or ""."""
    out, source = {}, {}
    for st, d in VIRTUAL_DONOR.items():
        v = pred[st].reindex(index) + (levels[d] - pred[d].reindex(index))
        out[st] = v
        source[st] = pd.Series("", index=index, dtype=object).mask(v.notna(), f"virtual:{d}")
    return pd.DataFrame(out), pd.DataFrame(source)


def match_highs(obs: pd.Series, model: pd.Series, window: str = "3h", distance: int = 80) -> pd.DataFrame:
    """Every high tide of ``obs`` (find_peaks, peaks at least ``distance`` samples apart: ~8 h
    at 6 min) with the max of ``model`` within +-``window``: time, obs_m, model_m, diff_m
    (model - obs). Highs with no model value near them are dropped."""
    from scipy.signal import find_peaks

    obs = obs.dropna()
    rows = []
    for p in find_peaks(obs.values, distance=distance)[0]:
        t = obs.index[p]
        mw = model[t - pd.Timedelta(window) : t + pd.Timedelta(window)]
        if len(mw):
            rows.append({"time": t, "obs_m": float(obs.iloc[p]), "model_m": float(mw.max())})
    d = pd.DataFrame(rows, columns=["time", "obs_m", "model_m"])
    d["diff_m"] = d.model_m - d.obs_m
    return d


FT = 0.3048


def usgs_event_series(event: str, site: str, param: str = "72279") -> pd.Series | None:
    """A gauge series fetched for ``event`` (data/gauges/usgs_events/<event>/<site>_<param>.csv),
    feet -> m, UTC without tz; None if missing or nearly empty."""
    from agri_sfincs import config

    p = config.GAUGE_DIR / "usgs_events" / event / f"{site}_{param}.csv"
    if not p.exists():
        return None
    o = pd.read_csv(p)
    o = pd.Series(o["value"].values * FT, index=pd.to_datetime(o["time"], utc=True, format="mixed").dt.tz_convert(None))
    return o.dropna() if o.notna().sum() > 100 else None


def covered(o: pd.Series, t: pd.Timestamp, half: str, step: str = "6min", share: float = 0.9) -> bool:
    """At least ``share`` of the ``step`` samples present within +-``half`` of ``t``."""
    w = pd.Timedelta(half)
    return o[t - w : t + w].size >= share * (2 * w / pd.Timedelta(step) + 1)


def match_extremes(obs: pd.Series, model: pd.Series, lows: bool = False) -> pd.DataFrame:
    """``match_highs`` on the highs, or on the lows (model's lowest level near each observed
    low; diff still model - obs), keeping only those where ``obs`` is complete within +-1 h:
    gauges often go out at a storm peak, and a gap's edge is not a high."""
    d = match_highs(-obs, -model) if lows else match_highs(obs, model)
    if lows:
        d[["obs_m", "model_m", "diff_m"]] *= -1
    return d[[covered(obs, t, "1h") for t in d.time]] if len(d) else d


def his_series(run) -> dict[str, pd.Series]:
    """A run's observation points, {name: water level series}."""
    import xarray as xr

    with xr.open_dataset(run / "sfincs_his.nc") as h:
        names = [s.strip() for s in h["station_name"].values.astype(str)]
        return {n: h["point_zs"].isel(stations=i).to_series() for i, n in enumerate(names)}


OFF_CHANNEL_M = -0.3  # cell bed above this: the point is not in a channel cell
CHANNEL_SNAP_M = 60.0  # a gauge off the channel is read from a channel cell this close to its centreline point


def channel_series(run, x: float, y: float, side: str = "nj") -> pd.Series | None:
    """Hourly map zs at the channel cell under a gauge that the his point misses: the gauge
    projected onto the nearest tidal centreline (riverbed_centrelines<side>_v2.gpkg), then the
    deepest cell within CHANNEL_SNAP_M of that point. On a 25 m grid the gauge's own
    coordinates can fall on a bank cell (Hancocks Bridge, 2026-10-24); the nearest deep cell
    can be an isolated pocket, so the centreline is the anchor. None if no channel cell.
    (Moved from scripts/check_creek_tides.py, 2026-10-27.)"""
    import geopandas as gpd
    import numpy as np
    import shapely
    import xarray as xr

    from agri_sfincs import config, domain

    cl = gpd.read_file(config.ELEV_DIR / f"riverbed_centrelines{domain.side(side).files}_v2.gpkg")
    cl = cl[cl.kind == "tidal"]
    pt = shapely.Point(x, y)
    line = cl.geometry.iloc[int(np.argmin(cl.distance(pt).values))]
    p = line.interpolate(line.project(pt))
    with xr.open_dataset(run / "sfincs_map.nc") as mp:
        if "mesh2d_face_x" in mp:  # quadtree output
            cx, cy, zb, dim = mp["mesh2d_face_x"].values, mp["mesh2d_face_y"].values, mp["zb"].values, "nmesh2d_face"
            zs = mp["zs"]
        else:  # uniform grid output: flatten (n, m)
            cx, cy, zb = mp["x"].values.ravel(), mp["y"].values.ravel(), mp["zb"].values.ravel()
            zs, dim = mp["zs"].stack(c=("n", "m")), "c"
        near = np.nonzero((np.hypot(cx - p.x, cy - p.y) < CHANNEL_SNAP_M) & (zb < OFF_CHANNEL_M))[0]
        if not len(near):
            return None
        return zs.isel({dim: int(near[np.argmin(zb[near])])}).to_series()


def gauge_series(run, name: str, side: str = "nj") -> tuple[pd.Series, str]:
    """(water level, source) at observation point ``name``: the his series, or, where the
    point's cell bed is above OFF_CHANNEL_M, ``channel_series`` (hourly, so a peak between
    map outputs is read low)."""
    import xarray as xr

    with xr.open_dataset(run / "sfincs_his.nc") as h:
        names = [s.strip() for s in h["station_name"].values.astype(str)]
        i = names.index(name)
        zb, x, y = float(h["point_zb"][i]), float(h["station_x"][i]), float(h["station_y"][i])
        zs = h["point_zs"].isel(stations=i).to_series()
    if zb > OFF_CHANNEL_M:
        c = channel_series(run, x, y, side)
        if c is not None:
            return c, "map (channel cell, hourly)"
    return zs, "his"
