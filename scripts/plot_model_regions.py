"""Overview map of the two SFINCS grids (NJ and Delaware) and the gauges they are checked against.

Water is each grid's own (WATER_RUNS: cells with bed at or below 0 m NAVD88); the census state shapes
hold the bay as land.

Shows each grid's outline (agri_sfincs.region.load_outline: the watershed ring plus its half of the
bay to the state line), the study counties, the USGS creek gauges the storm and tide checks score
(scripts/validate_storm_gauges.py GAUGES / DE_GAUGES), the NOAA CO-OPS bay gauges that drive
the boundary (domain.NOAA_STATIONS), and the stretch of each outline that is the driven bay boundary
(open_boundary: the grid's msk == 2 cells).
Writes reports/figs/model_regions.png.

Usage:  python scripts/plot_model_regions.py
"""

from __future__ import annotations

import geopandas as gpd
import matplotlib
import numpy as np
import xarray as xr

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from agri_sfincs import config, domain, region, runs  # noqa: E402

OUT = config.ROOT / "reports" / "figs" / "model_regions.png"
CRS = 32618
#: a run of each adopted grid whose map gives the water (bed < 0 m NAVD88; the bay and tidal creeks)
WATER_RUNS = {"nj": ("e3v2a30brm65_100m", "tide2024oct_intact_slr000_hrrr"),
              "de": ("de_v2ap45o_100m", "tide2024oct_intact_slr000_hrrr")}
HALO = [pe.withStroke(linewidth=2.2, foreground="white")]
#: the creek gauges scored by validate_storm_gauges.py and check_creek_tides.py (USGS, lon / lat
#: from data/gauges/usgs_series*.csv), label offset in points
CREEK = {
    "01412150": ("Bivalve", (6, -10)),
    "01413038": ("Greenwich", (6, 2)),
    "01483050": ("Hancocks Bridge", (6, 2)),
    "01483158": ("Odessa", (-6, 4)),
    "01484085": ("Bowers", (6, -2)),
    "01484080": ("Frederica", (-6, 2)),
    "01484235": ("Slaughter Beach", (-6, -4)),
}
NJ_COL, DE_COL = "#2a78d6", "#eb6834"  # reference palette slots 1-2
INK, INK2, LAND, WATER = "#0b0b0b", "#52514e", "#f4f4f2", "#bcd3e8"


def creek_gauges() -> gpd.GeoDataFrame:
    import pandas as pd
    t = pd.concat([pd.read_csv(config.DATA / "gauges" / f, dtype={"site": str})
                   for f in ("usgs_series.csv", "usgs_series_de.csv")])  # fmt: skip
    t = t[t.site.isin(CREEK)].drop_duplicates("site").set_index("site").loc[list(CREEK)]
    return gpd.GeoDataFrame({"name": [CREEK[s][0] for s in t.index], "off": [CREEK[s][1] for s in t.index]},
                            geometry=gpd.points_from_xy(t.lon, t.lat), crs=4326).to_crs(CRS)  # fmt: skip


def paint_water(ax, model: str, run: str) -> None:
    """The grid's cells with bed at or below 0 m NAVD88 (regular or quadtree map, runs.MapGrid)."""
    with xr.open_dataset(runs.resolve(f"{model}/{run}") / "sfincs_map.nc") as mp:
        g = runs.MapGrid.from_map(mp)
        zb, msk = g.as_grid(mp.zb.values), g.as_grid(mp.msk.values)
    w = np.where((np.nan_to_num(msk) > 0) & (zb <= 0.0), 1.0, np.nan)  # the mouth cells sit at exactly 0.0
    ext = (g.x0, g.x0 + g.m * g.dx, g.y0, g.y0 + g.n * g.dx)
    ax.imshow(w, origin="lower", extent=ext, cmap=matplotlib.colors.ListedColormap([WATER]), zorder=3.5,
              interpolation="nearest")  # fmt: skip


def open_boundary(model: str, run: str, outline: gpd.GeoDataFrame):
    """The stretch of the grid's outline where it is driven: the outline's edge within 150 m of an
    open-boundary cell (msk == 2, the bay water-level boundary)."""
    with xr.open_dataset(runs.resolve(f"{model}/{run}") / "sfincs_map.nc") as mp:
        g = runs.MapGrid.from_map(mp)
        msk = g.as_grid(mp.msk.values)
    jj, ii = np.nonzero(np.nan_to_num(msk) == 2)
    pts = gpd.GeoSeries(gpd.points_from_xy(g.x0 + (ii + 0.5) * g.dx, g.y0 + (jj + 0.5) * g.dx), crs=CRS)
    return outline.boundary.union_all().intersection(pts.buffer(150).union_all())


def main() -> None:
    nj, de = region.load_outline("nj").to_crs(CRS), region.load_outline("de").to_crs(CRS)
    states = region.load_states().to_crs(CRS)
    cty = region.load_counties().to_crs(CRS)
    x0, y0, x1, y1 = gpd.pd.concat([nj, de]).total_bounds
    pad = 6000
    ext = (x0 - pad, x1 + pad, y0 - pad, y1 + pad)

    fig, ax = plt.subplots(figsize=(6.6, 8.9), dpi=200)
    ax.set_facecolor(WATER)
    states.plot(ax=ax, color=LAND, edgecolor="#b9b8b3", lw=0.6, zorder=1)
    cty.boundary.plot(ax=ax, color="#d4d3ce", lw=0.4, zorder=2)
    for model, run in WATER_RUNS.values():
        paint_water(ax, model, run)
    for g, col in ((nj, NJ_COL), (de, DE_COL)):
        g.plot(ax=ax, color=col, alpha=0.16, lw=0, zorder=3)
        g.boundary.plot(ax=ax, color=col, lw=1.6, zorder=4)
    for (model, run), g in zip(WATER_RUNS.values(), (nj, de)):
        ob = gpd.GeoSeries([open_boundary(model, run, g)], crs=CRS)
        ob.plot(ax=ax, color="white", lw=3.0, zorder=4.5)
        ob.plot(ax=ax, color=INK, lw=1.3, linestyle=(0, (3, 2)), zorder=4.6)

    bay = gpd.GeoDataFrame(geometry=gpd.points_from_xy([s["lon"] for s in domain.NOAA_STATIONS],
                                                       [s["lat"] for s in domain.NOAA_STATIONS]), crs=4326).to_crs(CRS)  # fmt: skip
    ax.scatter(bay.geometry.x, bay.geometry.y, marker="^", s=46, facecolor="white", edgecolor=INK, lw=1.1, zorder=6)
    for s, p in zip(domain.NOAA_STATIONS, bay.geometry):
        if ext[0] < p.x < ext[1] and ext[2] < p.y < ext[3]:
            name = s["name"].replace(", NJ", "").replace(", DE", "").replace(", PA", "").replace(" Light", "")
            ax.annotate(name, (p.x, p.y), xytext=(6, -3), textcoords="offset points", fontsize=7, color=INK2, zorder=7,
                        path_effects=HALO)  # fmt: skip

    cg = creek_gauges()
    ax.scatter(cg.geometry.x, cg.geometry.y, s=40, color=INK, edgecolor="white", lw=1.0, zorder=8)
    for n, off, p in zip(cg.name, cg.off, cg.geometry):
        ax.annotate(n, (p.x, p.y), xytext=off, textcoords="offset points", fontsize=7.5, color=INK, zorder=9,
                    ha="right" if off[0] < 0 else "left", fontweight="bold", path_effects=HALO)  # fmt: skip

    for txt, (lo, la) in (("NEW JERSEY", (-75.12, 39.55)), ("DELAWARE", (-75.62, 39.08)),
                          ("Delaware Bay", (-75.24, 39.06))):  # fmt: skip
        p = gpd.GeoSeries(gpd.points_from_xy([lo], [la]), crs=4326).to_crs(CRS).iloc[0]
        bay_lbl = txt == "Delaware Bay"
        ax.text(p.x, p.y, txt, fontsize=8 if bay_lbl else 9, color="#4f6d8a" if bay_lbl else INK2, ha="center",
                style="italic" if bay_lbl else "normal", rotation=-48 if bay_lbl else 0, zorder=5,
                path_effects=HALO)  # fmt: skip

    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#b9b8b3")
    # 20 km scale bar, lower right
    sx, sy = ext[1] - 30000, ext[2] + 7000
    ax.plot([sx, sx + 20000], [sy, sy], color=INK, lw=2, solid_capstyle="butt", zorder=9)
    ax.text(sx + 10000, sy + 1500, "20 km", ha="center", fontsize=7, color=INK, zorder=9)

    handles = [Patch(facecolor=NJ_COL + "29", edgecolor=NJ_COL, lw=1.6, label="NJ model"),
               Patch(facecolor=DE_COL + "29", edgecolor=DE_COL, lw=1.6, label="Delaware model"),
               Line2D([], [], color=INK, lw=1.3, ls=(0, (3, 2)), label="Bay boundary: where the models are driven"),
               Line2D([], [], ls="", marker="o", ms=6.5, color=INK, mec="white", label="Creek gauge (USGS): model checked here"),
               Line2D([], [], ls="", marker="^", ms=7, mfc="white", mec=INK, label="Bay gauge (NOAA): sets the boundary water level")]  # fmt: skip
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=2, fontsize=7.5, frameon=False,
              columnspacing=1.6, handlelength=2.4)  # fmt: skip
    ax.set_title("The two flood models and their gauges", fontsize=11, color=INK, loc="left")
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor="white")
    print(OUT)


if __name__ == "__main__":
    main()
