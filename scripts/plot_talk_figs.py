"""Three dark ("cyberpunk", agri_sfincs.plotstyle) figures for talking the storm results over
with the ag-econ colleagues (FINDINGS §35, §37, §27). They redraw numbers made elsewhere:

1. talk_storm_footprint.png  the 12 storm tides flood one nested footprint: low crop field x
   storm, lit where the storm floods >= 10% of the field (tide only;
   data/analysis/sandy_panel/field_event.csv, the build_sandy_panel.py field set).
2. talk_crop_response.png    pooled same-season crop response to a spring storm, flooded minus
   flood-prone fields it missed; the marsh-edge fields wet on ordinary tides are left out
   (data/analysis/storm_panel/estimates.csv, scripts/plot_storm_panel.py).
3. talk_dike_slr.png         cropland flooded in an ordinary tide month with and without the
   dikes, by sea-level rise; the gap is what the dikes protect
   (data/analysis/scenario_cropland_tide2024oct.csv, scripts/plot_scenarios.py).

Writes reports/figs/talk_*.png.
Usage:  python scripts/plot_talk_figs.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

from agri_sfincs import config, domain, fieldflood, panel, plotstyle  # noqa: E402
from agri_sfincs.plotstyle import BG, CYAN, GRID, INK, MUTED, PINK  # noqa: E402

FIGS = config.REPORTS / "figs"
OUTCOMES = ["corn", "soybeans", "cropland", "grass (hay + pasture + idle)"]


def title(fig, head: str, sub: str) -> None:
    fig.text(0.012, 0.975, head, fontsize=15, fontweight="bold", color=INK, va="top")
    fig.text(0.012, 0.905, sub, fontsize=10, color=MUTED, va="top")


def footprint(mcp) -> None:
    f = pd.read_csv(config.ANALYSIS_DIR / "sandy_panel" / "fields.csv").set_index("field_id")
    fy = pd.read_csv(config.ANALYSIS_DIR / "sandy_panel" / "field_year.csv")
    f = f[panel.low_crop_fields(f, fy)]
    ev = pd.read_csv(config.ANALYSIS_DIR / "sandy_panel" / "field_event.csv")
    ev = ev[ev.field_id.isin(f.index)]
    w = ev.pivot(index="field_id", columns="event", values="tide_share").reindex(f.index).fillna(0) >= fieldflood.SHARE
    w = w[w.columns[np.argsort(-w.sum().values, kind="stable")]]  # biggest footprint on top
    hit = w[w.any(axis=1)]
    # fields: most storms first, then lexicographic on the storm order -> the staircase
    key = hit.astype(int).astype(str).agg("".join, axis=1)
    hit = hit.loc[sorted(hit.index, key=lambda i: (-hit.loc[i].sum(), [-int(c) for c in key[i]]))]
    v = hit.values
    nested = sum(r[: r.sum()].all() for r in v)

    with xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc") as ds:
        sj = ds["waterlevel"].sel(stations=domain.SHIP_JOHN).to_series()
    peaks = ev.groupby("event").peak.first()
    labels = [f"{'Sandy, ' if e == 'sandy2012' else ''}{pd.Timestamp(peaks[e]):%b %Y}  ·  {sj[pd.Timestamp(peaks[e])]:.2f} m"
              for e in hit.columns]  # fmt: skip

    fig, ax = plt.subplots(figsize=(12, 5.6))
    fig.subplots_adjust(left=0.17, right=0.98, top=0.8, bottom=0.12)
    ax.imshow(v.T, aspect="auto", interpolation="nearest", cmap=ListedColormap([BG, CYAN]))
    ax.set_yticks(range(len(labels)), labels, fontsize=9)
    s = list(hit.columns).index("sandy2012")
    ax.get_yticklabels()[s].set_color(PINK)
    ax.get_yticklabels()[s].set_fontweight("bold")
    ax.set_xticks([])
    ax.grid(False)
    ax.set_xlabel(f"{len(hit)} low crop fields that flood in at least one storm, most-flooded on the left "
                  f"({len(f) - len(hit)} more never flood)", color=MUTED, fontsize=9)  # fmt: skip
    ax.set_ylabel("storm tide (peak at Ship John Shoal)", color=MUTED, fontsize=9)
    title(fig, "12 storm tides, one footprint",
          f"Each column a field, lit where that storm floods it. {nested / len(hit):.0%} of flooded fields follow the "
          f"staircase:\na field flooded by k storms is flooded by the k biggest. Sandy (pink) floods nearly every "
          f"field the others do.")  # fmt: skip
    fig.savefig(FIGS / "talk_storm_footprint.png", dpi=170)
    plt.close(fig)


def crop_response(mcp) -> None:
    e = pd.read_csv(config.ANALYSIS_DIR / "storm_panel" / "estimates.csv")
    e = e[(e["flooded by"] == "tide") & (e.k == 0) & (e.storm == "all")].set_index(["comparison", "outcome"])
    d = e.loc["prone-dry"].loc[OUTCOMES]  # the marsh-edge fields wet on ordinary tides left out
    fig, ax = plt.subplots(figsize=(10, 5.6))
    fig.subplots_adjust(left=0.22, right=0.97, top=0.76, bottom=0.2)
    y = np.arange(len(OUTCOMES))[::-1]
    for yi, (_, r) in zip(y, d.iterrows()):
        ax.plot([r.lo, r.hi], [yi] * 2, color=CYAN, lw=2.5, alpha=0.85)
    ax.plot(d.pp, y, "o", color=CYAN, ms=9, ls="none", mec=BG, mew=1.5)
    mcp.make_lines_glow(ax)
    ax.axvline(0, color=INK, lw=1, alpha=0.6)
    ax.text(0, y[0] + 0.45, "no difference", color=INK, fontsize=9, ha="center", va="bottom",
            bbox={"facecolor": BG, "edgecolor": "none", "pad": 2})  # fmt: skip
    ax.set_ylim(y[-1] - 0.5, y[0] + 0.75)
    ax.set_yticks(y, ["corn", "soybeans", "all cropland", "hay, pasture, idle"], fontsize=11)
    ax.set_xlim(-7, 7)
    ax.set_xlabel("← less in flooded fields          difference, percentage points of field area          "
                  "more in flooded fields →", color=MUTED, fontsize=9)  # fmt: skip
    title(fig, "A spring storm flood did not change what fields grew that summer",
          "Share of each field in each land use in the storm year, flooded fields minus similar low fields the\n"
          "same storm missed (each measured against its own normal years). Dot: best estimate. Bar: 95% range.\n"
          "Every bar crosses zero: no detectable difference.")  # fmt: skip
    fig.text(0.012, 0.02, "943 low-lying crop fields, Salem / Cumberland / Gloucester; 7 spring storm tides 2010-2024 "
             "pooled; fields compared at the same height above high tide.", color=MUTED, fontsize=8)  # fmt: skip
    fig.savefig(FIGS / "talk_crop_response.png", dpi=170)
    plt.close(fig)


def dike_slr(mcp) -> None:
    t = pd.read_csv(config.ANALYSIS_DIR / "scenario_cropland_tide2024oct.csv")
    x = np.array([0.0, 0.3, 0.6, 1.0])
    assert len(t) == len(x), "scenario table rows are today, +0.3, +0.6, +1.0 m"
    wi, wo = t["floods with dikes (km²)"].values, t["floods without dikes (km²)"].values
    dep = t["dike-dependent (km²)"].values  # floods without the dikes but not with them
    fig, ax = plt.subplots(figsize=(10, 5.4))
    fig.subplots_adjust(left=0.09, right=0.8, top=0.78, bottom=0.15)
    ax.fill_between(x, wi, wo, color=PINK, alpha=0.18, lw=0)
    ax.plot(x, wo, "-o", color=PINK, lw=2.5, ms=7)
    ax.plot(x, wi, "-o", color=CYAN, lw=2.5, ms=7)
    mcp.make_lines_glow(ax)
    for xi, a, b, d in zip(x, wi, wo, dep):
        ax.text(xi + 0.015, (a + b) / 2, f"{d:.1f}", color=INK, fontsize=10, va="center")
    ax.text(x[-1] + 0.03, wo[-1] + 0.6, "without dikes", color=INK, fontsize=10, va="bottom")
    ax.text(x[-1] + 0.03, wi[-1] - 0.6, "with dikes", color=INK, fontsize=10, va="top")
    ax.fill_between([0.0, 0.06], [21.2] * 2, [22.6] * 2, color=PINK, alpha=0.18, lw=0)
    ax.text(0.08, 21.9, "shaded: cropland the dikes keep dry (km², labelled)", color=INK, fontsize=10, va="center")
    ax.set_xticks(x, ["today", "+0.3 m", "+0.6 m", "+1.0 m"])
    ax.set_xlim(-0.05, 1.18)
    ax.set_ylim(0, None)
    ax.set_xlabel("sea-level rise", color=MUTED, fontsize=9)
    ax.set_ylabel("cropland flooded, km²", color=MUTED, fontsize=9)
    title(fig, "Dikes matter most for the next 0.3 m of sea-level rise",
          "Cropland under water in an ordinary tide month (October 2024 tides, CDL 2024 cropland, three counties).\n"
          "The dikes keep 2.3 km² (230 ha) dry today and 5.4 km² at +0.3 m; by +1.0 m nearly all of it floods either way.")  # fmt: skip
    fig.text(0.012, 0.02, "Area actually under water, CDL cropland only. Counted as whole fields instead, 176 farm fields (about 1,100 ha) "
             "depend on their dikes today.\nDikes as modelled: lidar crests, one assumed check-valve gate per system "
             "(no gate inventory exists).", color=MUTED, fontsize=8)  # fmt: skip
    fig.savefig(FIGS / "talk_dike_slr.png", dpi=170)
    plt.close(fig)


def main() -> None:
    mcp = plotstyle.cyberpunk()
    plt.rcParams.update({"axes.facecolor": BG, "figure.facecolor": BG, "grid.color": GRID})
    footprint(mcp)
    crop_response(mcp)
    dike_slr(mcp)
    print(f"wrote {FIGS}/talk_{{storm_footprint,crop_response,dike_slr}}.png")


if __name__ == "__main__":
    main()
