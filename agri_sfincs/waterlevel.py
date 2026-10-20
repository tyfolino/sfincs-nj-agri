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

``match_highs`` pairs every observed high tide at a gauge with the model's highest level
near it (scripts/validate_sandy.py, scripts/validate_storm_gauges.py); ``match_extremes``
does highs or lows where the 6-min record is complete around them; ``usgs_event_series``
reads a fetched gauge series (scripts/fetch_usgs_event.py) in m; ``his_series`` a run's
observation points.
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
}


def datums(station: str) -> dict[str, float]:
    """CO-OPS tidal datums for a station, metres on station datum."""
    j = get(f"{MDAPI}/{station}/datums.json", {"units": "metric"}).json()
    return {d["name"]: float(d["value"]) for d in j.get("datums") or []}


def navd_minus_mllw(station: str, navd_from: list[str] | None = None) -> tuple[float, str]:
    """(NAVD88 - MLLW in m, how it was obtained) — see the module docstring."""
    own = datums(station)
    if "NAVD88" in own:
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
    obs: dict[str, pd.Series], pred: dict[str, pd.Series], index: pd.DatetimeIndex
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gap-fill every FORCING station on ``index``.

    obs/pred: station -> hourly series on the SAME datum per station (MLLW here).
    Returns (levels, source): levels[station] filled where possible; source[station]
    = "obs", or the donor id whose residual filled the hour, or "" if still missing.
    """
    resid = {s: (obs[s] - pred[s]).reindex(index) for s in obs if s in pred}
    levels, source = {}, {}
    for st in FORCING:
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
