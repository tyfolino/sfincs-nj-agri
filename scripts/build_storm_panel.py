"""Field x season flood exposure for the land-use test, from all modelled storm tides (FINDINGS
§35): replaces "Sandy with a 2008-12 baseline", which §35 showed is not clean (the same fields
flood in most storms, and in April 2011 before Sandy).

Fields = data/analysis/sandy_panel/fields.gpkg (scripts/build_sandy_panel.py): every LU/LC
polygon farmed in 2012. Season = CDL year t (2008-2025). Flooded = >= fieldflood.SHARE (10%)
of the field > 5 cm deep in the run (field_event.csv; dikes as built today).

field_season.csv (one row per field x CDL year):
  spring_peak_m      Ship John's highest hourly level in Mar-Jun of t (m NAVD88). Every spring
                     >= MODELLED_MIN is modelled; lower springs (2016 1.60, 2017 1.63, 2019 1.67,
                     2025 1.61) are not, and count as dry: below every modelled storm
  spring_storm       the modelled Mar-Jun storm of t, or blank
  spring_tide, spring_rain   flooded by it, tide only / with the storm's rain (0 if none)
  spring_tide_maxd_m mean peak depth over the field's flooded pixels (blank if not flooded)
  off_tide, off_rain flooded by a modelled storm of Jul (t-1) - Feb (t): the off-season before
                     the planting of t (Sandy and Dec 2012 -> 2013, Jan 2016 -> 2016, Sep 2018
                     -> 2019, Oct 2021 -> 2022)
  off_unmodelled_m   highest UNMODELLED storm tide >= UNMODELLED_MIN at Ship John in that
                     off-season (e.g. Irene, Aug 2011, 1.85 m -> 2012), blank if none
  floods_before_tide number of modelled tide-only floods of the field in seasons before t

fields_storm.csv (one row per field):
  n_storms_tide, n_storms_rain   modelled storms that flood it (of 12)
  chronic            flooded by ordinary spring tides (tide2024oct_intact_slr000, share >=
                     SHARE): wet every month, so a storm adds nothing (FINDINGS §32)
  chronic_share      that run's flooded share

Runs are read from config.MODELS (the Piscataway /scratch: run on a hal* node).
Writes data/analysis/storm_panel/{field_season.csv, fields_storm.csv, README.md}.
Usage:  python scripts/build_storm_panel.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr

from agri_sfincs import config, domain, fieldflood, runs

PANEL = config.ANALYSIS_DIR / "sandy_panel"
OUT = config.ANALYSIS_DIR / "storm_panel"
YEARS = range(2008, 2026)
MODELLED_MIN = 1.68  # the lowest modelled spring peak (storm2010mar)
UNMODELLED_MIN = 1.60
CHRONIC_RUN = ("tide2024oct", "intact", 0)


def ship_john() -> pd.Series:
    with xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc") as ds:
        return ds["waterlevel"].sel(stations=domain.SHIP_JOHN).to_series()


def cdl_year(t: pd.Timestamp) -> int:
    """The first CDL season whose planting can respond (as build_sandy_panel.event_table)."""
    return t.year if t.month <= 6 else t.year + 1


def storm_tides(sj: pd.Series, lo: float) -> pd.DataFrame:
    """Independent storm tides >= lo: daily maxima, peaks closer than 4 days merged."""
    d = sj.resample("D").max()
    rows: list[list] = []
    for t, v in d[d >= lo].items():
        if rows and (t - rows[-1][2]).days <= 3:
            rows[-1][2] = t
            if v > rows[-1][1]:
                rows[-1][:2] = [t, v]
        else:
            rows.append([t, v, t])
    e = pd.DataFrame([r[:2] for r in rows], columns=["day", "m"])
    e["cdl_year"] = e.day.map(cdl_year)
    e["spring"] = e.day.dt.month.between(3, 6)
    return e


def season_table(fields: pd.Index, ev: pd.DataFrame, sj: pd.Series) -> pd.DataFrame:
    spr = sj[sj.index.month.isin([3, 4, 5, 6])]
    spring_peak = spr.groupby(spr.index.year).max()
    ev = ev.assign(pk=pd.to_datetime(ev.peak))
    ev["spring"] = ev.pk.dt.month.between(3, 6)
    for k in ("tide", "rain"):
        ev[k] = ev[f"{k}_share"].fillna(0) >= fieldflood.SHARE

    idx = pd.MultiIndex.from_product([fields, YEARS], names=["field_id", "year"])
    out = pd.DataFrame(index=idx)
    out["spring_peak_m"] = out.index.get_level_values("year").map(spring_peak).values.round(2)

    s = ev[ev.spring].set_index(["field_id", "first_cdl_year"])
    s.index.names = ["field_id", "year"]
    assert not s.index.duplicated().any(), "two modelled spring storms in one year"
    names = ev[ev.spring].groupby("first_cdl_year").event.first()
    out["spring_storm"] = out.index.get_level_values("year").map(names).fillna("").values
    for k in ("tide", "rain"):
        out[f"spring_{k}"] = s[k].reindex(idx).fillna(False).astype(int).values
    out["spring_tide_maxd_m"] = s.tide_maxd_m.where(s.tide).reindex(idx).round(3).values

    o = ev[~ev.spring].groupby(["field_id", "first_cdl_year"])[["tide", "rain"]].any()
    o.index.names = ["field_id", "year"]
    for k in ("tide", "rain"):
        out[f"off_{k}"] = o[k].reindex(idx).fillna(False).astype(int).values

    modelled_days = set(ev.pk.dt.normalize().unique())
    st = storm_tides(sj, UNMODELLED_MIN)
    un = st[~st.spring & ~st.day.isin(modelled_days)].groupby("cdl_year").m.max().round(2)
    out["off_unmodelled_m"] = out.index.get_level_values("year").map(un).values

    flooded = (out.spring_tide | out.off_tide).groupby(level="field_id")
    out["floods_before_tide"] = (flooded.cumsum() - (out.spring_tide | out.off_tide)).values
    return out.reset_index()


def check_storm_days(ev: pd.DataFrame, sj: pd.Series) -> None:
    """Every modelled storm peak must be one of storm_tides' peaks (so the unmodelled list is right)."""
    st = storm_tides(sj, UNMODELLED_MIN)
    days = set(pd.to_datetime(ev.peak.unique()).normalize())
    missing = days - set(st.day)
    assert not missing, f"modelled peaks not found as storm-tide days: {missing}"


def main() -> None:
    f = gpd.read_file(PANEL / "fields.gpkg", columns=["field_id"]).sort_values("field_id")
    assert (f.field_id.values == np.arange(1, len(f) + 1)).all()
    ev = pd.read_csv(PANEL / "field_event.csv")
    sj = ship_john()
    check_storm_days(ev, sj)

    fs = season_table(pd.Index(f.field_id.values), ev, sj)

    print(f"{len(f):,} fields; chronic run ...", flush=True)
    px = fieldflood.field_pixels(f.to_crs(rasterio.open(runs.subgrid_dep()).crs))
    run = runs.run_dir(*CHRONIC_RUN)
    ch = fieldflood.run_stats(run, *px, len(f), CHRONIC_RUN[0])
    n = {k: ev[ev[f"{k}_share"].fillna(0) >= fieldflood.SHARE].groupby("field_id").size() for k in ("tide", "rain")}
    fl = pd.DataFrame({"field_id": f.field_id.values})
    for k in ("tide", "rain"):
        fl[f"n_storms_{k}"] = fl.field_id.map(n[k]).fillna(0).astype(int)
    fl["chronic_share"] = ch.share.reindex(fl.field_id).fillna(0).round(3).values
    fl["chronic"] = (fl.chronic_share >= fieldflood.SHARE).astype(int)

    OUT.mkdir(parents=True, exist_ok=True)
    fs.to_csv(OUT / "field_season.csv", index=False)
    fl.to_csv(OUT / "fields_storm.csv", index=False)
    (OUT / "README.md").write_text(readme(fs, fl))
    yr = fs.groupby("year").agg(spring_peak_m=("spring_peak_m", "first"), storm=("spring_storm", "first"),
                                spring_tide=("spring_tide", "sum"), spring_rain=("spring_rain", "sum"),
                                off_tide=("off_tide", "sum"), off_unmodelled_m=("off_unmodelled_m", "first"))  # fmt: skip
    print(yr.to_string())
    print(f"chronic fields: {fl.chronic.sum()}; flooded by >= 1 storm (tide): {(fl.n_storms_tide > 0).sum()}")
    print(f"wrote {OUT}")


def readme(fs: pd.DataFrame, fl: pd.DataFrame) -> str:
    return f"""# Storm panel: flood exposure per farm field and season

Generated by `scripts/build_storm_panel.py` (FINDINGS §35, §37). Fields: the {len(fl):,} NJDEP LU/LC
polygons farmed in 2012, same `field_id` as `../sandy_panel/` (join land use from
`../sandy_panel/field_year.csv` on field_id + year). Seasons = CDL years {YEARS.start}-{YEARS.stop - 1}.

Flooded = at least {fieldflood.SHARE:.0%} of the field more than 5 cm deep in a SFINCS run of
that storm tide, with dikes as they stand today.

## Files

- `field_season.csv`: one row per field and CDL year.
- `fields_storm.csv`: one row per field.

## Columns (`field_season.csv`)

| column | meaning |
|---|---|
| field_id, year | field, CDL year (the summer crop of that year) |
| spring_peak_m | highest water level at Ship John Shoal in March-June of that year (m NAVD88) |
| spring_storm | the modelled spring storm tide of that year, blank if none |
| spring_tide, spring_rain | 1 if that storm floods the field: tide only / tide plus the storm's rain |
| spring_tide_maxd_m | peak depth on the flooded part of the field (m), tide only |
| off_tide, off_rain | 1 if a modelled storm of the previous July-February floods the field |
| off_unmodelled_m | highest storm tide of that July-February that was NOT modelled (m at Ship John), blank if none >= {UNMODELLED_MIN} m |
| floods_before_tide | how many modelled storms (tide only) flooded the field in earlier seasons |

## Columns (`fields_storm.csv`)

| column | meaning |
|---|---|
| n_storms_tide, n_storms_rain | of the 12 modelled storm tides, how many flood the field |
| chronic | 1 if ordinary monthly spring tides (October 2024, no storm) already flood it |
| chronic_share | the share of the field those ordinary tides flood |

## Caveats

- **Spring is complete above {MODELLED_MIN} m.** Every March-June storm tide of at least {MODELLED_MIN} m
  at Ship John since 2008 is modelled. Springs just below (2016, 2017, 2019, 2025: 1.60-1.67 m)
  are not, and appear as dry; the lowest-lying fields may well have flooded then. Use
  `spring_peak_m` to drop or flag those years.
- **The off-season is NOT complete.** {fs.dropna(subset=['off_unmodelled_m']).year.nunique()} seasons follow an unmodelled storm tide of at least
  {UNMODELLED_MIN} m, including Irene (August 2011, 1.85 m, before the 2012 season).
- **The storms mostly flood the same fields** (FINDINGS §35): a field's history is close to
  one number, how big a storm it takes. `n_storms_tide` is that number.
- **Dikes as they stand today** for every year; banks repaired or raised after a storm are not
  dated. Flood depth is a peak; duration is not used (FINDINGS §16).
"""


if __name__ == "__main__":
    main()
