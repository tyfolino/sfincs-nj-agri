"""Copy the storm land-use panel (FINDINGS §34, §35, §37) into a stand-alone bundle for the
ag-econ colleague: one field table, one field x year table, one field x storm table, the
descriptive estimates, and a short README written for someone who has not seen this repo.
The bundle is its own git repo (config.RELEASE_DIR); data/insurance/ is never read.

Inputs: data/analysis/sandy_panel/ (scripts/build_sandy_panel.py) and data/analysis/storm_panel/
(scripts/build_storm_panel.py, scripts/plot_storm_panel.py). Full column definitions stay in
those two folders' READMEs.

Writes, under the bundle directory:
  data/fields.csv, data/fields.gpkg   one row per field: static attributes + sample flags
  data/field_year.csv                 one row per field x CDL year: flooding + land use
  data/field_storm.csv                one row per field x modelled storm it wets
  results/                            reports/storm_panel.md, its figure and estimates.csv
  code/                               plot_storm_panel.py and agri_sfincs/panel.py (reference)
  docs/                               those two folders' READMEs (every column)
  README.md
Existing files in the bundle are overwritten; anything else there (e.g. .git) is left alone.
``--tag T``: the sandy_panel_T / storm_panel_T build and its storm_panel_T report.
Usage:  python scripts/export_storm_panel.py [--out DIR] [--tag m65]
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from agri_sfincs import config, panel

SANDY, STORM = config.ANALYSIS_DIR / "sandy_panel", config.ANALYSIS_DIR / "storm_panel"
ROUND = 4  # decimals kept for shares and metres
SEASON_COLS = [f"{s}_{c}" for s in ("grow", "nongrow")
               for c in ("peak_m", "tide", "rain", "n_tide", "months_tide", "unmodelled_m")]  # fmt: skip
FLOOD_COLS = [*SEASON_COLS, "spring_peak_m", "spring_storm", "spring_tide", "spring_rain", "spring_tide_maxd_m",
              "off_tide", "off_rain", "off_unmodelled_m", "floods_before_tide"]  # fmt: skip


def build():
    f = pd.read_csv(SANDY / "fields.csv").set_index("field_id")
    fy = pd.read_csv(SANDY / "field_year.csv")
    fs = pd.read_csv(STORM / "field_season.csv")
    fl = pd.read_csv(STORM / "fields_storm.csv").set_index("field_id")

    f = f.join(fl[["n_storms_tide", "n_storms_rain", "chronic", "chronic_share"]])
    f["low_crop"] = panel.low_crop_fields(f, fy).astype(int)
    f["main_sample"] = ((f.low_crop == 1) & (f.chronic == 0)).astype(int)

    main = fy.assign(main_class=fy[panel.CLASSES].idxmax(axis=1).str.removeprefix("share_"))
    wide = main.pivot(index="field_id", columns="year", values="main_class")
    crop = fy.pivot(index="field_id", columns="year", values="cropland")
    farm = fy.assign(farmland=panel.farmland(fy)).pivot(index="field_id", columns="year", values="farmland")
    derived = pd.concat(
        {"main_changed": panel.switched(wide), "left_cropland": panel.left_cropland(crop),
         "left_farmland": panel.left_cropland(farm)}, axis=1
    ).stack(level=1, future_stack=True)
    derived.index.names = ["field_id", "year"]
    out = (fs[["field_id", "year", *FLOOD_COLS]]
           .merge(main, on=["field_id", "year"], how="outer", validate="1:1")
           .merge(derived.reset_index(), on=["field_id", "year"], how="left", validate="1:1"))  # fmt: skip
    for c in ("main_changed", "left_cropland", "left_farmland"):
        out[c] = out[c].astype("Int64")
    out = out.sort_values(["field_id", "year"])
    assert len(out) == len(fy) == len(fs), "field x year tables do not line up"

    fe = pd.read_csv(SANDY / "field_event.csv").sort_values(["field_id", "peak"])
    return f.reset_index().round(ROUND), out.round(ROUND), fe.round(ROUND)


#: Heads each copied column README: they describe our working folders, not this bundle's layout.
DOC_NOTE = """> **In this bundle:** these notes describe our working folders. `field_season.csv` and the land-use part
> of `field_year.csv` are merged into `data/field_year.csv`; `fields_storm.csv` is merged into
> `data/fields.csv`; `field_event.csv` is `data/field_storm.csv`; paths like `../sandy_panel/` mean `data/`.
> `main_class`, `main_changed`, `left_cropland`, `left_farmland`, `low_crop` and `main_sample` are defined in the top README.
> "FINDINGS §" points to our internal notes: ask us if you need one.

"""


def readme(f: pd.DataFrame, fy: pd.DataFrame, fe: pd.DataFrame, est: pd.DataFrame, sens: pd.DataFrame) -> str:
    low, main = int(f.low_crop.sum()), int(f.main_sample.sum())
    high = f[f.m_above_mhhw >= panel.MAX_H]
    all_ = est[(est.storm == "all") & (est["flooded by"] == "tide") & (est.comparison == "prone-dry")]
    mc = all_[(all_.outcome == "main crop changed") & (all_.k == 0)].iloc[0]
    mc_rain = est[(est.storm == "all") & (est["flooded by"] == "rain") & (est.comparison == "prone-dry")
                  & (est.outcome == "main crop changed") & (est.k == 0)].iloc[0]  # fmt: skip
    nv = est[(est.storm == "all") & (est["flooded by"] == "tide") & (est.comparison == "never") & (est.k == 1)
             & (est.outcome == "cropland")].iloc[0]  # fmt: skip
    lc = {int(x.k): x for x in all_[all_.outcome == "left cropland"].itertuples()}
    lf = {int(x.k): x for x in all_[all_.outcome == "left farmland"].itertuples()}
    never_all = est[(est.storm == "all") & (est["flooded by"] == "tide") & (est.comparison == "never")]
    lf_nv = {int(x.k): x for x in never_all[never_all.outcome == "left farmland"].itertuples()}
    never = f[(f.main_sample == 1) & (f.n_storms_tide == 0)]
    ci = lambda x: f"{x.pp:+.1f} [{x.lo:+.1f}, {x.hi:+.1f}]"  # noqa: E731
    pick = lambda c, comp, k, o: sens[(sens.check == c) & (sens.comparison == comp) & (sens.k == k) & (sens.outcome == o)].iloc[0]  # noqa: E731
    pre = sens[(sens.check == "before change") & (sens.comparison == "prone-dry") & sens.outcome.isin(["corn", "soybeans", "cropland"])]
    nv_pre, nv_eq = pick("before change", "never", 1, "cropland"), pick("before change, every field once", "never", 1, "cropland")
    grass, mc_eq = pick("every field once", "prone-dry", 0, "grass (hay + pasture + idle)"), pick("every field once", "prone-dry", 0, "main crop changed")
    drops = sens[sens.check.str.contains("without")]
    wo = ", ".join(f"{c.rsplit(' ', 1)[1]}: {ci(x)}" for c, x in zip(drops.check, drops.itertuples()))
    eff = est[(est.storm != "all") & (est["flooded by"] == "tide") & (est.k == 0) & (est.outcome == "corn")]
    eff_r = {c: f"{eff[eff.comparison == c].eff_comparison.min():.0f}-{eff[eff.comparison == c].eff_comparison.max():.0f}" for c in ("never", "prone-dry")}
    sample = f[f.main_sample == 1]
    prone = int(((f.main_sample == 1) & (f.n_storms_tide > 0)).sum())
    spring = fy.dropna(subset=["spring_storm"]).groupby("spring_storm").year.first().sort_values()
    lc_eq, lf_eq = pick("every field once", "never", 1, "left cropland"), pick("every field once", "never", 1, "left farmland")
    pd_eq = pick("before change, every field once", "prone-dry", 1, "cropland")
    peak_share = fe.groupby("field_id").tide_share.max().reindex(sample.field_id).fillna(0).values
    at = {s: (int((peak_share >= s).sum()), sample.ha.values[peak_share >= s].sum()) for s in (0.05, 0.10, 0.25, 0.50)}
    back_any, back_end = back_rate(fy, sample.field_id)
    return f"""# Bayshore storm panel

Map polygons farmed in 2012 (NJDEP land-use map; not farms) on the Delaware-draining side of Salem,
Cumberland and Gloucester counties, NJ, {fy.year.min()}-{fy.year.max()}: was the field flooded by a storm tide that year (from our SFINCS flood model), and what was
grown on it (USDA Cropland Data Layer, CDL). Public data plus our model runs.

## Files

| file | one row per |
|---|---|
| `data/field_year.csv` | field x year ({len(fy):,} rows): flooding + crops. **Start here.** |
| `data/fields.csv` | field ({len(f):,}): county, size, height, soils, sample flags. `fields.gpkg` = polygons |
| `data/field_storm.csv` | field x storm tide it wets (no row = stayed dry, tide and rain; key `event` + `peak`): flooded share and depth, the peak's date, month and season |
| `results/` | what we found so far (descriptive, no regression yet) |
| `docs/` | column definitions; the flood and land-use columns of the tables above |

Join on `field_id` (and `year`; for `field_storm.csv`, `first_cdl_year` or `season_year`).

## Which fields to use

- `main_sample = 1` ({main:,} fields): low (median height < 1.5 m above average higher high tide, 2021-25), at
  least half cropland in 2008-12 (a window that holds the 2010-12 storms, so early leavers are screened out), and not
  wet on the highest tides of an ordinary month in the model. {prone:,} of them flood in at least one modelled storm
  tide at the 10% line; {at[0.05][0]} at 5%, {at[0.25][0]} at 25%, {at[0.50][0]} at 50% ({at[0.05][1]:,.0f}, {at[0.10][1]:,.0f}, {at[0.25][1]:,.0f} and {at[0.50][1]:,.0f} ha at 5, 10, 25, 50%). Estimates
  have not been rerun at other lines, and the count is sensitive to this one: try `tide_share` in `field_storm.csv`.
- `low_crop = 1` ({low:,}) also keeps the {low - main:,} fields (`chronic = 1`) the model wets on those ordinary high
  tides in one simulated month (perhaps partly an error in the model, on small marsh-edge fields).

Of the {len(high):,} fields at {panel.MAX_H} m or higher, {int((high.n_storms_tide > 0).sum())} flood on a storm tide alone; counting rain, {int((high.n_storms_rain > 0).sum()):,} do.

Dikes are as they stand today for every year, mapped from elevation data, not surveyed, and gate sizes are assumed. So a
2010 flood means "a 2010 tide on today's banks".

The main sample is uneven: median {sample.ha.median():.2f} ha (a model grid square is about 1 ha), and the 10 largest
fields hold {sample.ha.nlargest(10).sum() / sample.ha.sum():.0%} of its area. {int(sample.county.str.contains("Glouc").sum())} of its fields are in Gloucester, on the river.

## Key columns (`field_year.csv`)

Flooded = at least 10% of the field under more than 5 cm in the model. 0 means no modelled flood, not dry: tides just
under the line are not modelled. Every storm tide (high water from any cause) of at least
1.68 m NAVD88 in our series for the Ship John Shoal gauge in the bay (gauge plus estimates where it was out: 2008-09, 2021; heights
uncertain by about 0.1 m), 2008-2025, is modelled ({fe.groupby(["event", "peak"]).ngroups} in this build), all year round.

By growing season (April-October; November-March before it is the non-growing season, so a
December storm counts toward the next year):
- `grow_tide`, `nongrow_tide`: 1 if a storm tide in that season flooded the field.
- `grow_n_tide`, `nongrow_n_tide`: how many; `grow_months_tide`, `nongrow_months_tide`: which
  months (e.g. `8`, or `4;8` for two storms).
- `grow_rain`, `nongrow_rain`: the same, counting the storm's rain too. Only rain during these storm-tide runs: not a
  general rain-flood measure, and not checked against observations.
- `grow_peak_m`, `nongrow_peak_m`: the season's highest water at Ship John (m), for weaker storms.

By planting (the first cut, used in `results/`):
- `spring_tide`: 1 if a storm tide in March-June of that year flooded the field (the season, not the tide cycle). Spring storms:
  {", ".join(map(str, spring.values))}.
- `off_tide`: 1 if a storm the previous Jul-Feb flooded it (before this year's planting).
- `spring_rain`, `off_rain`: the same, counting the storm's rain too.
- `share_corn`, `share_soybeans`, ..., `cropland`: share of the field in each crop that year.
- `main_class`: the field's largest land use. `main_changed`: 1 if it differs from last year (an ordinary corn-soybean
  rotation counts).
- `left_cropland`: 1 if the field went from at least half cropland to under half, for 2+ years. Cropland includes hay and
  idle land.
- `left_farmland`: the same on cropland + pasture. By area it removes most of the 2013 jump and much of 2024's, but not
  2011's or 2019's, and 2024 is still high. It can hide a field given up to grass.

**Neither flag means the field stopped farming; use both.** Two years out is all they require. Of `left_cropland` flags
through 2022 in the main sample, {back_any:.0f}% come back to at least half cropland at some point, and {back_end:.0f}% are there in 2023. A
field can be flagged twice, and abandoned grass labelled hay triggers neither. In a small aerial-photo check of low fields
(30 across NJ and Delaware, one reader, one later photo each, exits 2010-19), none of the 9 flagged by both was clearly
abandoned and 5 still looked farmed (5 of 7 in NJ). Too few to set a rate.

**CDL has breaks.** USDA changed how it makes the crop map in 2024, and `left_cropland` also jumps
in 2011-13 and 2019, on upland too (2011 by field count, 2013 by area). In the main sample `left_cropland` is {100 * fy[(fy.year == 2024) & fy.field_id.isin(sample.field_id)].left_cropland.mean():.0f}% in 2024 and `main_changed` {100 * fy[(fy.year == 2024) & fy.field_id.isin(sample.field_id)].main_changed.mean():.0f}%.
A `left_cropland` flag in 2023 also reads the 2024 map. Use year effects and compare fields within a year.

## What we found

Numbers are percentage points of field area: each field against its own average in nearby years without a modelled
flood, flooded minus comparison, reweighted to the same height mix. Brackets are 95% intervals from resampling fields.
Flooded groups are repeat-flood fields, and the baseline does not remove a different trend.

By area, we could not detect a change in crop mix from a spring storm tide in the flood model's map. In our
main comparison (storm tide alone; flooded fields against fields of similar height this storm missed but
others flood), pooled differences in corn, soybeans and cropland, that season or the
next, have intervals that include zero. Without 2024 and later they are at most {pre.pp.abs().max():.1f} percentage points,
with intervals from {pre.lo.min():+.1f} to {pre.hi.max():+.1f}. Counting every field once instead, same-season grass (hay + pasture + idle; {ci(grass)})
and main crop changed ({ci(mc_eq)}) exclude zero, and without 2024 and later so does next-season cropland ({ci(pd_eq)}), so the gap
below is not only against never-flooded fields. These intervals do not bound the effect of flooding: they may be too narrow,
random errors in the modelled flooding would shrink differences toward zero, errors tied to place could also create them, and
the comparison fields also flood in other storms.

Against fields none of the {fe.groupby(["event", "peak"]).ngroups} storm tides floods on tide alone ({int((never.n_storms_rain > 0).sum())} of these {len(never)} do flood with
rain), next-season cropland is {nv.pp:+.1f} [{nv.lo:+.1f}, {nv.hi:+.1f}]. We have not explained this, and it is not a stable number.
Without 2024 and later ({int(nv_pre.storms)} storms) it is {ci(nv_pre)}, or {ci(nv_eq)} counting every field once; the {int(nv_pre.storms)}-storm and full figures are different
storm sets that happen to agree. Leaving one of those storms out by area: {wo}.

Neither exit flag shows flooded fields leaving more in our main comparison, by area: left cropland {lc[0].pp:+.1f} [{lc[0].lo:+.1f}, {lc[0].hi:+.1f}] the
same season and {lc[1].pp:+.1f} [{lc[1].lo:+.1f}, {lc[1].hi:+.1f}] the next; left farmland {lf[0].pp:+.1f} [{lf[0].lo:+.1f}, {lf[0].hi:+.1f}] and {lf[1].pp:+.1f} [{lf[1].lo:+.1f}, {lf[1].hi:+.1f}], leaving out 2023 on because a 2023
flag needs the 2024 map. Against never-flooded fields, left farmland is {lf_nv[0].pp:+.1f} [{lf_nv[0].lo:+.1f}, {lf_nv[0].hi:+.1f}] and {lf_nv[1].pp:+.1f} [{lf_nv[1].lo:+.1f}, {lf_nv[1].hi:+.1f}]. But with every field counted
once against never-flooded fields, next-season exits read slightly higher: left cropland {lc_eq.pp:+.1f} [{lc_eq.lo:+.2f}, {lc_eq.hi:+.1f}], left farmland {lf_eq.pp:+.1f} [{lf_eq.lo:+.2f}, {lf_eq.hi:+.1f}],
barely excluding zero among many rows, beside the cropland gap above. Exits are rare (about 1% a year in quiet years) and these
flags are noisy. **Not a finding either way.**

**That is not evidence of no effect.** The flood map is a model result, noisy field by field, which
could hide real differences. Satellite water on this version (MNDWI, 3 Landsat and 4 Sentinel-2 scenes, hours to 1.5 days after the peak) is informative mainly in
cool-season scenes. On low fields in April 2011, January 2024 and March 2024, the model has 20-59% of the water the satellites
see at the overpass hour, and they confirm 4-11% of the model's water. Field by field at the 10% line, few agree (January 2024: 234
fields seen, 209 modelled, 16 both). Satellites miss water under crops and water that has drained, so this is not an error rate, but
do not read the field flags as observed floods. Peak water has been compared with three creek-mouth gauges for 7 storm tides in 2018-25, only 3 of them spring
storms (mean errors about 0.1 m, high on the Maurice and Cohansey, low on the Alloway); that does not test water on fields,
and the 2010-14 storms are unchecked. The model moves surface water only, so "flooded" does not mean salt damage. CDL is USDA's
satellite estimate of the crop, noisy on small fields; it does not measure yield. "Missed" means
missed by this storm: in 2022, 90% of comparison fields had flooded in the months before (46% in 2024;
0-7% in the other storms). In 2012 and 2024, flooded fields had flooded before far more often than
the comparison, so those storms are not clean single-flood tests.

"Main crop changed" reads higher on flooded fields ({mc.pp:+.0f} points the same season, interval {mc.lo:+.0f} to
{mc.hi:+.0f}; with rain counted, {mc_rain.pp:+.0f} [{mc_rain.lo:+.0f}, {mc_rain.hi:+.0f}]). It is much smaller if every field counts equally and
changes a lot with the 2-4 baseline years used. **Not a finding yet.** Results against never-flooded fields rest on as few
fields, in effect, as the main comparison ({eff_r["never"]} vs {eff_r["prone-dry"]} per storm, since a few large fields dominate), so lean on neither. Details and caveats in `results/storm_panel.md`.

Flood runs use model version `e3v2a30brm65_100m`: rebuilt creek channels, water levels from NOAA gauges along the bay with
estimated points where there is no gauge, and wind (a 3 km weather product from 2016; before that, coarser wind data scaled up
30%, which still underestimates peak winds). So the earlier and later storms are not treated alike. More fields flood than in
the earlier tables. On a one-month ordinary-tide test the rise was mostly the new bay water levels, with some from the rebuilt
creeks, and much of its size in field counts comes from fields just crossing the 10% line; this is not yet tested on the storm runs.
"""


def back_rate(fy: pd.DataFrame, ids) -> tuple[float, float]:
    """Of ``left_cropland`` flags through 2022 on these fields: % back at >= 50% cropland at some
    later year to 2023, and % at >= 50% in 2023 itself."""
    d = fy[fy.field_id.isin(ids)]
    w = d.pivot(index="field_id", columns="year", values="cropland")
    fl = d[(d.left_cropland == 1) & (d.year <= 2022)]
    later = [(w.loc[r.field_id, [t for t in w.columns if r.year < t <= 2023]] >= panel.LEFT_THR).any() for r in fl.itertuples()]
    return 100 * np.mean(later), 100 * np.mean([w.loc[r.field_id, 2023] >= panel.LEFT_THR for r in fl.itertuples()])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=config.RELEASE_DIR)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    global SANDY, STORM
    out, tag = a.out, f"_{a.tag}" if a.tag else ""
    SANDY, STORM = SANDY.with_name(f"sandy_panel{tag}"), STORM.with_name(f"storm_panel{tag}")
    for d in ("data", "results/figs", "code", "docs"):
        (out / d).mkdir(parents=True, exist_ok=True)

    f, fy, fe = build()
    f.to_csv(out / "data/fields.csv", index=False)
    fy.to_csv(out / "data/field_year.csv", index=False)
    fe.to_csv(out / "data/field_storm.csv", index=False)
    shutil.copy2(SANDY / "fields.gpkg", out / "data/fields.gpkg")
    md = (config.REPORTS / f"storm_panel{tag}.md").read_text()
    (out / "results/storm_panel.md").write_text(md.replace(f"figs/storm_panel{tag}.png", "figs/storm_panel.png"))
    shutil.copy2(config.REPORTS / f"figs/storm_panel{tag}.png", out / "results/figs/storm_panel.png")
    shutil.copy2(STORM / "estimates.csv", out / "results/storm_panel_estimates.csv")
    shutil.copy2(config.ROOT / "scripts/plot_storm_panel.py", out / "code/plot_storm_panel.py")
    shutil.copy2(config.ROOT / "agri_sfincs/panel.py", out / "code/panel.py")
    for src, name in ((SANDY, "fields"), (STORM, "storm_panel")):
        (out / f"docs/{name}_README.md").write_text(DOC_NOTE + (src / "README.md").read_text().replace(" (once all 18 are in)", ""))
    shutil.copy2(STORM / "sensitivity.csv", out / "results/storm_panel_sensitivity.csv")
    (out / "README.md").write_text(readme(f, fy, fe, pd.read_csv(STORM / "estimates.csv"), pd.read_csv(STORM / "sensitivity.csv")))
    print(f"wrote {out}: {len(f):,} fields, {len(fy):,} field-years, {len(fe):,} field-storms")


if __name__ == "__main__":
    main()
