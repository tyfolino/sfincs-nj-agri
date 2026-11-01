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
    derived = pd.concat(
        {"main_changed": panel.switched(wide), "left_cropland": panel.left_cropland(crop)}, axis=1
    ).stack(level=1, future_stack=True)
    derived.index.names = ["field_id", "year"]
    out = (fs[["field_id", "year", *FLOOD_COLS]]
           .merge(main, on=["field_id", "year"], how="outer", validate="1:1")
           .merge(derived.reset_index(), on=["field_id", "year"], how="left", validate="1:1"))  # fmt: skip
    for c in ("main_changed", "left_cropland"):
        out[c] = out[c].astype("Int64")
    out = out.sort_values(["field_id", "year"])
    assert len(out) == len(fy) == len(fs), "field x year tables do not line up"

    fe = pd.read_csv(SANDY / "field_event.csv").sort_values(["field_id", "peak"])
    return f.reset_index().round(ROUND), out.round(ROUND), fe.round(ROUND)


def readme(f: pd.DataFrame, fy: pd.DataFrame, fe: pd.DataFrame, est: pd.DataFrame) -> str:
    low, main = int(f.low_crop.sum()), int(f.main_sample.sum())
    high = f[f.m_above_mhhw >= panel.MAX_H]
    all_ = est[(est.storm == "all") & (est["flooded by"] == "tide") & (est.comparison == "prone-dry")]
    crops = all_[all_.outcome.isin(["corn", "soybeans", "cropland"])]
    mc = all_[(all_.outcome == "main crop changed") & (all_.k == 0)].iloc[0]
    sample = f[f.main_sample == 1]
    prone = int(((f.main_sample == 1) & (f.n_storms_tide > 0)).sum())
    spring = fy.dropna(subset=["spring_storm"]).groupby("spring_storm").year.first().sort_values()
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
| `docs/` | every column defined |

Join on `field_id` (and `year`; for `field_storm.csv`, `first_cdl_year` or `season_year`).

## Which fields to use

- `main_sample = 1` ({main:,} fields): low (< 1.5 m above high tide), mostly cropland in
  2008-12, and not already wet on ordinary tides. {prone:,} of them flood in at least one storm.
- `low_crop = 1` ({low:,}) also keeps the {low - main:,} fields ordinary tides already wet (`chronic = 1`).

Of the {len(high):,} fields at {panel.MAX_H} m or higher, {int((high.n_storms_tide > 0).sum())} flood on a storm tide alone; counting rain, {int((high.n_storms_rain > 0).sum()):,} do.

The main sample is uneven: median {sample.ha.median():.2f} ha (a model cell is about 1 ha), and the 10 largest
fields hold {sample.ha.nlargest(10).sum() / sample.ha.sum():.0%} of its area. {int(sample.county.str.contains("Glouc").sum())} of its fields are in Gloucester, on the river.

## Key columns (`field_year.csv`)

Flooded = at least 10% of the field under more than 5 cm. Every storm tide of at least
1.68 m NAVD88 recorded at Ship John Shoal in 2008-2025 is modelled ({fe.groupby(["event", "peak"]).ngroups} in this build), all year round.

By growing season (April-October; November-March before it is the non-growing season, so a
December storm counts toward the next year):
- `grow_tide`, `nongrow_tide`: 1 if a storm tide in that season flooded the field.
- `grow_n_tide`, `nongrow_n_tide`: how many; `grow_months_tide`, `nongrow_months_tide`: which
  months (e.g. `8`, or `4;8` for two storms).
- `grow_rain`, `nongrow_rain`: the same, counting the storm's rain too.
- `grow_peak_m`, `nongrow_peak_m`: the season's highest water at Ship John (m), for weaker storms.

By planting (the first cut, used in `results/`):
- `spring_tide`: 1 if that year's spring (Mar-Jun) storm tide flooded the field. Spring storms:
  {", ".join(map(str, spring.values))}.
- `off_tide`: 1 if a storm the previous Jul-Feb flooded it (before this year's planting).
- `spring_rain`, `off_rain`: the same, counting the storm's rain too.
- `share_corn`, `share_soybeans`, ..., `cropland`: share of the field in each crop that year.
- `main_class`: the field's largest land use. `main_changed`: 1 if it differs from last year.
- `left_cropland`: 1 if the field went from at least half cropland to under half, for 2+ years.

**CDL has breaks.** USDA changed how it makes the crop map in 2024, and `left_cropland` also spikes
in 2011, on upland too. In the main sample `left_cropland` is {100 * fy[(fy.year == 2024) & fy.field_id.isin(sample.field_id)].left_cropland.mean():.0f}% in 2024 and `main_changed` {100 * fy[(fy.year == 2024) & fy.field_id.isin(sample.field_id)].main_changed.mean():.0f}%.
Use year effects and compare fields within a year.

## What we found

We could not detect a change in crop mix from a spring storm tide in the flood model's map. Against
fields of the same heights that flood in other storms but not this one, pooled differences in corn,
soybeans and cropland, that season or the next, are at most {crops.pp.abs().max():.1f} percentage points, with
intervals from {crops.lo.min():+.1f} to {crops.hi.max():+.1f}. Against never-flooded fields, next-season cropland is about −3,
much of it USDA's 2024 change.

**That is not evidence of no effect.** The flood map is a model result, noisy field by field, which
hides real differences, and its flooded area has not been checked against satellite images on this
version. The model moves surface water only, so "flooded" does not mean salt damage. CDL records
what was grown, not yield. "Missed" means missed by this storm: many comparison fields flooded in
the months before.

"Main crop changed" reads higher on flooded fields ({mc.pp:+.0f} points the same season, interval {mc.lo:+.0f} to
{mc.hi:+.0f}), but it moves a lot with the baseline years, so it is not settled. Details and caveats in
`results/storm_panel.md`.

Flood runs use the latest model version: rebuilt creek channels, water levels from NOAA gauges, and
wind (a 3 km analysis from 2016; before that, a coarser reanalysis scaled up 30%, which still reads
low at the peak of a storm). More fields flood than in the earlier tables. We have not yet explained
why.
"""


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
        shutil.copy2(src / "README.md", out / f"docs/{name}_README.md")
    (out / "README.md").write_text(readme(f, fy, fe, pd.read_csv(STORM / "estimates.csv")))
    print(f"wrote {out}: {len(f):,} fields, {len(fy):,} field-years, {len(fe):,} field-storms")


if __name__ == "__main__":
    main()
