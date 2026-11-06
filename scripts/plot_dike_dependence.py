"""Compact NJ map of today's farm fields by how they flood on ordinary tides as the sea rises, in
the style of scripts/plot_model_regions.py (for write-ups to the ag-econ colleagues).

Reads data/analysis/field_flood_classes_<model><suffix>.gpkg (scripts/field_flood_classes.py: the
October 2024 tide month, dikes as built vs removed, sea level +0 / 0.3 / 0.6 / 1.0 m; a field floods
when > 10% of it is wetter than 5 cm; fields farmed in 2012 and 2020). Two ramps, darker = sooner:
  dike-dependent           floods with the dikes removed but not as built, first at that level
  floods even with dikes   floods as built, first at that level ("flooded today" = already at +0;
                           field_flood_classes' "overtopped" and "exposed" together)
Hectares are whole fields in each class (fieldflood.SHARE line), not flooded area.
Water is the model's own (maps.model_water), dikes its weir lines.
Writes reports/figs/dike_dependence_<model><suffix>.png.

Usage:  python scripts/plot_dike_dependence.py [--model e3v2a30brm65_100m] [--suffix _hrrr]
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from agri_sfincs import config, dikes, domain, fieldflood, maps, region, runs  # noqa: E402

CRS = 32618
LEVELS = ["today", "+0.3 m", "+0.6 m", "+1.0 m"]
#: darker = floods sooner (reference palette blue / orange ramps)
DIKE_RAMP = ["#0d366b", "#1c5cab", "#3f86de", "#8fb8ee"]
WITH_RAMP = ["#7f2704", "#c4471a", "#f08a4b", "#f8c39a"]
SAFE_COL, LAND, WATER, INK, INK2 = "#e2dccb", "#f4f4f2", "#cddbe6", "#0b0b0b", "#52514e"
HALO = [pe.withStroke(linewidth=2.2, foreground="white")]
PLACES = ["Paulsboro", "Penns Grove", "Pennsville", "Salem", "Hancocks Bridge", "Greenwich", "Bridgeton",
          "Fortescue", "Port Norris", "Mauricetown"]  # fmt: skip


def family_level(cls: str) -> tuple[str, int] | None:
    """field_flood_classes' class -> ("dike" | "with" | "safe", level index), None if outside the model."""
    if cls == "flooded today":
        return "with", 0
    if cls == fieldflood.SAFE:
        return "safe", -1
    for i, lv in enumerate(LEVELS):
        if cls == f"dike-dependent {lv}":
            return "dike", i
        if cls in (f"overtopped {lv}", f"exposed {lv}"):
            return "with", i
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="e3v2a30brm65_100m")
    ap.add_argument("--suffix", default="_hrrr", help="run-name ending of the class build (field_flood_classes.py)")
    a = ap.parse_args()
    tag = f"_{a.model}{a.suffix}"
    g = gpd.read_file(config.ANALYSIS_DIR / f"field_flood_classes{tag}.gpkg").to_crs(CRS)
    g = g[g.farmed2020.astype(bool)].copy()
    fl = g.cls.map(family_level)
    g = g[fl.notna()].copy()
    g["fam"], g["lvl"] = [f for f, _ in fl.dropna()], [lv for _, lv in fl.dropna()]
    g["col"] = [SAFE_COL if f == "safe" else (DIKE_RAMP if f == "dike" else WITH_RAMP)[lv] for f, lv in zip(g.fam, g.lvl)]
    ha = g.groupby(["fam", "lvl"]).ha.sum()

    hit = g[g.fam != "safe"]
    x0, y0, x1, y1 = hit.total_bounds
    pad = 2500
    ext = (x0 - pad, x1 + pad, y0 - pad, y1 + pad)

    fig = plt.figure(figsize=(6.6, 8.9), dpi=200)
    ax = fig.add_axes([0.02, 0.215, 0.96, 0.725])
    ax.set_facecolor(LAND)
    w, wext = maps.model_water(a.model, f"tide2024oct_intact_slr000{a.suffix}")
    ax.imshow(w, origin="lower", extent=wext, cmap=matplotlib.colors.ListedColormap([WATER]), zorder=1,
              interpolation="nearest")  # fmt: skip
    cty = region.load_counties().to_crs(CRS)
    cty[cty.fips.isin(domain.COUNTIES)].boundary.plot(ax=ax, color="#a9a8a3", lw=0.6, ls="--", zorder=2)
    g[g.fam == "safe"].plot(ax=ax, color=SAFE_COL, lw=0, zorder=3)
    hit.sort_values("lvl", ascending=False).plot(ax=ax, color=hit.sort_values("lvl", ascending=False).col, lw=0, zorder=4)
    for _, x, y, _ in dikes.read_weir(config.MODELS / a.model / "sfincs.weir"):
        ax.plot(x, y, color=INK, lw=0.6, zorder=5)

    px = gpd.GeoSeries(gpd.points_from_xy([domain.PLACES[p][0] for p in PLACES], [domain.PLACES[p][1] for p in PLACES]),
                       crs=4326).to_crs(CRS)  # fmt: skip
    for n, p in zip(PLACES, px):
        if ext[0] < p.x < ext[1] and ext[2] < p.y < ext[3]:
            ax.plot(p.x, p.y, "o", ms=2.6, color=INK, zorder=6)
            ax.annotate(n, (p.x, p.y), xytext=(4, 3), textcoords="offset points", fontsize=7, color=INK2, zorder=7,
                        path_effects=HALO)  # fmt: skip
    for txt, (lo, la), rot in (("Delaware Bay", (-75.36, 39.27), -38), ("Delaware River", (-75.53, 39.64), 58)):
        p = gpd.GeoSeries(gpd.points_from_xy([lo], [la]), crs=4326).to_crs(CRS).iloc[0]
        ax.text(p.x, p.y, txt, fontsize=8, color="#4f6d8a", style="italic", rotation=rot, ha="center", zorder=6,
                path_effects=HALO)  # fmt: skip
    for txt, (lo, la) in (("SALEM", (-75.33, 39.58)), ("CUMBERLAND", (-75.10, 39.36)), ("GLOUCESTER", (-75.18, 39.74))):
        p = gpd.GeoSeries(gpd.points_from_xy([lo], [la]), crs=4326).to_crs(CRS).iloc[0]
        if ext[0] < p.x < ext[1] and ext[2] < p.y < ext[3]:
            ax.text(p.x, p.y, txt, fontsize=7.5, color="#8d8c87", ha="center", zorder=6, path_effects=HALO)

    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#b9b8b3")
    sx, sy = ext[0] + 4000, ext[2] + 4000  # in the bay, lower left
    ax.plot([sx, sx + 10000], [sy, sy], color=INK, lw=2, solid_capstyle="butt", zorder=8)
    ax.text(sx + 5000, sy + 900, "10 km", ha="center", fontsize=7, color=INK, zorder=8, path_effects=HALO)
    fig.text(0.02, 0.975, "When NJ bayshore farm fields start to flood on ordinary tides", fontsize=11, color=INK,
             va="top")  # fmt: skip
    fig.text(0.02, 0.952, "October 2024 tides (no storm) with sea-level rise; farm fields of 2012 still farmed in 2020",
             fontsize=7.5, color=INK2, va="top")  # fmt: skip

    # legend: two ramps x four sea levels, hectares under each swatch; then the base layers; then a note
    lg = fig.add_axes([0.02, 0.01, 0.96, 0.19])
    lg.set_xlim(0, 10), lg.set_ylim(0, 6)
    lg.axis("off")
    for j, lv in enumerate(LEVELS):
        lg.text(3.6 + j * 1.6, 5.75, lv if lv == "today" else f"by {lv}", ha="center", va="top", fontsize=7.5, color=INK2)
    rows = (("dike", DIKE_RAMP, "Dike-dependent:\nfloods only if the dikes go"), ("with", WITH_RAMP, "Floods even\nwith the dikes"))
    for i, (fam, ramp, lab) in enumerate(rows):
        y = 4.45 - i * 1.75
        lg.text(0.05, y, lab, va="center", fontsize=7.5, color=INK)
        for j in range(4):
            lg.add_patch(plt.Rectangle((3.0 + j * 1.6, y - 0.35), 1.2, 0.7, color=ramp[j], lw=0))
            lg.text(3.6 + j * 1.6, y - 0.5, f"{ha.get((fam, j), 0):,.0f} ha", ha="center", va="top", fontsize=6.8,
                    color=INK2)  # fmt: skip
    lg.add_patch(plt.Rectangle((0.05, 0.85), 0.45, 0.6, color=SAFE_COL, lw=0))
    lg.text(0.62, 1.15, f"farm fields safe to +1.0 m ({ha.get(('safe', -1), 0):,.0f} ha)", va="center", fontsize=6.8,
            color=INK2)  # fmt: skip
    lg.plot([5.0, 5.45], [1.15, 1.15], color=INK, lw=0.8)
    lg.text(5.57, 1.15, "dike in the model", va="center", fontsize=6.8, color=INK2)
    lg.text(0.05, 0.1, "Hectares of whole fields; a field counts once > 10% of it is under > 5 cm of water at some "
            "point in the month. SFINCS NJ model.", fontsize=6.2, color="#8d8c87")  # fmt: skip

    out = config.REPORTS / "figs" / f"dike_dependence{tag}.png"
    fig.savefig(out, facecolor="white")
    print(out)
    print(pd.Series(ha).to_string())


if __name__ == "__main__":
    main()
