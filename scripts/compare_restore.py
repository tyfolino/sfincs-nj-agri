"""Farm -> wetland phase 1: what re-opening one dike system to the tide does, inside it and to
its neighbours (runs from scripts/setup_scenarios.py --restore; structures from
scripts/make_restore_scenarios.py).

Each scenario run is compared with its as-built twin (same event, same SLR, dikes intact):
  site     inside the system's NLD leveed area: area flooded > 5 cm at least once, mean wet
           days per pixel, and area wet on EVERY day of the month (ponded / open water)
  inside   farm fields (scripts/field_flood_classes.py) INSIDE the leveed area, i.e. behind the
           same bank: flooded fields (> 10% rule as there), flooded ha in them, wet field-days
           (sum of ha x wet days), as-built vs scenario
  fields   the same for farm fields OUTSIDE the leveed area with their centroid within RING_KM
  levels   per 100 m model cell, the change in mean daily high water (mean over the focus days
           of the daily max zs) and in the month's max zs, on cells wet in either run, outside
           the leveed area; summarised within RING_KM and beyond
The noise floor is the identical repeat tide2024oct_intact_slr000_rep vs tide2024oct_intact_slr000:
a difference smaller than it is not a result.

Writes reports/restore_phase1.md and reports/figs/restore_dlevel_<site>.png.
Usage:  python scripts/compare_restore.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import xarray as xr  # noqa: E402
from matplotlib.colors import SymLogNorm  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from shapely import contains_xy  # noqa: E402

import plot_scenarios as ps  # noqa: E402
from agri_sfincs import config, fieldflood  # noqa: E402
from agri_sfincs.events import EVENTS  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

RUNS = ps.RUNS
SITES = {"middle_neck": "Middle Neck", "durham": "Durham"}
RING_KM = 3.0
THRESH = 0.05


def done(run) -> bool:
    log = run / "sfincs_log.txt"
    return log.exists() and "Total time" in log.read_text(errors="ignore")


def cell_levels(run, event: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per model cell over the focus days: mean daily max zs, max zs, and zb."""
    with xr.open_dataset(run / "sfincs_map.nc") as mp:
        day = pd.to_datetime(mp["timemax"].values) - pd.Timedelta(days=1)
        k = np.flatnonzero(EVENTS[event].in_focus(day))
        z = mp["zsmax"].isel(timemax=k).values
        return np.nanmean(z, axis=0), np.nanmax(z, axis=0), mp["zb"].values


class Pixels:
    """10 m subgrid pixels of the site interior (unit 1) and of each neighbour field
    (unit = 1 + field index), mapped to their model cells."""

    def __init__(self, leveed, fields, tr, shape, dep, zshape, x0, y0, dx):
        shapes = [(leveed.union_all(), 1)] + [(gm, i + 2) for i, gm in enumerate(fields.geometry)]
        ids = rasterize(shapes, out_shape=shape, transform=tr, fill=0, dtype="uint32")
        rr, cc = np.nonzero(ids)
        nn = np.floor((tr.f + (rr + 0.5) * tr.e - y0) / dx).astype(np.int64)
        mm = np.floor((tr.c + (cc + 0.5) * tr.a - x0) / dx).astype(np.int64)
        ok = (nn >= 0) & (nn < zshape[1]) & (mm >= 0) & (mm < zshape[2]) & np.isfinite(dep[rr, cc])
        self.face = (nn * zshape[2] + mm)[ok]
        self.dep = dep[rr, cc][ok]
        self.uid = ids[rr, cc][ok].astype(np.int64)
        self.n = len(fields) + 1
        self.px_ha = abs(tr.a * tr.e) / 1e4

    def stats(self, run, event: str) -> pd.DataFrame:
        with xr.open_dataset(run / "sfincs_map.nc") as mp:
            day = pd.to_datetime(mp["timemax"].values) - pd.Timedelta(days=1)
            ks = np.flatnonzero(EVENTS[event].in_focus(day))
            maxd = np.zeros(self.face.size, "float32")
            wet = np.zeros(self.face.size, "uint16")
            for k in ks:
                h = mp["zsmax"][k].values.ravel()[self.face] - self.dep
                h = np.where(np.isfinite(h) & (h > 0), h, 0).astype("float32")
                maxd = np.maximum(maxd, h)
                wet += h > THRESH
        b = lambda w: np.bincount(self.uid, weights=w, minlength=self.n + 1)[1:]  # noqa: E731
        npx = b(np.ones(self.uid.size))
        return pd.DataFrame({"ha": npx * self.px_ha,
                             "flooded_ha": b((maxd > THRESH).astype(float)) * self.px_ha,
                             "wet_ha_days": b(wet.astype(float)) * self.px_ha,
                             "always_wet_ha": b((wet >= ks.size).astype(float)) * self.px_ha})  # fmt: skip


def main() -> None:
    model = RUNS.parent
    with rasterio.open(model / "subgrid" / "dep_subgrid_lev0.tif") as d:
        dep = d.read(1, masked=True).filled(np.nan)
        tr, crs, shape = d.transform, d.crs, d.shape
    base = ps.run_dir("tide2024oct", "intact", 0)
    with xr.open_dataset(base / "sfincs_map.nc") as mp:
        zshape = mp["zsmax"].shape
        x0, y0 = float(mp.corner_x.min()), float(mp.corner_y.min())
        dx = float(np.diff(np.unique(mp.corner_x.values.round(3)))[0])
        msk = mp["msk"].values
    cx = x0 + (np.arange(zshape[2]) + 0.5) * dx
    cy = y0 + (np.arange(zshape[1]) + 0.5) * dx
    CX, CY = np.meshgrid(cx, cy)
    lev = gpd.read_file(config.DATA / "structures" / "structures.gpkg", layer="nld_leveed_areas").to_crs(crs)
    allf = gpd.read_file(config.DATA / "analysis" / "field_flood_classes.gpkg").to_crs(crs)

    # noise floor
    lines, noise = [], {}
    rep = ps.run_dir("tide2024oct", "intact", 0).with_name("tide2024oct_intact_slr000_rep")
    if done(rep):
        a, am, zb = cell_levels(base, "tide2024oct")
        b, bm, _ = cell_levels(rep, "tide2024oct")
        wet = (msk > 0) & ((am - zb > THRESH) | (bm - zb > THRESH))
        noise = {"mean daily high water": np.nanmax(np.abs(b - a)[wet]), "month max": np.nanmax(np.abs(bm - am)[wet])}
        lines += ["## Noise floor (identical repeat of tide2024oct_intact_slr000)", "",
                  f"Largest |difference| on any wet cell: mean daily high water {noise['mean daily high water']:.4f} m, "
                  f"month max {noise['month max']:.4f} m.", ""]  # fmt: skip
    else:
        lines += ["## Noise floor: the repeat run has not finished.", ""]

    rows, lvl = [], []
    for slug, system in SITES.items():
        L = lev[lev.SYSTEM_NAME == system]
        ring = L.buffer(RING_KM * 1000).union_all().difference(L.union_all())
        nb = allf[allf.representative_point().within(ring)].reset_index(drop=True)
        px = Pixels(L, nb, tr, shape, dep, zshape, x0, y0, dx)
        inn = allf[allf.representative_point().within(L.union_all())].reset_index(drop=True)
        pxi = Pixels(L, inn, tr, shape, dep, zshape, x0, y0, dx)
        Lu = L.union_all()
        inside = contains_xy(Lu, CX, CY)
        near = contains_xy(Lu.buffer(RING_KM * 1000), CX, CY) & ~inside
        for event, slr, arm in [("tide2024oct", 0, "breach"), ("tide2024oct", 0, "restore_mllw100"),
                                ("tide2024oct", 0, "restore_mllw300"), ("tide2024oct", 60, "restore_mllw100"),
                                ("tide2024oct", 60, "restore_mllw300"), ("sandy2012", 0, "restore_mllw100"),
                                ("tide2024oct", 0, "restore_setback"), ("tide2024oct", 60, "restore_setback"),
                                ("sandy2012", 0, "restore_setback")]:  # fmt: skip
            dk = f"breach_{slug}" if arm == "breach" else f"restore_{slug}_{arm.split('_')[1]}"
            run, twin = ps.run_dir(event, dk, slr), ps.run_dir(event, "intact", slr)
            if not done(run):
                continue
            s0, s1 = px.stats(twin, event), px.stats(run, event)
            site0, site1 = s0.iloc[0], s1.iloc[0]
            f0, f1 = s0.iloc[1:], s1.iloc[1:]
            fl0 = (f0.flooded_ha / f0.ha >= fieldflood.SHARE)
            fl1 = (f1.flooded_ha / f1.ha >= fieldflood.SHARE)
            i0, i1 = pxi.stats(twin, event).iloc[1:], pxi.stats(run, event).iloc[1:]
            ii0 = (i0.flooded_ha / i0.ha >= fieldflood.SHARE).values
            ii1 = (i1.flooded_ha / i1.ha >= fieldflood.SHARE).values
            rows.append({"site": system, "event": event, "slr_m": slr / 100, "arm": arm,
                         "site ha": site0.ha, "site flooded ha (built -> scen)": f"{site0.flooded_ha:.0f} -> {site1.flooded_ha:.0f}",
                         "site always-wet ha": f"{site0.always_wet_ha:.0f} -> {site1.always_wet_ha:.0f}",
                         "fields inside": len(inn), "inside flooded fields": f"{int(ii0.sum())} -> {int(ii1.sum())}",
                         "inside flooded ha": f"{i0.flooded_ha.sum():.0f} -> {i1.flooded_ha.sum():.0f}",
                         "inside wet ha-days": f"{i0.wet_ha_days.sum():.0f} -> {i1.wet_ha_days.sum():.0f}",
                         "neighbour fields": len(nb), "nbr flooded fields": f"{int(fl0.sum())} -> {int(fl1.sum())}",
                         "nbr flooded ha": f"{f0.flooded_ha.sum():.1f} -> {f1.flooded_ha.sum():.1f}",
                         "nbr wet ha-days": f"{f0.wet_ha_days.sum():.0f} -> {f1.wet_ha_days.sum():.0f}"})  # fmt: skip
            a, am, zb = cell_levels(twin, event)
            b, bm, _ = cell_levels(run, event)
            wet = (msk > 0) & ((am - zb > THRESH) | (bm - zb > THRESH)) & ~inside
            d_mhw, d_max = b - a, bm - am
            far = wet & ~near
            lvl.append({"site": system, "event": event, "slr_m": slr / 100, "arm": arm,
                        f"ΔMHW ring p5/p50/p95 (cm)": "/".join(f"{100 * v:+.1f}" for v in np.nanpercentile(d_mhw[wet & near], [5, 50, 95])),
                        f"Δmax ring p5/p50/p95 (cm)": "/".join(f"{100 * v:+.1f}" for v in np.nanpercentile(d_max[wet & near], [5, 50, 95])),
                        "ring cells |ΔMHW| > 1 cm": int((np.abs(d_mhw) > 0.01)[wet & near].sum()),
                        "beyond-ring cells |ΔMHW| > 1 cm": int((np.abs(d_mhw) > 0.01)[far].sum()),
                        "largest |ΔMHW| beyond ring (cm)": 100 * float(np.nanmax(np.abs(d_mhw[far]))) if far.any() else np.nan})  # fmt: skip
            if event == "tide2024oct" and slr == 0 and arm in ("restore_mllw100", "restore_setback"):
                fig, ax = plt.subplots(figsize=(8, 8))
                show = np.where((msk > 0) & ((am - zb > THRESH) | (bm - zb > THRESH)), d_mhw, np.nan)
                # symmetric log: metres inside the site and millimetres outside on one bar
                norm = SymLogNorm(linthresh=0.005, linscale=0.5, vmin=-1.5, vmax=1.5, base=10)
                im = ax.imshow(show, origin="lower", cmap="RdBu_r", norm=norm,
                               extent=(x0, x0 + zshape[2] * dx, y0, y0 + zshape[1] * dx), interpolation="nearest")  # fmt: skip
                L.boundary.plot(ax=ax, color="#0b0b0b", lw=1)
                gpd.GeoSeries([ring], crs=crs).boundary.plot(ax=ax, color="#52514e", lw=0.8, ls="--")
                xb0, yb0, xb1, yb1 = L.buffer(RING_KM * 1500).total_bounds
                ax.set_xlim(xb0, xb1), ax.set_ylim(yb0, yb1)
                ax.set_xticks([]), ax.set_yticks([])
                ticks = [-1, -0.1, -0.01, 0, 0.01, 0.1, 1]
                cb = fig.colorbar(im, ax=ax, fraction=0.04, ticks=ticks,
                                  label="change in mean daily high water (log scale; linear within ±5 mm)")  # fmt: skip
                cb.ax.set_yticklabels(["−1 m", "−10 cm", "−1 cm", "0", "+1 cm", "+10 cm", "+1 m"])
                sb = config.DATA / "structures" / "scenarios" / "restore" / f"{slug}_setback.gpkg"
                if arm == "restore_setback" and sb.exists():
                    sg = gpd.read_file(sb)
                    sg[sg.what == "inner_dike"].plot(ax=ax, color="#eb6834", lw=1.2)
                what = ("seaward non-farmed land restored, farms behind an inner dike (orange)"
                        if arm == "restore_setback" else "re-opened to the tide (100 m to MLLW, gate removed)")
                ax.set_title(f"{system} {what} minus as built\n"
                             f"Oct 2024 tides, today's sea level; black = leveed area, dashed = {RING_KM:g} km ring",
                             fontsize=10, loc="left")  # fmt: skip
                fig.tight_layout()
                tag = "_setback" if arm == "restore_setback" else ""
                fig.savefig(config.REPORTS / "figs" / f"restore_dlevel_{slug}{tag}.png", dpi=130)
                plt.close(fig)

    text = "\n".join(["# Farm -> wetland phase 1: re-opening one dike system to the tide (2026-10-06)", "",
                      "Generated by `scripts/compare_restore.py` (method in its docstring).", "", *lines,
                      "## Inside the site and on neighbouring farm fields (as built -> scenario)", "",
                      md_table(pd.DataFrame(rows).set_index(["site", "event", "slr_m", "arm"]), floatfmt="{:,.0f}") if rows else "(no runs finished)", "",
                      "## Water levels outside the site (cells wet in either run)", "",
                      md_table(pd.DataFrame(lvl).set_index(["site", "event", "slr_m", "arm"]), floatfmt="{:.1f}") if lvl else "", ""])  # fmt: skip
    (config.REPORTS / "restore_phase1.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
