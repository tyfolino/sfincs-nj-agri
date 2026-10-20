"""Greenness after a spring storm tide (preliminary): in the summer after a spring storm floods a
low crop field, is the field less green (Landsat NDVI) than flood-prone fields the storm missed?
Descriptive only, same design as scripts/plot_storm_panel.py (FINDINGS §37) with NDVI as outcome.

Fields: the low crop fields (agri_sfincs.panel.low_crop_fields) minus the chronic ones, as in
plot_storm_panel.py, that match a Landsat field unit (data/landuse/field_units.gpkg, whose
per-scene means are data/landsat/field_scene_stats.parquet, scripts/landsat_field_stats.py):
the largest overlap, covering >= MATCH of both polygons; edge-only units are dropped.

Per field and year (CDL year = calendar year), from scenes where >= CLEAR of the field's
non-fill interior pixels are clear:
  peak      90th percentile of the June-September scene means
  jul-aug   mean of the July-August scene means
  month m   mean of the scene means in month m (April-October), for the seasonal curve
Comparison per spring storm (agri_sfincs.panel.deviations / estimate, height-reweighted):
flooded (spring_tide or spring_rain = 1; "deep" = spring_tide with peak depth >= DEEP_M) vs
prone-dry (flooded by another modelled storm, not this one) or never (no modelled storm); each
field against its own quiet years within panel.QUIET_WINDOW. Estimate in NDVI units; 95%
interval from Poisson-weight resampling of fields. Pooled ("all") = plain mean over the storms
with an estimate (a month with no clear scene for a storm year leaves that storm out).
Placebo: each storm's flooded / prone-dry split measured in each nearby QUIET year instead (that
year left out of the baseline). Its spread is the year-to-year noise between the two groups,
which the field resampling does not see; the pooled placebo picks one quiet year per storm.

Writes data/analysis/storm_panel/field_season_ndvi.csv (field x year: peak, jul_aug, n_summer),
data/analysis/storm_panel/ndvi_estimates.csv, reports/storm_ndvi.md, reports/figs/storm_ndvi.png.
Usage:  python scripts/storm_ndvi.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from agri_sfincs import config, panel  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

SANDY, STORM = config.ANALYSIS_DIR / "sandy_panel", config.ANALYSIS_DIR / "storm_panel"
SCENES = config.LANDSAT_DIR / "field_scene_stats.parquet"
MATCH, CLEAR = 0.8, 0.8
DEEP_M = 0.25  # m, about the top quarter of flooded fields
MONTHS = range(4, 11)
SUMMARY = ["peak", "jul_aug"]
N_BOOT, N_PLACEBO = 500, 2000
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED = "#222222", "#6b6b6b"


def load_fields():
    """Low non-chronic crop fields (as plot_storm_panel.load), exposure tables, storm and quiet years."""
    f = pd.read_csv(SANDY / "fields.csv").set_index("field_id")
    fy = pd.read_csv(SANDY / "field_year.csv")
    fs = pd.read_csv(STORM / "field_season.csv")
    fl = pd.read_csv(STORM / "fields_storm.csv").set_index("field_id")
    keep = panel.low_crop_fields(f, fy) & (fl.chronic.reindex(f.index) == 0)
    f = f[keep].join(fl)
    yr = fs.groupby("year").agg(storm=("spring_storm", "first"), off=("off_tide", "max"))
    quiet = [t for t in yr.index if not isinstance(yr.storm[t], str) and yr.off[t] == 0]
    spring = {t: s for t, s in yr.storm.items() if isinstance(s, str)}
    sp = {k: fs.pivot(index="field_id", columns="year", values=f"spring_{k}").reindex(f.index) for k in ("tide", "rain")}
    depth = fs.pivot(index="field_id", columns="year", values="spring_tide_maxd_m").reindex(f.index)
    sp["deep"] = ((sp["tide"] == 1) & (depth >= DEEP_M)).astype(int)
    return f, sp, spring, quiet


def match_units(fields: pd.Index) -> pd.Series:
    """field_id -> Landsat unit: largest overlap, >= MATCH of both polygons, not edge-only."""
    f = gpd.read_file(SANDY / "fields.gpkg")
    f = f[f.field_id.isin(fields)][["field_id", "geometry"]]
    u = gpd.read_file(config.LANDUSE_DIR / "field_units.gpkg")[["unit", "geometry"]]
    edge = pd.read_csv(config.LANDSAT_DIR / "edge_only_units.csv").iloc[:, 0]
    u = u[~u.unit.isin(edge)]
    f["fa"], u["ua"] = f.area, u.area
    ov = gpd.overlay(f, u, how="intersection", keep_geom_type=True)
    ov["oa"] = ov.area
    best = ov.sort_values("oa").groupby("field_id").tail(1)
    best = best[(best.oa >= MATCH * best.fa) & (best.oa >= MATCH * best.ua)]
    return best.set_index("field_id").unit


def ndvi_tables(unit: pd.Series, years: range) -> dict[str, pd.DataFrame]:
    """{outcome: field x year NDVI} for SUMMARY and each month (docstring)."""
    d = pd.read_parquet(SCENES, columns=["date", "unit", "n", "n_valid", "ndvi"],
                        filters=[("unit", "in", unit.unique().tolist())])  # fmt: skip
    d = d[(d.n >= CLEAR * d.n_valid) & d.ndvi.between(-1, 1) & d.date.dt.year.isin(years)]
    d = d.assign(year=d.date.dt.year, month=d.date.dt.month)
    by_unit = {}
    summer = d[d.month.between(6, 9)].groupby(["unit", "year"]).ndvi
    by_unit["peak"] = summer.quantile(0.9)
    by_unit["jul_aug"] = d[d.month.isin([7, 8])].groupby(["unit", "year"]).ndvi.mean()
    by_unit["n_summer"] = summer.size()
    for m in MONTHS:
        by_unit[f"m{m:02d}"] = d[d.month == m].groupby(["unit", "year"]).ndvi.mean()
    out = {}
    for k, s in by_unit.items():
        t = s.unstack("year").reindex(columns=list(years))
        out[k] = t.reindex(unit.values).set_axis(unit.index, axis=0)
    return out


def groups(f, sp, kind, comp, year):
    """Flooded and comparison masks and their height weights; the comparison never holds a field
    this storm flooded (for "deep": flooded at any depth)."""
    t = sp[kind][year] == 1
    wet = sp["tide" if kind == "deep" else kind][year] == 1
    prone = f.n_storms_tide > 0
    c = (prone & ~wet) if comp == "prone-dry" else ~prone & ~wet
    w = panel.height_weights(f.m_above_mhhw, f.ha, t, c)
    return t, c, w.where(t, 0.0), w.where(c, 0.0)


def compare(f, y, sp, spring, quiet, boot) -> pd.DataFrame:
    rows, draws = [], {}
    for kind in ("tide", "rain", "deep"):
        for comp in ("prone-dry", "never"):
            names = list(y) if (kind, comp) == ("tide", "prone-dry") else SUMMARY
            for year, storm in spring.items():
                t, c, w_t, w_c = groups(f, sp, kind, comp, year)
                for k in (0, 1):
                    if year + k not in y["peak"].columns:
                        continue
                    for name in names:
                        d = panel.deviations(y[name], year, quiet, k)
                        e = panel.estimate(d, w_t, w_c, boot, scale=1.0)
                        draws[(kind, comp, k, name, storm)] = e
                        rows.append({"flooded by": kind, "comparison": comp, "k": k, "outcome": name, "storm": storm,
                                     "year": year, "n_storms": 1, "n_flooded": int((t & d.notna()).sum()),
                                     "n_comparison": int((c & d.notna()).sum()),
                                     "ndvi": e[0], "lo": np.percentile(e[1:], 2.5), "hi": np.percentile(e[1:], 97.5)})  # fmt: skip
            for k in (0, 1):
                for name in names:
                    ds = [draws.get((kind, comp, k, name, s)) for s in spring.values()]
                    ds = [e for e in ds if e is not None and np.isfinite(e[0])]
                    e = np.nanmean(ds, axis=0)
                    rows.append({"flooded by": kind, "comparison": comp, "k": k, "outcome": name, "storm": "all",
                                 "n_storms": len(ds), "ndvi": e[0], "lo": np.nanpercentile(e[1:], 2.5),
                                 "hi": np.nanpercentile(e[1:], 97.5)})  # fmt: skip
    return pd.DataFrame(rows)


def placebo(f, y, sp, spring, quiet) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per (comparison, storm, quiet year) placebo estimates (tide), and the pooled placebo
    spread per comparison and outcome (one random nearby quiet year per storm, N_PLACEBO draws;
    storms without an estimate are left out, as in the pooled estimate)."""
    no_boot = np.empty((len(f), 0))
    rows = []
    for comp in ("prone-dry", "never"):
        for year, storm in spring.items():
            _, _, w_t, w_c = groups(f, sp, "tide", comp, year)
            near = [q for q in quiet if abs(q - year) <= panel.QUIET_WINDOW]
            for q in near:
                base = [b for b in near if b != q]
                for name, v in y.items():
                    d = v[q] - v[base].mean(axis=1)
                    rows.append({"comparison": comp, "storm": storm, "quiet": q, "outcome": name,
                                 "ndvi": panel.estimate(d, w_t, w_c, no_boot, scale=1.0)[0]})  # fmt: skip
    p = pd.DataFrame(rows).dropna(subset=["ndvi"])
    rng = np.random.default_rng(1)
    pooled = []
    for (comp, name), g in p.groupby(["comparison", "outcome"]):
        per = [s.ndvi.values for _, s in g.groupby("storm")]
        sims = np.mean([rng.choice(v, N_PLACEBO) for v in per], axis=0)
        pooled.append({"comparison": comp, "outcome": name, "lo": np.percentile(sims, 2.5),
                       "hi": np.percentile(sims, 97.5), "sd_single": g.ndvi.std()})  # fmt: skip
    return p, pd.DataFrame(pooled).set_index(["comparison", "outcome"])


def figure(r: pd.DataFrame, pp: pd.DataFrame) -> None:
    m = r[(r["flooded by"] == "tide") & (r.comparison == "prone-dry") & (r.storm == "all") & r.outcome.str.match(r"m\d\d")]
    x = np.array(list(MONTHS))
    labels = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    names = [f"m{v:02d}" for v in x]
    band = pp.loc["prone-dry"].loc[names]
    ax.fill_between(x, band.lo, band.hi, color="#e6e6e6", lw=0,
                    label="placebo: same groups in quiet years (95%)")  # fmt: skip
    ax.axhline(0, color=MUTED, lw=0.8)
    for k, col, lab in ((0, BLUE, "storm season"), (1, ORANGE, "next season")):
        s = m[m.k == k].set_index("outcome").loc[names]
        off = -0.08 if k == 0 else 0.08
        ax.errorbar(x + off, s.ndvi, yerr=[s.ndvi - s.lo, s.hi - s.ndvi], color=col, lw=2, marker="o", ms=5,
                    elinewidth=1, capsize=0, label=lab)  # fmt: skip
        ax.annotate(lab, (x[-1] + off, s.ndvi.iloc[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=8, color=INK)  # fmt: skip
    ax.set_xticks(x, labels)
    ax.set_xlim(3.6, 11.2)
    ax.set_ylabel("NDVI, flooded − missed fields", fontsize=9, color=MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    for sp_ in ("top", "right"):
        ax.spines[sp_].set_visible(False)
    ax.grid(axis="y", color="#eeeeee", lw=0.6)
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    ax.set_title("Greenness of low crop fields a spring storm tide flooded, vs flood-prone fields it missed\n"
                 "(7 storms pooled; same height mix; each field against its own quiet years; 95% intervals)",
                 fontsize=9, color=INK)  # fmt: skip
    fig.tight_layout()
    out = config.REPORTS / "figs" / "storm_ndvi.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def effective_n(f, sp, spring) -> dict[str, float]:
    """Median over the storms (tide) of the comparison group's effective size under the height
    weights, (sum w)^2 / sum w^2, per comparison."""
    out = {}
    for comp in ("prone-dry", "never"):
        ess = []
        for year in spring:
            _, c, _, w_c = groups(f, sp, "tide", comp, year)
            w = w_c[c]
            ess.append(w.sum() ** 2 / (w**2).sum())
        out[comp] = float(np.median(ess))
    return out


def report(r, pp, p, f, y, spring, quiet, cover: str, ess: dict) -> None:
    def ci(d):
        return d.apply(lambda x: f"{x.ndvi:+.3f} [{x.lo:+.3f}, {x.hi:+.3f}]", axis=1)

    main_ = r[(r["flooded by"] == "tide") & (r.comparison == "prone-dry") & r.outcome.isin(SUMMARY)]
    order = list(spring.values()) + ["all"]
    t1 = (main_.assign(v=ci(main_)).pivot_table(index="storm", columns=["k", "outcome"], values="v", aggfunc="first")
          .reindex(order))  # fmt: skip
    t1.columns = [f"{o} {'same' if k == 0 else 'next'} season" for k, o in t1.columns]
    nn = main_[(main_.k == 0) & (main_.outcome == "peak")].set_index("storm")[["n_flooded", "n_comparison"]]
    t1 = nn.reindex(order).astype("Int64").astype(str).replace("<NA>", "").join(t1)
    plc = p[(p.comparison == "prone-dry") & p.outcome.isin(SUMMARY)].pivot_table(index="storm", columns="outcome", values="ndvi",
                                                  aggfunc=lambda v: f"{v.min():+.3f} … {v.max():+.3f}")  # fmt: skip
    t1 = t1.join(plc.rename(columns={o: f"placebo range, {o}" for o in SUMMARY}))
    alt = r[(r.storm == "all") & r.outcome.isin(SUMMARY)]
    t2 = alt.assign(v=ci(alt)).pivot_table(index=["flooded by", "comparison", "k"], columns="outcome", values="v",
                                           aggfunc="first")[SUMMARY]  # fmt: skip
    t3 = pp.assign(v=pp.apply(lambda x: f"[{x.lo:+.3f}, {x.hi:+.3f}] (sd {x.sd_single:.3f})", axis=1)).v.unstack(0)
    t3 = t3.loc[SUMMARY + [f"m{m:02d}" for m in MONTHS], ["prone-dry", "never"]]
    mo = r[(r["flooded by"] == "tide") & (r.comparison == "prone-dry") & (r.storm == "all") & r.outcome.str.match(r"m\d\d")]
    t4 = mo.assign(v=ci(mo) + mo.n_storms.map(lambda n: "" if n == len(spring) else f" ({n} storms)"))
    t4 = t4.pivot_table(index="outcome", columns="k", values="v", aggfunc="first")
    t4.columns = ["storm season", "next season"]
    prone = f.n_storms_tide > 0
    quiet_peak = y["peak"].loc[prone, quiet]
    md = f"""# Greenness after a spring storm tide (preliminary)

Generated by `scripts/storm_ndvi.py`. Question: in the summer after a spring storm tide floods a
low crop field, is the field less green than flood-prone fields the same storm missed?
Greenness is Landsat NDVI (0-1; a full summer crop canopy here reads ~0.8-0.9).

Same design as `reports/storm_panel.md` (FINDINGS §37): the 7 modelled spring storm tides, the
low non-chronic crop fields, flooded vs flood-prone fields the storm missed at the same height
mix, each field measured against its own quiet years (no modelled storm: {', '.join(map(str, quiet))};
within {panel.QUIET_WINDOW} years). {cover}
Outcomes: **peak** = 90th percentile of clear June-September scenes; **jul_aug** = mean of
clear July-August scenes. Numbers are NDVI, flooded minus missed; brackets are 95% intervals from
resampling fields. Typical flood-prone field in a quiet year: peak {quiet_peak.stack().median():.2f}
(the field's own year-to-year SD {quiet_peak.std(axis=1).median():.3f}, median).

**Placebo.** The resampling interval sees only field-to-field noise. To see year-to-year noise,
each storm's two groups are compared in each nearby quiet year instead (no storm). If storms
mattered, the real estimates should sit outside the placebo range.

## Per storm (tide only, vs prone-dry)

{md_table(t1)}

## Pooled, every variant

k = 0 is the storm season, 1 the next. "deep" = flooded with a peak depth of at least {DEEP_M} m
(about the deepest quarter), against the same comparisons (fields the storm did not flood at all).

{md_table(t2)}

## Placebo spread (tide-flooded groups)

95% range of the 7-storm average when each storm is replaced by one of its nearby quiet years,
per comparison; sd = spread of single-storm placebo estimates. A pooled estimate inside this
range is what two groups of fields differ by in an ordinary year.

{md_table(t3)}

## Month by month (tide, prone-dry, 7 storms pooled)

![](figs/storm_ndvi.png)

{md_table(t4)}

## Caveats

- **The "never" comparison rests on few fields.** Height-reweighted to the flooded fields' mix,
  the never-flooded group is worth a median of {ess["never"]:.0f} fields per storm ({ess["prone-dry"]:.0f} for
  prone-dry): few never-flooded fields are as low as the flooded ones, as in FINDINGS §37.
- Flooded = the model's peak (≥ 10% of the field > 5 cm), dikes as built today; banks repaired
  after a storm are not dated (storm panel README).
- 2012 has only Landsat 7 (striped, fewer scenes); sensor changes hit both groups alike.
- The June 2012 and June 2023 storms come after most planting; the April-May months of those years
  are before the storm.
- Cloud masks miss thin haze: monthly means carry it, the 90th-percentile peak mostly does not.
- NDVI is greenness, not yield. A lower June value can be late planting that catches up.
"""
    out = config.REPORTS / "storm_ndvi.md"
    out.write_text(md)
    print(f"wrote {out}")


def main() -> None:
    f, sp, spring, quiet = load_fields()
    unit = match_units(f.index)
    left = f.drop(unit.index)
    cover = (f"{len(unit)} of {len(f)} fields match a Landsat field unit ({f.ha[unit.index].sum() / f.ha.sum():.0%} of "
             f"the area; {int((f.n_storms_tide[unit.index] > 0).sum())} flood-prone). The other {len(left)} are too "
             f"small for a clean 30 m pixel (median {left.ha.median():.1f} ha).")  # fmt: skip
    f = f.loc[unit.index]
    sp = {k: v.loc[f.index] for k, v in sp.items()}
    y = ndvi_tables(unit, range(2008, 2026))
    n_summer = y.pop("n_summer")
    tab = pd.concat({k: y[k].stack() for k in SUMMARY} | {"n_summer": n_summer.stack()}, axis=1)
    tab.index.names = ["field_id", "year"]
    tab.reset_index().to_csv(STORM / "field_season_ndvi.csv", index=False, float_format="%.4f")
    boot = np.random.default_rng(0).poisson(1.0, size=(len(f), N_BOOT)).astype(float)
    r = compare(f, y, sp, spring, quiet, boot)
    p, pp = placebo(f, y, sp, spring, quiet)
    r.to_csv(STORM / "ndvi_estimates.csv", index=False, float_format="%.4f")
    print(md_table(r[(r.storm == "all") & r.outcome.isin(SUMMARY)]))
    print(pp)
    figure(r, pp)
    report(r, pp, p, f, y, spring, quiet, cover, effective_n(f, sp, spring))


if __name__ == "__main__":
    main()
