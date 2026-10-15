"""Field-scale flooding on cropland from an event run: depth per 10 m subgrid pixel,
per day, summarised by county x crop.

Works for UNIFORM quadtree models (every model so far), whose map output SFINCS writes on
the regular (n, m) grid: each 10 m pixel of ``subgrid/dep_subgrid_lev0.tif`` is matched to
its cell by coordinates (agri_sfincs.runs). A refined model needs hydromt's downscale_floodmap.

Per day (``timemax`` blocks of dtmaxout = 1 day):
  depth = zsmax[face of pixel] - dep[pixel], kept where > 0
Then on cropland pixels (that year's CDL, agri_sfincs.cdl.CROPLAND), per county in
domain.COUNTIES and per crop group (corn, soybeans, wheat, other):
  area_gt_{5,15,30}cm_km2   flooded cropland area that day
Over the event's focus PERIOD (Event.focus: one month, or a year for the y<YYYY> runs):
  max_depth (per pixel) -> written as a GeoTIFF for maps
  wet_days (days with daily max depth > 5 cm, per pixel) -> GeoTIFF + area-days
Per focus MONTH and county (all crop groups): peak area, area-days and the PERSISTENT
area (cropland wet > 5 cm on every day of that month the run holds).

A day is the day a zsmax block COVERS: the block ending at ``timemax`` = D 00:00 is day
D - 1 (until 2026-10-05 the focus mask used the block's END date, so a month's
focus_*.tif ran from the last day of the previous month to the second-to-last day of
the month; the CSV dates were already right).

⚠️ Permanent water inside crop pixels (irrigation ponds mislabelled by CDL) shows as
"flooded" every day; the ``baseline`` columns (the first spin-up day's area) say how much.

Writes, in <run>/summary/: daily_county_crop.csv, monthly_county.csv,
focus_max_depth.tif, focus_wet_days.tif, and prints the county totals.

Reads one zsmax block at a time, so a year run's map (~400 blocks) fits in memory.

Usage:  python scripts/event_summary.py --run <run dir> --event sep2023
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT

from agri_sfincs import cdl, domain, region, runs
from agri_sfincs.events import EVENTS

THRESH_M = (0.05, 0.15, 0.30)
GROUPS = {1: "corn", 5: "soybeans", 24: "wheat", 26: "wheat", 225: "corn", 241: "corn"}


def crop_group(code: np.ndarray) -> np.ndarray:
    """0 not cropland, 1 corn, 2 soybeans, 3 wheat, 4 other cropland."""
    g = np.zeros(code.shape, dtype="uint8")
    crop = np.isin(code, list(cdl.CROPLAND))
    g[crop] = 4
    g[np.isin(code, [1, 225, 241])] = 1  # corn (+ dbl crop wheat/corn, corn/soy)
    g[np.isin(code, [5, 26, 254])] = 2  # soybeans (+ dbl crop wheat/soy, barley/soy)
    g[np.isin(code, [21, 22, 23, 24, 205])] = 3  # small grains: wheat, barley, triticale
    return g


GROUP_NAMES = {1: "corn", 2: "soybeans", 3: "wheat_small_grains", 4: "other_crops"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--event", required=True, choices=sorted(EVENTS))
    a = ap.parse_args()
    ev, run = EVENTS[a.event], a.run
    model = run.parents[1]
    out = run / "summary"
    out.mkdir(exist_ok=True)

    # SFINCS writes a uniform quadtree's map output on the regular (n, m) grid.
    mp = xr.open_dataset(run / "sfincs_map.nc")
    tmax = pd.to_datetime(mp["timemax"].values)
    grid = runs.MapGrid.from_map(mp)

    dep_f = model / "subgrid" / "dep_subgrid_lev0.tif"
    with rasterio.open(dep_f) as d:
        dep = d.read(1, masked=True).filled(np.nan)
        tr, crs, shape = d.transform, d.crs, d.shape
    face = grid.face(*runs.pixel_centres(tr, *np.indices(shape)))

    # CDL of the event year on the dep grid; counties on the dep grid.
    year = ev.focus_start.year
    with rasterio.open(cdl.path(year)) as c:
        with WarpedVRT(c, crs=crs, transform=tr, width=shape[1], height=shape[0],
                       resampling=Resampling.nearest) as v:  # fmt: skip
            grp = crop_group(v.read(1))
    cty = region.load_counties().to_crs(crs)
    cty = cty[cty.fips.isin(domain.COUNTIES)].reset_index(drop=True)
    cid = rasterize(((geom, i + 1) for i, geom in enumerate(cty.geometry)),
                    out_shape=shape, transform=tr, fill=0, dtype="uint8")  # fmt: skip
    px_km2 = abs(tr.a * tr.e) / 1e6
    sel = (grp > 0) & (cid > 0) & (face >= 0) & np.isfinite(dep)
    f_sel, d_sel, g_sel, c_sel = face[sel], dep[sel], grp[sel], cid[sel]

    day = runs.block_days(mp)
    focus = ev.in_focus(day)
    month = day.strftime("%Y-%m")
    rows = []
    max_depth = np.zeros(sel.sum(), dtype="float32")
    wet_days = np.zeros(sel.sum(), dtype="uint16")
    wet_month: dict[str, np.ndarray] = {}  # per focus month: wet days per pixel
    for k, t in enumerate(tmax):
        h = runs.depth(mp, k, f_sel, d_sel)
        if focus[k]:
            max_depth = np.maximum(max_depth, h)
            wet_days += h > THRESH_M[0]
            wm = wet_month.setdefault(month[k], np.zeros(sel.sum(), dtype="uint16"))
            wm += h > THRESH_M[0]
        for ci, crow in cty.iterrows():
            for gi, gname in GROUP_NAMES.items():
                s = (c_sel == ci + 1) & (g_sel == gi)
                rec = {"date": day[k].date(), "fips": crow.fips,
                       "county": crow["name"], "crop_group": gname,
                       "cropland_km2": s.sum() * px_km2}  # fmt: skip
                for th in THRESH_M:
                    rec[f"area_gt_{int(th * 100)}cm_km2"] = (s & (h > th)).sum() * px_km2
                rows.append(rec)
    mp.close()
    df = pd.DataFrame(rows)
    df.to_csv(out / "daily_county_crop.csv", index=False)

    # Per focus month x county (all crop groups)
    per_day = df.groupby(["county", "date"]).area_gt_5cm_km2.sum().reset_index()
    per_day["month"] = pd.to_datetime(per_day.date).dt.strftime("%Y-%m")
    mrows = []
    for mon, wm in sorted(wet_month.items()):
        ndays = int((month[focus] == mon).sum())
        for ci, crow in cty.iterrows():
            d = per_day[(per_day.county == crow["name"]) & (per_day.month == mon)]
            mrows.append({"month": mon, "fips": crow.fips, "county": crow["name"],
                          "n_days": ndays,
                          "cropland_km2": (c_sel == ci + 1).sum() * px_km2,
                          "peak_area_gt_5cm_km2": d.area_gt_5cm_km2.max(),
                          "area_days_gt_5cm": d.area_gt_5cm_km2.sum(),
                          "persistent_gt_5cm_km2": ((c_sel == ci + 1) & (wm >= ndays)).sum() * px_km2})  # fmt: skip
    pd.DataFrame(mrows).to_csv(out / "monthly_county.csv", index=False)

    prof = dict(driver="GTiff", width=shape[1], height=shape[0], count=1, crs=crs,
                transform=tr, compress="deflate")  # fmt: skip
    md = np.full(shape, np.nan, dtype="float32")
    md[sel] = max_depth
    with rasterio.open(out / "focus_max_depth.tif", "w", dtype="float32", nodata=np.nan,
                       **prof) as dst:  # fmt: skip
        dst.write(md, 1)
    wd = np.zeros(shape, dtype="uint16")
    wd[sel] = wet_days
    with rasterio.open(out / "focus_wet_days.tif", "w", dtype="uint16", nodata=0,
                       **prof) as dst:  # fmt: skip
        dst.write(wd, 1)

    # County totals over the focus period
    fdf = df[ev.in_focus(df.date)]
    base = df[df.date == df.date.min()].groupby("county")["area_gt_5cm_km2"].sum()
    tot = fdf.groupby("county").agg(
        cropland_km2=("cropland_km2", "first"),
        peak_area_gt_5cm_km2=("area_gt_5cm_km2", "max"),
        area_days_gt_5cm=("area_gt_5cm_km2", "sum"),
    )
    tot["cropland_km2"] = df[df.date == df.date.min()].groupby("county").cropland_km2.sum()
    tot["peak_area_gt_5cm_km2"] = fdf.groupby(["county", "date"]).area_gt_5cm_km2.sum().groupby("county").max()
    tot["baseline_gt_5cm_km2"] = base
    print(f"focus {ev.focus} ({int(focus.sum())} days), county totals (all crop groups):")
    print(tot.round(2).to_string())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
