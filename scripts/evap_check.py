"""Checks for the open-water evaporation forcing (agri_sfincs/evap.py): a base run vs the
same run with P - E. Run validate_event.py and event_summary.py on both first.

1. Partial wetness: SFINCS removes negative net rain over the WHOLE cell area once a
   subgrid cell holds any water (sfincs_continuity.f90:469-495; the clamp is only
   ``z_volume <= 0``, sfincs_meteo.f90:1316-1330). Per engine-wet cell (zs above the
   cell's lowest 10 m pixel, map ``zb``) the true wet fraction f = share of its 10 m pixels below
   zs (``subgrid/dep_subgrid_lev0.tif`` of the static model); the sink is 1/f times
   open-water physics. Reported at 18Z on the given days, base run.
2. Rain lost to blending: the engine interpolates the ~1 km netampr grid bilinearly
   to cell centres and linearly in time over each second half hour, so a -E node next
   to a raining node (in space or time) lowers or cancels the rain there. The rain
   delivered per cell is emulated for base, the evap run and the buffered default.
3. cnb state: cuminf (daily) and Seff (hourly) base vs evap; cumprcp minimum.
4. Cropland area > 5 cm per county per day (summary/daily_county_crop.csv).
5. Farm-dike interiors (the 18 leveed areas of dikes_built.gpkg ``gates``): mean
   cell depth (zs - lowest pixel) over cells with lowest pixel < 1 m, 5-day means.

Prints markdown tables (agri_sfincs.report.md_table) and writes
<evap run>/summary/evap_check_*.csv. reports/evaporation.md was written by hand from them.

Usage:  python scripts/evap_check.py --base v1_100m/sep2023 --evap v1_100m/sep2023_evap \
            --days 2023-09-14 2023-09-20
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.features import rasterize
from scipy.interpolate import RegularGridInterpolator

from agri_sfincs import config, dikes, domain, runs
from agri_sfincs.report import md_table

STRUCT = config.STRUCT_DIR


def cell_pixels(model, n: int, m: int, x0: float, y0: float) -> np.ndarray:
    """(n, m, 100) 10 m pixel elevations per 100 m cell (map row 0 = south)."""
    with rasterio.open(model / "subgrid" / "dep_subgrid_lev0.tif") as d:
        tr = d.transform
        assert tr.a == 10 and tr.e == 10, "expects a south-up 10 m dep raster"
        c0, r0 = round((x0 - tr.c) / 10), round((y0 - tr.f) / 10)
        dep = d.read(1, masked=True).filled(np.nan)[r0:r0 + 10 * n, c0:c0 + 10 * m]
    return dep.reshape(n, 10, m, 10).transpose(0, 2, 1, 3).reshape(n, m, 100)


def partial_wetness(zs: np.ndarray, pix: np.ndarray, zmin: np.ndarray) -> pd.Series:
    """Stats of the wet fraction f over engine-wet cells at one instant. ``zs`` is the
    map output, which SFINCS writes only where zs - zmin > huthresh (write_cell_var_wet,
    sfincs_ncoutput_helpers.F90:186-230), and huthresh is forced to 0 with subgrid
    (sfincs_subgrid.F90:40): finite zs = the cell holds water."""
    act = np.isfinite(zmin)
    wet = act & np.isfinite(zs)
    nvalid = np.isfinite(pix).sum(2)

    def frac(sel):
        return np.maximum((pix[sel] < zs[sel][:, None]).sum(1), 1) / nvalid[sel]

    f = frac(wet)
    land = wet & (zmin > 0.5)  # not channel / bay / marsh-creek cells
    fl = frac(land)
    return pd.Series({
        "active_cells": int(act.sum()),
        "engine_wet_share": wet.sum() / act.sum(),
        "f_p10": np.percentile(f, 10), "f_p50": np.percentile(f, 50),
        "f_p90": np.percentile(f, 90),
        "sink_overcount_all": wet.sum() / f.sum(),  # whole-cell / wet-area sink
        "sink_overcount_land": land.sum() / fl.sum(),
        "share_f_le_0.01": float((f <= 0.01).mean()),
        "share_f_gt_0.9": float((f > 0.9).mean()),
    })  # fmt: skip


def _pos_area(a: np.ndarray, b: np.ndarray, dur: float) -> np.ndarray:
    """Integral over ``dur`` of max(r, 0) for r linear from a to b."""
    both = (a >= 0) & (b >= 0)
    out = np.where(both, 0.5 * (a + b) * dur, 0.0)
    cross = (a > 0) != (b > 0)
    top = np.where(a > 0, a, b)
    den = np.abs(a - b)
    out = np.where(cross & ~both, dur * top**2 / (2 * np.where(den > 0, den, 1)), out)
    return out


def engine_rain(fields: np.ndarray, x, y, xc, yc) -> np.ndarray:
    """Rain (the P > 0 part, mm) per cell as the engine delivers it from hourly fields
    (time, y, x): bilinear to cell centres (sfincs_meteo.f90:1176-1236); per hour the
    first half is the hour's value, the second half ramps linearly to the next hour's
    (dtwnd = 1800 s samples of the block series, sfincs_lib.f90:495-501,
    sfincs_meteo.f90:1272, 1312)."""
    if y[0] > y[-1]:
        y, fields = y[::-1], fields[:, ::-1]
    pts = np.column_stack([yc, xc])

    def at(k):
        return RegularGridInterpolator((y, x), fields[k], bounds_error=False, fill_value=0)(pts)

    tot = np.zeros(len(xc))
    cur = at(0)
    for k in range(fields.shape[0]):
        nxt = at(k + 1) if k + 1 < fields.shape[0] else cur
        tot += 0.5 * np.clip(cur, 0, None) + _pos_area(cur, nxt, 0.5)
        cur = nxt
    return tot


def edge_rain_loss(base_f, evap_f, xc, yc) -> pd.DataFrame:
    """Rain delivered to cells (mean mm) base vs the evap run's file vs the buffered
    default (evap.net_precip(buffer=1)) built from the base file."""
    from agri_sfincs import evap

    with xr.open_dataset(base_f) as b, xr.open_dataset(evap_f) as e:
        pb = b["Precipitation"].load()
        pe = e["Precipitation"].values
        tag = e["Precipitation"].attrs.get(evap.STAMP, "?")
    x, y = pb["x"].values, pb["y"].values
    pbuf = evap.precip_minus_evap(pb, buffer=1).values
    rb = engine_rain(pb.values, x, y, xc, yc)
    rows = {}
    for name, f in ((f"evap run ({tag})", pe), ("dry_hours, buffer=1", pbuf)):
        r = engine_rain(f, x, y, xc, yc)
        rows[name] = {"rain_base_mm": rb.mean(), "rain_mm": r.mean(),
                      "lost_share": 1 - r.sum() / rb.sum(),
                      "cells_losing_gt_1mm": float((rb - r > 1).mean())}  # fmt: skip
    return pd.DataFrame(rows).T


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--evap", required=True)
    ap.add_argument("--days", nargs=2, default=["2023-09-14", "2023-09-20"])
    a = ap.parse_args()
    base, ev = runs.resolve(a.base), runs.resolve(a.evap)
    model = base.parents[1]
    out = ev / "summary"
    out.mkdir(exist_ok=True)

    mb = xr.open_dataset(base / "sfincs_map.nc")
    me = xr.open_dataset(ev / "sfincs_map.nc")
    n, m = mb.sizes["n"], mb.sizes["m"]
    x0, y0 = float(mb["corner_x"].min()), float(mb["corner_y"].min())
    pix = cell_pixels(model, n, m, x0, y0)
    # The engine's cell bed (subgrid z_zmin, = the lowest 10 m pixel within mm); NaN
    # outside the active mask.
    zmin = mb["zb"].values.astype("float64")

    # 1. partial wetness
    days = pd.date_range(*a.days, freq="D") + pd.Timedelta(hours=18)
    pw = pd.DataFrame({f"{t:%m-%d %HZ} {lab}": partial_wetness(
        mm["zs"].sel(time=t).values, pix, zmin) for t in days[[0, len(days) // 2, -1]]
        for lab, mm in (("base", mb), ("evap", me))}).T  # fmt: skip
    pw.to_csv(out / "evap_check_partial_wet.csv")
    print("## 1. Wet fraction of engine-wet cells\n")
    print(md_table(pw, "{:,.3f}"))

    # 2. edge rain loss
    xc, yc = mb["x"].values.ravel(), mb["y"].values.ravel()
    ok = np.isfinite(zmin.ravel())
    er = edge_rain_loss(base / "sfincs_netampr.nc", ev / "sfincs_netampr.nc", xc[ok], yc[ok])
    er.to_csv(out / "evap_check_edge_rain.csv")
    print("\n## 2. Rain the engine delivers to cells (what cnb sees)\n")
    print(md_table(er, "{:,.4g}"))

    # 3. cnb state
    act = np.isfinite(zmin)
    rows = {}
    for v in ("cuminf", "cumprcp"):
        b, e = mb[v].values[:, act], me[v].values[:, act]
        rows[v] = {"base_mean_end_mm": 1000 * np.nanmean(b[-1]),
                   "evap_mean_end_mm": 1000 * np.nanmean(e[-1]),
                   "max_abs_diff_mm": 1000 * np.nanmax(np.abs(e - b)),
                   "evap_min_mm": 1000 * np.nanmin(e),
                   "cells_negative_end": int((e[-1] < 0).sum())}  # fmt: skip
    sb = mb["Seff"].values[:, act]
    se = me["Seff"].values[:, act]
    rows["Seff"] = {"base_mean_end_mm": 1000 * np.nanmean(sb[-1]),
                    "evap_mean_end_mm": 1000 * np.nanmean(se[-1]),
                    "max_abs_diff_mm": 1000 * np.nanmax(np.abs(se - sb)),
                    "evap_min_mm": 1000 * np.nanmin(se), "cells_negative_end": int((se[-1] < 0).sum())}  # fmt: skip
    del sb, se
    cnb = pd.DataFrame(rows).T
    cnb.to_csv(out / "evap_check_cnb.csv")
    print("\n## 3. cnb state, evap vs base (all active cells)\n")
    print(md_table(cnb, "{:,.3f}"))

    # 4. cropland
    def daily(run):
        d = pd.read_csv(run / "summary" / "daily_county_crop.csv", parse_dates=["date"])
        return d.groupby(["date", "county"]).area_gt_5cm_km2.sum().unstack()
    cb, ce = daily(base), daily(ev)
    crop = pd.concat({"base": cb, "evap": ce}, axis=1).swaplevel(axis=1).sort_index(axis=1)
    crop = crop.loc["2023-09-08":"2023-09-30"]
    crop.columns = [f"{c} {r}" for c, r in crop.columns]
    crop.index = crop.index.strftime("%m-%d")
    crop.to_csv(out / "evap_check_cropland.csv")
    print("\n## 4. Cropland > 5 cm (km2, daily max depth)\n")
    print(md_table(crop, "{:,.2f}"))

    # 5. diked interiors
    la = dikes.leveed_areas()
    gates = gpd.read_file(STRUCT / "dikes_built.gpkg", layer="gates")
    la = la[la.LEVEED_ID.isin(gates.leveed_id)].to_crs(domain.EPSG)
    tr = rasterio.Affine(100, 0, x0, 0, 100, y0)  # south-up rows, as the map output
    masks = {}
    for _, r in la.iterrows():
        mask = rasterize([(r.geometry, 1)], out_shape=(n, m), transform=tr, fill=0,
                         dtype="uint8").astype(bool) & (zmin < 1.0)  # fmt: skip
        if mask.any():
            masks[r.SYSTEM_NAME] = masks.get(r.SYSTEM_NAME, False) | mask
    blocks = []
    for lab, mm in (("base", mb), ("evap", me)):
        zs = mm["zs"].values
        t = pd.to_datetime(mm["time"].values)
        for name, mask in masks.items():
            h = np.nan_to_num(zs[:, mask] - zmin[mask], nan=0.0).clip(0)  # NaN zs = dry
            s = pd.Series(h.mean(axis=1), index=t)
            blocks.append(s.resample("5D").mean().rename((name, lab)))
        del zs
    dk = pd.concat(blocks, axis=1).T.sort_index()
    dk.columns = dk.columns.strftime("%m-%d")
    dk.index = [f"{s} {lab}" for s, lab in dk.index]
    dk.to_csv(out / "evap_check_dikes.csv")
    print("\n## 5. Farm-dike interiors: mean depth (m) over cells with bed < 1 m, 5-day means\n")
    print(md_table(dk, "{:,.2f}"))


if __name__ == "__main__":
    main()
