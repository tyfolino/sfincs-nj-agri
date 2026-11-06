"""Two-panel figure for the write-up to the ag-econ colleagues, in the style of
scripts/plot_model_regions.py. NJ low crop fields (panel.low_crop_fields: < 1.5 m above MHHW, >= half
CDL cropland 2008-12); flooded = >= 10% of the field > 5 cm in a storm tide's run on today's ground
and dikes.

Left: build_storm_panel.py's pooled estimates (storm = "all": the 8 planting-season storm tides, tide
only, comparison = flood-prone fields the storm missed), storm season and next year, flooded minus
comparison, pp with 95% intervals (FINDINGS §53, §57).
Right: share out of farming in CDL 2023 (cropland + pasture below half), below 0.5 m and 0.5-1.5 m
above MHHW, by behind an NLD levee or not (FINDINGS §70, §71; per band in scripts/exit_counts.py).
The never-flooded comparison's one off-zero interval (next-year cropland, §53) is in the footnote,
read from the same table.
Writes reports/figs/flood_response_<tag>.png.

Usage:  python scripts/plot_flood_response.py [--tag m65]
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from agri_sfincs import config, panel  # noqa: E402

SAME, NEXT = "#2a78d6", "#eb6834"  # reference palette slots 1-2
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8d8c87", "#e4e3df"
EXPOSED, DIKED = "#c4471a", "#1c5cab"  # the dike map's orange / blue (plot_dike_dependence.py)
OUTCOMES = [("left farmland", "Left farming"), ("cropland", "Cropland share"), ("corn", "Corn share"),
            ("soybeans", "Soybean share")]  # fmt: skip
HEIGHTS = [(-np.inf, 0.5, "below 0.5 m"), (0.5, 1.5, "0.5-1.5 m")]


def out_2023(tag: str) -> pd.DataFrame:
    d = config.ANALYSIS_DIR / f"sandy_panel_{tag}"
    f = pd.read_csv(d / "fields.csv").set_index("field_id")
    fy = pd.read_csv(d / "field_year.csv")
    f = f[panel.low_crop_fields(f, fy)].copy()
    farm = fy.assign(fm=panel.farmland(fy)).pivot(index="field_id", columns="year", values="fm").reindex(f.index)
    f["out"] = farm[2023] < 0.5
    return f


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", default="m65")
    a = ap.parse_args()
    est = pd.read_csv(config.ANALYSIS_DIR / f"storm_panel_{a.tag}" / "estimates.csv")
    est = est[(est.storm == "all") & (est["flooded by"] == "tide")].set_index(["comparison", "k", "outcome"])
    nv = est.loc[("never", 1, "cropland")]
    f = out_2023(a.tag)

    fig = plt.figure(figsize=(8.4, 3.9), dpi=200)

    # left: change after a storm tide
    ax = fig.add_axes([0.15, 0.21, 0.37, 0.6])
    ys = np.arange(len(OUTCOMES))[::-1]
    for k, col, dy, lab in ((0, SAME, 0.14, "storm season"), (1, NEXT, -0.14, "next year")):
        for y, (o, _) in zip(ys, OUTCOMES):
            r = est.loc[("prone-dry", k, o)]
            ax.plot([r.lo, r.hi], [y + dy, y + dy], color=col, lw=2, solid_capstyle="round", zorder=3)
            ax.plot(r.pp, y + dy, "o", ms=5.5, color=col, mec="white", mew=1.1, zorder=4)
        ax.plot([], [], "o-", color=col, ms=5.5, lw=2, mec="white", label=lab)
    ax.axvline(0, color=INK2, lw=0.9, zorder=2)
    ax.set_yticks(ys, [lab for _, lab in OUTCOMES], fontsize=8, color=INK)
    ax.set_ylim(-0.6, len(OUTCOMES) - 0.4)
    ax.set_xlim(-8, 8)
    ax.set_xticks([-8, -4, 0, 4, 8])
    ax.tick_params(axis="x", labelsize=7.5, colors=INK2, length=0)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, lw=0.6, zorder=1)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("flooded − comparison fields, percentage points", fontsize=7.5, color=INK2)
    ax.legend(loc="lower left", bbox_to_anchor=(-0.03, 1.0), ncol=2, fontsize=7.5, frameon=False, handlelength=1.5)
    fig.text(0.02, 0.96, "After a planting-season storm tide", fontsize=10.5, color=INK, va="top", fontweight="bold")

    # right: out of farming in 2023 by height x levee
    bx = fig.add_axes([0.64, 0.21, 0.33, 0.6])
    ns = []
    for i, (lo, hi, lab) in enumerate(HEIGHTS):
        b = f[(f.m_above_mhhw >= lo) & (f.m_above_mhhw < hi)]
        for j, (lev, col) in enumerate(((False, EXPOSED), (True, DIKED))):
            g = b[b.behind_levee.astype(bool) == lev]
            v = 100 * g.out.mean()
            ns.append(len(g))
            x = i + (j - 0.5) * 0.34
            bx.bar(x, v, width=0.31, color=col, zorder=3)
            bx.text(x, v + 0.5, f"{v:.0f}%", ha="center", va="bottom", fontsize=8, color=INK)
    bx.set_xticks(range(len(HEIGHTS)), [h[2] for h in HEIGHTS], fontsize=8, color=INK)
    bx.tick_params(axis="x", length=0)
    bx.set_yticks([])
    bx.set_ylim(0, 25)
    for s in ("top", "right", "left"):
        bx.spines[s].set_visible(False)
    bx.spines["bottom"].set_color(INK2)
    bx.bar(0, 0, color=EXPOSED, label="no levee")
    bx.bar(0, 0, color=DIKED, label="behind a levee")
    bx.legend(loc="lower left", bbox_to_anchor=(-0.03, 1.0), ncol=2, fontsize=7.5, frameon=False, handlelength=1.2)
    bx.set_xlabel("ground height above normal high tide", fontsize=7.5, color=INK2)
    fig.text(0.6, 0.96, "Out of farming in 2023", fontsize=10.5, color=INK, va="top", fontweight="bold")

    fig.text(0.02, 0.055, "NJ crop fields < 1.5 m above normal high tide. Left: 8 planting-season storm tides, flooded "
             "fields vs flood-prone fields the storm missed, 95% intervals. Against never-flooded", fontsize=5.8,
             color=MUTED)  # fmt: skip
    fig.text(0.02, 0.025, f"fields, next-year cropland is {nv.pp:+.1f} [{nv.lo:+.1f}, {nv.hi:+.1f}], not stable across "
             f"storms. Right: one CDL year; fields per bar {', '.join(map(str, ns))}. Flooding modelled on today's ground "
             "and dikes.", fontsize=5.8,
             color=MUTED)  # fmt: skip
    out = config.REPORTS / "figs" / f"flood_response_{a.tag}.png"
    fig.savefig(out, facecolor="white")
    print(out)


if __name__ == "__main__":
    main()
