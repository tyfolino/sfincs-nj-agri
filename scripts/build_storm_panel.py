"""Field x season flood exposure for the land-use test, from all modelled storm tides (FINDINGS
§35): replaces "Sandy with a 2008-12 baseline", which §35 showed is not clean (the same fields
flood in most storms, and in April 2011 before Sandy).

Fields = data/analysis/sandy_panel/fields.gpkg (scripts/build_sandy_panel.py): every LU/LC
polygon farmed in 2012. Season = CDL year t (2008-2025). Flooded = >= fieldflood.SHARE (10%)
of the field > 5 cm deep in the run (field_event.csv: one row per field x storm TIDE; dikes as
built today). Every storm tide >= panel.STORM_MIN at Ship John 2008-25 is modelled (18).

field_season.csv (one row per field x CDL year), two ways to cut the year:
  By growing season (Seowoo, 2026-10-26; panel.storm_season): grow = Apr-Oct of t, nongrow =
  Nov (t-1) - Mar (t), so a December storm counts toward the next year.
  grow_peak_m, nongrow_peak_m   Ship John's highest hourly level in that season (m NAVD88)
  grow_tide, grow_rain          flooded by a modelled storm tide of the season, tide only / with
  nongrow_tide, nongrow_rain    the storm's rain (0 if none)
  grow_n_tide, nongrow_n_tide   how many of the season's storm tides flood it (tide only)
  grow_months_tide, nongrow_months_tide   their peak months, e.g. "4" or "3;4" (blank if none)
  grow_unmodelled_m, nongrow_unmodelled_m highest UNMODELLED storm tide >= UNMODELLED_MIN in the
                     season (all are below STORM_MIN now), blank if none
  By planting (FINDINGS §35, the first cut):
  spring_peak_m      Ship John's highest hourly level in Mar-Jun of t (m NAVD88). Every spring
                     >= STORM_MIN is modelled; lower springs (2016 1.60, 2017 1.63, 2019 1.67,
                     2025 1.61) are not, and count as dry: below every modelled storm
  spring_storm       the modelled Mar-Jun storm run of t, or blank
  spring_tide, spring_rain   flooded by it, tide only / with the storm's rain (0 if none)
  spring_tide_maxd_m mean peak depth over the field's flooded pixels (deepest storm tide if two;
                     blank if not flooded)
  off_tide, off_rain flooded by a modelled storm of Jul (t-1) - Feb (t): the off-season before
                     the planting of t (panel.cdl_year)
  off_unmodelled_m   highest UNMODELLED storm tide >= UNMODELLED_MIN in that off-season, blank
                     if none
  floods_before_tide number of seasons before t with a modelled tide-only flood (spring or off)

fields_storm.csv (one row per field):
  n_storms_tide, n_storms_rain   modelled storm tides that flood it (of those in field_event.csv)
  chronic            flooded by ordinary spring tides (tide2024oct_intact_slr000, share >=
                     SHARE): wet every month, so a storm adds nothing (FINDINGS §32); blank if
                     that run is not on --model yet
  chronic_share      that run's flooded share

Runs are read from config.MODELS (the Piscataway /scratch: run on a hal* node), on ``--model``
(default runs.MODEL); ``--panel`` is build_sandy_panel.py's folder for the same model.
Writes data/analysis/storm_panel/{field_season.csv, fields_storm.csv, README.md} (or ``--out``).
Usage:  python scripts/build_storm_panel.py [--model M --panel DIR --out DIR]
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr

from agri_sfincs import config, domain, fieldflood, panel, runs

PANEL = config.ANALYSIS_DIR / "sandy_panel"
OUT = config.ANALYSIS_DIR / "storm_panel"
YEARS = range(2008, 2026)
UNMODELLED_MIN = 1.60
CHRONIC_RUN = ("tide2024oct", "intact", 0)
SEASONS = ("grow", "nongrow")


def ship_john() -> pd.Series:
    with xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc") as ds:
        return ds["waterlevel"].sel(stations=domain.SHIP_JOHN).to_series()


def season_peaks(sj: pd.Series) -> pd.DataFrame:
    """Ship John's highest level per (season_year, season) of panel.storm_season."""
    m, y = sj.index.month, sj.index.year
    grow = np.isin(m, panel.GROW_MONTHS)
    year = np.where(grow | (m < panel.GROW_MONTHS.start), y, y + 1)
    lab = np.where(grow, "grow", "nongrow")
    return sj.groupby([year, lab]).max().unstack()


def season_table(fields: pd.Index, ev: pd.DataFrame, sj: pd.Series) -> pd.DataFrame:
    spr = sj[sj.index.month.isin([3, 4, 5, 6])]
    spring_peak = spr.groupby(spr.index.year).max()
    ev = ev.assign(pk=pd.to_datetime(ev.peak))
    ev["spring"] = ev.pk.dt.month.between(3, 6)
    for k in ("tide", "rain"):
        ev[k] = ev[f"{k}_share"].fillna(0) >= fieldflood.SHARE

    idx = pd.MultiIndex.from_product([fields, YEARS], names=["field_id", "year"])
    yr = idx.get_level_values("year")
    out = pd.DataFrame(index=idx)

    # by growing season
    peaks = season_peaks(sj)
    modelled_days = set(ev.pk.dt.normalize().unique())
    st = panel.storm_tides(sj, UNMODELLED_MIN)
    un = st[~st.day.isin(modelled_days)].groupby(["season_year", "season"]).m.max().round(2).unstack()
    for s in SEASONS:
        e = ev[ev.season == s]
        g = e.groupby(["field_id", "season_year"])
        a = g[["tide", "rain"]].any()
        a.index.names = ["field_id", "year"]
        out[f"{s}_peak_m"] = yr.map(peaks[s]).values.round(2)
        for k in ("tide", "rain"):
            out[f"{s}_{k}"] = a[k].reindex(idx).fillna(False).astype(int).values
        n = g.tide.sum()
        n.index.names = ["field_id", "year"]
        out[f"{s}_n_tide"] = n.reindex(idx).fillna(0).astype(int).values
        mo = e[e.tide].groupby(["field_id", "season_year"]).peak_month.agg(lambda x: ";".join(str(v) for v in sorted(set(x))))
        mo.index.names = ["field_id", "year"]
        out[f"{s}_months_tide"] = mo.reindex(idx).fillna("").values
        out[f"{s}_unmodelled_m"] = yr.map(un[s] if s in un else pd.Series(dtype=float)).values

    # by planting (spring / off-season)
    out["spring_peak_m"] = yr.map(spring_peak).values.round(2)
    sp = ev[ev.spring]
    assert sp.groupby("first_cdl_year").event.nunique().max() <= 1, "two modelled spring storm runs in one year"
    names = sp.groupby("first_cdl_year").event.first()
    out["spring_storm"] = yr.map(names).fillna("").values
    s = sp.assign(d=sp.tide_maxd_m.where(sp.tide)).groupby(["field_id", "first_cdl_year"])
    s = s.agg(tide=("tide", "any"), rain=("rain", "any"), d=("d", "max"))
    s.index.names = ["field_id", "year"]
    for k in ("tide", "rain"):
        out[f"spring_{k}"] = s[k].reindex(idx).fillna(False).astype(int).values
    out["spring_tide_maxd_m"] = s.d.reindex(idx).round(3).values

    o = ev[~ev.spring].groupby(["field_id", "first_cdl_year"])[["tide", "rain"]].any()
    o.index.names = ["field_id", "year"]
    for k in ("tide", "rain"):
        out[f"off_{k}"] = o[k].reindex(idx).fillna(False).astype(int).values
    off_un = st[~st.spring & ~st.day.isin(modelled_days)].groupby("cdl_year").m.max().round(2)
    out["off_unmodelled_m"] = yr.map(off_un).values

    flooded = (out.spring_tide | out.off_tide).groupby(level="field_id")
    out["floods_before_tide"] = (flooded.cumsum() - (out.spring_tide | out.off_tide)).values
    return out.reset_index()


def check_storm_days(ev: pd.DataFrame, sj: pd.Series) -> None:
    """Every modelled storm peak must be one of storm_tides' peaks (so the unmodelled list is right)."""
    st = panel.storm_tides(sj, UNMODELLED_MIN)
    days = set(pd.to_datetime(ev.peak.unique()).normalize())
    missing = days - set(st.day)
    assert not missing, f"modelled peaks not found as storm-tide days: {missing}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=runs.MODEL)
    ap.add_argument("--panel", default=None, help=f"build_sandy_panel.py output (default {PANEL})")
    ap.add_argument("--out", default=None, help=f"output folder (default {OUT})")
    a = ap.parse_args()
    src = config.ROOT / a.panel if a.panel else PANEL
    out = config.ROOT / a.out if a.out else OUT

    f = gpd.read_file(src / "fields.gpkg", columns=["field_id"]).sort_values("field_id")
    assert (f.field_id.values == np.arange(1, len(f) + 1)).all()
    ev = pd.read_csv(src / "field_event.csv")
    sj = ship_john()
    check_storm_days(ev, sj)

    fs = season_table(pd.Index(f.field_id.values), ev, sj)

    n = {k: ev[ev[f"{k}_share"].fillna(0) >= fieldflood.SHARE].groupby("field_id").size() for k in ("tide", "rain")}
    fl = pd.DataFrame({"field_id": f.field_id.values})
    for k in ("tide", "rain"):
        fl[f"n_storms_{k}"] = fl.field_id.map(n[k]).fillna(0).astype(int)
    run = runs.run_dir(*CHRONIC_RUN, model=a.model)
    if runs.finished(run):
        print(f"{len(f):,} fields; chronic run ...", flush=True)
        px = fieldflood.field_pixels(f.to_crs(rasterio.open(runs.subgrid_dep(a.model)).crs), a.model)
        ch = fieldflood.run_stats(run, *px, len(f), CHRONIC_RUN[0])
        fl["chronic_share"] = ch.share.reindex(fl.field_id).fillna(0).round(3).values
        fl["chronic"] = (fl.chronic_share >= fieldflood.SHARE).astype(int)
    else:
        print(f"{run.name} not finished on {a.model}: chronic columns blank", flush=True)
        fl["chronic_share"], fl["chronic"] = np.nan, pd.NA

    out.mkdir(parents=True, exist_ok=True)
    fs.to_csv(out / "field_season.csv", index=False)
    fl.to_csv(out / "fields_storm.csv", index=False)
    (out / "README.md").write_text(readme(fs, fl, ev, a.model))
    agg = {f"{s}_{c}": (f"{s}_{c}", "sum") for s in SEASONS for c in ("tide",)}
    yr = fs.groupby("year").agg(grow_peak_m=("grow_peak_m", "first"), nongrow_peak_m=("nongrow_peak_m", "first"),
                                **agg, spring_tide=("spring_tide", "sum"), off_tide=("off_tide", "sum"))  # fmt: skip
    print(yr.to_string())
    print(f"storm tides in field_event.csv: {ev.groupby(['event', 'peak']).ngroups}; "
          f"fields flooded by >= 1 (tide): {(fl.n_storms_tide > 0).sum()}")  # fmt: skip
    print(f"wrote {out}")


def readme(fs: pd.DataFrame, fl: pd.DataFrame, ev: pd.DataFrame, model: str) -> str:
    tides = ev.groupby(["event", "peak", "season", "season_year"]).size().reset_index().sort_values("peak")
    listing = "\n".join(f"| {r.peak[:10]} | {r.event} | {r.season} | {r.season_year} |" for r in tides.itertuples())
    return f"""# Storm panel: flood exposure per farm field and season

Generated by `scripts/build_storm_panel.py` (FINDINGS §35, §37) from runs on `{model}`. Fields:
the {len(fl):,} NJDEP LU/LC polygons farmed in 2012, same `field_id` as `../sandy_panel/` (join
land use from `../sandy_panel/field_year.csv` on field_id + year). Seasons = CDL years
{YEARS.start}-{YEARS.stop - 1}.

Flooded = at least {fieldflood.SHARE:.0%} of the field more than 5 cm deep in a SFINCS run of
that storm tide, with dikes as they stand today.

## Storm tides modelled

Every storm tide of at least {panel.STORM_MIN} m NAVD88 at Ship John Shoal, 2008-2025, has a run.
In this build ({tides.shape[0]} of 18):

| peak day | run | season | CDL year |
|---|---|---|---|
{listing}

## Files

- `field_season.csv`: one row per field and CDL year.
- `fields_storm.csv`: one row per field.
- Per storm tide: `../sandy_panel/field_event.csv` (share and depth, with the peak's month).

## Columns (`field_season.csv`)

The year is cut two ways. **By growing season**: `grow` = April-October of the year;
`nongrow` = the November-March before it (a December storm counts toward the next year).
**By planting** (the first cut): spring = March-June; off-season = the July-February before.

| column | meaning |
|---|---|
| field_id, year | field, CDL year (the summer crop of that year) |
| grow_peak_m, nongrow_peak_m | highest water level at Ship John Shoal in that season (m NAVD88) |
| grow_tide, nongrow_tide | 1 if a modelled storm tide of that season floods the field (tide only) |
| grow_rain, nongrow_rain | the same counting the storm's rain |
| grow_n_tide, nongrow_n_tide | how many of the season's storm tides flood it |
| grow_months_tide, nongrow_months_tide | the months of those storm tides, e.g. `8` or `3;4` |
| grow_unmodelled_m, nongrow_unmodelled_m | highest storm tide of that season that was NOT modelled (m), blank if none >= {UNMODELLED_MIN} m |
| spring_peak_m | highest water level at Ship John Shoal in March-June of that year (m NAVD88) |
| spring_storm | the modelled spring storm run of that year, blank if none |
| spring_tide, spring_rain | 1 if that spring's storm tide(s) flood the field: tide only / tide plus the storm's rain |
| spring_tide_maxd_m | peak depth on the flooded part of the field (m), tide only |
| off_tide, off_rain | 1 if a modelled storm of the previous July-February floods the field |
| off_unmodelled_m | highest storm tide of that July-February that was NOT modelled (m at Ship John), blank if none >= {UNMODELLED_MIN} m |
| floods_before_tide | how many earlier seasons had a modelled storm (tide only) flood the field |

## Columns (`fields_storm.csv`)

| column | meaning |
|---|---|
| n_storms_tide, n_storms_rain | of the {tides.shape[0]} modelled storm tides, how many flood the field |
| chronic | 1 if ordinary monthly spring tides (October 2024, no storm) already flood it |
| chronic_share | the share of the field those ordinary tides flood |

## Caveats

- **Complete above {panel.STORM_MIN} m, all year** (once all 18 are in). Storm tides just below
  ({UNMODELLED_MIN}-{panel.STORM_MIN} m) are not modelled and appear as dry; the lowest-lying
  fields may well have flooded then. The `*_unmodelled_m` columns flag those seasons.
- **One storm tide, its own days.** Flooding is read from the day before to the day after the
  peak, so the two storm tides of spring 2024 (March 10, April 12) are counted separately.
- **The storms mostly flood the same fields** (FINDINGS §35): a field's history is close to
  one number, how big a storm it takes. `n_storms_tide` is that number.
- **Dikes as they stand today** for every year; banks repaired or raised after a storm are not
  dated. Flood depth is a peak; duration is not used (FINDINGS §16).
"""


if __name__ == "__main__":
    main()
