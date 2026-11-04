"""Is it salt? Three descriptive tests on the storm panel (user, 2026-11-04; STATUS 5a). If a
spring storm tide changes what is grown because of SALT rather than wetness, the response
should be larger where the bay is saltier, larger for tide water than for rain water, and last
more than one season. None of these can prove salt; a null here says little, because the main
effect itself is not detectable (FINDINGS §53, §57) and the field flags are noisy (§58).

Same design as scripts/plot_storm_panel.py (agri_sfincs.panel.load / deviations / estimate):
per spring storm, flooded fields against the flood-prone fields that storm missed ("prone-dry"),
reweighted to the flooded group's area per height bin, each field's outcome measured against
its own quiet years; plain mean over the storms; 95% intervals from N_BOOT Poisson-weight
resamplings of fields (the storms held fixed). Percentage points: of area for the share
outcomes, of the chance (area-weighted) for the yes/no ones.

1. Bay position: each field's distance up the estuary (agri_sfincs.domain.up_estuary_km, km
   from the bay mouth of its centroid's projection onto the shipping-channel axis; salinity falls
   along it). Fields are split into a LOWER (saltier) and UPPER band at SPLIT_KM; flooded and
   comparison fields are taken within the same band. Also lower - upper, on the same resamples.
   Dose: flooded fields by the storm's flooded share of the field (tide_share, field_event.csv;
   the larger of two peaks in one spring), DOSE_BINS, each against the band's prone-dry fields.
2. Tide vs rain: fields flooded by the storm tide (spring_tide = 1) and fields flooded only once
   the storm's rain is added (spring_rain = 1, spring_tide = 0), each against fields dry in both
   that are flooded by some other storm. Rain flags are not checked against observations.
3. Recovery: k = 0..3 seasons after the storm (k = 0: the storm's own season). A storm whose
   season Y + k holds its own spring storm is marked: there, k mixes recovery with a new flood;
   "clean" = the mean over the storms whose Y + 1 .. Y + k hold none.
A contrast is left out of a storm (and of the mean) when either group has fewer than MIN_FIELDS.

POOLED NJ + DE (``--de-tag D``, 2026-11-04; FINDINGS §62: Delaware adds a salinity range not tied
to one county). Choices:
- Fields are keyed ``state-field_id`` ("NJ-123", "DE-45"; export_storm_panel.py's field_key):
  field_id is 1..N within each state's build.
- Both builds must hold the same storm tides (event + peak in field_event.csv), the same spring
  storms and the same quiet years; the script stops otherwise. The pooled mean is over that one
  storm list (the same Ship John storm tides), each storm's flooded / prone-dry groups being
  the union of both states' fields under that state's own model run.
- A flooded field is compared only with prone-dry fields of its OWN state: the height
  reweighting is by state x height bin (panel.height_weights ``strata``), so the comparison
  group also takes the flooded group's mix of states. The two grids are not forced on one bay
  water level and their CDL / land-use maps differ, so a cross-state comparison would read a
  state difference as a flood effect. A pooled number is thus a mix of the two within-state
  contrasts, weighted by flooded area. MIN_FIELDS applies per state: a state with fewer than MIN_FIELDS
  flooded or comparison fields in a storm's contrast sits that storm out (a handful of fields would carry
  all its matching weight); csv ``by_state`` = storms each state took part in.
- A bootstrap resample can leave a small group with no weight; such draws are left out of the
  interval (csv ``nan_draws``, "*" in the report). It does not happen on NJ alone.
- Each result is also given per state ("NJ", "DE": the same code on that state's fields alone,
  on the same bootstrap draws), beside the pooled "all"; NJ's rows equal the NJ-only run.
- Same SPLIT_KM by default for both states (``--split-km`` to try another; NJ's default is
  unchanged). up_estuary_km uses the one shipping-channel axis for both shores; fields seaward
  of the axis's start (the Broadkill near Lewes) all read 0 km.
- A build with no chronic flag (fields_storm.csv ``chronic`` all blank) keeps its chronic
  fields, and the report says so; NJ's are dropped as before.

Writes reports/salt_tests[_T].md and data/analysis/storm_panel[_T]/salt_tests.csv; pooled,
reports/salt_tests[_T]_D.md and data/analysis/storm_panel[_T]/salt_tests_D.csv (column
``state``: all / NJ / DE). A non-default --split-km adds ``_splitK`` to both names.
Usage:  python scripts/salt_tests.py [--tag m65] [--de-tag deo] [--split-km 70]
(pooled on the 4-CPU vscode node: OPENBLAS_NUM_THREADS=1 takes ~35 s; unset, BLAS oversubscribes, >2 min)
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import numpy as np
import pandas as pd

from agri_sfincs import config, domain, panel, region
from agri_sfincs.report import md_table

SANDY, STORM = config.ANALYSIS_DIR / "sandy_panel", config.ANALYSIS_DIR / "storm_panel"
N_BOOT = 500
MIN_FIELDS = 5
#: lower / upper band edge. Flood-prone NJ fields leave a gap here: Cumberland's sit 33-72 km up
#: the estuary, Salem's 71-119 (Gloucester's ~120-140), so on NJ the split is Cumberland vs the rest.
SPLIT_KM = 70.0
DOSE_BINS = [(0.10, 0.25), (0.25, 0.50), (0.50, 1.01)]
OUTCOMES = ["cropland", "corn", "soybeans", "grass (hay + pasture + idle)", "left cropland", "left farmland"]
KS = (0, 1, 2, 3)
STATES = ("NJ", "DE")  # pooled order: NJ rows first (so NJ keeps the NJ-only bootstrap draws)
KM_BIN = 10.0  # km, the pooled distribution table


def key_index(ids, state: str) -> pd.Index:
    """field_id -> field_key "NJ-123" (scripts/export_storm_panel.py's key)."""
    return pd.Index([f"{state}-{i}" for i in ids], name="field_key")


def storm_list(ev: pd.DataFrame) -> list[tuple[str, str]]:
    """The (event, peak) storm tides of a field_event.csv table, sorted."""
    return sorted(set(zip(ev.event, ev.peak)))


def check_same(parts: dict) -> None:
    """Raise unless every state's build holds the same storm tides, spring storms and quiet years."""
    (a, pa), *rest = parts.items()
    for b, pb in rest:
        for what in ("storms", "spring", "quiet"):
            if pa[what] != pb[what]:
                x, y = pa[what], pb[what]
                diff = sorted(set(x) ^ set(y)) if not isinstance(x, dict) else sorted(set(x.items()) ^ set(y.items()))
                raise ValueError(f"{a} and {b} builds differ in {what}: {diff or (x, y)}")


def load_state(sandy, storm) -> dict:
    """One build's tables (panel.load), each field's km up the estuary and, per spring storm,
    its flooded share. A build with no chronic flag keeps its chronic fields (``no_chronic``)."""
    no_chronic = bool(pd.read_csv(storm / "fields_storm.csv", usecols=["chronic"]).chronic.isna().all())
    f, y, sp, spring, quiet = panel.load(sandy, storm, keep_chronic=no_chronic)
    g = gpd.read_file(sandy / "fields.gpkg").set_index("field_id").reindex(f.index)
    c = g.geometry.centroid
    f["km"] = domain.up_estuary_km(c.x.values, c.y.values, g.crs.to_epsg())
    ev_all = pd.read_csv(sandy / "field_event.csv")
    ev = ev_all[pd.to_datetime(ev_all.peak).dt.month.between(3, 6)]
    share = {yr: ev[ev.event == s].groupby("field_id").tide_share.max().reindex(f.index).fillna(0)
             for yr, s in spring.items()}  # fmt: skip
    return {"f": f, "y": y, "sp": sp, "spring": spring, "quiet": [int(t) for t in quiet], "share": share,
            "storms": storm_list(ev_all), "no_chronic": no_chronic, "centroids": c, "crs": g.crs}  # fmt: skip


def combine(parts: dict) -> dict:
    """Stack the states' tables (``parts``: state -> load_state dict, NJ first), keyed by
    field_key; adds ``state`` (field_key -> state). The storm lists must agree (check_same)."""
    check_same(parts)
    rekey = lambda d, st: d.set_axis(key_index(d.index, st), axis=0)  # noqa: E731
    first = next(iter(parts.values()))
    out = {"f": pd.concat([rekey(p["f"], st) for st, p in parts.items()]),
           "y": {o: pd.concat([rekey(p["y"][o], st) for st, p in parts.items()]) for o in first["y"]},
           "sp": {k: pd.concat([rekey(p["sp"][k], st) for st, p in parts.items()]) for k in first["sp"]},
           "share": {yr: pd.concat([rekey(p["share"][yr], st) for st, p in parts.items()]) for yr in first["share"]},
           "spring": first["spring"], "quiet": first["quiet"]}  # fmt: skip
    out["state"] = pd.Series([st for st, p in parts.items() for _ in range(len(p["f"]))], index=out["f"].index)
    return out


class Panel:
    def __init__(self, f, y, sp, spring, quiet, share, split_km=SPLIT_KM, state=None, boot=None):
        self.f, self.y, self.sp, self.spring, self.quiet, self.share = f, y, sp, spring, quiet, share
        self.split, self.state = split_km, state  # state: field -> "NJ" / "DE" when pooled, else None
        if boot is None:
            boot = np.random.default_rng(0).poisson(1.0, size=(len(self.f), N_BOOT)).astype(float)
        self.boot = boot
        self.prone = self.f.n_storms_tide > 0

    @classmethod
    def from_parts(cls, parts: dict, split_km=SPLIT_KM) -> Panel:
        """One state's panel (one part: field_id index, as before) or the pooled one (field_key)."""
        if len(parts) == 1:
            p = next(iter(parts.values()))
            return cls(p["f"], p["y"], p["sp"], p["spring"], p["quiet"], p["share"], split_km)
        c = combine(parts)
        return cls(c["f"], c["y"], c["sp"], c["spring"], c["quiet"], c["share"], split_km, c["state"])

    def subset(self, state: str) -> Panel:
        """The pooled panel's ``state`` fields alone, on their rows of the same bootstrap draws."""
        m = (self.state == state).values
        ix = self.f.index[m]
        return Panel(self.f[m], {o: v.loc[ix] for o, v in self.y.items()}, {k: v.loc[ix] for k, v in self.sp.items()},
                     self.spring, self.quiet, {yr: v.loc[ix] for yr, v in self.share.items()}, self.split,
                     None, self.boot[m])  # fmt: skip

    def contrast(self, t: pd.Series, c: pd.Series, outcome: str, year: int, k: int):
        """flooded ``t`` - comparison ``c`` draws for one storm, or None (too few / no outcome)."""
        if self.state is not None:  # pooled: a state with too few fields in either group sits this storm out
            thin = [s for s in STATES if (t & (self.state == s)).sum() < MIN_FIELDS or (c & (self.state == s)).sum() < MIN_FIELDS]
            out = self.state.isin(thin)
            t, c = t & ~out, c & ~out
        if t.sum() < MIN_FIELDS or c.sum() < MIN_FIELDS or year + k not in self.y[outcome].columns:
            return None
        d = panel.deviations(self.y[outcome], year, self.quiet, k)
        if d[t].isna().all() or d[c].isna().all():
            return None
        w = panel.height_weights(self.f.m_above_mhhw, self.f.ha, t, c, strata=self.state)
        self.eff.append(panel.effective_n(w.where(t, 0.0) * d.notna()))
        if self.state is not None:
            self.used.extend(sorted(set(self.state[t])))
        return panel.estimate(d, w.where(t, 0.0), w.where(c, 0.0), self.boot)

    def pooled(self, groups, outcome: str, k: int, years=None):
        """Plain mean over the storms of ``groups(year) -> (t, c)``; (draws, n storms). The flooded
        groups' effective sizes (agri_sfincs.panel.effective_n) are kept in ``last_eff``."""
        self.eff, self.used = [], []
        ds = [e for yr in (years or self.spring) if (e := self.contrast(*groups(yr), outcome, yr, k)) is not None]
        self.last_eff = (min(self.eff), max(self.eff)) if self.eff else (np.nan, np.nan)
        return (np.mean(ds, axis=0), len(ds)) if ds else (None, 0)

    def tag(self) -> dict:
        """Pooled: storms each state took part in over the last ``pooled`` call (``by_state``)."""
        return {} if self.state is None else {"by_state": " ".join(f"{s}:{self.used.count(s)}" for s in STATES)}


def row(test: str, group: str, outcome: str, k: int, e, n: int, **kw) -> dict:
    if e is None:
        return {"test": test, "group": group, "outcome": outcome, "k": k, "storms": 0, **kw}
    nan = int(np.isnan(e[1:]).sum())  # draws where a resample emptied a group (small groups); left out
    if nan:
        kw["nan_draws"] = nan
    return {"test": test, "group": group, "outcome": outcome, "k": k, "storms": n, "pp": e[0],
            "lo": np.nanpercentile(e[1:], 2.5), "hi": np.nanpercentile(e[1:], 97.5), **kw}  # fmt: skip


def run(p: Panel) -> pd.DataFrame:
    rows = []
    tide = lambda yr: p.sp["tide"][yr] == 1  # noqa: E731
    rain_only = lambda yr: (p.sp["rain"][yr] == 1) & ~tide(yr)  # noqa: E731
    dry = lambda yr: p.prone & ~tide(yr) & (p.sp["rain"][yr] != 1)  # noqa: E731
    lower = p.f.km < p.split
    bands = {"lower (saltier)": lower, "upper (fresher)": ~lower}
    for o in OUTCOMES:
        for k in (0, 1):
            # 1. bay position
            band_e = {}
            for name, b in bands.items():
                e, n = p.pooled(lambda yr, b=b: (tide(yr) & b, p.prone & ~tide(yr) & b), o, k)
                band_e[name] = (e, n)
                rows.append(row("bay position", name, o, k, e, n, eff_lo=p.last_eff[0], eff_hi=p.last_eff[1], **p.tag()))
            (e, n), (u, m) = band_e["lower (saltier)"], band_e["upper (fresher)"]
            rows.append(row("bay position", "lower - upper", o, k, None if e is None or u is None else e - u, min(n, m)))
            for name, b in bands.items():
                for lo_s, hi_s in DOSE_BINS:
                    g = lambda yr, b=b, lo_s=lo_s, hi_s=hi_s: (tide(yr) & b & p.share[yr].between(lo_s, hi_s, inclusive="left"),
                                                              p.prone & ~tide(yr) & b)  # fmt: skip
                    e, n = p.pooled(g, o, k)
                    rows.append(row("dose", f"{name}, share {lo_s:.0%}-{min(hi_s, 1):.0%}", o, k, e, n, **p.tag()))
            # 2. tide vs rain
            for name, t in (("tide", tide), ("rain only", rain_only)):
                e, n = p.pooled(lambda yr, t=t: (t(yr), dry(yr)), o, k)
                rows.append(row("tide vs rain", name, o, k, e, n, **p.tag()))
        # 3. recovery
        springs = set(p.spring)
        for k in KS:
            e, n = p.pooled(lambda yr: (tide(yr), p.prone & ~tide(yr)), o, k)
            rows.append(row("recovery", "all storms", o, k, e, n, **p.tag()))
            clean = [yr for yr in p.spring if not any(yr + j in springs for j in range(1, k + 1))]
            e, n = p.pooled(lambda yr: (tide(yr), p.prone & ~tide(yr)), o, k, clean)
            rows.append(row("recovery", "clean storms", o, k, e, n, which=" ".join(str(y) for y in clean), **p.tag()))
    return pd.DataFrame(rows)


def run_all(p: Panel) -> pd.DataFrame:
    """run(p); pooled, the pooled rows ("all") then each state's own, in a leading ``state`` column."""
    if p.state is None:
        return run(p)
    res = pd.concat([run(q).assign(state=s) for s, q in [("all", p), *((s, p.subset(s)) for s in STATES)]],
                    ignore_index=True)  # fmt: skip
    return res[["state", *[c for c in res.columns if c != "state"]]]


def counts(p: Panel) -> pd.DataFrame:
    """Per storm: flooded fields and ha per band, rain-only fields."""
    out = []
    for yr, s in p.spring.items():
        t = p.sp["tide"][yr] == 1
        r = (p.sp["rain"][yr] == 1) & ~t
        lo = p.f.km < p.split
        out.append({"storm": s, "year": yr, "flooded lower": int((t & lo).sum()), "flooded upper": int((t & ~lo).sum()),
                    "ha lower": round(p.f.ha[t & lo].sum()), "ha upper": round(p.f.ha[t & ~lo].sum()),
                    "rain only": int(r.sum()), "Y+1 storm": "yes" if yr + 1 in p.spring else ""})  # fmt: skip
    return pd.DataFrame(out)


def counts_pooled(p: Panel) -> pd.DataFrame:
    """Per storm and state: flooded and prone-dry fields per band (the groups each state brings)."""
    out = []
    lo = p.f.km < p.split
    for yr, s in p.spring.items():
        t = p.sp["tide"][yr] == 1
        for st in STATES:
            m = p.state == st
            out.append({"storm": s, "state": st, "flooded lower": int((t & lo & m).sum()),
                        "prone-dry lower": int((p.prone & ~t & lo & m).sum()), "flooded upper": int((t & ~lo & m).sum()),
                        "prone-dry upper": int((p.prone & ~t & ~lo & m).sum()),
                        "ha flooded lower": round(p.f.ha[t & lo & m].sum()), "ha flooded upper": round(p.f.ha[t & ~lo & m].sum())})  # fmt: skip
    return pd.DataFrame(out).set_index(["storm", "state"])


def km_tables(p: Panel, hucs: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Pooled diagnostics of km up the estuary: by state x county, prone fields per KM_BIN, and
    prone fields by state x county x HUC12 (``hucs``: field_key -> HUC12 name)."""
    f = p.f.assign(state=p.state, prone=p.prone, lower=p.f.km < p.split, huc=hucs)
    fp = f[f.prone]
    q = lambda s: fp.groupby(["state", "county"]).km.quantile(s)  # noqa: E731
    by_cty = pd.DataFrame({
        "fields": f.groupby(["state", "county"]).size(), "flood-prone": fp.groupby(["state", "county"]).size(),
        "km min": fp.groupby(["state", "county"]).km.min(), "km 10%": q(0.1), "km median": q(0.5), "km 90%": q(0.9),
        "km max": fp.groupby(["state", "county"]).km.max(),
        "prone in lower band": fp.groupby(["state", "county"]).lower.mean().map("{:.0%}".format)})  # fmt: skip
    by_cty = by_cty.sort_values("km median")
    by_cty[[c for c in by_cty if c.startswith("km")]] = by_cty.filter(like="km").round(0).astype(int)
    edges = np.arange(0, np.ceil(fp.km.max() / KM_BIN) * KM_BIN + KM_BIN, KM_BIN)
    b = pd.cut(fp.km, edges, right=False, labels=[f"{a:.0f}-{a + KM_BIN:.0f}" for a in edges[:-1]])
    hist = fp.groupby([b, "state"], observed=False).size().unstack("state").reindex(columns=list(STATES)).fillna(0).astype(int)
    hist.index.name = "km (prone fields)"
    by_huc = fp.groupby(["state", "county", "huc"]).km.agg(fields="size", min="min", median="median", max="max")
    by_huc = by_huc.sort_values("median")
    by_huc[["min", "median", "max"]] = by_huc[["min", "median", "max"]].round(0).astype(int)
    return by_cty, hist, by_huc


def field_hucs(parts: dict) -> pd.Series:
    """field_key -> name of the HUC12 holding the field's centroid (the side's own domain HUC12s)."""
    out = []
    for st, p in parts.items():
        h = region.load_huc12(side=st.lower()).to_crs(p["crs"])
        pts = gpd.GeoDataFrame(geometry=p["centroids"].values, index=key_index(p["f"].index, st), crs=p["crs"])
        j = gpd.sjoin(pts, h[["name", "geometry"]], how="left", predicate="within")
        out.append(j[~j.index.duplicated()]["name"].fillna("(outside)"))
    return pd.concat(out)


def fmt(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["estimate"] = [f"{r.pp:+.1f} [{r.lo:+.1f}, {r.hi:+.1f}]" if r.storms else "too few" for r in d.itertuples()]
    if "nan_draws" in d:  # pooled / small groups only: flag intervals that left out empty resamples
        d["estimate"] += np.where(d.nan_draws.fillna(0) > 0, "*", "")
    return d


def report(p: Panel, res: pd.DataFrame, tag: str) -> str:
    f = p.f
    fl = f[f.n_storms_tide > 0]
    km = fl.km.quantile([0.1, 0.5, 0.9]).round(0)
    by = f.groupby(f.km < p.split).agg(n=("ha", "size"), ha=("ha", "sum"), h=("m_above_mhhw", "median"))
    r = fmt(res)
    tab = lambda test, k: md_table(  # noqa: E731
        r[(r.test == test) & (r.k == k)].pivot(index="group", columns="outcome", values="estimate")[OUTCOMES])
    rec = r[r.test == "recovery"].assign(col=lambda d: d.group + ", k=" + d.k.astype(str))
    rec = rec[~((rec.group == "clean storms") & (rec.k == 0))]  # the same as all storms
    rec_t = rec.pivot(index="col", columns="outcome", values="estimate")[OUTCOMES]
    rec_t.index.name = "storms, k"
    clean = rec[rec.group == "clean storms"].drop_duplicates("k")[["k", "which"]]
    bp = res[(res.test == "bay position") & res.eff_lo.notna()]
    eff_rng = f"{bp.eff_lo.min():.0f}-{bp.eff_hi.max():.0f}"
    n_cells = int(res.pp.notna().sum())
    return f"""# Is it salt? Bay position, tide vs rain, recovery (storm panel{tag})

Generated by `scripts/salt_tests.py` (design in its docstring). Descriptive; no regression. The main
effect of a spring storm tide on crop mix is not detectable (FINDINGS §53, §57) and the field flags are
noisy (§58), so these splits can show a pattern consistent with salt, not prove it, and a null says little.

**Fields:** the {len(f):,} main-sample fields (low crop fields, not wet on ordinary high tides).
Distance up the estuary from the bay mouth (km along the shipping channel; Ship John Shoal ≈ 57,
Reedy Point ≈ 91, Delaware Memorial Bridge ≈ 110): flood-prone fields span {km[0.1]:.0f}-{km[0.9]:.0f} km (10th-90th
percentile), median {km[0.5]:.0f}. Split at {p.split:.0f} km: lower (saltier) {int(by.n[True])} fields, {by.ha[True]:,.0f} ha, median
{by.h[True]:.2f} m above MHHW; upper (fresher) {int(by.n[False])} fields, {by.ha[False]:,.0f} ha, median {by.h[False]:.2f} m.
Salinity is not measured here: the upper band is brackish rather than fresh on most of it (the salt front
averages near the Memorial Bridge), so this is saltier vs less salty water.

## Fields per storm

{md_table(counts(p).set_index("storm"))}

## 1. Bay position (tide only; flooded vs prone-dry within the same band)

Same season (k = 0):

{tab("bay position", 0)}

Next season (k = 1):

{tab("bay position", 1)}

**Dose** (flooded share of the field; each bin against the band's prone-dry fields), same season:

{tab("dose", 0)}

## 2. Tide vs rain (each against fields dry in both, flooded by another storm)

Same season:

{tab("tide vs rain", 0)}

Next season:

{tab("tide vs rain", 1)}

## 3. Recovery (tide only, all bands; k = seasons after the storm)

{md_table(rec_t)}

"Clean" storms (no spring storm of their own in Y+1 .. Y+k): {"; ".join(f"k={c.k}: {c.which or 'none'}" for c in clean.itertuples())}.
Yes/no outcomes stop before CDL's 2024 change (the two left flags before 2023), so later k have fewer storms.

## Caveats

- **Bay position is not only salinity, and on NJ it is the county line.** Flood-prone fields leave a gap at
  ~70 km: below it is Cumberland's bayshore, above it Salem (and a few Gloucester fields);
  they differ in farm type, soils, drainage, dike systems and how the model does there (storm peaks run
  high near Bivalve and low in the Alloway, FINDINGS §50). A difference between bands is not a salt effect
  by itself.
- **Rain-only flags are unchecked** and few; rain may also fall on fields already wet from the tide.
- **Recovery mixes with the next storm** in most years (4 of the 7 spring storms are followed by another the
  next season), and the clean subsets are one or two storms.
- **Small groups, many cells:** a few large fields carry much of the area (the flooded groups behave like
  {eff_rng} fields per storm in the band tests); contrasts with fewer than {MIN_FIELDS} fields in either group are left out.
  With ~{n_cells} intervals in this report, several will exclude zero by chance alone.
"""


def report_pooled(p: Panel, res: pd.DataFrame, tags: dict, parts: dict, hucs: pd.Series) -> str:
    """The pooled NJ + DE report: every table holds the pooled rows ("all") and each state's."""
    f, st = p.f, p.state
    order = {s: i for i, s in enumerate(("all", *STATES))}
    r = fmt(res)

    def piv(d: pd.DataFrame, index: str) -> pd.DataFrame:
        t = d.pivot(index=[index, "state"], columns="outcome", values="estimate")[OUTCOMES]
        return t.sort_index(key=lambda ix: ix.map(order) if ix.name == "state" else ix)

    tab = lambda test, k: md_table(piv(r[(r.test == test) & (r.k == k)], "group"))  # noqa: E731
    rec = r[r.test == "recovery"].assign(col=lambda d: d.group + ", k=" + d.k.astype(str))
    rec = rec[~((rec.group == "clean storms") & (rec.k == 0))]
    rec_t = piv(rec, "col").rename_axis(index=["storms, k", "state"])
    clean = rec[rec.group == "clean storms"].drop_duplicates("k")[["k", "which"]]
    bp = res[(res.test == "bay position") & res.eff_lo.notna()]
    eff_rng = f"{bp.eff_lo.min():.0f}-{bp.eff_hi.max():.0f}"
    n_cells = int(res.pp.notna().sum())
    n_star = int((res.get("nan_draws", pd.Series(dtype=float)).fillna(0) > 0).sum())
    lower = f.km < p.split
    band = f.assign(state=st, band=np.where(lower, "lower (saltier)", "upper (fresher)"), prone=p.prone)
    comp = band.groupby(["band", "state"]).agg(fields=("ha", "size"), **{"flood-prone": ("prone", "sum")},
                                               ha=("ha", "sum"), **{"median m above MHHW": ("m_above_mhhw", "median")},
                                               **{"median km": ("km", "median")})  # fmt: skip
    comp = comp.sort_index(key=lambda ix: ix.map(order) if ix.name == "state" else ix)
    comp[["ha", "median km"]] = comp[["ha", "median km"]].round(0).astype(int)
    comp["median m above MHHW"] = comp["median m above MHHW"].map("{:.2f}".format)
    by_cty, hist, by_huc = km_tables(p, hucs)
    fp = band[band.prone].assign(lower=lambda d: d.km < p.split)
    split_cty = fp.groupby(["state", "county"]).lower.mean()
    straddle = [f"{c} ({s}, {v:.0%} lower)" for (s, c), v in split_cty.items() if 0.1 < v < 0.9]
    whole = "; ".join(f"{b}: " + ", ".join(f"{c} ({s})" for (s, c), v in split_cty.items() if (v >= 0.9 if b == "lower" else v <= 0.1))
                      for b in ("lower", "upper"))  # fmt: skip
    zero = int(((f.km < 0.5) & p.prone).sum())
    fl_ha = pd.DataFrame([{"band": bd, "state": s, "ha": f.ha[(p.sp["tide"][yr] == 1) & (lower == (bd == "lower")) & (st == s)].sum()}
                          for yr in p.spring for bd in ("lower", "upper") for s in STATES])  # fmt: skip
    de_share = fl_ha.pivot_table(index="band", columns="state", values="ha", aggfunc="sum")
    de_share = (de_share["DE"] / de_share.sum(axis=1)).map("{:.0%}".format)
    springs = list(p.spring)
    n_next = sum(yr + 1 in p.spring for yr in springs)
    no_chronic = [s for s, q in parts.items() if q["no_chronic"]]
    chronic_txt = (f" **{', '.join(no_chronic)} has no chronic flag in this build, so its fields wet on ordinary high tides"
                   " are KEPT** (NJ's are dropped): its flood-prone share is not comparable to NJ's." if no_chronic else "")  # fmt: skip
    n_by = f.groupby(st).size()
    prone_by = p.prone.groupby(st).sum()
    name = " + ".join(f"{s} storm_panel{t}" for s, t in tags.items())
    return f"""# Is it salt? Pooled NJ + DE: bay position, tide vs rain, recovery ({name})

Generated by `scripts/salt_tests.py --de-tag` (design and pooling choices in its docstring). Descriptive; no
regression. The main effect of a spring storm tide on crop mix is not detectable (FINDINGS §53, §57) and the field
flags are noisy (§58), so these splits can show a pattern consistent with salt, not prove it, and a null says little.

**Pooling.** Both states' builds hold the same {len(parts[STATES[0]]["storms"])} storm tides (the same Ship John peaks), the same
{len(springs)} spring storms and the same quiet years. A flooded field is compared only with prone-dry fields of its own state
(height reweighting by state x height bin), so "all" is a mix of the two within-state contrasts, weighted by flooded
area; a state with fewer than {MIN_FIELDS} flooded or comparison fields in a storm sits that storm out of "all". Each table
also gives NJ and DE alone (same code, same bootstrap draws; the NJ rows equal the NJ-only report). "*": some resamples
left a group empty and are left out of that interval ({n_star} cells; `nan_draws` in the csv).

**Fields:** {n_by["NJ"]:,} NJ and {n_by["DE"]:,} DE main-sample fields (low crop fields, not wet on ordinary high tides),
{int(prone_by["NJ"])} and {int(prone_by["DE"])} of them flood-prone.{chronic_txt} Distance up the estuary from the bay mouth (km along
the shipping channel, one axis for both shores; Ship John Shoal ≈ 57, Reedy Point ≈ 91, Delaware Memorial Bridge ≈ 110).
{zero} flood-prone fields lie seaward of the axis's start (near Lewes) and read 0 km. Split at {p.split:.0f} km.

### Where the fields sit (flood-prone fields; km up the estuary)

{md_table(by_cty)}

Flood-prone fields per {KM_BIN:.0f} km, by state:

{md_table(hist)}

### Bands: what each holds

{md_table(comp)}

Delaware's share of the flooded area, summed over the spring storms: lower band {de_share["lower"]}, upper {de_share["upper"]}
("all" weights each state by its flooded area, before any state sits a storm out).
Counties split by the band edge: {"; ".join(straddle) or "none: each band is a set of whole counties"}. Whole counties per band
(at least 90% of their flood-prone fields): {whole}.

## Fields per storm (by state; each state's flooded fields are compared with its own prone-dry ones)

{md_table(counts_pooled(p))}

## 1. Bay position (tide only; flooded vs prone-dry within the same band and state)

Same season (k = 0):

{tab("bay position", 0)}

Next season (k = 1):

{tab("bay position", 1)}

**Dose** (flooded share of the field; each bin against the band's prone-dry fields), same season:

{tab("dose", 0)}

## 2. Tide vs rain (each against fields dry in both, flooded by another storm)

Same season:

{tab("tide vs rain", 0)}

Next season:

{tab("tide vs rain", 1)}

## 3. Recovery (tide only, all bands; k = seasons after the storm)

{md_table(rec_t)}

"Clean" storms (no spring storm of their own in Y+1 .. Y+k): {"; ".join(f"k={c.k}: {c.which or 'none'}" for c in clean.itertuples())}.
Yes/no outcomes stop before CDL's 2024 change (the two left flags before 2023), so later k have fewer storms.

## Caveats

- **Bay position is not only salinity.** Each band still holds whole counties (table above), now from two states, so
  a band difference that shows in BOTH states' own rows is harder to put on one county's farms, soils or dikes; one
  that shows in only one state is that state's (or county's) difference.
- **Two models, two maps.** Each state's flags come from its own SFINCS grid, forced on its own shore's tide (the two
  differ by ~0.11 m of range mid-bay, FINDINGS §51), with its own model errors (DE storm peaks: §61 for the build in
  use), and DE fields are FirstMap polygons, NJ's NJDEP ones. Comparisons stay within a state for that reason.
- **Rain-only flags are unchecked** and few; rain may also fall on fields already wet from the tide.
- **Recovery mixes with the next storm** in most years ({n_next} of the {len(springs)} spring storms are followed by another the
  next season), and the clean subsets are one or two storms.
- **Small groups, many cells:** a few large fields carry much of the area (the flooded groups behave like
  {eff_rng} fields per storm in the band tests); contrasts with fewer than {MIN_FIELDS} fields in either group are left out.
  With ~{n_cells} intervals in this report, several will exclude zero by chance alone.

## Appendix: flood-prone fields by watershed (HUC12 of the field's centroid), km up the estuary

{md_table(by_huc)}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", default="")
    ap.add_argument("--de-tag", default="", help="pool with Delaware's sandy_panel_D / storm_panel_D build")
    ap.add_argument("--split-km", type=float, default=SPLIT_KM, help="lower / upper band edge, km up the estuary")
    a = ap.parse_args()
    tag = f"_{a.tag}" if a.tag else ""
    sandy, storm = SANDY.with_name(f"sandy_panel{tag}"), STORM.with_name(f"storm_panel{tag}")
    split = "" if a.split_km == SPLIT_KM else f"_split{a.split_km:g}"
    parts = {"NJ": load_state(sandy, storm)}
    if a.de_tag:
        parts["DE"] = load_state(SANDY.with_name(f"sandy_panel_{a.de_tag}"), STORM.with_name(f"storm_panel_{a.de_tag}"))
    p = Panel.from_parts(parts, a.split_km)
    res = run_all(p)
    if a.de_tag:
        res.to_csv(storm / f"salt_tests_{a.de_tag}{split}.csv", index=False, float_format="%.4f")
        out = config.REPORTS / f"salt_tests{tag}_{a.de_tag}{split}.md"
        out.write_text(report_pooled(p, res, {"NJ": tag, "DE": f"_{a.de_tag}"}, parts, field_hucs(parts)))
        print(counts_pooled(p).to_string())
    else:
        res.to_csv(storm / f"salt_tests{split}.csv", index=False, float_format="%.4f")
        out = config.REPORTS / f"salt_tests{tag}{split}.md"
        out.write_text(report(p, res, tag))
        print(counts(p).to_string(index=False))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
