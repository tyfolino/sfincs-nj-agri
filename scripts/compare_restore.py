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

Runs are read from ``--model`` (default runs.MODEL, v1_100m), names ending in ``--suffix``
(e.g. ``_hrrr``).

Writes reports/restore_phase1.md and reports/figs/restore_dlevel_<site>.png; with --model or
--suffix, restore_phase1_<model><suffix>.md and restore_dlevel_<site>_<model><suffix>.png.

``--payoff`` (the dike pay-off, FINDINGS §27, §30): instead, every farm system of
setup_scenarios.py --payoff (SITES + restore/sites_all_farm.csv) re-opened at its outlet
(restore_mllw100) on tide2024oct x SLR {0, 0.3, 0.6, 1.0}, against the intact twin at the same
SLR; joint systems (restore/sites_joint.csv) on their members' leveed areas together. Per system x SLR: farm fields inside the leveed area, flooded ha in them (water > 5 cm at
least once) as built -> opened, and whole-field ha counted flooded at a flooded share of
fieldflood.SHARE with the range over SHARES (§55); the same flooded ha on neighbour fields
(RING_KM). Writes reports/restore_payoff_<model><suffix>.md and data/analysis/restore_payoff_<model><suffix>.csv.
Usage:  python scripts/compare_restore.py [--model e3v2a30brm65_100m] [--suffix _hrrr] [--payoff]
"""

from __future__ import annotations

import argparse

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

from agri_sfincs import config, dikes, fieldflood, runs  # noqa: E402
from agri_sfincs.events import EVENTS  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

SITES = {"middle_neck": "Middle Neck", "durham": "Durham"}
RING_KM = 3.0
THRESH = runs.THRESH
PAYOFF_SLR = (0, 30, 60, 100)
SHARES = (0.05, 0.10, 0.25, 0.50)  # flooded-share lines for the threshold range (FINDINGS §55)


def payoff_sites() -> dict[str, tuple[str, list[str]]]:
    """slug -> (label, NLD system names) for every system of setup_scenarios.py --payoff,
    joint ones (make_restore_scenarios.py --joint) last."""
    R = config.STRUCT_DIR / "scenarios" / "restore"
    extra = pd.read_csv(R / "sites_all_farm.csv")
    out = {sl: (sy, [sy]) for sl, sy in [*SITES.items(), *zip(extra.slug, extra.system)]}
    if (R / "sites_joint.csv").exists():
        j = pd.read_csv(R / "sites_joint.csv")
        out |= {sl: (sy, m.split(";")) for sl, sy, m in zip(j.slug, j.system, j.members)}
    return out


def cell_levels(run, event: str, grid: runs.MapGrid) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per model cell (2-D, ``grid.as_grid``) over the focus days: mean daily max zs, max zs, and zb."""
    with xr.open_dataset(run / "sfincs_map.nc") as mp:
        k = np.flatnonzero(EVENTS[event].in_focus(runs.block_days(mp)))
        z = mp["zsmax"].isel(timemax=k).values
        return (grid.as_grid(np.nanmean(z, axis=0)), grid.as_grid(np.nanmax(z, axis=0)),
                grid.as_grid(mp["zb"].values))  # fmt: skip


class Pixels:
    """10 m subgrid pixels of the site interior (unit 1) and of each neighbour field
    (unit = 1 + field index), mapped to their model cells."""

    def __init__(self, leveed, fields, tr, shape, dep, grid: runs.MapGrid):
        shapes = [(leveed.union_all(), 1)] + [(gm, i + 2) for i, gm in enumerate(fields.geometry)]
        ids = rasterize(shapes, out_shape=shape, transform=tr, fill=0, dtype="uint32")
        self.face, self.dep, self.uid = runs.pixel_cells(ids, tr, dep, grid)
        self.n = len(fields) + 1
        self.px_ha = abs(tr.a * tr.e) / 1e4

    def stats(self, run, event: str) -> pd.DataFrame:
        with xr.open_dataset(run / "sfincs_map.nc") as mp:
            ks = np.flatnonzero(EVENTS[event].in_focus(runs.block_days(mp)))
            maxd = np.zeros(self.face.size, "float32")
            wet = np.zeros(self.face.size, "uint16")
            for k in ks:
                h = runs.depth(mp, k, self.face, self.dep)
                maxd = np.maximum(maxd, h)
                wet += h > THRESH
        b = lambda w: np.bincount(self.uid, weights=w, minlength=self.n + 1)[1:]  # noqa: E731
        npx = b(np.ones(self.uid.size))
        return pd.DataFrame({"ha": npx * self.px_ha,
                             "flooded_ha": b((maxd > THRESH).astype(float)) * self.px_ha,
                             "wet_ha_days": b(wet.astype(float)) * self.px_ha,
                             "always_wet_ha": b((wet >= ks.size).astype(float)) * self.px_ha})  # fmt: skip


def field_ha(s: pd.DataFrame, share: float) -> float:
    """ha of the whole fields in ``s`` (Pixels.stats rows) with a flooded share >= ``share``."""
    return float(s.ha[s.flooded_ha / s.ha >= share].sum())


def payoff(model, suffix, out_tag, lines, dep, tr, shape, grid, lev, allf) -> None:
    """The --payoff report (docstring)."""
    rows = []
    for slug, (system, members) in payoff_sites().items():
        L = lev[lev.SYSTEM_NAME.isin(members)]
        Lu = L.union_all()
        ring = L.buffer(RING_KM * 1000).union_all().difference(Lu)
        inn = allf[allf.representative_point().within(Lu)].reset_index(drop=True)
        nb = allf[allf.representative_point().within(ring)].reset_index(drop=True)
        pxi, px = Pixels(L, inn, tr, shape, dep, grid), Pixels(L, nb, tr, shape, dep, grid)
        for slr in PAYOFF_SLR:
            run = runs.run_dir("tide2024oct", f"restore_{slug}_mllw100", slr, suffix, model=model)
            twin = runs.run_dir("tide2024oct", "intact", slr, suffix, model=model)
            if not (runs.finished(run) and runs.finished(twin)):
                continue
            # unit 1 from px: in pxi the inside fields overwrite the leveed area
            s0, s1 = px.stats(twin, "tide2024oct"), px.stats(run, "tide2024oct")
            n0, n1 = s0.iloc[1:], s1.iloc[1:]
            f0, f1 = pxi.stats(twin, "tide2024oct").iloc[1:], pxi.stats(run, "tide2024oct").iloc[1:]
            d = {sh: field_ha(f1, sh) - field_ha(f0, sh) for sh in SHARES}
            rows.append({"system": system, "slr_cm": slr, "leveed ha": s0.ha.iloc[0],
                         "fields": len(inn), "field ha": f0.ha.sum(),
                         "leveed flooded ha, built": s0.flooded_ha.iloc[0], "opened": s1.flooded_ha.iloc[0],
                         "field flooded ha, built": f0.flooded_ha.sum(), "field flooded ha, opened": f1.flooded_ha.sum(),
                         "Δ field flooded ha": f1.flooded_ha.sum() - f0.flooded_ha.sum(),
                         f"Δ whole-field ha @{fieldflood.SHARE:.0%}": d[fieldflood.SHARE],
                         **{f"Δ whole-field ha @{sh:.0%}": d[sh] for sh in SHARES if sh != fieldflood.SHARE},
                         "Δ nbr field flooded ha": n1.flooded_ha.sum() - n0.flooded_ha.sum()})  # fmt: skip
    df = pd.DataFrame(rows)
    df.to_csv(config.ANALYSIS_DIR / f"restore_payoff{out_tag}.csv", index=False)
    show = df.copy()
    lo, hi = show.filter(like="Δ whole-field ha @").min(axis=1), show.filter(like="Δ whole-field ha @").max(axis=1)
    k = f"Δ whole-field ha @{fieldflood.SHARE:.0%}"
    show[f"Δ whole-field ha, {fieldflood.SHARE:.0%} line ({SHARES[0]:.0%}-{SHARES[-1]:.0%} range)"] = [f"{v:+,.0f} ({a:+,.0f} to {b:+,.0f})" for v, a, b in zip(show[k], lo, hi)]
    show = show.drop(columns=[c for c in show if c.startswith("Δ whole-field ha @")])
    text = "\n".join(["# Dike pay-off: farmland behind each bank, re-opened to the tide (tide2024oct x SLR)", "",
                      "Generated by `scripts/compare_restore.py --payoff` (method in its docstring). Each farm "
                      "system's outlet re-opened 100 m to local MLLW, gate removed, every other bank as built; "
                      f"compared with the intact run at the same SLR. Runs: `{model}`, names ending `{suffix or '(none)'}`. "
                      "Fields: farmed 2020 (`field_flood_classes.gpkg`), inside = representative point in the "
                      f"NLD leveed area; neighbours within {RING_KM:g} km outside it. Flooded = water > "
                      f"{100 * THRESH:.0f} cm at least once in the focus days. Gibbstown has several outlets and "
                      "is cut at one (it loses all its valves). Table: `data/analysis/restore_payoff"
                      f"{out_tag}.csv`.", "", *lines,
                      "## Per system and sea-level rise (as built -> opened)", "",
                      md_table(show.set_index(["system", "slr_cm"]), floatfmt="{:,.0f}") if rows else "(no runs finished)", ""])  # fmt: skip
    (config.REPORTS / f"restore_payoff{out_tag}.md").write_text(text + "\n")
    print(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=runs.MODEL)
    ap.add_argument("--suffix", default="", help="run-name ending, e.g. _hrrr")
    ap.add_argument("--payoff", action="store_true", help="every farm system x SLR (docstring)")
    a_ = ap.parse_args()
    model, suffix = a_.model, a_.suffix
    out_tag = "" if model == runs.MODEL and not suffix else f"_{model}{suffix}"
    with rasterio.open(runs.subgrid_dep(model)) as d:
        dep = d.read(1, masked=True).filled(np.nan)
        tr, crs, shape = d.transform, d.crs, d.shape
    base = runs.run_dir("tide2024oct", "intact", 0, suffix, model=model)
    with xr.open_dataset(base / "sfincs_map.nc") as mp:
        grid = runs.MapGrid.from_map(mp)
        msk = grid.as_grid(mp["msk"].values)
    x0, y0, dx = grid.x0, grid.y0, grid.dx
    cx = x0 + (np.arange(grid.m) + 0.5) * dx
    cy = y0 + (np.arange(grid.n) + 0.5) * dx
    CX, CY = np.meshgrid(cx, cy)
    lev = dikes.leveed_areas(crs)
    allf = gpd.read_file(config.ANALYSIS_DIR / "field_flood_classes.gpkg").to_crs(crs)

    # noise floor
    lines, noise = [], {}
    rep = runs.run_dir("tide2024oct", "intact", 0, f"_rep{suffix}", model=model)
    if runs.finished(rep):
        a, am, zb = cell_levels(base, "tide2024oct", grid)
        b, bm, _ = cell_levels(rep, "tide2024oct", grid)
        wet = (msk > 0) & ((am - zb > THRESH) | (bm - zb > THRESH))
        noise = {"mean daily high water": np.nanmax(np.abs(b - a)[wet]), "month max": np.nanmax(np.abs(bm - am)[wet])}
        lines += ["## Noise floor (identical repeat of tide2024oct_intact_slr000)", "",
                  f"Largest |difference| on any wet cell: mean daily high water {noise['mean daily high water']:.4f} m, "
                  f"month max {noise['month max']:.4f} m.", ""]  # fmt: skip
    else:
        lines += ["## Noise floor: the repeat run has not finished.", ""]
    if a_.payoff:
        payoff(model, suffix, out_tag, lines, dep, tr, shape, grid, lev, allf)
        return

    rows, lvl = [], []
    for slug, system in SITES.items():
        L = lev[lev.SYSTEM_NAME == system]
        ring = L.buffer(RING_KM * 1000).union_all().difference(L.union_all())
        nb = allf[allf.representative_point().within(ring)].reset_index(drop=True)
        px = Pixels(L, nb, tr, shape, dep, grid)
        inn = allf[allf.representative_point().within(L.union_all())].reset_index(drop=True)
        pxi = Pixels(L, inn, tr, shape, dep, grid)
        Lu = L.union_all()
        inside = contains_xy(Lu, CX, CY)
        near = contains_xy(Lu.buffer(RING_KM * 1000), CX, CY) & ~inside
        for event, slr, arm in [("tide2024oct", 0, "breach"), ("tide2024oct", 0, "restore_mllw100"),
                                ("tide2024oct", 0, "restore_mllw300"), ("tide2024oct", 60, "restore_mllw100"),
                                ("tide2024oct", 60, "restore_mllw300"), ("sandy2012", 0, "restore_mllw100"),
                                ("tide2024oct", 0, "restore_setback"), ("tide2024oct", 60, "restore_setback"),
                                ("sandy2012", 0, "restore_setback")]:  # fmt: skip
            dk = f"breach_{slug}" if arm == "breach" else f"restore_{slug}_{arm.split('_')[1]}"
            run, twin = runs.run_dir(event, dk, slr, suffix, model=model), runs.run_dir(event, "intact", slr, suffix, model=model)
            if not runs.finished(run):
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
            a, am, zb = cell_levels(twin, event, grid)
            b, bm, _ = cell_levels(run, event, grid)
            wet = (msk > 0) & ((am - zb > THRESH) | (bm - zb > THRESH)) & ~inside
            d_mhw, d_max = b - a, bm - am
            far = wet & ~near
            lvl.append({"site": system, "event": event, "slr_m": slr / 100, "arm": arm,
                        "ΔMHW ring p5/p50/p95 (cm)": "/".join(f"{100 * v:+.1f}" for v in np.nanpercentile(d_mhw[wet & near], [5, 50, 95])),
                        "Δmax ring p5/p50/p95 (cm)": "/".join(f"{100 * v:+.1f}" for v in np.nanpercentile(d_max[wet & near], [5, 50, 95])),
                        "ring cells |ΔMHW| > 1 cm": int((np.abs(d_mhw) > 0.01)[wet & near].sum()),
                        "beyond-ring cells |ΔMHW| > 1 cm": int((np.abs(d_mhw) > 0.01)[far].sum()),
                        "largest |ΔMHW| beyond ring (cm)": 100 * float(np.nanmax(np.abs(d_mhw[far]))) if far.any() else np.nan})  # fmt: skip
            if event == "tide2024oct" and slr == 0 and arm in ("restore_mllw100", "restore_setback"):
                fig, ax = plt.subplots(figsize=(8, 8))
                show = np.where((msk > 0) & ((am - zb > THRESH) | (bm - zb > THRESH)), d_mhw, np.nan)
                # symmetric log: metres inside the site and millimetres outside on one bar
                norm = SymLogNorm(linthresh=0.005, linscale=0.5, vmin=-1.5, vmax=1.5, base=10)
                im = ax.imshow(show, origin="lower", cmap="RdBu_r", norm=norm,
                               extent=(x0, x0 + grid.m * dx, y0, y0 + grid.n * dx), interpolation="nearest")  # fmt: skip
                L.boundary.plot(ax=ax, color="#0b0b0b", lw=1)
                gpd.GeoSeries([ring], crs=crs).boundary.plot(ax=ax, color="#52514e", lw=0.8, ls="--")
                xb0, yb0, xb1, yb1 = L.buffer(RING_KM * 1500).total_bounds
                ax.set_xlim(xb0, xb1), ax.set_ylim(yb0, yb1)
                ax.set_xticks([]), ax.set_yticks([])
                ticks = [-1, -0.1, -0.01, 0, 0.01, 0.1, 1]
                cb = fig.colorbar(im, ax=ax, fraction=0.04, ticks=ticks,
                                  label="change in mean daily high water (log scale; linear within ±5 mm)")  # fmt: skip
                cb.ax.set_yticklabels(["−1 m", "−10 cm", "−1 cm", "0", "+1 cm", "+10 cm", "+1 m"])
                sb = config.STRUCT_DIR / "scenarios" / "restore" / f"{slug}_setback.gpkg"
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
                fig.savefig(config.REPORTS / "figs" / f"restore_dlevel_{slug}{tag}{out_tag}.png", dpi=130)
                plt.close(fig)

    text = "\n".join(["# Farm -> wetland phase 1: re-opening one dike system to the tide (2026-10-06)", "",
                      "Generated by `scripts/compare_restore.py` (method in its docstring). Maps of the change "
                      f"in daily high water: `figs/restore_dlevel_<site>[_setback]{out_tag}.png`. "
                      f"Runs: `{model}`, names ending `{suffix or '(none)'}`.", "", *lines,
                      "## Inside the site and on neighbouring farm fields (as built -> scenario)", "",
                      md_table(pd.DataFrame(rows).set_index(["site", "event", "slr_m", "arm"]), floatfmt="{:,.0f}") if rows else "(no runs finished)", "",
                      "## Water levels outside the site (cells wet in either run)", "",
                      md_table(pd.DataFrame(lvl).set_index(["site", "event", "slr_m", "arm"]), floatfmt="{:.1f}") if lvl else "", ""])  # fmt: skip
    (config.REPORTS / f"restore_phase1{out_tag}.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
