"""First look with every modelled spring storm tide (FINDINGS §35, §37): in the season a storm
floods a crop field, does its crop mix differ from flood-prone fields the same storm missed?
Descriptive only (no model fits): the econ colleague does the estimation.

Fields: the low crop fields (agri_sfincs.panel.low_crop_fields) minus the chronic ones (flooded
by the highest ordinary tides of the month: a storm adds nothing there). Exposure: data/analysis/storm_panel/
(scripts/build_storm_panel.py). Land use: data/analysis/sandy_panel/field_year.csv.

Per spring storm (CDL year Y):
  flooded     spring_tide = 1 in Y (tide only; the rain variant uses spring_rain)
  prone-dry   flooded by at least one modelled storm, but not this one   (main comparison)
  never       flooded by none of the modelled storm tides                 (second comparison)
Both comparisons are reweighted to the flooded group's area per height bin
(agri_sfincs.panel.height_weights). Outcome per field: its share in Y minus its own mean over
the QUIET years within +-QUIET_WINDOW of Y (no modelled storm of either season: QUIET), leaving
out the outcome year itself, so the 2010-12 run of floods does not sit in the baseline. Estimate = flooded - comparison, area
weighted, in percentage points; 95% interval from Poisson-weight resampling of fields (N_BOOT).
"All" = the plain mean of the storms (each storm counts once). k = +1 repeats it for Y + 1.

Three yes/no outcomes per field, same comparison (agri_sfincs.panel.switched / left_cropland):
  main crop changed   the field's largest class (CLASSES) differs from the year before
  left cropland       >= 50% cropland the year before, < 50% that year and the next
  left farmland       the same on cropland + pasture (agri_sfincs.panel.farmland)
Outcome years from CDL_CHANGE on are left out of these: CDL's 2024 product change shows as
a drop in cropland on every low field (FINDINGS §37). The two left outcomes also drop CDL_CHANGE - 1, whose
flag reads the next year's map.

The storm tides outside the planting season (Jul - Feb) get the same test, by the first CDL year that can respond
(off_season(); estimates_off.csv and storm_panel_off.md).

Writes reports/storm_panel.md, reports/figs/storm_panel.png and data/analysis/storm_panel/estimates.csv
(every estimate in the report, one row each) and sensitivity.csv (the checks the report and bundle
README quote: before CDL_CHANGE, every field counted once, never-flooded cropland without one storm).
``--tag T`` reads sandy_panel_T/ and storm_panel_T/
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
OUTCOMES, EVENTS = panel.OUTCOMES, panel.EVENTS
CLASSES, CDL_CHANGE = panel.CLASSES, panel.CDL_CHANGE
QUIET_WINDOW = panel.QUIET_WINDOW
N_BOOT = 500
BLUE = "#2a78d6"
INK, MUTED = "#222222", "#6b6b6b"


def load(keep_chronic: bool = False):
    """agri_sfincs.panel.load on this build's folders."""
    return panel.load(SANDY, STORM, keep_chronic)


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
                                     "eff_flooded": panel.effective_n(w_t), "eff_comparison": panel.effective_n(w_c),
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


def sensitivity(f, y, sp, spring, quiet) -> pd.DataFrame:
    """Tide-only pooled checks (docstring), one row each: check, comparison, k, outcome, storms, pp, lo, hi."""
    rows = []

    def add(check, comp, k, o, e, n):
        rows.append({"check": check, "comparison": comp, "k": k, "outcome": o, "storms": n, "pp": e[0],
                     "lo": np.percentile(e[1:], 2.5), "hi": np.percentile(e[1:], 97.5)})  # fmt: skip

    before = [t for t in quiet if t < CDL_CHANGE]
    for comp in ("prone-dry", "never"):
        for k in (0, 1):
            for o in OUTCOMES:
                add("before change", comp, k, o, pooled(f, y, sp, spring, before, o, comp, k, CDL_CHANGE),
                    sum(1 for t in spring if t + k < CDL_CHANGE))  # fmt: skip
    equal = f.assign(ha=1.0)
    for comp in ("prone-dry", "never"):
        for k in (0, 1):
            for o in y:
                add("every field once", comp, k, o, pooled(equal, y, sp, spring, quiet, o, comp, k), np.nan)
    o = "cropland"
    for comp in ("prone-dry", "never"):
        for k in (0, 1):
            add("before change, every field once", comp, k, o, pooled(equal, y, sp, spring, before, o, comp, k, CDL_CHANGE),
                sum(1 for t in spring if t + k < CDL_CHANGE))  # fmt: skip
    kept = [t for t in spring if t + 1 < CDL_CHANGE]
    for drop in kept:
        rest = {t: n for t, n in spring.items() if t != drop}
        add(f"before change, without {drop}", "never", 1, o, pooled(f, y, sp, rest, before, o, "never", 1, CDL_CHANGE), len(kept) - 1)
    return pd.DataFrame(rows)


def text_ci(d: pd.DataFrame) -> pd.Series:
    return d.apply(lambda x: f"{x.pp:+.1f} [{x.lo:+.1f}, {x.hi:+.1f}]", axis=1)


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
    prone, fl, cp, before, before_t = f.n_storms_tide > 0, [], [], {}, {}
    for year in spring:
        t = sp["tide"][year] == 1
        c = prone & ~t
        fl.append(f.n_storms_tide[t].mean())
        cp.append(f.n_storms_tide[c].mean())
        before[year] = 100 * off[year][c].mean()
        before_t[year] = 100 * off[year][t].mean()
    return {"flooded": (min(fl), max(fl)), "comparison": (min(cp), max(cp)), "before": before,
            "before_flooded": before_t}  # fmt: skip


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
    sens = sensitivity(f, y, sp, spring, quiet)
    sens.round(3).to_csv(STORM / "sensitivity.csv", index=False)
    report(pd.concat([r, rc]), f, f.n_storms_tide > 0, spring, quiet, fc, chronic_gap(fc, yc["cropland"]),
           quiet_rates(f, y, quiet), sens, baseline_check(f, y, sp, spring, quiet), history(f, sp, spring))  # fmt: skip
    off_season(f, y, spring, quiet)


def off_season(f, y, spring, quiet) -> None:
    """The same test for the storm tides OUTSIDE the planting season (Jul - Feb, 2026-11-06, FINDINGS §72): per
    CDL year t, flooded = off_tide (a modelled storm of Jul (t-1) - Feb (t) floods the field, before t's
    planting; build_storm_panel.py), against prone-dry / never as compare(). k = 0 is the first season that
    can respond. 2012 (Irene + Jun 2012) and 2024 (Jan 2024 + spring) also hold a spring storm, so the
    pooled rows are given with and without them. Writes STORM/estimates_off.csv and storm_panel_off<TAG>.md."""
    fs = pd.read_csv(STORM / "field_season.csv")
    osp = {k: fs.pivot(index="field_id", columns="year", values=f"off_{k}").reindex(f.index) for k in ("tide", "rain")}
    ev = pd.read_csv(SANDY / "field_event.csv", usecols=["event", "peak", "first_cdl_year"]).drop_duplicates()
    ev = ev[~pd.to_datetime(ev.peak).dt.month.between(3, 6) & ev.first_cdl_year.isin(y["corn"].columns)]
    off = {int(t): "+".join(sorted(g.event.unique())) for t, g in ev.groupby("first_cdl_year")}
    mixed = [t for t in off if t in spring]
    ro = compare(f, y, osp, off, quiet, kinds=("tide",))
    rx = compare(f, y, osp, {t: s for t, s in off.items() if t not in mixed}, quiet, kinds=("tide",))
    rx = rx[rx.storm == "all"].assign(storm=f"all without {', '.join(map(str, mixed))}")
    r = pd.concat([ro, rx])
    r.round(3).to_csv(STORM / "estimates_off.csv", index=False)

    def ci(d):
        return d.apply(lambda x: f"{x.pp:+.1f} [{x.lo:+.1f}, {x.hi:+.1f}]", axis=1)

    keep = list(OUTCOMES) + ["left cropland", "left farmland"]
    tabs = []
    for comp in ("prone-dry", "never"):
        for k in (0, 1):
            d = r[(r.comparison == comp) & (r.k == k) & r.outcome.isin(keep)]
            t = d.assign(v=ci(d)).pivot(index="storm", columns="outcome", values="v")
            order = [off[x] for x in off if off[x] in t.index] + [x for x in t.index if x.startswith("all")]
            n = d.drop_duplicates("storm").set_index("storm").n_flooded.reindex(order)
            t = t.loc[order, [c for c in keep if c in t.columns]]
            t.insert(0, "fields flooded", n.map(lambda x: "" if pd.isna(x) else f"{x:.0f}"))
            tabs.append(f"### vs {comp}, k = {k}\n\n{md_table(t)}")
    cells = r[(r.storm.isin(off.values())) & (r.comparison == "prone-dry") & r.outcome.isin(keep)]
    n_ex, n_c = int(((cells.lo > 0) | (cells.hi < 0)).sum()), len(cells)
    years = "; ".join(f"{t}: {s}" for t, s in off.items())
    md = f"""# Storm panel, the storm tides outside the planting season

Generated by `plot_storm_panel.py{' --tag ' + TAG[1:] if TAG else ''}` (FINDINGS §72). The planting-season test (`storm_panel{TAG}.md`) used
the {len(spring)} spring storm years only. Here: every modelled storm tide of July to February, grouped by the first CDL
year whose planting can respond ({years}). Flooded = a storm of that off-season floods the field (tide only,
>= 10% > 5 cm); comparison = flood-prone fields it missed ("prone-dry") or fields no storm tide floods ("never"),
weighted to the same heights; each field against its own quiet years ({', '.join(map(str, quiet))}). k = 0 the first
season after the storm, k = 1 the one after. Percentage points of field area (shares) or of the chance (yes/no), with
95% intervals from resampling fields. {', '.join(map(str, mixed))} also hold a planting-season storm, so "all without"
leaves them out. Yes/no outcomes from {CDL_CHANGE} on are blank (CDL's product change), and {CDL_CHANGE - 1} for the two
left outcomes. Per-storm-year results vs prone-dry excluding zero: {n_ex} of {n_c} (about {0.05 * n_c:.1f} by chance).

""" + "\n\n".join(tabs) + "\n"
    out = config.REPORTS / f"storm_panel_off{TAG}.md"
    out.write_text(md)
    print(md)


def figure(r: pd.DataFrame, spring: dict) -> None:
    labels = [f"{s.replace('storm', '')[:4]} {s.replace('storm', '')[4:]}" for s in spring.values()] + [f"all {len(spring)}"]
    order = list(spring.values()) + ["all"]
    fig, axes = plt.subplots(1, len(OUTCOMES), figsize=(12, 4.2), sharey=True, sharex=True)
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
           fc: pd.DataFrame, gap: pd.DataFrame, rates: dict, sens: pd.DataFrame, bc: dict, hist: dict) -> None:  # fmt: skip
    def ci(d):
        return d.apply(lambda x: f"{x.pp:+.1f} [{x.lo:+.1f}, {x.hi:+.1f}]", axis=1)

    main_ = r[(r["flooded by"] == "tide") & (r.comparison == "prone-dry") & (r.k == 0)]
    order = list(spring.values()) + ["all"]
    t1 = main_.assign(v=ci(main_)).pivot(index="storm", columns="outcome", values="v").loc[order, list(OUTCOMES)]
    cells = main_[(main_.storm != "all") & main_.outcome.isin(OUTCOMES)]
    n_excl, n_cells = int(((cells.lo > 0) | (cells.hi < 0)).sum()), len(cells)
    nn = main_.drop_duplicates("storm").set_index("storm")[["n_flooded", "eff_flooded", "n_comparison", "eff_comparison"]]
    nn = nn.reindex(t1.index).map(lambda x: "" if pd.isna(x) else f"{x:.0f}")
    t1 = nn.join(t1)
    alt = r[r.storm == "all"].assign(v=ci(r[r.storm == "all"]))
    t2 = alt.pivot_table(index=["flooded by", "comparison", "k"], columns="outcome", values="v", aggfunc="first")[list(OUTCOMES)]
    t3 = alt.pivot_table(index=["flooded by", "comparison", "k"], columns="outcome", values="v", aggfunc="first")[EVENTS]
    in_pool = r[(r.storm != "all") & (r["flooded by"] == "tide") & (r.comparison == "prone-dry")]
    n_storms = {(e, k): in_pool[(in_pool.outcome == e) & (in_pool.k == k)].storm.nunique() for e in EVENTS for k in (0, 1)}
    sens = sens.assign(v=text_ci(sens))
    p = sens[sens.check == "before change"].pivot(index=["comparison", "k"], columns="outcome", values="v")
    pre = p.loc[["prone-dry", "never"], list(OUTCOMES)]
    e_ = sens[(sens.check == "every field once") & (sens.comparison == "prone-dry")]
    eq = e_.assign(col=e_.k.map(lambda k: f"k = {k}")).pivot(index="outcome", columns="col", values="v").loc[list(r[r.storm == "all"].outcome.drop_duplicates())]
    nc = sens[(sens.comparison == "never") & (sens.k == 1) & (sens.outcome == "cropland")].set_index("check").v
    drops = [c for c in nc.index if "without" in c]
    wo = "; ".join(f"without {c.rsplit(' ', 1)[1]}, {nc[c]}" for c in drops)
    n_before = int(sens[(sens.check == "before change, every field once") & (sens.comparison == "never") & (sens.k == 1)].storms.iloc[0])
    eff = in_pool[(in_pool.k == 0) & (in_pool.outcome == "corn")]
    eff_nv = r[(r.storm != "all") & (r["flooded by"] == "tide") & (r.comparison == "never") & (r.k == 0) & (r.outcome == "corn")]
    n_tides = pd.read_csv(SANDY / "field_event.csv").groupby(["event", "peak"]).ngroups
    all_tides = fc.chronic & (fc.n_storms_tide == n_tides)
    gap_early = gap.loc["flood-prone", [2008, 2009, 2010]].mean()
    gap_late = gap.loc["flood-prone", list(range(2015, CDL_CHANGE))].mean()
    all_rows = r[(r.storm == "all") & (r["flooded by"] == "tide") & (r.k == 0)].set_index(["comparison", "outcome"]).pp
    tilt = {o: (all_rows[("prone-dry", o)], all_rows[("prone-dry, incl. chronic", o)]) for o in ("corn", "soybeans")}
    before = ", ".join(f"{t}: {p:.0f}%" for t, p in hist["before"].items())
    before_t = ", ".join(f"{t}: {p:.0f}%" for t, p in hist["before_flooded"].items())
    never_rain = int(((~prone) & (f.n_storms_rain > 0)).sum())
    mc = r[(r["flooded by"] == "tide") & (r.comparison == "prone-dry") & (r.k == 0) & (r.outcome == "main crop changed")]
    mc_all, mc_storms = mc[mc.storm == "all"].iloc[0], mc[mc.storm != "all"]
    all_never = r[(r.storm == "all") & (r["flooded by"] == "tide") & (r.comparison == "never") & (r.k == 1)
                  & (r.outcome == "cropland")].iloc[0]  # fmt: skip
    left = r[(r.storm == "all") & (r["flooded by"] == "tide") & (r.comparison == "prone-dry") & (r.outcome == "left cropland")]
    left = {int(x.k): f"{x.pp:+.1f} [{x.lo:+.1f}, {x.hi:+.1f}]" for x in left.itertuples()}
    lf = r[(r.storm == "all") & (r["flooded by"] == "tide") & (r.comparison == "prone-dry") & (r.outcome == "left farmland")]
    left_f = {int(x.k): f"{x.pp:+.1f} [{x.lo:+.1f}, {x.hi:+.1f}]" for x in lf.itertuples()}
    nv_eq = sens[(sens.check == "every field once") & (sens.comparison == "never") & (sens.k == 1)].set_index("outcome")
    eq_nv = {o: f"{nv_eq.pp[o]:+.1f} [{nv_eq.lo[o]:+.2f}, {nv_eq.hi[o]:+.1f}]" for o in ("left cropland", "left farmland")}
    next_storm = sum(1 for t in spring if t + 1 in spring)
    base = ", ".join(f"{e} {r:.0f}%" for e, r in rates.items())
    md = f"""# Storm panel: crop mix in the season a spring storm tide floods a field

Generated by `plot_storm_panel.py` (for reference only: it needs our private package). Descriptive;
no regression.

**Flooded** means at least 10% of the field under more than 5 cm in the flood model. Runs use rebuilt
creek channels, NOAA gauge water levels, and wind: a 3 km analysis from 2016, and before that a coarser
reanalysis scaled up 30% that still reads low at storm peaks. So the 2010-14 and 2022-24 storms are not
forced alike. Peak water was compared with creek gauges only for 2018-25, so the 2010-14 storms are
unchecked on this version. Where checked, peaks are mostly within 0.2 m (usually high near Bivalve, low
in the Alloway), which matters on flat fields. More fields flood than on the earlier version: on a
one-month ordinary-tide test the rise was mostly the new bay water levels, with some from the rebuilt
creeks, and much of its size in field counts comes from fields just crossing the 10% line.

**Fields:** {len(f):,} low crop fields (farmed in NJDEP's 2012 land-use map, < {panel.MAX_H} m above average
higher high tide, at least half cropland 2008-12), not flooded by the highest ordinary tides of the month in the model.
On the storm tide alone, {int(prone.sum())} are flooded by at least one of the {n_tides} modelled storm tides;
{int((~prone).sum())} by none. These are map polygons, not farms: most are small, and the estimates are
weighted by area, so a few large fields count for much.

**Comparison:** in each spring-storm year, the fields that storm floods (storm tide alone) against
"prone-dry" fields, which flood in other modelled storm tides but not this one, weighted to the
same mix of field heights. Each field's share is measured against its own mean in nearby quiet
years ({', '.join(map(str, quiet))}; within {QUIET_WINDOW} years, never the outcome year itself). A quiet year has no modelled spring storm and no
flood from the July before through February: autumn or late-summer storms after that year's
planting do not count against it. Numbers are percentage points of field area, flooded minus
comparison, with 95% intervals from resampling fields. Crop-share signs flip between storms. In the
per-storm table, {n_excl} of {n_cells} storm-and-crop results exclude zero, against about {0.05 * n_cells:.1f} expected by chance
(results are not independent; no formal test).

![storm panel](figs/storm_panel{TAG}.png)

## Same season, per storm (tide only, vs prone-dry)

`eff_` columns are the effective number of fields once area weights are counted (Kish): a few large
fields carry each group, so the groups behave as far fewer fields than their counts.

{md_table(t1)}

## All {len(spring)} storms, the variants

k = 0: the season of the storm; k = 1: the next season. "never" = fields no modelled storm tide
floods on its own (weighted to the same heights; {never_rain} of these {int((~prone).sum())} flood when rain is counted).
"rain" = flooded counting the storm's rain. "incl. chronic" = the
{int(fc.chronic.sum())} fields wet on the highest ordinary tides of the month put back ({int(all_tides.sum())} of them flood in all {n_tides} storm tides, so
they are almost always in the flooded group).

{md_table(t2)}

Next-season cropland against never-flooded fields is {all_never.pp:+.1f} [{all_never.lo:+.1f}, {all_never.hi:+.1f}]. We have not explained this, and it
is not a stable number. USDA changed how it makes the crop map in {CDL_CHANGE}. With {CDL_CHANGE} and later removed from both
outcomes and baselines (table below; tide only; {n_before} storms) it is {nc["before change"]}, or
{nc["before change, every field once"]} counting every field once. The 7-storm and {n_before}-storm figures are different pools that happen to
agree. Leaving one storm out of the {n_before}: {wo}. Against prone-dry fields it spans zero.

{md_table(pre)}

The {len(spring)}-storm rows above keep {CDL_CHANGE}-on baseline years for the 2022-24 storms, and the {CDL_CHANGE} storm cannot avoid
straddling the change, so this table is the safer reading of those rows.

**Every field counted once** instead of by area (still matched on height; flooded - prone-dry, tide only):

{md_table(eq)}

Some differences grow when every field counts equally, and same-season grass and main crop changed then
exclude zero, so the area-weighted result rests partly on a few large fields.

## Yes/no per field: did it change crop, did it leave cropland?

Same comparison, with a yes/no outcome per field instead of a share: **main crop changed** (the
field's largest land use differs from the year before), **left cropland** (at least half
cropland the year before, under half that year and the next) and **left farmland** (the same on
cropland + pasture). Numbers are percentage points of
the chance, flooded minus comparison. Outcome years from {CDL_CHANGE} on are left out (USDA's crop-map
change), and {CDL_CHANGE - 1} too for the two left outcomes, whose flag reads the next year's map. Pooled rows use, for k = 0
and k = 1, {n_storms[(EVENTS[0], 0)]} and {n_storms[(EVENTS[0], 1)]} storms (main crop changed), {n_storms[(EVENTS[1], 0)]} and {n_storms[(EVENTS[1], 1)]} (left cropland).
Usual yearly rates on the flood-prone fields in quiet years: {base}.

{md_table(t3)}

Left cropland is {left[0]} the same season and {left[1]} the next; left farmland {left_f[0]} and {left_f[1]}, by area against
flood-prone comparison fields. Neither flag means the field stopped farming (over half of flags come back). With every field
counted once, next-season exits against never-flooded fields read slightly higher: left cropland {eq_nv["left cropland"]}, left
farmland {eq_nv["left farmland"]} (`sensitivity.csv`). Among many rows, two barely excluding zero is weak evidence, but they sit
beside the next-season cropland gap. Not a finding.

## The chronic fields over time

The {int(fc.chronic.sum())} low crop fields where the model puts the highest ordinary tides of the month on at least 10% of the field in
one simulated month (October 2024 with wind, today's dikes) are left out above. This may be partly a
model artefact: they are small, and on the older version many were a couple of wet days on the low part
of a marsh-edge field, where a 100 m model cannot see berms or ditches. The group grew from 100 to {int(fc.chronic.sum())}
with this model version. Whether storms caused their wetness is untested. Their cropland, minus other
fields reweighted to the same heights (percentage points of field area, by CDL year):

{md_table(gap.round(0), '{:+.0f}')}

Against flood-prone fields the gap averages {gap_early:+.0f} in 2008-10 and {gap_late:+.0f} in 2015-{CDL_CHANGE - 1}.
Against never-flooded fields it widens at 2019 (cause unclear: CDL, weather or the 2018 storms) and at
USDA's 2024 change in the crop map, which hit wet low ground hardest; earlier years are noisy.

Put back into the storm comparison (rows "incl. chronic" above), they move the pooled same-season
result on corn from {tilt["corn"][0]:+.1f} to {tilt["corn"][1]:+.1f} and on soybeans from {tilt["soybeans"][0]:+.1f} to {tilt["soybeans"][1]:+.1f} percentage points. {int(all_tides.sum())} of them flood
in every storm tide and so sit in the flooded group of every storm, so this is partly one group's
storm years against its quiet years, not seven tests. This cannot say WHY: the model has today's banks for every
year, and the chronic fields sit lower on average than the comparison fields.

## Caveats

- **Not detectable is not "no effect".** "Flooded" is a model result, noisy field by field, which
  pulls differences toward zero. Against satellite water on this version (3 Landsat and 4 Sentinel-2
  scenes), on low fields in the three informative cool-season scenes (April 2011, January and March
  2024) the model's wet area is 5-7 times what the satellites see, and they confirm
  only 4-11% of it; field by field at the 10% line few agree. Satellites miss water under crops and
  water that has drained, so this is not an error rate, but the field flags are not observed floods. CDL is USDA's satellite estimate of the crop, noisy
  on small fields; it does not measure yield or salt damage.
- **The model moves surface water only:** no salt, groundwater, crop or marsh processes, so "flooded"
  does not mean salt damage. Gate sizes are assumed (no public inventory).
- **The groups differ in more than this year's flood.** Flooded groups are repeat-flood fields: on
  average they flood in {hist["flooded"][0]:.0f}-{hist["flooded"][1]:.0f} of the {n_tides} storm tides, the comparison fields in {hist["comparison"][0]:.0f}-{hist["comparison"][1]:.0f}. The
  quiet-year baseline removes their usual crop mix, not a different trend.
- **"Missed" means missed by this storm.** Share flooded in the months before, comparison fields: {before}.
  Flooded fields: {before_t}. So 2012 and 2024 partly test the earlier storm, and 2022's comparison
  fields had nearly all just flooded. {next_storm} of {len(spring)} storms have another spring storm the next season, so
  "next season" is not recovery from one flood.
- **Selection.** Fields must be at least half cropland in 2008-12, a window holding the 2010-12 storms,
  so fields that left early are screened out.
- **CDL year = the summer crop.** March-April storms come before or during planting; early-June storms
  (2012, 2023) during or after it (dates approximate, not checked against local crop calendars).
- **Unmodelled storms.** Storms are picked from our Ship John series, gauge plus estimates where it was
  out (2008-09, 2021); heights are uncertain by about 0.1 m. Storm tides below {panel.STORM_MIN} m are not modelled, and the
  quiet years 2015, 2017, 2020 and 2025 hold tides of 1.61-1.64 m. A tide just above the line (March 2010)
  floods a quarter of the flood-prone fields, so these may be wet too. Quiet 2008 may be one as well: the
  gauge stops at the crest of May 12, when other bay gauges read higher than in March 2010.
- **"Main crop changed" is not a finding yet.** It reads higher on flooded fields in {int((mc_storms.pp > 0).sum())} of {len(mc_storms)} storms, {mc_all.pp:+.0f}
  [{mc_all.lo:+.0f}, {mc_all.hi:+.0f}] by area ({eq.loc["main crop changed", "k = 0"]} if every field counts once), but it changes a lot with the
  2-4 baseline years each storm has. On the storms with both ({", ".join(map(str, bc["storms"]))}), it is {bc["even"]:+.0f} points against even
  quiet years and {bc["odd"]:+.0f} against odd ones, with some storms resting on one baseline year on a side; with no
  baseline, {bc["none"]:+.1f} over the storms before {CDL_CHANGE}. The same-season with-rain rows and two "never, incl. chronic" rows exclude
  zero, but "never" rows rest on as few effective fields as prone-dry rows ({eff_nv.eff_comparison.min():.0f}-{eff_nv.eff_comparison.max():.0f} vs {eff.eff_comparison.min():.0f}-{eff.eff_comparison.max():.0f} per storm), so lean on neither. Possibly rotation, and on the older
  version some of the switch was to CDL "wetland", perhaps standing water in that summer's image. The yearly
  rate also shifts between eras (higher up to 2015).
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
