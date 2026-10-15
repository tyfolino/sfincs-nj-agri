"""First look at the Sandy panel: did crop fields that Sandy flooded change course after 2012,
compared with fields of the same height that stayed dry? Descriptive only (no model fits):
the econ colleague does the estimation.

Fields (data/analysis/sandy_panel/, scripts/build_sandy_panel.py): LU/LC farm in 2012, ground
< 1.5 m above MHHW, at least half CDL cropland on average over 2008-12, with a Sandy value.
Groups:
  flooded     the model floods >= fieldflood.SHARE of the field (sandy_share)
  MOTF only   the model leaves it dry but FEMA's dike-blind MOTF footprint floods >= SHARE
  dry         dry in both
The comparison groups are reweighted to the flooded group's height distribution (0.25 m bins
of m_above_mhhw), so the lines compare fields at the same height. Fields weigh by area.

Per outcome (CDL group shares; cropland; grass = hay + pasture + idle; vegetation = wetland
+ forest/shrub) and year: the area-weighted mean minus the group's own 2008-12 mean. The table
gives the 2013-16 and 2017-25 means of that change, and flooded minus dry with a 95% interval
from resampling fields (500 draws).

Writes reports/sandy_panel.md and reports/figs/sandy_panel.png.
Usage:  python scripts/plot_sandy_panel.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from agri_sfincs import config, fieldflood  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

PANEL = config.ANALYSIS_DIR / "sandy_panel"
PRE, EARLY, LATE = range(2008, 2013), range(2013, 2017), range(2017, 2026)
MAX_H, BIN = 1.5, 0.25
OUTCOMES = {
    "cropland": ["cropland"],
    "corn": ["share_corn"],
    "soybeans": ["share_soybeans"],
    "grass (hay + pasture + idle)": ["share_hay", "share_pasture", "share_idle"],
    "vegetation (wetland + forest/shrub)": ["share_herb_wetland", "share_woody_wetland", "share_forest_shrub"],
}
GROUPS = ["flooded", "MOTF only", "dry"]
COLORS = {"flooded": "#1f5fa8", "MOTF only": "#d08a1f", "dry": "#666666"}
N_BOOT = 500


def load() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    f = pd.read_csv(PANEL / "fields.csv").set_index("field_id")
    fy = pd.read_csv(PANEL / "field_year.csv")
    years = sorted(fy.year.unique())
    y = {k: sum(fy.pivot(index="field_id", columns="year", values=c) for c in cols).reindex(columns=years)
         for k, cols in OUTCOMES.items()}  # fmt: skip
    pre_crop = y["cropland"][list(PRE)].mean(axis=1)
    keep = (f.m_above_mhhw < MAX_H) & (pre_crop.reindex(f.index) >= 0.5) & f.sandy_share.notna()
    f = f[keep].copy()
    flooded = f.sandy_share >= fieldflood.SHARE
    motf = (f.sandy_share == 0) & (f.motf_share >= fieldflood.SHARE)
    dry = (f.sandy_share == 0) & (f.motf_share.fillna(0) < fieldflood.SHARE)
    f["group"] = np.select([flooded, motf, dry], GROUPS, default="")
    f = f[f.group != ""]
    # reweight each group to the flooded group's area per height bin
    f["bin"] = np.floor(f.m_above_mhhw / BIN).astype(int)
    target = f[f.group == "flooded"].groupby("bin").ha.sum()
    target = target / target.sum()
    f["w"] = f.ha
    for g in GROUPS[1:]:
        m = f.group == g
        have = f[m].groupby("bin").ha.sum()
        scale = (target / (have / have.sum())).reindex(f.loc[m, "bin"]).fillna(0).values
        f.loc[m, "w"] = f.loc[m, "ha"] * scale
    return f, {k: v.loc[f.index] for k, v in y.items()}


def change(v: pd.DataFrame, w: pd.Series) -> pd.Series:
    """Weighted mean per year minus the weighted 2008-12 mean."""
    m = v.mul(w, axis=0).sum() / w.sum()
    return m - m[list(PRE)].mean()


def main() -> None:
    f, y = load()
    rng = np.random.default_rng(0)
    rows, curves = [], {}
    for k, v in y.items():
        cg = {g: change(v[f.group == g], f.w[f.group == g]) for g in GROUPS}
        curves[k] = cg
        diffs = {p: [] for p in ("early", "late")}
        fl, dr = f.index[f.group == "flooded"], f.index[f.group == "dry"]
        for _ in range(N_BOOT):
            a, b = rng.choice(fl, len(fl)), rng.choice(dr, len(dr))
            d = change(v.loc[a], f.w.loc[a]) - change(v.loc[b], f.w.loc[b])
            diffs["early"].append(d[list(EARLY)].mean())
            diffs["late"].append(d[list(LATE)].mean())
        r = {"outcome": k}
        for g in GROUPS:
            r[f"{g}, 2013-16"] = 100 * cg[g][list(EARLY)].mean()
            r[f"{g}, 2017-25"] = 100 * cg[g][list(LATE)].mean()
        for p, lab in (("early", "2013-16"), ("late", "2017-25")):
            d = cg["flooded"] - cg["dry"]
            lo, hi = np.percentile(diffs[p], [2.5, 97.5])
            r[f"flooded - dry, {lab}"] = (f"{100 * d[list(EARLY if p == 'early' else LATE)].mean():+.1f} "
                                          f"[{100 * lo:+.1f}, {100 * hi:+.1f}]")  # fmt: skip
        rows.append(r)
    t = pd.DataFrame(rows).set_index("outcome")

    fig, axes = plt.subplots(1, len(OUTCOMES), figsize=(4.2 * len(OUTCOMES), 3.6), sharex=True)
    for ax, (k, cg) in zip(axes, curves.items()):
        for g in GROUPS:
            ax.plot(cg[g].index, 100 * cg[g].values, color=COLORS[g], lw=2 if g == "flooded" else 1.4, label=g)
        ax.axvline(2012.5, color="k", lw=0.8, ls="--")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_title(k, fontsize=10)
        ax.set_xticks([2008, 2012, 2016, 2020, 2024])
        ax.set_ylabel("change from own 2008-12 mean, % of area")
    axes[0].legend(fontsize=8, loc="lower left")
    fig.suptitle("Crop fields < 1.5 m above high tide: Sandy-flooded vs same-height dry fields (CDL)", fontsize=11)
    fig.tight_layout()
    fig.savefig(config.REPORTS / "figs" / "sandy_panel.png", dpi=130)
    plt.close(fig)

    n = f.groupby("group").agg(fields=("ha", "size"), ha=("ha", "sum"), median_m_above_mhhw=("m_above_mhhw", "median"))
    lines = [
        "# Sandy panel: a first look (descriptive)",
        "",
        "Written by `scripts/plot_sandy_panel.py` from `data/analysis/sandy_panel/` (docstring: groups, "
        "weights). No model fits.",
        "",
        "![Sandy panel](figs/sandy_panel.png)",
        "",
        "Fields: LU/LC farm in 2012, < 1.5 m above MHHW, at least half cropland over 2008-12. "
        f"Flooded = the model floods at least {fieldflood.SHARE:.0%} of the field; MOTF only = the model "
        "leaves it dry but FEMA's dike-blind bathtub floods it; dry = dry in both. Dry and MOTF-only "
        "fields are reweighted to the flooded fields' height mix.",
        "",
        md_table(n.round(2), floatfmt="{:,.2f}"),
        "",
        "Change from each group's own 2008-12 mean, percentage points of field area; flooded - dry "
        f"with a 95% interval from resampling fields ({N_BOOT} draws):",
        "",
        md_table(t.round(1), floatfmt="{:+.1f}"),
        "",
        "CDL 2012 is the summer BEFORE Sandy (Oct 29): a gap already open in 2012 is not Sandy's doing.",
        "",
        "Caveats: CDL class definitions jump between years (pasture 2% of field area in 2012 vs 15% "
        "in 2013; idle ~0 from 2016; cropland and developed in 2024), which moves every group; only "
        "the gap between groups is informative. Sandy flooding is modelled with today's dikes. Fields "
        "within a farm are not independent, so the intervals are too narrow if anything.",
        "",
    ]
    out = config.REPORTS / "sandy_panel.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
