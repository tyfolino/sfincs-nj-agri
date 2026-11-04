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

Writes reports/salt_tests[_T].md and data/analysis/storm_panel[_T]/salt_tests.csv.
Usage:  python scripts/salt_tests.py [--tag m65]
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import numpy as np
import pandas as pd

from agri_sfincs import config, domain, panel
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


class Panel:
    def __init__(self, sandy, storm):
        self.f, self.y, self.sp, self.spring, self.quiet = panel.load(sandy, storm)
        g = gpd.read_file(sandy / "fields.gpkg").set_index("field_id").reindex(self.f.index)
        c = g.geometry.centroid
        self.f["km"] = domain.up_estuary_km(c.x.values, c.y.values, g.crs.to_epsg())
        ev = pd.read_csv(sandy / "field_event.csv")
        ev = ev[pd.to_datetime(ev.peak).dt.month.between(3, 6)]
        self.share = {yr: ev[ev.event == s].groupby("field_id").tide_share.max().reindex(self.f.index).fillna(0)
                      for yr, s in self.spring.items()}  # fmt: skip
        self.boot = np.random.default_rng(0).poisson(1.0, size=(len(self.f), N_BOOT)).astype(float)
        self.prone = self.f.n_storms_tide > 0

    def contrast(self, t: pd.Series, c: pd.Series, outcome: str, year: int, k: int):
        """flooded ``t`` - comparison ``c`` draws for one storm, or None (too few / no outcome)."""
        if t.sum() < MIN_FIELDS or c.sum() < MIN_FIELDS or year + k not in self.y[outcome].columns:
            return None
        d = panel.deviations(self.y[outcome], year, self.quiet, k)
        if d[t].isna().all() or d[c].isna().all():
            return None
        w = panel.height_weights(self.f.m_above_mhhw, self.f.ha, t, c)
        self.eff.append(panel.effective_n(w.where(t, 0.0) * d.notna()))
        return panel.estimate(d, w.where(t, 0.0), w.where(c, 0.0), self.boot)

    def pooled(self, groups, outcome: str, k: int, years=None):
        """Plain mean over the storms of ``groups(year) -> (t, c)``; (draws, n storms). The flooded
        groups' effective sizes (agri_sfincs.panel.effective_n) are kept in ``last_eff``."""
        self.eff = []
        ds = [e for yr in (years or self.spring) if (e := self.contrast(*groups(yr), outcome, yr, k)) is not None]
        self.last_eff = (min(self.eff), max(self.eff)) if self.eff else (np.nan, np.nan)
        return (np.mean(ds, axis=0), len(ds)) if ds else (None, 0)


def row(test: str, group: str, outcome: str, k: int, e, n: int, **kw) -> dict:
    if e is None:
        return {"test": test, "group": group, "outcome": outcome, "k": k, "storms": 0, **kw}
    return {"test": test, "group": group, "outcome": outcome, "k": k, "storms": n, "pp": e[0],
            "lo": np.percentile(e[1:], 2.5), "hi": np.percentile(e[1:], 97.5), **kw}  # fmt: skip


def run(p: Panel) -> pd.DataFrame:
    rows = []
    tide = lambda yr: p.sp["tide"][yr] == 1  # noqa: E731
    rain_only = lambda yr: (p.sp["rain"][yr] == 1) & ~tide(yr)  # noqa: E731
    dry = lambda yr: p.prone & ~tide(yr) & (p.sp["rain"][yr] != 1)  # noqa: E731
    lower = p.f.km < SPLIT_KM
    bands = {"lower (saltier)": lower, "upper (fresher)": ~lower}
    for o in OUTCOMES:
        for k in (0, 1):
            # 1. bay position
            band_e = {}
            for name, b in bands.items():
                e, n = p.pooled(lambda yr, b=b: (tide(yr) & b, p.prone & ~tide(yr) & b), o, k)
                band_e[name] = (e, n)
                rows.append(row("bay position", name, o, k, e, n, eff_lo=p.last_eff[0], eff_hi=p.last_eff[1]))
            (e, n), (u, m) = band_e["lower (saltier)"], band_e["upper (fresher)"]
            rows.append(row("bay position", "lower - upper", o, k, None if e is None or u is None else e - u, min(n, m)))
            for name, b in bands.items():
                for lo_s, hi_s in DOSE_BINS:
                    g = lambda yr, b=b, lo_s=lo_s, hi_s=hi_s: (tide(yr) & b & p.share[yr].between(lo_s, hi_s, inclusive="left"),
                                                              p.prone & ~tide(yr) & b)  # fmt: skip
                    e, n = p.pooled(g, o, k)
                    rows.append(row("dose", f"{name}, share {lo_s:.0%}-{min(hi_s, 1):.0%}", o, k, e, n))
            # 2. tide vs rain
            for name, t in (("tide", tide), ("rain only", rain_only)):
                e, n = p.pooled(lambda yr, t=t: (t(yr), dry(yr)), o, k)
                rows.append(row("tide vs rain", name, o, k, e, n))
        # 3. recovery
        springs = set(p.spring)
        for k in KS:
            e, n = p.pooled(lambda yr: (tide(yr), p.prone & ~tide(yr)), o, k)
            rows.append(row("recovery", "all storms", o, k, e, n))
            clean = [yr for yr in p.spring if not any(yr + j in springs for j in range(1, k + 1))]
            e, n = p.pooled(lambda yr: (tide(yr), p.prone & ~tide(yr)), o, k, clean)
            rows.append(row("recovery", "clean storms", o, k, e, n, which=" ".join(str(y) for y in clean)))
    return pd.DataFrame(rows)


def counts(p: Panel) -> pd.DataFrame:
    """Per storm: flooded fields and ha per band, rain-only fields."""
    out = []
    for yr, s in p.spring.items():
        t = p.sp["tide"][yr] == 1
        r = (p.sp["rain"][yr] == 1) & ~t
        lo = p.f.km < SPLIT_KM
        out.append({"storm": s, "year": yr, "flooded lower": int((t & lo).sum()), "flooded upper": int((t & ~lo).sum()),
                    "ha lower": round(p.f.ha[t & lo].sum()), "ha upper": round(p.f.ha[t & ~lo].sum()),
                    "rain only": int(r.sum()), "Y+1 storm": "yes" if yr + 1 in p.spring else ""})  # fmt: skip
    return pd.DataFrame(out)


def fmt(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["estimate"] = [f"{r.pp:+.1f} [{r.lo:+.1f}, {r.hi:+.1f}]" if r.storms else "too few" for r in d.itertuples()]
    return d


def report(p: Panel, res: pd.DataFrame, tag: str) -> str:
    f = p.f
    fl = f[f.n_storms_tide > 0]
    km = fl.km.quantile([0.1, 0.5, 0.9]).round(0)
    by = f.groupby(f.km < SPLIT_KM).agg(n=("ha", "size"), ha=("ha", "sum"), h=("m_above_mhhw", "median"))
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
percentile), median {km[0.5]:.0f}. Split at {SPLIT_KM:.0f} km: lower (saltier) {int(by.n[True])} fields, {by.ha[True]:,.0f} ha, median
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    tag = f"_{a.tag}" if a.tag else ""
    sandy, storm = SANDY.with_name(f"sandy_panel{tag}"), STORM.with_name(f"storm_panel{tag}")
    p = Panel(sandy, storm)
    res = run(p)
    res.to_csv(storm / "salt_tests.csv", index=False, float_format="%.4f")
    out = config.REPORTS / f"salt_tests{tag}.md"
    out.write_text(report(p, res, tag))
    print(counts(p).to_string(index=False))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
