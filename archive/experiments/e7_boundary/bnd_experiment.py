"""Bay-boundary experiment (scratch): stage tidecal2023may runs with a rebuilt water-level boundary.

E7a: the 5 forcing gauges + 2 virtual NJ-shore gauges (Fortescue 8536931, Bidwell Creek
     entrance 8536581) = own harmonic prediction + donor non-tidal residual. Hourly, and SFINCS
     blends neighbouring points itself (as v1).
E7b: E7a's 7-gauge chain, but one boundary point per ~1 km of boundary, each a LAG-AWARE blend
     of its two chain neighbours (both shifted to the point's phase before weighting), 6-min.
Base run: v1_100m/runs/tidecal2023may_e1open (opened Alloway weirs).
Usage: python bnd_experiment.py {e7a|e7b}
"""
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

SP = Path(__file__).parent
REPO = Path("/cache/home/tpj8/sfincs-nj-agri")
RUNS = Path("/scratch/tpj8/sfincs-nj-agri/models/v1_100m/runs")
BASE = RUNS / "tidecal2023may_e1open"
NOAA = REPO / "data/gauges/noaa"
T0, T1 = pd.Timestamp("2023-05-21"), pd.Timestamp("2023-06-01")

# chain along the estuary axis; NAVD88 - MLLW (m)
CHAIN = ["8545240", "8540433", "8551910", "8537121", "8536931", "8536581", "8536110"]
LONLAT = {"8545240": (-75.1420, 39.9331), "8540433": (-75.4095, 39.8118), "8551910": (-75.5719, 39.5583),
          "8537121": (-75.3767, 39.3054), "8536931": (-75.175, 39.2383), "8536581": (-74.892, 39.128),
          "8536110": (-74.9600, 38.9683)}
# Fortescue: CO-OPS tie; Bidwell: MSL-MLLW + mean NAVD88-MSL of Cape May and Fortescue
NAVD_MLLW_VIRT = {"8536931": 0.982, "8536581": (1.910 - 0.948) + np.mean([1.657 - 1.521, 2.157 - 2.149])}  # 1.034
DONOR = {"8536931": "8537121", "8536581": "8536110"}


def hourly(fn, col):
    return pd.read_csv(fn, index_col=0, parse_dates=True)[col]


def series() -> pd.DataFrame:
    """Hourly NAVD88 levels at the 7 chain points over the window (+-1 day)."""
    win = slice(T0 - pd.Timedelta("1D"), T1 + pd.Timedelta("1D"))
    with xr.open_dataset(REPO / "data/gauges/waterlevel_forcing_navd88.nc") as ds:
        f = ds.waterlevel.sel(time=win).to_pandas()
    out = {s: f[s] for s in f.columns}
    for v, d in DONOR.items():
        pred = pd.read_csv(SP / f"{v}_pred2023.csv", index_col=0, parse_dates=True).iloc[:, 0][win]
        res = (hourly(NOAA / f"{d}_hourly_mllw.csv.gz", "wl_m_mllw") - hourly(NOAA / f"{d}_pred_mllw.csv.gz", "pred_m_mllw"))[win]
        out[v] = pred - NAVD_MLLW_VIRT[v] + res.reindex(pred.index)
    return pd.DataFrame(out)[CHAIN].interpolate(limit=3)


def utm(lon, lat):
    from pyproj import Transformer
    return Transformer.from_crs(4326, 32618, always_xy=True).transform(lon, lat)


def lags(s6: pd.DataFrame) -> dict:
    """Lag (h) of chain[i+1] behind chain[i], from 6-min series."""
    out = {}
    for a, b in zip(CHAIN[:-1], CHAIN[1:]):
        x, y = s6[a] - s6[a].mean(), s6[b] - s6[b].mean()
        k = max(range(-40, 41), key=lambda k: x.corr(y.shift(-k)))
        out[(a, b)] = k * 0.1
    return out


def at(s: pd.Series, t: pd.DatetimeIndex) -> np.ndarray:
    ns = lambda i: i.as_unit("ns").asi8
    return np.interp(ns(t), ns(s.index), s.values, left=np.nan, right=np.nan)


def write_bnd(run: Path, df: pd.DataFrame, xs, ys, names):
    t = df.index
    ds = xr.Dataset(
        {"zs": (("time", "stations"), df.values.astype("float32"))},
        coords={"time": t, "stations": np.arange(len(xs)), "x": ("stations", np.asarray(xs, float)),
                "y": ("stations", np.asarray(ys, float)), "name": ("stations", np.asarray(names, str))},
    )
    enc = {"time": {"units": f"minutes since {T0:%Y-%m-%d}", "dtype": "float64"}}
    ds.to_netcdf(run / "sfincs_netbndbzsbzifile.nc", encoding=enc)


def stage(name: str) -> Path:
    run = RUNS / f"tidecal2023may_{name}"
    if run.exists():
        raise FileExistsError(run)
    keep = lambda d, fs: [f for f in fs if f.endswith(".rst") or f in ("sfincs_map.nc", "sfincs_his.nc", "sfincs_log.txt", "sfincs.log")]
    shutil.copytree(BASE, run, ignore=keep)
    return run


def main(which):
    s = series()
    xy = {k: utm(*LONLAT[k]) for k in CHAIN}
    if which == "e7a":
        s = s[T0:T1]
        run = stage("e7a")
        write_bnd(run, s, [xy[k][0] for k in CHAIN], [xy[k][1] for k in CHAIN], CHAIN)
        print(run)
        return
    s6 = s.resample("6min").interpolate("cubic")
    lg = lags(s6)
    print({f"{a}->{b}": v for (a, b), v in lg.items()})
    with xr.open_dataset(BASE / "sfincs_map.nc") as m:
        msk, X, Y = m.msk.values, m.x.values, m.y.values
    iy, ix = np.where(msk == 2)
    bx, by = X[iy, ix], Y[iy, ix]
    # ~1 km thinning
    key = pd.Series(list(zip((bx // 1000).astype(int), (by // 1000).astype(int))))
    first = ~key.duplicated()
    px, py = bx[first.values], by[first.values]
    gx = np.array([xy[k][0] for k in CHAIN]); gy = np.array([xy[k][1] for k in CHAIN])
    idx = pd.date_range(T0, T1, freq="6min")
    cols, names = [], []
    for x, y in zip(px, py):
        d = np.hypot(gx - x, gy - y)
        n = int(np.argmin(d))
        nb = [i for i in (n - 1, n + 1) if 0 <= i < len(CHAIN)]
        m_ = min(nb, key=lambda i: d[i])
        a, b = sorted((n, m_))
        w = d[a] / (d[a] + d[b])  # 0 at a, 1 at b
        tau = pd.Timedelta(hours=lg[(CHAIN[a], CHAIN[b])])
        A = at(s6[CHAIN[a]], idx - w * tau)  # A at the point's phase (later by w*tau)
        B = at(s6[CHAIN[b]], idx + (1 - w) * tau)  # B earlier by (1-w)*tau
        cols.append((1 - w) * A + w * B)
        names.append(f"{CHAIN[a][-4:]}-{CHAIN[b][-4:]}:{w:.2f}")
    df = pd.DataFrame(np.array(cols).T, index=idx)
    if df.isna().any().any():
        raise ValueError("NaN in boundary series (shift off the 6-min lattice?)")
    run = stage("e7b")
    write_bnd(run, df, px, py, names)
    print(run, len(px), "points")


if __name__ == "__main__":
    main(sys.argv[1])
