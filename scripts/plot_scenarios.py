"""Dike x sea-level-rise scenario matrix (plan §2.4): how much cropland floods, and where.

Inputs: <run>/summary/{daily_county_crop.csv, focus_max_depth.tif} from scripts/event_summary.py
for the runs staged by scripts/setup_scenarios.py (v1_100m/runs/<event>_<dikes>_slr<cm>).

1. Peak flooded cropland (> 5 cm, the three counties together, on the same day) and mean
   flooded area per day, per run. The ponds that CDL calls crops are subtracted: the first
   spin-up day's area in the event's present-day intact run (event_summary's "baseline"). Not
   each run's own first day: in the sea-level-rise runs day 1 already holds tidal flooding.
2. Map, ordinary tide month (tide2024oct, CDL 2024 cropland): the lowest sea-level rise at which
   each 10 m cropland pixel's monthly max depth exceeds 5 cm, with dikes as built and with the
   dikes removed. "Dike-dependent at L" = floods at L without the dikes but not with them.

Writes reports/figs/scenario_cropland_slr.png, reports/figs/scenario_first_flood_{map,zoom}.png and
reports/scenario_matrix.md.
Usage:  python scripts/plot_scenarios.py
"""

from __future__ import annotations

import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import xarray as xr  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from pyproj import Transformer  # noqa: E402

import bayshore_exposure as be  # noqa: E402
from agri_sfincs import config, dikes, domain, region  # noqa: E402
from agri_sfincs.events import EVENTS  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

RUNS = config.MODELS / "v1_100m" / "runs"
SLR = [0, 30, 60, 100]
DIKES = {"intact": "dikes as built", "removed": "dikes removed", "breach_all_farm": "100 m breach in every farm bank"}
COL = {"intact": "#2a78d6", "removed": "#eb6834", "breach_all_farm": "#1baf7a"}
THRESH = 0.05
# lowest rise at which a pixel floods: today ... +1.0 m (dark -> light), then "not by +1.0 m"
FLOOD_COLS = ["#7f2704", "#c4471a", "#f08a4b", "#f8c39a"]
LEVEL_NAMES = ["today", "+0.3 m", "+0.6 m", "+1.0 m"]
CROP_COL, WATER_COL, LAND_COL = "#e2dccb", "#c6dbef", "#f4f4f2"


def run_dir(event: str, dikes: str, slr: int):
    return RUNS / f"{event}_{dikes}_slr{slr:03d}"


def daily_total(run) -> pd.Series:
    """Domain-total flooded cropland per day (km², > 5 cm)."""
    d = pd.read_csv(run / "summary" / "daily_county_crop.csv", parse_dates=["date"])
    return d.groupby("date").area_gt_5cm_km2.sum()


def metrics(event: str, dikes: str, slr: int, suffix: str = "") -> dict:
    base = float(daily_total(run_dir(event, "intact", 0)).iloc[0])
    s = daily_total(RUNS / f"{event}_{dikes}_slr{slr:03d}{suffix}")
    s = s[EVENTS[event].in_focus(s.index)]
    return {"event": event, "dikes": dikes + suffix, "slr_m": slr / 100, "baseline_km2": base,
            "peak_km2": max(s.max() - base, 0.0), "peak_day": s.idxmax().date(),
            "mean_daily_km2": max(s.mean() - base, 0.0)}  # fmt: skip


def first_flood(dikes: str) -> tuple[np.ndarray, rasterio.Affine, object]:
    """Index of the lowest SLR level that floods each cropland pixel (0..3), 4 = not by +1 m,
    NaN = not cropland."""
    out = None
    for k, slr in reversed(list(enumerate(SLR))):
        with rasterio.open(run_dir("tide2024oct", dikes, slr) / "summary" / "focus_max_depth.tif") as r:
            a, tr, crs = r.read(1), r.transform, r.crs
        if out is None:
            out = np.where(np.isfinite(a), 4.0, np.nan)
        out[a > THRESH] = k
    return out, tr, crs


def block_min(a: np.ndarray, f: int) -> np.ndarray:
    """Coarsen by f with nanmin (earliest flooding wins), for display only."""
    n, m = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    b = a[:n, :m].reshape(n // f, f, m // f, f)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN blocks
        return np.nanmin(b, axis=(1, 3))


def line_chart(m: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, (event, title) in zip(axes, [("tide2024oct", "Ordinary tide month (Oct 2024 tides, no rain)"),
                                         ("sandy2012", "Hurricane Sandy (Oct 2012 storm tide, no rain)")]):  # fmt: skip
        x = m[m.event == event]
        for dk in DIKES:
            y = x[x.dikes == dk].sort_values("slr_m")
            if y.empty:
                continue
            ax.plot(y.slr_m, y.peak_km2, "-o", color=COL[dk], lw=2, ms=6, label=DIKES[dk])
            ax.annotate(f"{y.peak_km2.iloc[-1]:.0f}", (y.slr_m.iloc[-1], y.peak_km2.iloc[-1]),
                        xytext=(6, -3 if dk != "removed" else 6), textcoords="offset points",
                        fontsize=8, color="#52514e")  # fmt: skip
        r = x[x.dikes == "intact_rain"]
        if not r.empty:
            ax.plot(r.slr_m, r.peak_km2, "o", mfc="white", mec=COL["intact"], mew=2, ms=8)
            ax.annotate("as built, WITH Sandy's rain", (r.slr_m.iloc[0], r.peak_km2.iloc[0]),
                        xytext=(8, 0), textcoords="offset points", fontsize=8, color="#52514e",
                        va="center")  # fmt: skip
        ax.set_title(title, fontsize=10, loc="left")
        ax.set_xticks([0, 0.3, 0.6, 1.0], ["today", "+0.3 m", "+0.6 m", "+1.0 m"])
        ax.set_xlabel("sea-level rise on the Delaware Bay boundary")
        ax.grid(axis="y", color="#e5e4e0", lw=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("peak flooded cropland, > 5 cm (km²)")
    axes[1].legend(loc="upper left", fontsize=8, frameon=False)
    fig.suptitle("Cropland flooded in Salem + Cumberland + Gloucester, by dike scenario and sea-level rise",
                 fontsize=11, x=0.01, ha="left")  # fmt: skip
    fig.text(0.01, 0.005, "SFINCS v1_100m; CDL cropland of the event year; ponds (day-1 wet area of the present-day intact run) subtracted.",
             fontsize=7, color="#52514e")  # fmt: skip
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(config.REPORTS / "figs" / "scenario_cropland_slr.png", dpi=150)
    plt.close(fig)


ZOOMS = {  # lon0, lat0, lon1, lat1
    "Salem River / Mannington Meadow / Hancocks Bridge": (-75.57, 39.47, -75.38, 39.63),
    "Cumberland bayshore: Greenwich to the Maurice River": (-75.40, 39.21, -74.93, 39.42),
}  # fmt: skip


def backdrop(crs):
    """Water (model cells with bed < 0 m NAVD88: bay, tidal rivers; 100 m), counties, and the dike
    lines the model runs with (sfincs.weir; NLD alignments)."""
    with xr.open_dataset(run_dir("tide2024oct", "intact", 0) / "sfincs_map.nc") as mp:
        zb, msk = mp.zb.values, mp.msk.values
        wx0, wy0 = float(mp.corner_x.min()), float(mp.corner_y.min())
    water = np.where((msk > 0) & (zb < 0.0), 1, np.nan)
    wext = (wx0, wx0 + water.shape[1] * 100.0, wy0, wy0 + water.shape[0] * 100.0)
    cty = region.load_counties().to_crs(crs)
    cty = cty[cty.fips.isin(domain.COUNTIES)]
    lev = [(x, y) for _, x, y, _ in dikes.read_weir(run_dir("tide2024oct", "intact", 0) / "sfincs.weir")]
    return water, wext, cty, lev


def draw(ax, cls_full, tr, win, f, bd, dikes_on: bool, crs) -> None:
    """One map panel: ``win`` = (r0, r1, c0, c1) rows/cols of the 10 m grid, coarsened by ``f``."""
    r0, r1, c0, c1 = win
    cls = block_min(cls_full[r0:r1, c0:c1], f)
    x0, y0 = tr.c + c0 * tr.a, tr.f + r0 * tr.e
    ext = (x0, x0 + cls.shape[1] * f * tr.a, y0, y0 + cls.shape[0] * f * tr.e)  # rows run south -> north
    water, wext, cty, lev = bd
    ax.set_facecolor(LAND_COL)
    ax.imshow(water, extent=wext, origin="lower", cmap=ListedColormap([WATER_COL]), interpolation="nearest")
    ax.imshow(np.where(cls == 4, 1, np.nan), extent=ext, origin="lower",
              cmap=ListedColormap([CROP_COL]), interpolation="nearest")  # fmt: skip
    ax.imshow(np.where(cls < 4, cls, np.nan), extent=ext, origin="lower",
              cmap=ListedColormap(FLOOD_COLS), vmin=-0.5, vmax=3.5, interpolation="nearest")  # fmt: skip
    if dikes_on:
        for x, y in lev:
            ax.plot(x, y, color="#0b0b0b", lw=0.8)
    cty.boundary.plot(ax=ax, color="#52514e", lw=0.8, ls="--")
    px, py = Transformer.from_crs(4326, crs, always_xy=True).transform(
        [v[0] for v in be.PLACES.values()], [v[1] for v in be.PLACES.values()])  # fmt: skip
    for n, x, y in zip(be.PLACES, px, py):
        if ext[0] < x < ext[1] and ext[2] < y < ext[3]:
            ax.plot(x, y, ".", color="#0b0b0b", ms=4)
            ax.annotate(n, (x, y), xytext=(3, 3), textcoords="offset points", fontsize=8)
    ax.set_xlim(ext[0], ext[1]), ax.set_ylim(ext[2], ext[3])
    ax.set_xticks([]), ax.set_yticks([])


def legend(ax) -> None:
    for c, n in zip(FLOOD_COLS, LEVEL_NAMES):
        ax.plot([], [], "s", color=c, ms=9, label=f"first floods {n}")
    ax.plot([], [], "s", color=CROP_COL, ms=9, label="cropland, dry at +1.0 m")
    ax.plot([], [], "s", color=WATER_COL, ms=9, label="tidal water")
    ax.plot([], [], "-", color="#0b0b0b", lw=0.8, label="model dike (weir; left panels)")
    ax.legend(loc="lower left", fontsize=8, framealpha=0.95)


def flood_map(ff: dict, tr, crs) -> None:
    bd = backdrop(crs)
    title = ("Ordinary tide month (Oct 2024, no rain): the sea-level rise at which each field first "
             "floods (> 5 cm), CDL 2024 cropland")  # fmt: skip

    # overview: the bbox of everything that floods by +1 m without dikes, 3 km pad, 40 m pixels
    rows, cols = np.nonzero(np.isfinite(ff["removed"]) & (ff["removed"] < 4))
    n, m = ff["removed"].shape
    win = (max(rows.min() - 300, 0), min(rows.max() + 300, n), max(cols.min() - 300, 0), min(cols.max() + 300, m))
    fig, axes = plt.subplots(1, 2, figsize=(13, 9.2), sharex=True, sharey=True)
    for ax, dk in zip(axes, ["intact", "removed"]):
        draw(ax, ff[dk], tr, win, 4, bd, dk == "intact", crs)
        ax.set_title(DIKES[dk].capitalize(), fontsize=10, loc="left")
    legend(axes[0])
    fig.suptitle(title, fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(config.REPORTS / "figs" / "scenario_first_flood_map.png", dpi=130)
    plt.close(fig)

    # zooms at 20 m
    to = Transformer.from_crs(4326, crs, always_xy=True)
    fig, axes = plt.subplots(2, 2, figsize=(13, 12.5), gridspec_kw={"height_ratios": [1, 0.8]})
    for i, (name, (lo0, la0, lo1, la1)) in enumerate(ZOOMS.items()):
        (xa, xb), (ya, yb) = to.transform([lo0, lo1], [la0, la1])
        c0, c1 = int((xa - tr.c) / tr.a), int((xb - tr.c) / tr.a)
        r0, r1 = sorted((int((ya - tr.f) / tr.e), int((yb - tr.f) / tr.e)))
        for j, dk in enumerate(["intact", "removed"]):
            draw(axes[i, j], ff[dk], tr, (max(r0, 0), min(r1, n), max(c0, 0), min(c1, m)), 2, bd, dk == "intact", crs)
            axes[i, j].set_title(f"{name}: {DIKES[dk]}", fontsize=9, loc="left")
    legend(axes[0, 0])
    fig.suptitle(title, fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(config.REPORTS / "figs" / "scenario_first_flood_zoom.png", dpi=130)
    plt.close(fig)


def main() -> None:
    m = [metrics(e, dk, s) for e in ("tide2024oct", "sandy2012") for dk in DIKES for s in SLR
         if run_dir(e, dk, s).exists()]  # fmt: skip
    m.append(metrics("sandy2012", "intact", 0, "_rain"))
    m = pd.DataFrame(m)
    line_chart(m)

    ff = {}
    for dk in ("intact", "removed"):
        ff[dk], tr, crs = first_flood(dk)
    px_km2 = abs(tr.a * tr.e) / 1e6
    crop = np.isfinite(ff["intact"])
    tab = []
    for k, n in enumerate(LEVEL_NAMES):
        wi, wr = ff["intact"] <= k, ff["removed"] <= k
        tab.append({"sea level": n, "floods with dikes (km²)": (crop & wi).sum() * px_km2,
                    "floods without dikes (km²)": (crop & wr).sum() * px_km2,
                    "dike-dependent (km²)": (crop & wr & ~wi).sum() * px_km2,
                    "floods even with dikes, not without (km²)": (crop & wi & ~wr).sum() * px_km2})  # fmt: skip
    tab = pd.DataFrame(tab).set_index("sea level")
    flood_map(ff, tr, crs)

    show = m.assign(slr_m=m.slr_m.map("{:+.1f}".format)).set_index(["event", "dikes"]).round(2)
    lines = ["# Dike × sea-level-rise scenario matrix (2026-10-06)", "",
             "Generated by `scripts/plot_scenarios.py` (method in its docstring). Figures: "
             "`figs/scenario_cropland_slr.png`, `figs/scenario_first_flood_map.png`.", "",
             f"## Ordinary tide month (tide2024oct, no rain): CDL 2024 cropland, {crop.sum() * px_km2:.0f} km² "
             "in the three counties", "",
             "Cumulative: a pixel that floods at +0.3 m is counted at +0.6 and +1.0 m too. Flooded = monthly "
             "max depth > 5 cm (ponds that CDL calls crops are included here; ~0.6 km²).", "",
             md_table(tab.round(2), floatfmt="{:.2f}"), "",
             "## Every run: flooded cropland (> 5 cm, three counties, baseline subtracted)", "",
             md_table(show, floatfmt="{:.2f}"), ""]  # fmt: skip
    text = "\n".join(lines)
    (config.REPORTS / "scenario_matrix.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
