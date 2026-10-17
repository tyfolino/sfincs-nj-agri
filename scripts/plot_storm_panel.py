"""First look with every modelled spring storm tide (FINDINGS §35, §37): in the season a storm
floods a crop field, does its crop mix differ from flood-prone fields the same storm missed?
Descriptive only (no model fits): the econ colleague does the estimation.

Fields: the low crop fields (agri_sfincs.panel.low_crop_fields) minus the chronic ones (flooded
by ordinary spring tides: a storm adds nothing there). Exposure: data/analysis/storm_panel/
(scripts/build_storm_panel.py). Land use: data/analysis/sandy_panel/field_year.csv.

Per spring storm (CDL year Y):
  flooded     spring_tide = 1 in Y (tide only; the rain variant uses spring_rain)
  prone-dry   flooded by at least one modelled storm, but not this one   (main comparison)
  never       flooded by none of the 12 modelled storms                   (second comparison)
Both comparisons are reweighted to the flooded group's area per height bin
(agri_sfincs.panel.height_weights). Outcome per field: its share in Y minus its own mean over
the QUIET years within +-QUIET_WINDOW of Y (no modelled storm of either season: QUIET), so the
2010-12 run of floods does not sit in the baseline. Estimate = flooded - comparison, area
weighted, in percentage points; 95% interval from Poisson-weight resampling of fields (N_BOOT).
"All" = the plain mean of the storms (each storm counts once). k = +1 repeats it for Y + 1.

Two yes/no outcomes per field, same comparison (agri_sfincs.panel.switched / left_cropland):
  main crop changed   the field's largest class (CLASSES) differs from the year before
  left cropland       >= 50% cropland the year before, < 50% that year and the next
Outcome years from CDL_CHANGE on are left out of these two: CDL's 2024 product change shows as
a drop in cropland on every low field (FINDINGS §37).

Writes reports/storm_panel.md, reports/figs/storm_panel.png and data/analysis/storm_panel/estimates.csv
(every estimate in the report, one row each).
Usage:  python scripts/plot_storm_panel.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from agri_sfincs import config, panel  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

SANDY, STORM = config.ANALYSIS_DIR / "sandy_panel", config.ANALYSIS_DIR / "storm_panel"
OUTCOMES = {
    "corn": ["share_corn"],
    "soybeans": ["share_soybeans"],
    "cropland": ["cropland"],
    "grass (hay + pasture + idle)": ["share_hay", "share_pasture", "share_idle"],
}
EVENTS = ["main crop changed", "left cropland"]
CLASSES = ["share_corn", "share_soybeans", "share_other_grains", "share_hay", "share_idle", "share_other_crops",
           "share_pasture", "share_herb_wetland", "share_woody_wetland", "share_forest_shrub", "share_developed",
           "share_water", "share_other"]  # fmt: skip
CDL_CHANGE = 2024
QUIET_WINDOW = 5
N_BOOT = 500
BLUE = "#2a78d6"
INK, MUTED = "#222222", "#6b6b6b"


def load(keep_chronic: bool = False):
    f = pd.read_csv(SANDY / "fields.csv").set_index("field_id")
    fy = pd.read_csv(SANDY / "field_year.csv")
    fs = pd.read_csv(STORM / "field_season.csv")
    fl = pd.read_csv(STORM / "fields_storm.csv").set_index("field_id")
    keep = panel.low_crop_fields(f, fy)
    if not keep_chronic:
        keep &= fl.chronic.reindex(f.index) == 0
    f = f[keep].join(fl)
    years = sorted(fy.year.unique())
    y = {k: sum(fy.pivot(index="field_id", columns="year", values=c) for c in cols).reindex(index=f.index, columns=years)
         for k, cols in OUTCOMES.items()}  # fmt: skip
    main = fy.assign(main=fy[CLASSES].idxmax(axis=1)).pivot(index="field_id", columns="year", values="main")
    main = main.reindex(index=f.index, columns=years)
    late = [t for t in years if t >= CDL_CHANGE]
    y["main crop changed"] = panel.switched(main)
    y["left cropland"] = panel.left_cropland(y["cropland"])
    for e in EVENTS:
        y[e][late] = np.nan
    yr = fs.groupby("year").agg(storm=("spring_storm", "first"), off=("off_tide", "max"))
    quiet = [t for t in years if not isinstance(yr.storm[t], str) and yr.off[t] == 0]
    spring = {t: s for t, s in yr.storm.items() if isinstance(s, str)}
    sp = {k: fs.pivot(index="field_id", columns="year", values=f"spring_{k}").reindex(f.index) for k in ("tide", "rain")}
    return f, y, sp, spring, quiet


def deviations(v: pd.DataFrame, year: int, quiet: list[int], k: int) -> pd.Series:
    """Each field's share in year + k minus its mean over the quiet years near ``year``."""
    base = [t for t in quiet if abs(t - year) <= QUIET_WINDOW]
    return v[year + k] - v[base].mean(axis=1)


def estimate(d: pd.Series, w_t: pd.Series, w_c: pd.Series, boot: np.ndarray) -> np.ndarray:
    """Flooded - comparison weighted means for the point (column 0) and each bootstrap draw."""
    ok = d.notna().values
    dv, wt, wc = d.fillna(0).values, w_t.values * ok, w_c.values * ok
    W = np.column_stack([np.ones(len(dv)), boot])  # field x draw
    return 100 * ((dv * wt) @ W / (wt @ W) - (dv * wc) @ W / (wc @ W))


def compare(f, y, sp, spring, quiet, kinds=("tide", "rain"), comps=("prone-dry", "never")) -> pd.DataFrame:
    """Per storm and pooled ("all") flooded - comparison estimates (docstring)."""
    rng = np.random.default_rng(0)
    boot = rng.poisson(1.0, size=(len(f), N_BOOT)).astype(float)
    prone = f.n_storms_tide > 0
    rows, draws = [], {}
    for kind in kinds:
        for comp in comps:
            for year, storm in spring.items():
                t = sp[kind][year] == 1
                c = (prone & ~t) if comp == "prone-dry" else ~prone & ~t
                w = panel.height_weights(f.m_above_mhhw, f.ha, t, c)
                w_t, w_c = w.where(t, 0.0), w.where(c, 0.0)
                for k in (0, 1):
                    if year + k not in y["corn"].columns:
                        continue
                    for name, v in y.items():
                        if v[year + k].isna().all():
                            continue
                        e = estimate(deviations(v, year, quiet, k), w_t, w_c, boot)
                        draws[(kind, comp, k, name, storm)] = e
                        rows.append({"flooded by": kind, "comparison": comp, "k": k, "outcome": name, "storm": storm,
                                     "year": year, "n_flooded": int(t.sum()), "n_comparison": int(c.sum()),
                                     "pp": e[0], "lo": np.percentile(e[1:], 2.5), "hi": np.percentile(e[1:], 97.5)})  # fmt: skip
            for k in (0, 1):
                for name in y:
                    ds = [draws[(kind, comp, k, name, s)] for s in spring.values() if (kind, comp, k, name, s) in draws]
                    if not ds:
                        continue
                    e = np.mean(ds, axis=0)
                    rows.append({"flooded by": kind, "comparison": comp, "k": k, "outcome": name, "storm": "all",
                                 "year": np.nan, "n_flooded": np.nan, "n_comparison": np.nan, "pp": e[0],
                                 "lo": np.percentile(e[1:], 2.5), "hi": np.percentile(e[1:], 97.5)})  # fmt: skip
    return pd.DataFrame(rows)


def quiet_rates(f: pd.DataFrame, y: dict, quiet: list[int]) -> dict:
    """Area-weighted yearly rate (%) of each yes/no outcome on the flood-prone fields in quiet years."""
    m = f.n_storms_tide > 0
    out = {}
    for e in EVENTS:
        v = y[e].loc[m, [t for t in quiet if t < CDL_CHANGE]]
        w = pd.DataFrame(np.repeat(f.ha[m].values[:, None], v.shape[1], axis=1), index=v.index, columns=v.columns)
        out[e] = 100 * (v * w).sum().sum() / w.where(v.notna()).sum().sum()
    return out


def chronic_gap(f: pd.DataFrame, cropland: pd.DataFrame) -> pd.DataFrame:
    """Cropland (pp) of the chronic fields minus each comparison group, per CDL year, the
    comparison reweighted to the chronic fields' height mix."""
    ch = f.chronic == 1
    groups = {"flood-prone": (f.n_storms_tide > 0) & ~ch, "never flooded": f.n_storms_tide == 0}
    out = {}
    for name, c in groups.items():
        w = panel.height_weights(f.m_above_mhhw, f.ha, ch, c)
        mean = lambda m: cropland[m].mul(w[m], axis=0).sum() / w[m].sum()  # noqa: E731
        out[name] = 100 * (mean(ch) - mean(c))
    return pd.DataFrame(out).T.rename_axis("chronic minus")


def main() -> None:
    f, y, sp, spring, quiet = load()
    r = compare(f, y, sp, spring, quiet)
    fc, yc, spc, _, _ = load(keep_chronic=True)
    rc = compare(fc, yc, spc, spring, quiet, kinds=("tide",))
    rc = rc[rc.storm == "all"].assign(comparison=lambda d: d.comparison + ", incl. chronic")
    figure(r[(r["flooded by"] == "tide") & (r.comparison == "prone-dry") & (r.k == 0)], spring)
    pd.concat([r, rc]).round(3).to_csv(STORM / "estimates.csv", index=False)
    report(pd.concat([r, rc]), f, f.n_storms_tide > 0, spring, quiet, fc, chronic_gap(fc, yc["cropland"]),
           quiet_rates(f, y, quiet))  # fmt: skip


def figure(r: pd.DataFrame, spring: dict) -> None:
    labels = [f"{s.replace('storm', '')[:4]} {s.replace('storm', '')[4:]}" for s in spring.values()] + ["all 7"]
    order = list(spring.values()) + ["all"]
    fig, axes = plt.subplots(1, len(OUTCOMES), figsize=(12, 4.2), sharey=True)
    for ax, name in zip(axes, OUTCOMES):
        d = r[r.outcome == name].set_index("storm").loc[order]
        yy = np.arange(len(order))[::-1]
        for i, (s, row) in enumerate(d.iterrows()):
            pooled = s == "all"
            ax.plot([row.lo, row.hi], [yy[i]] * 2, color=BLUE, lw=2, solid_capstyle="round")
            ax.plot(row.pp, yy[i], "o", ms=9 if pooled else 7, color=BLUE if pooled else "white",
                    mec=BLUE, mew=2, zorder=3)  # fmt: skip
        ax.axvline(0, color=MUTED, lw=0.8)
        ax.axhline(0.5, color="#dddddd", lw=0.8)
        ax.set_title(name, fontsize=10, color=INK)
        ax.set_xlabel("flooded − prone-dry, pp", fontsize=9, color=MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)
        for sp_ in ("top", "right"):
            ax.spines[sp_].set_visible(False)
        ax.grid(axis="x", color="#eeeeee", lw=0.6)
    axes[0].set_yticks(np.arange(len(order))[::-1], labels, fontsize=9, color=INK)
    fig.suptitle("Crop mix in the season a spring storm tide floods a low crop field, vs flood-prone fields it missed "
                 "(same height mix; 95% intervals)", fontsize=10, color=INK)  # fmt: skip
    fig.tight_layout()
    out = config.REPORTS / "figs" / "storm_panel.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def report(r: pd.DataFrame, f: pd.DataFrame, prone: pd.Series, spring: dict, quiet: list[int],
           fc: pd.DataFrame, gap: pd.DataFrame, rates: dict) -> None:  # fmt: skip
    def ci(d):
        return d.apply(lambda x: f"{x.pp:+.1f} [{x.lo:+.1f}, {x.hi:+.1f}]", axis=1)

    main_ = r[(r["flooded by"] == "tide") & (r.comparison == "prone-dry") & (r.k == 0)]
    order = list(spring.values()) + ["all"]
    t1 = main_.assign(v=ci(main_)).pivot(index="storm", columns="outcome", values="v").loc[order, list(OUTCOMES)]
    nn = main_.drop_duplicates("storm").set_index("storm")[["n_flooded", "n_comparison"]].reindex(t1.index)
    t1 = nn.astype("Int64").astype(str).replace("<NA>", "").join(t1)
    alt = r[r.storm == "all"].assign(v=ci(r[r.storm == "all"]))
    t2 = alt.pivot_table(index=["flooded by", "comparison", "k"], columns="outcome", values="v", aggfunc="first")[list(OUTCOMES)]
    t3 = alt.pivot_table(index=["flooded by", "comparison", "k"], columns="outcome", values="v", aggfunc="first")[EVENTS]
    n_storms = {k: sum(1 for t in spring if t + k < CDL_CHANGE) for k in (0, 1)}
    base = ", ".join(f"{e} {r:.0f}%" for e, r in rates.items())
    md = f"""# Storm panel: crop mix in the season a spring storm tide floods a field

Generated by `scripts/plot_storm_panel.py` (FINDINGS §37). Descriptive; no model fits.

**Fields:** {len(f):,} low crop fields (LU/LC farm 2012, < {panel.MAX_H} m above MHHW, at least half cropland
2008-12), not flooded by ordinary spring tides. {int(prone.sum())} are flooded by at least one of the 12
modelled storm tides; {int((~prone).sum())} by none.

**Comparison:** in each spring-storm year, the fields that storm floods (tide only) against
flood-prone fields it missed, reweighted to the same height mix. Each field's share is
measured against its own mean in nearby quiet years (no modelled storm: {', '.join(map(str, quiet))};
within {QUIET_WINDOW} years). Numbers are percentage points of field area, flooded minus
comparison, with 95% intervals from resampling fields.

![storm panel](figs/storm_panel.png)

## Same season, per storm (tide only, vs prone-dry)

{md_table(t1)}

## All 7 storms, the variants

k = 0: the season of the storm; k = 1: the next season. "never" = fields no modelled storm
floods (height-reweighted). "rain" = flooded counting the storm's rain. "incl. chronic" = the
{int(fc.chronic.sum())} fields wet on ordinary spring tides put back ({int((fc.chronic & (fc.n_storms_tide == 12)).sum())} of them flood in all 12 storms, so
they are almost always in the flooded group).

{md_table(t2)}

## Yes/no per field: did it change crop, did it leave cropland?

Same comparison, with a yes/no outcome per field instead of a share: **main crop changed** (the
field's largest land use differs from the year before) and **left cropland** (at least half
cropland the year before, under half that year and the next). Numbers are percentage points of
the chance, flooded minus comparison. Outcome years from {CDL_CHANGE} on are left out (CDL's
product change), so the pooled rows use {n_storms[0]} storms for k = 0 and {n_storms[1]} for k = 1.
Usual yearly rates on the flood-prone fields in quiet years: {base}.

{md_table(t3)}

## The chronic fields over time

The {int(fc.chronic.sum())} low crop fields that ordinary monthly spring tides flood TODAY (October 2024, dikes as
they stand now) are left out above: a storm adds little to a field wet every month. But some
may be wet every month BECAUSE earlier storms wore their banks down. Their cropland, minus
other fields at the same heights (pp of field area, by CDL year):

{md_table(gap.round(0), '{:+.0f}')}

Against flood-prone fields the gap widens from about −5 (2008-10) to about −9 by 2015 and then
holds; much of the widening shows in 2012 and 2014, both spring-storm years. Against
never-flooded fields it keeps growing, with steps at CDL's 2019 and 2024 product changes,
which hit wet low ground hardest.

Put back into the storm comparison (rows "incl. chronic" above), they tilt the pooled result
toward corn → soybeans (same season: corn −2.2, soybeans +3.1 pp). The same ~{int((fc.chronic & (fc.n_storms_tide == 12)).sum())} fields
sit in the flooded group of every storm, so this is one group's storm years against its quiet
years, not seven tests. This cannot say WHY: the model has today's banks for every
year, and the chronic fields are lower and more exposed than any comparison.

## Caveats

- **The groups differ in more than this year's flood.** Because footprints are nested (FINDINGS
  §35), fields a small storm floods are the most exposed ones, flooded in most other storms
  too. The quiet-year baseline removes their usual crop mix, not a different trend.
- **CDL year = the summer crop.** March-April storms come before planting; June storms
  (2012, 2023) after it, when CDL sees the crop already in the ground.
- **Unmodelled storms.** Springs of 1.60-1.67 m (2016, 2017, 2019, 2025) are not modelled and
  some quiet years follow unmodelled off-season storm tides (Isaias, August 2020, before 2021).
- **Dikes as they stand today**, for every year.
- Seven storms, a few hundred flooded fields each, mostly the SAME fields: the storms are not
  independent, and the "all" interval treats them as if they were (it is too narrow).
"""
    out = config.REPORTS / "storm_panel.md"
    out.write_text(md)
    print(md_table(t1))
    print(md_table(t2))
    print(md_table(t3))
    print(base)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
