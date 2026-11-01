"""First look with every modelled spring storm tide (FINDINGS §35, §37): in the season a storm
floods a crop field, does its crop mix differ from flood-prone fields the same storm missed?
Descriptive only (no model fits): the econ colleague does the estimation.

Fields: the low crop fields (agri_sfincs.panel.low_crop_fields) minus the chronic ones (flooded
by ordinary spring tides: a storm adds nothing there). Exposure: data/analysis/storm_panel/
(scripts/build_storm_panel.py). Land use: data/analysis/sandy_panel/field_year.csv.

Per spring storm (CDL year Y):
  flooded     spring_tide = 1 in Y (tide only; the rain variant uses spring_rain)
  prone-dry   flooded by at least one modelled storm, but not this one   (main comparison)
  never       flooded by none of the modelled storm tides                 (second comparison)
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
(every estimate in the report, one row each). ``--tag T`` reads sandy_panel_T/ and storm_panel_T/
and writes storm_panel_T.md / .png beside them, leaving the untagged build alone.
Usage:  python scripts/plot_storm_panel.py [--tag m65]
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from agri_sfincs import config, panel  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

SANDY, STORM = config.ANALYSIS_DIR / "sandy_panel", config.ANALYSIS_DIR / "storm_panel"
TAG = ""  # --tag, with its leading "_"
OUTCOMES = {
    "corn": ["share_corn"],
    "soybeans": ["share_soybeans"],
    "cropland": ["cropland"],
    "grass (hay + pasture + idle)": ["share_hay", "share_pasture", "share_idle"],
}
EVENTS = ["main crop changed", "left cropland"]
CLASSES, CDL_CHANGE = panel.CLASSES, panel.CDL_CHANGE
QUIET_WINDOW = panel.QUIET_WINDOW
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
                        e = panel.estimate(panel.deviations(v, year, quiet, k), w_t, w_c, boot)
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


def pooled(f, y, sp, spring, base, outcome: str, comp: str, k: int, last: int | None = None) -> np.ndarray | None:
    """Tide-only flooded - comparison ("prone-dry" / "never"), plain mean of the storms with an
    outcome year before ``last``, against the quiet years ``base`` (empty: no baseline):
    (point, then the resampled draws)."""
    boot = np.random.default_rng(0).poisson(1.0, size=(len(f), N_BOOT)).astype(float)
    prone = f.n_storms_tide > 0
    ds = []
    for year in spring:
        if last is not None and year + k >= last:
            continue
        t = sp["tide"][year] == 1
        c = (prone & ~t) if comp == "prone-dry" else ~prone & ~t
        w = panel.height_weights(f.m_above_mhhw, f.ha, t, c)
        d = panel.deviations(y[outcome], year, base, k) if base else y[outcome][year + k]
        if d.notna().any():
            ds.append(panel.estimate(d, w.where(t, 0.0), w.where(c, 0.0), boot))
    return np.nanmean(ds, axis=0) if ds else None


def pre_change_table(f, y, sp, spring, quiet) -> pd.DataFrame:
    """Crop shares pooled over outcome years before CDL_CHANGE, as text, per comparison and k."""
    rows = []
    for comp in ("prone-dry", "never"):
        for k in (0, 1):
            row = {"comparison": comp, "k": k}
            for o in ("corn", "soybeans", "cropland"):
                e = pooled(f, y, sp, spring, quiet, o, comp, k, CDL_CHANGE)
                row[o] = f"{e[0]:+.1f} [{np.percentile(e[1:], 2.5):+.1f}, {np.percentile(e[1:], 97.5):+.1f}]"
            rows.append(row)
    return pd.DataFrame(rows).set_index(["comparison", "k"])


def baseline_check(f, y, sp, spring, quiet) -> dict:
    """"main crop changed", same season, vs prone-dry, per baseline: the storms with BOTH an even
    and an odd quiet year in reach (so the two are like for like), and with no baseline."""
    o, pool = "main crop changed", [t for t in quiet if t < CDL_CHANGE]
    v = y[o]
    even, odd = [t for t in pool if t % 2 == 0 and v[t].notna().any()], [t for t in pool if t % 2 and v[t].notna().any()]
    both = {t: s for t, s in spring.items() if t < CDL_CHANGE and any(abs(q - t) <= QUIET_WINDOW for q in even)
            and any(abs(q - t) <= QUIET_WINDOW for q in odd)}  # fmt: skip
    return {"storms": sorted(both), "even": pooled(f, y, sp, both, even, o, "prone-dry", 0)[0],
            "odd": pooled(f, y, sp, both, odd, o, "prone-dry", 0)[0],
            "none": pooled(f, y, sp, spring, [], o, "prone-dry", 0, CDL_CHANGE)[0]}  # fmt: skip


def history(f, sp, spring) -> dict:
    """Per spring storm, fields' mean storm-tide count in the flooded and comparison groups, and
    the comparison's share (%) already flooded in the months before (off_tide)."""
    off = pd.read_csv(STORM / "field_season.csv", usecols=["field_id", "year", "off_tide"])
    off = off.pivot(index="field_id", columns="year", values="off_tide").reindex(f.index)
    prone, fl, cp, before = f.n_storms_tide > 0, [], [], {}
    for year in spring:
        t = sp["tide"][year] == 1
        c = prone & ~t
        fl.append(f.n_storms_tide[t].mean())
        cp.append(f.n_storms_tide[c].mean())
        before[year] = 100 * off[year][c].mean()
    return {"flooded": (min(fl), max(fl)), "comparison": (min(cp), max(cp)), "before": before}


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
    global SANDY, STORM, TAG
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", default="")
    tag = ap.parse_args().tag
    if tag:
        TAG = f"_{tag}"
        SANDY, STORM = SANDY.with_name(f"sandy_panel{TAG}"), STORM.with_name(f"storm_panel{TAG}")
    f, y, sp, spring, quiet = load()
    r = compare(f, y, sp, spring, quiet)
    fc, yc, spc, _, _ = load(keep_chronic=True)
    rc = compare(fc, yc, spc, spring, quiet, kinds=("tide",))
    rc = rc[rc.storm == "all"].assign(comparison=lambda d: d.comparison + ", incl. chronic")
    figure(r[(r["flooded by"] == "tide") & (r.comparison == "prone-dry") & (r.k == 0)], spring)
    pd.concat([r, rc]).round(3).to_csv(STORM / "estimates.csv", index=False)
    report(pd.concat([r, rc]), f, f.n_storms_tide > 0, spring, quiet, fc, chronic_gap(fc, yc["cropland"]),
           quiet_rates(f, y, quiet), pre_change_table(f, y, sp, spring, quiet),
           baseline_check(f, y, sp, spring, quiet), history(f, sp, spring))  # fmt: skip


def figure(r: pd.DataFrame, spring: dict) -> None:
    labels = [f"{s.replace('storm', '')[:4]} {s.replace('storm', '')[4:]}" for s in spring.values()] + [f"all {len(spring)}"]
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
        ax.set_xlabel("flooded − prone-dry, percentage points", fontsize=9, color=MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)
        for sp_ in ("top", "right"):
            ax.spines[sp_].set_visible(False)
        ax.grid(axis="x", color="#eeeeee", lw=0.6)
    axes[0].set_yticks(np.arange(len(order))[::-1], labels, fontsize=9, color=INK)
    fig.suptitle("Crop mix in the season a spring storm tide floods a low crop field, vs flood-prone fields it missed "
                 "(same height mix; 95% intervals)", fontsize=10, color=INK)  # fmt: skip
    fig.tight_layout()
    out = config.REPORTS / "figs" / f"storm_panel{TAG}.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def report(r: pd.DataFrame, f: pd.DataFrame, prone: pd.Series, spring: dict, quiet: list[int],
           fc: pd.DataFrame, gap: pd.DataFrame, rates: dict, pre: pd.DataFrame, bc: dict, hist: dict) -> None:  # fmt: skip
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
    n_tides = pd.read_csv(SANDY / "field_event.csv").groupby(["event", "peak"]).ngroups
    all_tides = fc.chronic & (fc.n_storms_tide == n_tides)
    gap_early = gap.loc["flood-prone", [2008, 2009, 2010]].mean()
    gap_late = gap.loc["flood-prone", list(range(2015, CDL_CHANGE))].mean()
    all_rows = r[(r.storm == "all") & (r["flooded by"] == "tide") & (r.k == 0)].set_index(["comparison", "outcome"]).pp
    tilt = {o: (all_rows[("prone-dry", o)], all_rows[("prone-dry, incl. chronic", o)]) for o in ("corn", "soybeans")}
    top = sorted(hist["before"].items(), key=lambda kv: -kv[1])[:2]
    before = " and ".join(f"{p:.0f}% in {t}" for t, p in top)
    next_storm = sum(1 for t in spring if t + 1 in spring)
    base = ", ".join(f"{e} {r:.0f}%" for e, r in rates.items())
    md = f"""# Storm panel: crop mix in the season a spring storm tide floods a field

Generated by `plot_storm_panel.py` (in `code/`, for reference: it needs our private package).
Descriptive; no regression.

**Fields:** {len(f):,} low crop fields (farmed in NJDEP's 2012 land-use map, < {panel.MAX_H} m above average
higher high tide, at least half cropland 2008-12), not flooded by ordinary spring tides in the model.
On the storm tide alone, {int(prone.sum())} are flooded by at least one of the {n_tides} modelled storm tides;
{int((~prone).sum())} by none. These are map polygons, not farms: most are small, and the estimates are
weighted by area, so a few large fields count for much.

**Comparison:** in each spring-storm year, the fields that storm floods (storm tide alone) against
"prone-dry" fields, which flood in other modelled storm tides but not this one, weighted to the
same mix of field heights. Each field's share is measured against its own mean in nearby quiet
years ({', '.join(map(str, quiet))}; within {QUIET_WINDOW} years). A quiet year has no modelled spring storm and no
flood from the July before through February: autumn or late-summer storms after that year's
planting do not count against it. Numbers are percentage points of field area, flooded minus
comparison, with 95% intervals from resampling fields. Signs flip between storms, and a few cells
excluding zero is about what chance gives.

![storm panel](figs/storm_panel{TAG}.png)

## Same season, per storm (tide only, vs prone-dry)

{md_table(t1)}

## All {len(spring)} storms, the variants

k = 0: the season of the storm; k = 1: the next season. "never" = fields no modelled storm tide
floods on its own (weighted to the same heights; some of them flood when rain is counted).
"rain" = flooded counting the storm's rain. "incl. chronic" = the
{int(fc.chronic.sum())} fields wet on ordinary spring tides put back ({int(all_tides.sum())} of them flood in all {n_tides} storm tides, so
they are almost always in the flooded group).

{md_table(t2)}

Next-season cropland against never-flooded fields excludes zero, but much of that is USDA's 2024
change in how it makes the crop map. Leaving out outcome years from {CDL_CHANGE} on (tide only):

{md_table(pre)}

## Yes/no per field: did it change crop, did it leave cropland?

Same comparison, with a yes/no outcome per field instead of a share: **main crop changed** (the
field's largest land use differs from the year before) and **left cropland** (at least half
cropland the year before, under half that year and the next). Numbers are percentage points of
the chance, flooded minus comparison. Outcome years from {CDL_CHANGE} on are left out (CDL's
product change), so the pooled rows use {n_storms[0]} storms for k = 0 and {n_storms[1]} for k = 1.
Usual yearly rates on the flood-prone fields in quiet years: {base}.

{md_table(t3)}

## The chronic fields over time

The {int(fc.chronic.sum())} low crop fields where the model puts ordinary spring tides on at least 10% of the field in
one simulated month (October 2024, today's dikes) are left out above. They are often small and at
the marsh edge, and the group grew from 100 to {int(fc.chronic.sum())} with this model version. Whether storms caused
their wetness is untested. Their cropland, minus other fields at the same heights (percentage
points of field area, by CDL year):

{md_table(gap.round(0), '{:+.0f}')}

Against flood-prone fields the gap averages {gap_early:+.0f} in 2008-10 and {gap_late:+.0f} in 2015-{CDL_CHANGE - 1}.
Against never-flooded fields it widens in steps: around 2011, at 2019 (cause unclear: CDL, weather
or the 2018 storms) and at USDA's 2024 change in the crop map, which hit wet low ground hardest.

Put back into the storm comparison (rows "incl. chronic" above), they move the pooled same-season
result on corn from {tilt["corn"][0]:+.1f} to {tilt["corn"][1]:+.1f} and on soybeans from {tilt["soybeans"][0]:+.1f} to {tilt["soybeans"][1]:+.1f} percentage points. {int(all_tides.sum())} of them flood
in every storm tide and so sit in the flooded group of every storm, so this is partly one group's
storm years against its quiet years, not seven tests. This cannot say WHY: the model has today's banks for every
year, and the chronic fields are lower and more exposed than any comparison.

## Caveats

- **Not detectable is not "no effect".** "Flooded" is a model result, noisy field by field, which
  pulls differences toward zero. Its flooded area has not been checked against satellite images on
  this version; on an older version Landsat confirmed only a small part of the model's water at
  overpass. CDL records what was grown, not yield or salt damage.
- **The model moves surface water only:** no salt, groundwater, crop or marsh processes, so "flooded"
  does not mean salt damage. Gate sizes are assumed (no public inventory).
- **The groups differ in more than this year's flood.** Flooded groups are repeat-flood fields: on
  average they flood in {hist["flooded"][0]:.0f}-{hist["flooded"][1]:.0f} of the {n_tides} storm tides, the comparison fields in {hist["comparison"][0]:.0f}-{hist["comparison"][1]:.0f}. The
  quiet-year baseline removes their usual crop mix, not a different trend.
- **"Missed" means missed by this storm.** Comparison fields had often flooded just before ({before}),
  and {next_storm} of {len(spring)} storms have another spring storm the next season, so "next season" is not recovery
  from one flood.
- **Selection.** Fields must be at least half cropland in 2008-12, a window holding the 2010-12 storms,
  so fields that left early are screened out.
- **CDL year = the summer crop.** March-April storms come before planting; June storms
  (2012, 2023) after it, when CDL sees the crop already in the ground.
- **Unmodelled storms.** Storm tides below {panel.STORM_MIN} m at Ship John are not modelled, and the quiet years
  2015, 2017, 2020 and 2025 hold tides of 1.61-1.64 m. A tide just above the line (March 2010) floods
  a quarter of the flood-prone fields, so these may be wet too.
- **"Main crop changed" is not settled.** On the storms that have both ({", ".join(map(str, bc["storms"]))}), it is {bc["even"]:+.0f} points
  against even quiet years and {bc["odd"]:+.0f} against odd ones; with no baseline, {bc["none"]:+.1f} over the
  storms before {CDL_CHANGE}. The with-rain rows exclude zero. Possibly rotation; the yearly rate also shifts
  between eras (higher up to 2015).
- **Dikes as they stand today in the model**, for every year: mapped from lidar, not surveyed.
- **Seven storms, mostly the SAME fields.** The "all" interval resamples fields and holds the seven
  storms fixed, so it leaves out year-to-year differences and may be too narrow.
"""
    out = config.REPORTS / f"storm_panel{TAG}.md"
    out.write_text(md)
    print(md_table(t1))
    print(md_table(t2))
    print(md_table(t3))
    print(base)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
