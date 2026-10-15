"""Hourly NAVD88 water levels at the five forcing gauges, 2002-2025, gaps filled.

Inputs: the observed hourly MLLW files from scripts/gauge_inventory.py
(data/gauges/noaa/<id>_hourly_mllw.csv.gz). Downloads and caches NOAA hourly tide
predictions per station-year (data/gauges/noaa/<id>_pred_mllw.csv.gz).

Writes data/gauges/waterlevel_forcing_navd88.nc:
  waterlevel(time, stations)  m NAVD88, UTC hourly
  source(time, stations)      "obs" | donor id (residual-filled) | "" (missing)
  lon, lat, name(stations); attrs carry each station's NAVD88-MLLW and how it was got
and prints, per station and year, the % observed and % filled.

Usage:  python scripts/build_waterlevels.py [--years 2002-2025]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import xarray as xr

from agri_sfincs import config, domain, waterlevel
from agri_sfincs.cli import parse_years

NOAA_DIR = config.GAUGE_DIR / "noaa"
OUT = config.GAUGE_DIR / "waterlevel_forcing_navd88.nc"
STATIONS = {s["id"]: s for s in domain.NOAA_STATIONS}


def observed(st: str) -> pd.Series:
    f = NOAA_DIR / f"{st}_hourly_mllw.csv.gz"
    return pd.read_csv(f, index_col=0, parse_dates=True)["wl_m_mllw"]


def predicted(st: str, years: list[int]) -> pd.Series:
    f = NOAA_DIR / f"{st}_pred_mllw.csv.gz"
    have = (
        pd.read_csv(f, index_col=0, parse_dates=True)["pred_m_mllw"]
        if f.exists()
        else pd.Series(dtype="float64", index=pd.DatetimeIndex([]))
    )
    parts = [have]
    for y in years:
        if (have.index.year == y).any():
            continue
        parts.append(waterlevel.predictions_year(st, y))
        print(f"  predictions {st} {y}", flush=True)
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated()]
    s.rename("pred_m_mllw").rename_axis("time").to_csv(f)
    return s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", default="2002-2025")
    a = ap.parse_args()
    years = parse_years(a.years)
    index = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-31 23:00", freq="h")

    involved = sorted(set(waterlevel.FORCING) | {d for v in waterlevel.DONORS.values() for d in v})
    obs = {s: observed(s) for s in involved}
    pred = {s: predicted(s, years) for s in involved}
    levels, source = waterlevel.fill_gaps(obs, pred, index)

    offsets, hows = {}, {}
    for st in waterlevel.FORCING:
        off, how = waterlevel.navd_minus_mllw(st, STATIONS[st].get("navd_from"))
        offsets[st], hows[st] = off, how
        levels[st] = levels[st] - off
        print(f"  {st} {STATIONS[st]['name']}: NAVD88-MLLW {off:.3f} m ({how})")

    ids = waterlevel.FORCING
    ds = xr.Dataset(
        {
            "waterlevel": (("time", "stations"), levels[ids].to_numpy("float32")),
            "source": (("time", "stations"), source[ids].to_numpy().astype(str)),
        },
        coords={
            "time": index,
            "stations": ids,
            "lon": ("stations", [STATIONS[s]["lon"] for s in ids]),
            "lat": ("stations", [STATIONS[s]["lat"] for s in ids]),
            "name": ("stations", [STATIONS[s]["name"] for s in ids]),
        },
        attrs={
            "title": "Hourly water level at the Delaware forcing gauges, gap-filled",
            "units": "m NAVD88",
            "fill_method": "predicted tide + donor non-tidal residual "
            "(agri_sfincs.waterlevel.DONORS)",
            **{f"navd88_minus_mllw_{s}": offsets[s] for s in ids},
            **{f"navd88_method_{s}": hows[s] for s in ids},
        },
    )
    ds.waterlevel.attrs["units"] = "m"
    ds.to_netcdf(OUT)

    yr = source.index.year
    rows = []
    for st in ids:
        for y in years:
            s = source.loc[yr == y, st]
            rows.append({"station": f"{st} {STATIONS[st]['name']}", "year": y,
                         "obs%": round(100 * (s == "obs").mean(), 1),
                         "filled%": round(100 * ((s != "obs") & (s != "")).mean(), 1),
                         "missing%": round(100 * (s == "").mean(), 1)})  # fmt: skip
    t = pd.DataFrame(rows)
    bad = t[t["obs%"] < 100]
    print("\nstation-years not fully observed:\n" + bad.to_string(index=False))
    print(f"still missing anywhere: {int((source == '').to_numpy().sum())} station-hours")
    print(f"NAVD88 range per station (m): "
          f"{ {s: (round(float(np.nanmin(levels[s])), 2), round(float(np.nanmax(levels[s])), 2)) for s in ids} }")  # fmt: skip
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
