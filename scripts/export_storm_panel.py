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
  README.md
Existing files in the bundle are overwritten; anything else there (e.g. .git) is left alone.
Usage:  python scripts/export_storm_panel.py [--out DIR]
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

from agri_sfincs import config, panel

SANDY, STORM = config.ANALYSIS_DIR / "sandy_panel", config.ANALYSIS_DIR / "storm_panel"
ROUND = 4  # decimals kept for shares and metres
FLOOD_COLS = ["spring_peak_m", "spring_storm", "spring_tide", "spring_rain", "spring_tide_maxd_m",
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


def readme(f: pd.DataFrame, fy: pd.DataFrame, fe: pd.DataFrame) -> str:
    low, main = int(f.low_crop.sum()), int(f.main_sample.sum())
    prone = int(((f.main_sample == 1) & (f.n_storms_tide > 0)).sum())
    spring = fy.dropna(subset=["spring_storm"]).groupby("spring_storm").year.first().sort_values()
    return f"""# Bayshore storm panel

Farm fields on the NJ Delaware Bay shore (Salem, Cumberland, Gloucester), {fy.year.min()}-{fy.year.max()}:
was the field flooded by a storm tide that year (from our SFINCS flood model), and what was
grown on it (USDA Cropland Data Layer, CDL). Public data plus our model runs.

## Files

| file | one row per |
|---|---|
| `data/field_year.csv` | field x year ({len(fy):,} rows): flooding + crops. **Start here.** |
| `data/fields.csv` | field ({len(f):,}): county, size, height, soils, sample flags. `fields.gpkg` = polygons |
| `data/field_storm.csv` | field x storm: flooded share and depth, for finer exposure measures |
| `results/` | what we found so far (descriptive, no regression yet) |

Join on `field_id` (and `year`).

## Which fields to use

- `main_sample = 1` ({main:,} fields): low (< 1.5 m above high tide), mostly cropland in
  2008-12, and not already wet on ordinary tides. {prone:,} of them flood in at least one storm.
- `low_crop = 1` ({low:,}) also keeps the 100 fields ordinary tides already wet (`chronic = 1`).

Fields higher up never flood in any modelled storm.

## Key columns (`field_year.csv`)

- `spring_tide`: 1 if that year's spring (Mar-Jun) storm tide flooded the field. Flooded = at
  least 10% of the field under more than 5 cm. Spring storms: {", ".join(map(str, spring.values))}.
- `off_tide`: 1 if a storm the previous Jul-Feb flooded it (before this year's planting).
- `spring_rain`, `off_rain`: the same, counting the storm's rain too.
- `share_corn`, `share_soybeans`, ..., `cropland`: share of the field in each crop that year.
- `main_class`: the field's largest land use. `main_changed`: 1 if it differs from last year.
- `left_cropland`: 1 if the field went from at least half cropland to under half, for 2+ years.

## What we found

Comparing fields a spring storm flooded with similar fields it missed: no clear change in corn,
soybeans or cropland, that season or the next (pooled differences within about ±4 percentage
points). Details and caveats in `results/storm_panel.md`.
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=config.RELEASE_DIR)
    out = ap.parse_args().out
    for d in ("data", "results/figs", "code"):
        (out / d).mkdir(parents=True, exist_ok=True)

    f, fy, fe = build()
    f.to_csv(out / "data/fields.csv", index=False)
    fy.to_csv(out / "data/field_year.csv", index=False)
    fe.to_csv(out / "data/field_storm.csv", index=False)
    shutil.copy2(SANDY / "fields.gpkg", out / "data/fields.gpkg")
    shutil.copy2(config.REPORTS / "storm_panel.md", out / "results/storm_panel.md")
    shutil.copy2(config.REPORTS / "figs/storm_panel.png", out / "results/figs/storm_panel.png")
    shutil.copy2(STORM / "estimates.csv", out / "results/storm_panel_estimates.csv")
    shutil.copy2(config.ROOT / "scripts/plot_storm_panel.py", out / "code/plot_storm_panel.py")
    shutil.copy2(config.ROOT / "agri_sfincs/panel.py", out / "code/panel.py")
    (out / "README.md").write_text(readme(f, fy, fe))
    print(f"wrote {out}: {len(f):,} fields, {len(fy):,} field-years, {len(fe):,} field-storms")


if __name__ == "__main__":
    main()
