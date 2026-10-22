"""Do the spring storm-tide runs get the water level right inside the creeks? The §33 gauge
check (scripts/validate_sandy.py) for the 7 spring storms of the storm panel (FINDINGS §37).

Gauges: the interior USGS tidal gauges with a record in the storm window, Maurice River at
Bivalve (01412150), Cohansey River at Greenwich (01413038) and Alloway Creek at Hancocks
Bridge (01483050). Ship John Shoal (NOAA 8537121) is the boundary forcing, shown for scale.
Every observed high (6 min, ft -> m NAVD88) is paired with the model's highest level within
+-3 h (agri_sfincs.waterlevel.match_highs), for the tide-only run and the run with rain; lows
the same way (model's lowest level). A high or low counts only where the record is >= 90%
complete within +-1 h of it: the gauges often go out at the storm peak, and find_peaks would
otherwise score the edge of a gap. Scored: all highs of the window, its 5 highest, all lows,
and the storm high: the model's highest level within 1 day of the Ship John peak against the
observed maximum within +-3 h of it, only where the record is >= 90% complete within +-2 h
(else "gauge out").

Observations: data/gauges/usgs_events/<storm>/ (fetch_usgs_event.py --event <storm>).
Writes reports/storm_gauges.md and reports/figs/storm_gauges.png; with ``--model`` other than
runs.MODEL, storm_gauges_<model>.md and figs/storm_gauges_<model>.png.
Usage:  python scripts/validate_storm_gauges.py [--model v1_100m]
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

from agri_sfincs import config, domain, runs, waterlevel  # noqa: E402
from agri_sfincs.events import EVENTS  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

STORMS = ["storm2010mar", "storm2011apr", "storm2012jun", "storm2014apr", "storm2022apr", "storm2023jun", "storm2024spr"]
GAUGES = {"01412150": "Bivalve (Maurice)", "01413038": "Greenwich (Cohansey)", "01483050": "Hancocks Bridge (Alloway)"}
BLUE, ORANGE, INK, MUTED = "#2a78d6", "#eb6834", "#222222", "#6b6b6b"


def score(storm: str, sj: pd.Series, model: str) -> tuple[pd.DataFrame, dict]:
    ev = EVENTS[storm]
    peak_t = sj[ev.tstart : ev.tstop].idxmax()
    zs = {k: waterlevel.his_series(runs.run_dir(storm, "intact", 0, suffix=s, model=model))
          for k, s in (("tide", ""), ("rain", "_rain"))}  # fmt: skip
    rows, series = [], {}
    for site, name in GAUGES.items():
        o = waterlevel.usgs_event_series(storm, site)
        if o is None:
            continue
        series[name] = (o, zs["tide"][f"usgs_{site}"], zs["rain"][f"usgs_{site}"])
        r = {"storm": storm, "gauge": name}
        hi = waterlevel.match_extremes(o, zs["tide"][f"usgs_{site}"])
        r["n_highs"] = len(hi)
        r["bias_all_m"] = hi.diff_m.mean()
        r["rmse_all_m"] = float(np.sqrt((hi.diff_m**2).mean()))
        r["bias_top5_m"] = hi.nlargest(5, "obs_m").diff_m.mean()
        r["bias_lows_m"] = waterlevel.match_extremes(o, zs["tide"][f"usgs_{site}"], lows=True).diff_m.mean()
        m = zs["tide"][f"usgs_{site}"][peak_t - pd.Timedelta("1D") : peak_t + pd.Timedelta("1D")]
        tm = m.idxmax()
        r["storm_high_model_m"] = m.max()
        r["storm_high_rain_m"] = zs["rain"][f"usgs_{site}"][tm - pd.Timedelta("3h") : tm + pd.Timedelta("3h")].max()
        if waterlevel.covered(o, tm, "2h"):
            r["storm_high_obs_m"] = o[tm - pd.Timedelta("3h") : tm + pd.Timedelta("3h")].max()
        rows.append(r)
    return pd.DataFrame(rows), {"peak": peak_t, "sj": sj, "series": series}


def figure(panels: dict, tag: str) -> None:
    gauges = list(GAUGES.values())
    fig, axes = plt.subplots(len(STORMS), len(gauges), figsize=(11, 2.0 * len(STORMS)), sharey=True)
    for i, storm in enumerate(STORMS):
        p = panels[storm]
        t0, t1 = p["peak"] - pd.Timedelta("2D"), p["peak"] + pd.Timedelta("2D")
        for j, g in enumerate(gauges):
            ax = axes[i, j]
            if g in p["series"]:
                o, mt, mr = p["series"][g]
                ow = o[t0:t1]
                ow = ow.reindex(ow.index.union(ow.index[:-1][np.diff(ow.index) > pd.Timedelta("30min")] + pd.Timedelta("6min")))
                ax.plot(ow.index, ow.values, color=INK, lw=1.2, label="observed (gaps left blank)")
                ax.plot(mt[t0:t1].index, mt[t0:t1].values, color=BLUE, lw=1.4, label="model, tide only")
                ax.plot(mr[t0:t1].index, mr[t0:t1].values, color=ORANGE, lw=1.0, ls="--", label="model, tide + rain")
            else:
                ax.text(0.5, 0.5, "no record", transform=ax.transAxes, ha="center", va="center", color=MUTED, fontsize=8)
            ax.set_xlim(t0, t1)
            ax.set_xticks([p["peak"].normalize() + pd.Timedelta(f"{d}D") for d in (-1, 0, 1, 2)])
            ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
            ax.tick_params(colors=MUTED, labelsize=7)
            ax.grid(color="#eeeeee", lw=0.6)
            for sp_ in ("top", "right"):
                ax.spines[sp_].set_visible(False)
            if i == 0:
                ax.set_title(g, fontsize=9, color=INK)
            if j == 0:
                ax.set_ylabel(f"{storm[5:]}\nm NAVD88", fontsize=8, color=MUTED)
    axes[0, 0].legend(fontsize=7, frameon=False, loc="lower left")
    fig.suptitle("Interior tide gauges vs the model, 2 days either side of each spring storm's peak", fontsize=10, color=INK)
    fig.tight_layout()
    out = config.REPORTS / "figs" / f"storm_gauges{tag}.png"
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=runs.MODEL)
    a = ap.parse_args()
    tag = "" if a.model == runs.MODEL else f"_{a.model}"
    with xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc") as ds:
        sj = ds["waterlevel"].sel(stations=domain.SHIP_JOHN).to_series()
    tabs, panels = [], {}
    for storm in STORMS:
        t, panels[storm] = score(storm, sj, a.model)
        tabs.append(t)
    d = pd.concat(tabs, ignore_index=True)
    d["storm_high_diff_m"] = d.storm_high_model_m - d.storm_high_obs_m
    d["rain_adds_m"] = d.storm_high_rain_m - d.storm_high_model_m
    figure(panels, tag)
    by_gauge = d.groupby("gauge")[["bias_all_m", "rmse_all_m", "bias_top5_m", "bias_lows_m", "storm_high_diff_m"]].mean()
    by_gauge["storms_with_peak_observed"] = d.groupby("gauge").storm_high_obs_m.count()
    cols = ["storm", "gauge", "n_highs", "bias_all_m", "rmse_all_m", "bias_top5_m", "bias_lows_m", "storm_high_obs_m",
            "storm_high_model_m", "storm_high_diff_m", "rain_adds_m"]  # fmt: skip
    md = f"""# Spring storm tides at the interior gauges ({a.model})

Generated by `scripts/validate_storm_gauges.py --model {a.model}`. The §33 Sandy check repeated for the 7 spring
storms of the storm panel (FINDINGS §37): every observed high tide in each run window against
the model's highest level within ±3 h, runs `<storm>_intact_slr000` (tide only) and `_rain`.
Metres NAVD88; diff and bias = model − observed. Highs and lows count only where the record is
complete around them. "storm high" = the model's highest level within a day of the Ship John
peak vs the observed maximum within ±3 h; blank where the gauge was out at that time (it often
is). The gauges sit in the creek mouths: they test the water the creeks deliver to the banks,
not flooding on the fields.

## Per storm and gauge

{md_table(d[cols], floatfmt="{:+.2f}")}

## Mean over the storms

{md_table(by_gauge, floatfmt="{:+.2f}")}

![](figs/storm_gauges{tag}.png)
"""
    out = config.REPORTS / f"storm_gauges{tag}.md"
    out.write_text(md)
    print(md_table(d[cols], floatfmt="{:+.2f}"))
    print(md_table(by_gauge, floatfmt="{:+.2f}"))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
