"""Does a field go to hay a few years after it floods? A distributed-lag test on the storm panel.

Seowoo (2026-11): her county data show farms shifting to hay / lower-intensity crops about three
years after flooding, rather than leaving farming. §62/§64's recovery tests (k = 0-3 after a
SPRING storm, per-storm contrasts) used hay + pasture + idle together and were null; this asks
her question directly, with every storm tide and every field's own flood history.

Model (per state, and pooled), one row per field and CDL year t:

    y[i,t] = field[i] + county x year[t] + sum_k b_k * F[i,t-k] + e

- y: percent of the field in that land use (CDL shares, field_year.csv): hay (alfalfa + other
  hay, CDL 36/37), "low-intensity" (hay + pasture + idle), cropland, corn, soybeans.
- F[i,t] = 1 if a modelled storm tide floods the field (tide only, >= 10% of it > 5 cm) between
  the planting of crop t-1 and of crop t: off_tide (July t-1 - February t) or spring_tide
  (March - June t), field_season.csv. So k = 0 is the first crop planted after the flood.
  Rain-only flags are not used (unchecked, FINDINGS §63).
- Lags k = 0..4 (her "about three years" plus one) and two LEADS, k = -1 and -2, as placebos:
  a flood next year cannot change this year's crop. k = -1 holds storms in July-October of t,
  inside crop t's season, so only k = -2 is clean.
- Field effects take out each field's own usual mix; county x year effects take out anything
  that moves a whole county in a year (prices, CDL's yearly classifier, the 2008-25 hay trend).
- Outcome years OUTCOME_YEARS = 2012-2023: the lags reach back to 2008 (CDL's first year here),
  the leads forward to 2025, and CDL's 2024 product change (hay share drops from ~8% to ~2% on
  every field, FINDINGS §37) never enters an outcome.
- Also a "cumulative" model: same effects, y on F[t] + (F[t-1] + F[t-2] + F[t-3]) + the two
  leads: the change per extra flood year in the three before.
- Sample: the panel's main sample (panel.load: crop fields <= 1.5 m above MHHW farmed in
  2008-12, fields wet on ordinary tides out). Each field counts once ("fields"); also by area
  ("ha"), where a few large fields carry the result.
- 95% intervals: N_BOOT resamples of whole HUC12 watersheds (floods are shared by neighbours,
  so fields are not independent); 18-30 watersheds per state hold sample fields, so the
  intervals are rough. Pooled: county x year effects keep the two states apart.

LONG DIFFERENCE (the slow version; the model above sees only changes timed to floods): each
field's change in share from 2009-12 to 2020-23 (both ends before CDL's 2024 change; 2008 left
out, CDL's first year here reads little hay) against how often it flooded in 2010-19: never,
1-3 years, 4+ years, or wet on ordinary tides (`chronic`, kept in here), each group against
"never", with county and height (LONG_H_BIN m above MHHW bins) dummies; and again also
controlling for the field's 2009-12 share (a group that starts low can drift up toward the
average). Same watershed resampling.

Assumptions to say with the result: CDL "Other Hay" also labels abandoned grass (§57), so a
hay rise can be a field let go; the field flags are noisy (§58); floods recur in 2010-14, so
neighbouring lags share information and their sum is steadier than any one of them.

Writes reports/hay_lag[_T]_D.md and data/analysis/storm_panel[_T]/hay_lag_D.csv (and
hay_lag_long_D.csv); ``--keep-chronic`` puts the fields wet on ordinary tides into the lag
model too and adds ``_chronic`` to both names.
Usage:  python scripts/hay_lag_test.py [--tag m65] [--de-tag dek] [--keep-chronic]
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import numpy as np
import pandas as pd

from agri_sfincs import config, panel, region
from agri_sfincs.report import md_table

SANDY, STORM = config.ANALYSIS_DIR / "sandy_panel", config.ANALYSIS_DIR / "storm_panel"
N_BOOT = 500
SEED = 20261112
OUTCOME_YEARS = range(2012, 2024)
LAGS = (-2, -1, 0, 1, 2, 3, 4)
OUTCOMES = {
    "hay": ["share_hay"],
    "low-intensity (hay + pasture + idle)": ["share_hay", "share_pasture", "share_idle"],
    "cropland": ["cropland"],
    "corn": ["share_corn"],
    "soybeans": ["share_soybeans"],
}
REPORTED = list(OUTCOMES)[:3]
LONG_PRE, LONG_POST = [2009, 2010, 2011, 2012], [2020, 2021, 2022, 2023]
LONG_FLOOD_YEARS = range(2010, 2020)
LONG_H_BIN = 0.25  # m; heights below -1 m and above 1.25 m share the end bins
LONG_GROUPS = ["flooded 1-3 yrs", "flooded 4+ yrs", "wet on ordinary tides"]


def lag_name(k: int) -> str:
    return f"lead {-k}" if k < 0 else f"lag {k}"


def flood_flags(storm) -> pd.DataFrame:
    """field_id x CDL year: 1 if a modelled storm tide floods the field between the planting of
    the year before's crop and this year's (off_tide or spring_tide)."""
    fs = pd.read_csv(storm / "field_season.csv", usecols=["field_id", "year", "spring_tide", "off_tide"])
    fs["F"] = ((fs.spring_tide == 1) | (fs.off_tide == 1)).astype(int)
    return fs.pivot(index="field_id", columns="year", values="F")


def field_hucs(sandy, ids: pd.Index, state: str) -> pd.Series:
    g = gpd.read_file(sandy / "fields.gpkg").set_index("field_id").reindex(ids)
    return region.huc12_names(g.geometry.representative_point(), side=state.lower())


def load_state(sandy, storm, state: str, keep_chronic: bool = False) -> pd.DataFrame:
    """Long table field x outcome year: outcomes (percent), F at every lag, group keys, ha."""
    f = panel.load(sandy, storm, keep_chronic=keep_chronic)[0]
    fy = pd.read_csv(sandy / "field_year.csv", usecols=lambda c: c != "dom_name")
    flood = flood_flags(storm).reindex(f.index)
    huc = field_hucs(sandy, f.index, state)
    fy = fy[fy.field_id.isin(f.index) & fy.year.isin(OUTCOME_YEARS)].copy()
    out = pd.DataFrame({"field": state + "-" + fy.field_id.astype(str), "year": fy.year.values})
    for name, cols in OUTCOMES.items():
        out[name] = 100 * fy[cols].sum(axis=1).values
    flood = flood.stack()
    for k in LAGS:
        out[lag_name(k)] = flood.reindex(pd.MultiIndex.from_arrays([fy.field_id, fy.year - k])).values
    out["F 1-3"] = out[["lag 1", "lag 2", "lag 3"]].sum(axis=1)
    out["state"] = state
    out["cty_year"] = state + "-" + f.county.reindex(fy.field_id).values.astype(str) + "-" + out.year.astype(str)
    out["huc"] = state + "-" + huc.reindex(fy.field_id).values
    out["ha"] = f.ha.reindex(fy.field_id).values
    assert out[[lag_name(k) for k in LAGS]].notna().all().all(), "flood flag missing for a lag year"
    return out.reset_index(drop=True)


def demean(M: np.ndarray, groups: list[np.ndarray], w: np.ndarray, tol: float = 1e-9, maxit: int = 2000) -> np.ndarray:
    """Weighted residual of every column of M on the fixed effects ``groups`` (integer codes),
    by alternating projections. Rows with zero weight stay but do not count."""
    M = M.copy()
    sizes = [np.bincount(g, weights=w) for g in groups]
    for _ in range(maxit):
        delta = 0.0
        for g, s in zip(groups, sizes):
            means = np.zeros((len(s), M.shape[1]))
            ok = s > 0
            for j in range(M.shape[1]):
                means[ok, j] = np.bincount(g, weights=w * M[:, j], minlength=len(s))[ok] / s[ok]
            M -= means[g]
            delta = max(delta, np.abs(means).max())
        if delta < tol:
            return M
    raise RuntimeError("fixed effects did not converge")


SPECS = {"lags": [lag_name(k) for k in LAGS], "cumulative": ["lead 2", "lead 1", "lag 0", "F 1-3"]}
XCOLS = SPECS["lags"] + ["F 1-3"]


def fit(d: pd.DataFrame, groups: list[np.ndarray], w: np.ndarray) -> dict[str, np.ndarray]:
    """spec -> b (outcome x regressor) of the two-way fixed-effects regression with weights w."""
    ycols = list(OUTCOMES)
    M = demean(d[ycols + XCOLS].to_numpy(float), groups, w) * np.sqrt(w)[:, None]
    Y = M[:, : len(ycols)]
    return {spec: np.linalg.lstsq(M[:, [len(ycols) + XCOLS.index(x) for x in xs]], Y, rcond=None)[0].T
            for spec, xs in SPECS.items()}  # fmt: skip


def run(d: pd.DataFrame, label: str, rng: np.random.Generator) -> pd.DataFrame:
    groups = [pd.factorize(d.field)[0], pd.factorize(d.cty_year)[0]]
    hucs, code = np.unique(d.huc, return_inverse=True)
    draws = rng.multinomial(len(hucs), np.full(len(hucs), 1 / len(hucs)), size=N_BOOT)
    rows = []
    for wname, base in {"fields": np.ones(len(d)), "ha": d.ha.to_numpy(float)}.items():
        point = fit(d, groups, base)
        fits = [fit(d, groups, base * c[code]) for c in draws]
        for spec, xcols in SPECS.items():
            pt, boot = point[spec], np.stack([b[spec] for b in fits])
            terms = list(xcols)
            if spec == "lags":  # the sum of lags 1-3, on the same draws
                cols = [xcols.index(f"lag {k}") for k in (1, 2, 3)]
                pt = np.column_stack([pt, pt[:, cols].sum(1)])
                boot = np.concatenate([boot, boot[:, :, cols].sum(2, keepdims=True)], axis=2)
                terms.append("sum lags 1-3")
            lo, hi = np.nanpercentile(boot, [2.5, 97.5], axis=0)
            for i, o in enumerate(OUTCOMES):
                for j, x in enumerate(terms):
                    rows.append({"sample": label, "weight": wname, "spec": spec, "outcome": o, "term": x,
                                 "b": pt[i, j], "lo": lo[i, j], "hi": hi[i, j]})  # fmt: skip
    return pd.DataFrame(rows)


def load_long(sandy, storm, state: str) -> pd.DataFrame:
    """One row per field (main sample WITH the chronic fields): change in each outcome (percent,
    LONG_POST mean - LONG_PRE mean), its LONG_PRE level, flood group, county, height bin, huc, ha."""
    f = panel.load(sandy, storm, keep_chronic=True)[0]
    fy = pd.read_csv(sandy / "field_year.csv", usecols=lambda c: c != "dom_name")
    n = flood_flags(storm).reindex(index=f.index, columns=LONG_FLOOD_YEARS).sum(axis=1)
    grp = np.where(f.chronic == 1, LONG_GROUPS[2], np.where(n == 0, "never", np.where(n <= 3, *LONG_GROUPS[:2])))
    out = pd.DataFrame({"group": grp, "county": f.county.values, "ha": f.ha.values}, index=f.index)
    out["h_bin"] = np.clip(np.floor(f.m_above_mhhw / LONG_H_BIN), -1 / LONG_H_BIN, panel.MAX_H / LONG_H_BIN - 1)
    for name, cols in OUTCOMES.items():
        v = 100 * fy.assign(v=fy[cols].sum(axis=1)).pivot(index="field_id", columns="year", values="v").reindex(f.index)
        out[f"{name} pre"] = v[LONG_PRE].mean(axis=1)
        out[name] = v[LONG_POST].mean(axis=1) - out[f"{name} pre"]
    out["huc"] = state + "-" + field_hucs(sandy, f.index, state).values
    return out


def long_diff(dl: pd.DataFrame, label: str, rng: np.random.Generator) -> pd.DataFrame:
    """Each flood group - "never" in the long change, with county + height-bin dummies (and,
    "+ start level", the outcome's LONG_PRE level), least squares; watershed resampling."""
    base = pd.get_dummies(dl[["county", "h_bin"]].astype(str), drop_first=True).astype(float)
    base.insert(0, "const", 1.0)
    groups = [g for g in LONG_GROUPS if (dl.group == g).any()]
    G = pd.DataFrame({g: (dl.group == g).astype(float) for g in groups}, index=dl.index)
    hucs, code = np.unique(dl.huc, return_inverse=True)
    draws = rng.multinomial(len(hucs), np.full(len(hucs), 1 / len(hucs)), size=N_BOOT)
    rows = []
    for wname, w in {"fields": np.ones(len(dl)), "ha": dl.ha.to_numpy(float)}.items():
        for ctrl in ("height + county", "+ start level"):
            for o in REPORTED:
                X = pd.concat([G, base] + ([dl[[f"{o} pre"]]] if ctrl == "+ start level" else []), axis=1).to_numpy()
                y = dl[o].to_numpy()

                def b(ww, X=X, y=y):
                    sw = np.sqrt(ww)
                    return np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0][: len(groups)]

                pt, bt = b(w), np.stack([b(w * c[code]) for c in draws])
                lo, hi = np.percentile(bt, [2.5, 97.5], axis=0)
                for j, g in enumerate(groups):
                    rows.append({"sample": label, "weight": wname, "controls": ctrl, "outcome": o, "group": g,
                                 "fields": int((dl.group == g).sum()), "b": pt[j], "lo": lo[j], "hi": hi[j]})  # fmt: skip
    return pd.DataFrame(rows)


def long_table(lr: pd.DataFrame, sample: str, weight: str) -> str:
    s = lr[(lr["sample"] == sample) & (lr.weight == weight)]
    t = s.assign(v=s.apply(cell, axis=1)).pivot(index=["controls", "group"], columns="outcome", values="v")
    order = [(c, g) for c in ("height + county", "+ start level") for g in LONG_GROUPS]
    return md_table(t.reindex(index=[i for i in order if i in t.index], columns=REPORTED))


def describe(d: pd.DataFrame) -> dict:
    fl = d.groupby("field")["lag 0"].agg(["min", "max"])
    return {"fields": d.field.nunique(), "ha": round(d.groupby("field").ha.first().sum()),
            "watersheds": d.huc.nunique(), "flooded in some 2012-23 years": int((fl["max"] > fl["min"]).sum()),
            "mean hay %": round(d.hay.mean(), 1), "mean hay % by area": round(np.average(d.hay, weights=d.ha), 1)}  # fmt: skip


def cell(r) -> str:
    star = "**" if (r.lo > 0 or r.hi < 0) else ""
    return f"{star}{r.b:+.1f}{star} [{r.lo:+.1f}, {r.hi:+.1f}]"


def table(res: pd.DataFrame, sample: str, weight: str, spec: str, terms: list[str]) -> str:
    s = res[(res["sample"] == sample) & (res.weight == weight) & (res.spec == spec) & res.outcome.isin(REPORTED)]
    t = s.assign(v=s.apply(cell, axis=1)).pivot(index="term", columns="outcome", values="v")
    return md_table(t.reindex(index=terms, columns=REPORTED).rename_axis("term"))


def report(res: pd.DataFrame, desc: dict, tags: dict, lr: pd.DataFrame, longs: dict, chronic: bool) -> str:
    lag_terms = [lag_name(k) for k in LAGS] + ["sum lags 1-3"]
    cum_terms = ["lead 2", "lead 1", "lag 0", "F 1-3"]
    samples = md_table(pd.DataFrame.from_dict(desc, orient="index").rename_axis("sample"), floatfmt="{:,.1f}")
    L = [f"""# Do fields go to hay a few years after they flood?

Generated by `scripts/hay_lag_test.py` from the storm panels {', '.join(f'`storm_panel{t}` ({s})' for s, t in tags.items())}.
Asked by Seowoo (2026-11): her county numbers show a shift to hay / lower-intensity crops about three years after
flooding. Here, per field: its land use in year t against whether a modelled storm tide flooded it k years before
(k = 0: the first crop planted after the flood; leads = a flood AFTER the crop, which should show nothing).
Field effects and county x year effects; outcome years 2012-2023 (before CDL's 2024 change).
{"Fields wet on ordinary tides are IN this run (`--keep-chronic`)." if chronic else "Main sample: fields wet on ordinary tides are out of the lag model (in the long difference)."}
Percentage points of the field; 95% intervals from resampling whole HUC12 watersheds; **bold** = the interval excludes zero.
With {(len(lag_terms) + len(cum_terms)) * len(REPORTED) * 2 * len(desc)} intervals below, a few bold cells are expected by chance.

## Samples

{samples}

"""]
    for sample in desc:
        for weight, wtxt in {"fields": "each field counts once", "ha": "by area"}.items():
            L.append(f"## {sample}, {wtxt}\n\nPer lag:\n\n{table(res, sample, weight, 'lags', lag_terms)}\n")
            L.append(f"Cumulative (`F 1-3` = per extra flood year among the three before):\n\n"
                     f"{table(res, sample, weight, 'cumulative', cum_terms)}\n")  # fmt: skip
    L.append(f"""## The slow version: change from 2009-12 to 2020-23

Each field's change in share between those two four-year spans (both before CDL's 2024 change), by how often it
flooded in 2010-19, each group against never-flooded fields of the same county and height (0.25 m bins); "+ start
level" also holds the field's 2009-12 share fixed. Fields per group:
{md_table(pd.DataFrame({s: d.group.value_counts() for s, d in longs.items()}).fillna(0).astype(int).rename_axis("group"))}
""")
    for sample in longs:
        for weight, wtxt in {"fields": "each field counts once", "ha": "by area"}.items():
            L.append(f"### {sample}, {wtxt}\n\n{long_table(lr, sample, weight)}\n")
    L.append("""## Reading it

- **CDL hay is not only hay.** CDL labels abandoned grass "Other Hay" (FINDINGS §57), so a hay rise can be a field
  let go, not a farmer's switch.
- **The flags are noisy** (§58): many fields marked flooded may not have been, which pulls every estimate toward zero.
- **Floods cluster in 2010-14**, so neighbouring lags share information; the sum of lags 1-3 and the cumulative
  term are steadier than any single lag.
- **Lead 1 is not a clean placebo:** it holds storms in July-October of the crop's own season. Lead 2 is.
- **Few watersheds** (see Samples): the intervals are rough.
- **The long difference compares places, not times:** often-flooded fields are lower, wetter and nearer the marsh;
  height and county are held, drainage, soils and owners are not. CDL may also read hay and grass differently on wet
  ground in different years.
- Corn and soybeans are in the csv.
""")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", default="m65")
    ap.add_argument("--de-tag", default="dek")
    ap.add_argument("--keep-chronic", action="store_true", help="fields wet on ordinary tides into the lag model")
    a = ap.parse_args()
    tags = {"NJ": f"_{a.tag}" if a.tag else "", "DE": f"_{a.de_tag}"}
    dirs = {st: (SANDY.with_name(f"sandy_panel{t}"), STORM.with_name(f"storm_panel{t}")) for st, t in tags.items()}
    parts = {st: load_state(*d, st, keep_chronic=a.keep_chronic) for st, d in dirs.items()}
    longs = {st: load_long(*d, st) for st, d in dirs.items()}
    samples = {**parts, "NJ + DE": pd.concat(parts.values(), ignore_index=True)}
    rng = np.random.default_rng(SEED)
    res = pd.concat([run(d, s, rng) for s, d in samples.items()], ignore_index=True)
    lr = pd.concat([long_diff(d, s, rng) for s, d in longs.items()], ignore_index=True)
    desc = {s: describe(d) for s, d in samples.items()}
    sfx = f"{a.de_tag}{'_chronic' if a.keep_chronic else ''}"
    folder = STORM.with_name(f"storm_panel{tags['NJ']}")
    res.to_csv(folder / f"hay_lag_{sfx}.csv", index=False, float_format="%.4f")
    lr.to_csv(folder / f"hay_lag_long_{sfx}.csv", index=False, float_format="%.4f")
    out = config.REPORTS / f"hay_lag{tags['NJ']}_{sfx}.md"
    out.write_text(report(res, desc, tags, lr, longs, a.keep_chronic))
    print(pd.DataFrame.from_dict(desc, orient="index").to_string())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
