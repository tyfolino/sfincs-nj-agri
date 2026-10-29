"""How low does gridded wind read over the bay? ERA5 or HRRR 10 m wind against the CO-OPS lights.

nj_bight_sfincs found ERA5 0.6-0.8x the over-water lights in the NJ bays; this measures a
source (``--source era5|hrrr``) here, to set ``setup_scenarios.py --wind SCALE``
(agri_sfincs.wind).

Stations (CO-OPS ``wind`` product, hourly; positions and anemometer heights from the
metadata API): Ship John Shoal 8537121 and Brandywine Shoal 8555889, lights in open water,
set the scale; Lewes 8557380 and Cape May 8536110 sit on the shore and are shown beside
them. Each observed speed is brought to 10 m with a neutral log profile over water
(z0 = 0.2 mm; the heights are read as feet above the water, so the correction is a few %).
The source is bilinear at the station. Only storm-wind hours (the hours that build setup)
count: scale = sum(observed) / sum(model) over the hours with OBSERVED 10 m speed >=
MIN_SPEED, and again over the hours with MODEL speed >= MIN_SPEED. Picking hours on one
side's speed biases the ratio toward that side, so the two bracket it. Per station and
pooled over the two lights; also the median direction difference.

Windows: every storm event (agri_sfincs.events, storm* and sandy2012) the source has wind
for. Observations are cached in data/gauges/noaa/<id>_wind_<event>.csv.
Writes reports/<source>_wind.md.

Usage:  python scripts/check_wind.py [--source era5|hrrr]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from agri_sfincs import config, wind
from agri_sfincs.events import EVENTS
from agri_sfincs.net import get
from agri_sfincs.report import md_table

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
MDAPI = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations"
LIGHTS = {"8537121": "Ship John Shoal", "8555889": "Brandywine Shoal"}
SHORE = {"8557380": "Lewes", "8536110": "Cape May"}
MIN_SPEED = 8.0  # m/s at 10 m
Z0_M = 0.0002


def meta(st: str) -> tuple[float, float, float]:
    """(lon, lat, anemometer height m) from the CO-OPS metadata API."""
    s = get(f"{MDAPI}/{st}.json", {}, timeout=60).json()["stations"][0]
    sens = get(f"{MDAPI}/{st}/sensors.json", {}, timeout=60).json()["sensors"]
    h_ft = next(x["elevation"] for x in sens if x["name"] == "Wind")
    return float(s["lng"]), float(s["lat"]), float(h_ft) * 0.3048


def observed(st: str, event: str, t0, t1) -> pd.DataFrame:
    """Hourly observed wind (speed m/s, direction FROM deg), cached per event."""
    f = config.GAUGE_DIR / "noaa" / f"{st}_wind_{event}.csv"
    if f.exists():
        return pd.read_csv(f, index_col=0, parse_dates=True)
    rows = []
    for a in pd.date_range(t0, t1, freq="30D"):
        b = min(a + pd.Timedelta("30D") - pd.Timedelta("1h"), pd.Timestamp(t1))
        j = get(API, {"product": "wind", "application": "sfincs-nj-agri", "station": st,
                      "begin_date": f"{a:%Y%m%d %H:%M}", "end_date": f"{b:%Y%m%d %H:%M}",
                      "time_zone": "gmt", "units": "metric", "interval": "h", "format": "json"},
                timeout=120).json()  # fmt: skip
        rows += j.get("data", [])
    d = pd.DataFrame(rows)
    if d.empty:
        out = pd.DataFrame(columns=["speed", "dir"], index=pd.DatetimeIndex([], name="time"))
    else:
        out = pd.DataFrame({"speed": pd.to_numeric(d.s, errors="coerce").values,
                            "dir": pd.to_numeric(d.d, errors="coerce").values},
                           index=pd.DatetimeIndex(pd.to_datetime(d.t), name="time"))  # fmt: skip
    out.to_csv(f)
    return out


def scales(g: pd.DataFrame) -> pd.Series:
    """Hours and observed / model ratios on the two selections (see module doc)."""
    o, m = g[g.obs >= MIN_SPEED], g[g.model >= MIN_SPEED]
    return pd.Series({"hours_obs_sel": len(o), "scale_obs_sel": o.obs.sum() / o.model.sum(),
                      "hours_model_sel": len(m), "scale_model_sel": m.obs.sum() / m.model.sum(),
                      "ddir_median": o.ddir.median()})  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=wind.SOURCES, default="era5")
    a = ap.parse_args()
    stations = {**LIGHTS, **SHORE}
    where = {st: meta(st) for st in stations}
    rows, evs = [], []
    for ev in [e for n, e in EVENTS.items() if n.startswith("storm") or n == "sandy2012"]:
        try:
            ds = wind.load(a.source, ev.tstart, ev.tstop)
        except FileNotFoundError:
            continue
        evs.append(ev.name)
        idx = pd.DatetimeIndex(ds.time.values)
        for st, name in stations.items():
            lon, lat, h = where[st]
            u, v = wind.at_point(ds, lon, lat)
            o = observed(st, ev.name, ev.tstart, ev.tstop)
            o10 = o.speed * np.log(10.0 / Z0_M) / np.log(max(h, 2.0) / Z0_M)
            d = pd.DataFrame({"obs": o10, "dir_obs": o["dir"],
                              "model": pd.Series(np.hypot(u, v), index=idx),
                              "dir_model": pd.Series(np.degrees(np.arctan2(-u, -v)) % 360, index=idx)}).dropna()  # fmt: skip
            d = d[(d.obs >= MIN_SPEED) | (d.model >= MIN_SPEED)]
            rows += [{"storm": ev.name, "station": name, "time": t, **r.to_dict()} for t, r in d.iterrows()]
    d = pd.DataFrame(rows)
    d["ddir"] = (d.dir_model - d.dir_obs + 180) % 360 - 180
    agg = d.groupby("station").apply(scales, include_groups=False)
    lights = d[d.station.isin(LIGHTS.values())]
    pooled = scales(lights)
    per_storm = lights.groupby("storm").apply(scales, include_groups=False)
    src = a.source.upper()
    md = f"""# {src} 10 m wind against the bay lights (storm windows)

Generated by `scripts/check_wind.py --source {a.source}`. {len(evs)} storm windows: {", ".join(evs)}.
scale = observed / {src} speed summed over storm-wind hours (>= {MIN_SPEED:.0f} m/s at 10 m), with
the hours picked on the OBSERVED speed (`obs_sel`) and on {src}'s (`model_sel`): each pick
favours its own side, so the two bracket the scale. ddir = {src} − observed direction, degrees
(observed-picked hours).

{md_table(agg.reset_index(), floatfmt="{:.2f}")}

**Pooled over the two lights (Ship John Shoal, Brandywine Shoal): scale {pooled.scale_obs_sel:.2f}
(observed-picked, {pooled.hours_obs_sel:.0f} h) .. {pooled.scale_model_sel:.2f} ({src}-picked,
{pooled.hours_model_sel:.0f} h); direction {pooled.ddir_median:+.0f} deg.** Per storm, both lights:

{md_table(per_storm.reset_index(), floatfmt="{:.2f}")}
"""
    out = config.REPORTS / f"{a.source}_wind.md"
    out.write_text(md)
    print(md)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
