"""Side-by-side comparison of event runs of the same event (e.g. v0 vs v1 arms).

Reads, per run, what validate_event.py and event_summary.py wrote in <run>/summary/
(gauges.csv, daily_county_crop.csv, monthly_county.csv, focus_wet_days.tif) and the run's
sfincs_his.nc (drainage-structure discharge, when the run has any). Run those two scripts
first; the gauge tables are left out for runs without gauges.csv.

Tables:
  tidal gauges   RMSE / bias / r of hourly levels
  stream gauges  r of de-meaned stage, modelled vs observed rise, peak lag
  cropland       per county, focus period: peak area > 5 cm, area-days > 5 cm, and the
                 PERSISTENT area (wet > 5 cm on every focus day: the FINDINGS §10 artifact)
  by month       (focus periods longer than a month, e.g. the y<YYYY> runs) per county x
                 month: area-days and persistent area, from summary/monthly_county.csv
  gates          volume each run's check valves drained over the whole window

Writes reports/compare_<event>.md (or --out) and prints it.

Usage:  python scripts/compare_runs.py --event sep2023 \
            --runs v0_100m/sep2023 v1dikes_100m/sep2023 v1_100m/sep2023 v1_100m/sep2023_gatehi
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.features import rasterize

from agri_sfincs import config, domain, region
from agri_sfincs.events import EVENTS
from agri_sfincs.report import md_table


def persistent_km2(run, ndays: int) -> pd.Series:
    with rasterio.open(run / "summary" / "focus_wet_days.tif") as s:
        wd, tr, crs, shape = s.read(1), s.transform, s.crs, s.shape
    cty = region.load_counties().to_crs(crs)
    cty = cty[cty.fips.isin(domain.COUNTIES)]
    out = {}
    for _, c in cty.iterrows():
        m = rasterize([(c.geometry, 1)], out_shape=shape, transform=tr, fill=0, dtype="uint8")
        out[c["name"]] = float(((m == 1) & (wd >= ndays)).sum() * abs(tr.a * tr.e) / 1e6)
    return pd.Series(out)


def gate_volumes(run) -> pd.Series | None:
    his = run / "sfincs_his.nc"
    with xr.open_dataset(his) as h:
        if "drainage_discharge" not in h:
            return None
        q = h["drainage_discharge"].fillna(0.0)
        dt = np.diff(h["time"].values).astype("timedelta64[s]").astype(float)
        # his stores the INTAKE's source term (qtsrc(jin) = -q, sfincs_discharges.f90),
        # so a draining valve reads negative: flip it to volume drained.
        vol = -(q.values[1:] * dt[:, None]).sum(axis=0)  # m3 per structure
    return pd.Series(vol)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--event", required=True, choices=sorted(EVENTS))
    ap.add_argument("--runs", nargs="+", required=True, help="<model>/<run> under MODELS")
    ap.add_argument("--out", default=None, help="report path (default reports/compare_<event>.md)")
    a = ap.parse_args()
    ev = EVENTS[a.event]
    runs = {r: config.MODELS / r.split("/")[0] / "runs" / r.split("/")[1] for r in a.runs}
    ndays = (ev.focus_stop - ev.focus_start).days

    gf = {k: p / "summary" / "gauges.csv" for k, p in runs.items()}
    gf = {k: f for k, f in gf.items() if f.is_file()}  # none for runs with no USGS window
    order = list(runs)

    def by_run(df, index, values):
        """rows = (index, metric), columns = run, in the order the runs were given."""
        long = df.melt(id_vars=[index, "run"], value_vars=values, var_name="metric")
        out = long.pivot_table(index=[index, "metric"], columns="run", values="value",
                               sort=False)  # fmt: skip
        return out[[r for r in order if r in out.columns]]

    gauge_lines = []
    if gf:
        g = pd.concat({k: pd.read_csv(f, dtype={"site": str, "param": str}) for k, f in gf.items()},
                      names=["run"]).reset_index(level=0)  # fmt: skip
        tid = by_run(g[g.param == "72279"], "name", ["rmse_m", "bias_m", "r_demeaned"])
        st = g[g.param == "00065"].copy()
        st["rise_ratio"] = st.mod_rise_m / st.obs_rise_m
        stm = by_run(st, "name", ["r_demeaned", "rise_ratio", "peak_lag_h"])
        gauge_lines = ["## Tidal gauges (hourly water level, m)", "", md_table(tid.round(3)), "",
                       "## Stream gauges (stage; rise_ratio = modelled / observed rise)", "",
                       md_table(stm.round(2)), ""]  # fmt: skip

    rows = []
    for k, p in runs.items():
        d = pd.read_csv(p / "summary" / "daily_county_crop.csv")
        d = d[ev.in_focus(d.date)]
        ndays = min(ndays, d.date.nunique())  # a run may stop before the focus does (y2025)
        day = d.groupby(["county", "date"]).area_gt_5cm_km2.sum()
        per = persistent_km2(p, ndays)
        for c in day.index.get_level_values(0).unique():
            rows.append({"county": c, "run": k, "peak_km2": day[c].max(),
                         "area_days": day[c].sum(), "persistent_km2": per.get(c, np.nan)})  # fmt: skip
    crop = by_run(pd.DataFrame(rows), "county", ["peak_km2", "area_days", "persistent_km2"])

    lines = [f"# Run comparison: {a.event} (focus {ev.focus})", "",
             "Runs: " + ", ".join(f"`{r}`" for r in runs), "", *gauge_lines,
             "## Cropland wet > 5 cm in the focus period (km², km²·days)", "",
             md_table(crop.round(2), floatfmt="{:.2f}"), ""]  # fmt: skip
    if len(ev.focus_months()) > 1:
        m = pd.concat({k: pd.read_csv(p / "summary" / "monthly_county.csv")
                       for k, p in runs.items()}, names=["run"]).reset_index(level=0)  # fmt: skip
        m["key"] = m.county + " " + m.month
        bym = by_run(m, "key", ["area_days_gt_5cm", "persistent_gt_5cm_km2"])
        lines += ["## Cropland wet > 5 cm by month (km²·days; km² wet every day of the month)",
                  "", md_table(bym.round(2), floatfmt="{:.2f}"), ""]  # fmt: skip
    vols = {k: gate_volumes(p) for k, p in runs.items()}
    vols = {k: v for k, v in vols.items() if v is not None and len(v)}
    if vols:
        gv = pd.DataFrame({k: [v.sum() / 1e6, (v > 1e3).sum(), len(v)] for k, v in vols.items()},
                          index=["drained (hm³ = 10⁶ m³)", "valves passing > 1000 m³",
                                 "valves"])  # fmt: skip
        lines += ["## Check valves", "", md_table(gv, floatfmt="{:.3f}"), ""]
    text = "\n".join(lines)
    out = Path(a.out) if a.out else config.REPORTS / f"compare_{a.event}.md"
    out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
