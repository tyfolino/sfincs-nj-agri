"""Hourly flood animation of two scenario runs side by side, over one bayshore window.

Depth per 10 m subgrid pixel = hourly zs of its model cell - the pixel's ground (as in
scripts/event_summary.py, but every output hour instead of the daily max), shown on land
only (pixels whose ground is above 0 m NAVD88), coarsened to 20 m for display. Cropland
(CDL of the event year) is drawn under the water so you can see which fields go under.
A strip below the maps shows the boundary water level at the forcing gauge nearest the window.
The model's dike lines (sfincs.weir) are drawn on maps whose run keeps them.

Writes reports/figs/anim_<event>_<a>_vs_<b>.gif.
Usage:  python scripts/animate_scenarios.py --event sandy2012 --runs intact_slr000 intact_slr100 \
            --start "2012-10-28 12:00" --end "2012-10-31 00:00"
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import xarray as xr  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.vrt import WarpedVRT  # noqa: E402
from rasterio.windows import Window  # noqa: E402

from agri_sfincs import cdl, config, dikes, maps, runs  # noqa: E402
from agri_sfincs.events import EVENTS  # noqa: E402

WINDOW = (-75.58, 39.36, -75.25, 39.63)  # lon0, lat0, lon1, lat1: Salem River to Greenwich
F = 2  # display pixel = 20 m
DEPTH_CMAP = plt.get_cmap("Blues")
LABEL = {"intact": "dikes as built", "removed": "dikes removed", "breach_all_farm": "breach in every farm bank"}


def label(run: str) -> str:
    dk, slr = run.rsplit("_slr", 1)
    return f"{LABEL.get(dk, dk)}, " + ("today's sea level" if int(slr) == 0 else f"+{int(slr) / 100:.1f} m sea level")


def coarsen(a: np.ndarray, f: int, how=np.nanmean) -> np.ndarray:
    n, m = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return how(a[:n, :m].reshape(n // f, f, m // f, f), axis=(1, 3))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--event", required=True, choices=sorted(EVENTS))
    ap.add_argument("--runs", nargs=2, required=True, help="two <dikes>_slr<cm> suffixes")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--fps", type=int, default=6)
    a = ap.parse_args()
    ev = EVENTS[a.event]
    run_dirs = [runs.resolve(f"{a.event}_{r}") for r in a.runs]

    with rasterio.open(runs.subgrid_dep()) as d:
        tr, crs = d.transform, d.crs
        (xa, xb), (ya, yb) = Transformer.from_crs(4326, crs, always_xy=True).transform(
            [WINDOW[0], WINDOW[2]], [WINDOW[1], WINDOW[3]])  # fmt: skip
        c0, c1 = int((xa - tr.c) / tr.a), int((xb - tr.c) / tr.a)
        r0, r1 = sorted((int((ya - tr.f) / tr.e), int((yb - tr.f) / tr.e)))
        c0, c1, r0, r1 = max(c0, 0), min(c1, d.width), max(r0, 0), min(r1, d.height)
        win = Window(c0, r0, c1 - c0, r1 - r0)
        dep = d.read(1, window=win, masked=True).filled(np.nan)
        wtr = d.window_transform(win)
    with rasterio.open(cdl.path(ev.focus_start.year)) as c:
        with WarpedVRT(c, crs=crs, transform=wtr, width=dep.shape[1], height=dep.shape[0],
                       resampling=Resampling.nearest) as v:  # fmt: skip
            crop = np.isin(v.read(1), list(cdl.CROPLAND))

    # 10 m pixel -> model cell (event_summary.py's mapping)
    mds = [xr.open_dataset(r / "sfincs_map.nc") for r in run_dirs]
    mp = mds[0]
    nn, mm, inside = runs.MapGrid.from_map(mp).index(*runs.pixel_centres(wtr, *np.indices(dep.shape)))
    nn, mm = np.clip(nn, 0, mp.zs.shape[1] - 1), np.clip(mm, 0, mp.zs.shape[2] - 1)
    n0, n1, m0, m1 = nn.min(), nn.max() + 1, mm.min(), mm.max() + 1
    nn, mm = nn - n0, mm - m0
    land = np.isfinite(dep) & (dep > 0.0) & inside

    times = pd.to_datetime(mp.time.values)
    sel = np.flatnonzero((times >= pd.Timestamp(a.start)) & (times <= pd.Timestamp(a.end)))
    zs = [m.zs.isel(time=sel, n=slice(n0, n1), m=slice(m0, m1)).values for m in mds]

    # boundary strip: the forcing gauge nearest the window's SW corner (the bay side)
    bnd = [xr.open_dataset(r / "sfincs_netbndbzsbzifile.nc") for r in run_dirs]
    k = int(np.argmin(np.hypot(bnd[0].x.values - xa, bnd[0].y.values - ya)))
    st_name = f"{str(bnd[0].name.values[k]).strip()} (NOAA {bnd[0].noaa_id.values[k]}), boundary forcing"
    ht = pd.to_datetime(bnd[0].time.values)
    hsel = (ht >= pd.Timestamp(a.start)) & (ht <= pd.Timestamp(a.end))

    ext = (wtr.c, wtr.c + dep.shape[1] // F * F * wtr.a, wtr.f, wtr.f + dep.shape[0] // F * F * wtr.e)
    crop_d = coarsen(crop.astype(float), F, np.nanmax)
    land_d = coarsen(land.astype(float), F, np.nanmax)
    fig = plt.figure(figsize=(12, 7.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 0.22], hspace=0.12, wspace=0.03)
    axes = [fig.add_subplot(gs[0, i]) for i in range(2)]
    axl = fig.add_subplot(gs[1, :])
    ims = []
    for ax, r in zip(axes, a.runs):
        ax.set_facecolor("#c6dbef")  # below 0 m NAVD88: water
        ax.imshow(np.where(land_d > 0, 1, np.nan), extent=ext, origin="lower",
                  cmap=ListedColormap(["#f4f4f2"]), interpolation="nearest")  # fmt: skip
        ax.imshow(np.where(crop_d > 0, 1, np.nan), extent=ext, origin="lower",
                  cmap=ListedColormap(["#e2dccb"]), interpolation="nearest")  # fmt: skip
        ims.append(ax.imshow(np.full(crop_d.shape, np.nan), extent=ext, origin="lower", cmap=DEPTH_CMAP,
                             vmin=0, vmax=1.5, interpolation="nearest"))  # fmt: skip
        if not r.startswith("removed"):
            for _, wx, wy, _ in dikes.read_weir(run_dirs[0] / "sfincs.weir"):
                ax.plot(wx, wy, color="#0b0b0b", lw=0.6)
        maps.label_places(ax, crs, ext)
        ax.set_xlim(ext[0], ext[1]), ax.set_ylim(ext[2], ext[3])
        ax.set_xticks([]), ax.set_yticks([])
        ax.set_title(label(r), fontsize=10, loc="left")
    cb = fig.colorbar(ims[1], ax=axes, fraction=0.025, pad=0.01)
    cb.set_label("water depth on land (m)")
    for h, r, col in zip(bnd, a.runs, ["#2a78d6", "#eb6834"]):
        axl.plot(ht[hsel], h.zs.values[hsel, k], color=col, lw=2, label=label(r))
    axl.set_ylabel("m NAVD88", fontsize=8)
    axl.set_title(f"water level at {st_name}", fontsize=9, loc="left")
    axl.grid(axis="y", color="#e5e4e0")
    axl.legend(fontsize=7, frameon=False, loc="upper left")
    for s in ("top", "right"):
        axl.spines[s].set_visible(False)
    vline = axl.axvline(times[sel[0]], color="#0b0b0b", lw=1)
    stamp = fig.suptitle("", fontsize=12, x=0.01, ha="left")
    fig.text(0.01, 0.005, "SFINCS v1_100m; land = ground above 0 m NAVD88; tan = CDL cropland; black = model dikes; tide only, no rain.",
             fontsize=7, color="#52514e")  # fmt: skip

    def frame(i):
        for im, z in zip(ims, zs):
            h = z[i][nn, mm] - dep
            h = np.where(land & np.isfinite(h) & (h > runs.THRESH), h, np.nan)
            im.set_data(coarsen(h, F, np.nanmax))
        vline.set_xdata([times[sel[i]]] * 2)
        stamp.set_text(f"{ev.name}: {times[sel[i]]:%Y-%m-%d %H:%M} UTC")
        return [*ims, vline, stamp]

    import warnings

    warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN blocks in nanmax
    out = config.REPORTS / "figs" / f"anim_{a.event}_{a.runs[0]}_vs_{a.runs[1]}.gif"
    FuncAnimation(fig, frame, frames=len(sel), blit=False).save(out, writer=PillowWriter(fps=a.fps), dpi=100)
    print(f"wrote {out} ({len(sel)} frames, station {st_name})")


if __name__ == "__main__":
    main()
