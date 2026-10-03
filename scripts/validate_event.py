"""Compare an event run's observation-point water levels with the USGS 15-min records.

v0 has no cross-sections, so DISCHARGE is not compared yet. What is:
  * tidal gauges (72279, ft -> m): RMSE / bias / correlation of hourly levels, and of
    the de-meaned series (the datum of 72279 is checked, not assumed: the means differ
    by any datum offset);
  * stream gauges (00065 gage height, local datum): correlation of de-meaned hourly
    stage, observed vs modelled RISE (max - median), and peak timing for the biggest
    event in the focus month.

Writes <run>/summary/gauges.csv and gauges.png and prints the table.

Usage:  python scripts/validate_event.py --run <run dir> --event sep2023
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

from agri_sfincs import config  # noqa: E402
from agri_sfincs.events import EVENTS  # noqa: E402

FT = 0.3048


def model_series(run: Path) -> pd.DataFrame:
    with xr.open_dataset(run / "sfincs_his.nc") as h:
        names = [s.strip() for s in h["station_name"].values.astype(str)]
        zs = h["point_zs"].values  # (time, stations)
        t = pd.to_datetime(h["time"].values)
    return pd.DataFrame(zs, index=t, columns=names)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--event", required=True, choices=sorted(EVENTS))
    a = ap.parse_args()
    ev = EVENTS[a.event]
    out = a.run / "summary"
    out.mkdir(exist_ok=True)
    mod = model_series(a.run).resample("h").mean()
    obs_dir = config.GAUGE_DIR / "usgs_events" / ev.name
    inv = pd.read_csv(config.GAUGE_DIR / "usgs_series.csv", dtype={"site": str})
    names = inv.drop_duplicates("site").set_index("site")["name"]

    rows, panels = [], []
    for f in sorted(obs_dir.glob("*.csv")):
        site, pc = f.stem.split("_")
        if pc not in ("72279", "00065") or f"usgs_{site}" not in mod:
            continue
        o = pd.read_csv(f, index_col=0, parse_dates=True)["value"] * FT
        o = o.resample("h").mean()
        m = mod[f"usgs_{site}"]
        j = pd.concat({"obs": o, "mod": m}, axis=1).dropna()
        j = j[j.index >= pd.Timestamp(ev.tstart) + pd.Timedelta(days=3)]  # skip spin-up
        if len(j) < 48:
            continue
        foc = j[j.index.strftime("%Y-%m") == ev.focus]
        rec = {"site": site, "name": names.get(site, "")[:34], "param": pc, "n_h": len(j),
               "r_demeaned": j.obs.corr(j["mod"]),
               "obs_mean_m": j.obs.mean(), "mod_mean_m": j["mod"].mean()}  # fmt: skip
        if pc == "72279":
            d = j["mod"] - j.obs
            rec |= {"rmse_m": float(np.sqrt((d**2).mean())), "bias_m": float(d.mean()),
                    "rmse_demeaned_m": float(np.sqrt(((d - d.mean()) ** 2).mean()))}  # fmt: skip
        else:
            rec |= {"obs_rise_m": foc.obs.max() - foc.obs.median(),
                    "mod_rise_m": foc["mod"].max() - foc["mod"].median(),
                    "obs_peak": foc.obs.idxmax(), "mod_peak": foc["mod"].idxmax(),
                    "peak_lag_h": (foc["mod"].idxmax() - foc.obs.idxmax()).total_seconds() / 3600}  # fmt: skip
        rows.append(rec)
        panels.append((site, pc, j))

    t = pd.DataFrame(rows)
    t.to_csv(out / "gauges.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(t.round(3).to_string(index=False))

    n = len(panels)
    fig, axs = plt.subplots(n, 1, figsize=(11, 2.0 * n), sharex=True, squeeze=False)
    for ax, (site, pc, j) in zip(axs[:, 0], panels):
        ax.plot(j.index, j.obs - j.obs.mean(), lw=0.8, label="observed (de-meaned)")
        ax.plot(j.index, j["mod"] - j["mod"].mean(), lw=0.8, label="SFINCS (de-meaned)")
        ax.set_title(f"{site} {names.get(site, '')[:40]} [{pc}]", fontsize=8, loc="left")
        ax.tick_params(labelsize=7)
    axs[0, 0].legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(out / "gauges.png", dpi=110)
    print(f"wrote {out / 'gauges.csv'} and gauges.png")


if __name__ == "__main__":
    main()
