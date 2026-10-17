"""Data table for a cheap test: does modelled Hurricane Sandy (Oct 2012) flooding explain farm
land-use change better than ground height alone? Assembles the table only (no model fits).

Fields = every NJDEP LU/LC polygon farmed in 2012 (spring 2012 photography, before Sandy):
the previous-edition code of data/landuse/njlulc_2012_2015.gpkg (scripts/fetch_njlulc.py), in
Salem, Cumberland and Gloucester. That layer is cut where the 2015 code differs, so a field
that partly left farming by 2015 is two pieces. Not the 2015-and-2020 survivors of
field_flood_classes.gpkg: those would hide every 2013-19 exit.

fields.csv / fields.gpkg (one row per field, static):
  attributes        county, ha, behind_levee (agri_sfincs.fieldflood.add_county_levee)
  land use          lulc2012 (farm code), lulc2015 (that layer's next code), lulc2020 (the
                    2015-2020 layer's next code by largest overlap; blank if not farm in 2015)
  height            m_above_mhhw, leveed_share (agri_sfincs.exposure.add_exposure, FINDINGS §21)
  Sandy             per field from the runs (agri_sfincs.fieldflood.run_stats, 10 m pixels,
                    peak depth > 5 cm): sandy_* = sandy2012_intact_slr000 (dikes as built, tide
                    only), sandy_nodikes_* = sandy2012_removed_slr000, sandy_rain_* =
                    sandy2012_intact_slr000_rain; each _share, _maxd_m, _flooded (share > 0).
                    wetdays left out (duration not trusted, FINDINGS §16)
  bathtub           motf_share: share of the field's FEMA MOTF pixels (15 m, nj_bight_sfincs
                    validation_v4) inside the Sandy surge extent, of those in MOTF's NJ-valid
                    area; a dike-blind rival to the model (FINDINGS §33)
  soil              SSURGO, dominant component per map unit (data/soils/ssurgo_mapunits.gpkg,
                    scripts/fetch_ssurgo.py; ssurgo_drainage.csv, scripts/fetch_ssurgo_drainage.py):
                    hsg_dominant (soil group covering most of the field), hsg_wet_share (share
                    in D or dual A/D, B/D, C/D = water table within ~60 cm when undrained),
                    drain_dominant (natural drainage class covering most of the field),
                    drain_poor_share (share poorly or very poorly drained) and
                    drain_spoor_share (share somewhat poorly drained)
  CDL pixels        n_cdl_px, cdl_px_fallback (field holds no 30 m pixel centre: one pixel
                    under its representative point stands in)

field_year.csv (one row per field x CDL year 2008-2025): share of the field's CDL pixels in
each agri_sfincs.cdl.GROUPS group + other, cropland (= sum of the six crop groups =
cdl.CROPLAND), and the dominant class dom_code / dom_name. Pixel-to-field = pixel centre in
polygon on the NJ CDL grid (as scripts/field_flood_sample.py), agri_sfincs.cdl.polygon_pixels.

field_event.csv (one row per field x storm): every Sandy-class or planting-season storm tide
with a finished run (STORMS; scripts/setup_scenarios.py --storms), dikes as built: peak (Ship
John's peak hour), peak_month, first_cdl_year (the first CDL season whose planting can respond:
the peak's year for Jan-Jun, the next year for Jul-Dec), tide_share / tide_maxd_m (tide only)
and rain_share / rain_maxd_m (tide + rain), as the Sandy columns. Rows only for fields wet in
either run (share > 0); a missing field-storm pair means dry.

Writes data/analysis/sandy_panel/{fields.csv, fields.gpkg, field_year.csv, field_event.csv, README.md}.
Usage:  python scripts/build_sandy_panel.py
"""

from __future__ import annotations

import time

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.features import rasterize
from rasterio.windows import from_bounds

from agri_sfincs import cdl, config, domain, exposure, fieldflood, landuse, runs
from agri_sfincs.events import EVENTS

OUT = config.ANALYSIS_DIR / "sandy_panel"
YEARS = range(2008, 2026)
EVENT = "sandy2012"
RUNS = {"sandy": ("intact", ""), "sandy_nodikes": ("removed", ""), "sandy_rain": ("intact", "_rain")}
MOTF = config.BIGHT_DATA / "validation_v4" / "sandy_motf_extent_v4.tif"
MOTF_VALID = config.BIGHT_DATA / "validation_v4" / "sandy_motf_valid_nj_v4.tif"
WET_HSG = ("D", "A/D", "B/D", "C/D")
POOR_DRAIN = ("Poorly drained", "Very poorly drained")
SPOOR_DRAIN = ("Somewhat poorly drained",)
#: every storm tide in field_event.csv (FINDINGS §25, §34): Sandy and the other Sandy-class ones,
#: then the planting-season (Mar-Jun) ones and Sep 2018
STORMS = ["sandy2012", "storm2012dec", "storm2016jan", "storm2021oct", "storm2010mar", "storm2011apr",
          "storm2012jun", "storm2014apr", "storm2018sep", "storm2022apr", "storm2023jun", "storm2024spr"]


def load_fields() -> gpd.GeoDataFrame:
    """LU/LC farm polygons of 2012 in the study counties: field_id 1..N, ha, county,
    behind_levee, lulc2012 / 2015 / 2020 (EPSG:32618)."""
    g = gpd.read_file(config.LANDUSE_DIR / "njlulc_2012_2015.gpkg").to_crs(domain.EPSG)
    g = g[g.prev.map(landuse.is_farmed)].explode(index_parts=False).reset_index(drop=True)
    g = fieldflood.add_county_levee(g[["prev", "next", "geometry"]])
    g = g.rename(columns={"prev": "lulc2012", "next": "lulc2015"})
    g["field_id"] = np.arange(1, len(g) + 1)
    g["ha"] = g.area / 1e4
    l20 = gpd.read_file(config.LANDUSE_DIR / "njlulc_2015_2020.gpkg").to_crs(domain.EPSG)[["next", "geometry"]]
    x = gpd.overlay(g[["field_id", "geometry"]], l20, how="intersection", keep_geom_type=True)
    x["a"] = x.area
    best = x.sort_values("a", ascending=False).drop_duplicates("field_id").set_index("field_id")["next"]
    farm15 = g.lulc2015.map(landuse.is_farmed)
    g["lulc2020"] = g.field_id.map(best).where(farm15).astype("Int64")
    return g[["field_id", "county", "ha", "behind_levee", "lulc2012", "lulc2015", "lulc2020", "geometry"]]


def sandy_columns(g: gpd.GeoDataFrame, px) -> pd.DataFrame:
    """Per field, from each run in RUNS: share, maxd_m, flooded (share > 0); NaN when the field
    has no pixel in the model grid. ``px`` = fieldflood.field_pixels(g)."""
    f_sel, d_sel, fid = px
    out = {}
    for pre, (dk, suffix) in RUNS.items():
        st = fieldflood.run_stats(runs.run_dir(EVENT, dk, 0, suffix), f_sel, d_sel, fid, len(g), EVENT)
        out[f"{pre}_share"] = st.share
        out[f"{pre}_maxd_m"] = st.maxd
        out[f"{pre}_flooded"] = (st.share > 0).astype("boolean").mask(st.share.isna())
        print(f"  {pre}: {int((st.share > 0).sum())} fields wet, {int((st.share >= fieldflood.SHARE).sum())} "
              f">= {fieldflood.SHARE:.0%}", flush=True)  # fmt: skip
    return pd.DataFrame(out).reindex(g.field_id.values)


def storm_peaks() -> dict[str, pd.Timestamp]:
    """Ship John's peak hour in each storm's focus period."""
    with xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc") as ds:
        sj = ds["waterlevel"].sel(stations=domain.SHIP_JOHN).to_series()
    out = {}
    for ev in STORMS:
        e = EVENTS[ev]
        w = sj[e.focus_start : e.focus_stop - pd.Timedelta("1h")]
        out[ev] = w.idxmax()
    return out


def event_table(g: gpd.GeoDataFrame, px) -> pd.DataFrame:
    """field_event.csv (docstring): fields wet in either run of each finished storm."""
    f_sel, d_sel, fid = px
    peaks, rows = storm_peaks(), []
    for ev in STORMS:
        tide, rain = runs.run_dir(ev, "intact", 0), runs.run_dir(ev, "intact", 0, "_rain")
        if not (runs.finished(tide) and runs.finished(rain)):
            print(f"  {ev}: runs not finished, left out", flush=True)
            continue
        st = {k: fieldflood.run_stats(r, f_sel, d_sel, fid, len(g), ev) for k, r in (("tide", tide), ("rain", rain))}
        t = pd.DataFrame({"field_id": g.field_id.values, "tide_share": st["tide"].share.values,
                          "tide_maxd_m": st["tide"].maxd.values, "rain_share": st["rain"].share.values,
                          "rain_maxd_m": st["rain"].maxd.values})  # fmt: skip
        t = t[(t.tide_share > 0) | (t.rain_share > 0)]
        pk = peaks[ev]
        t.insert(1, "event", ev)
        t.insert(2, "peak", pk.strftime("%Y-%m-%d %H:00"))
        t.insert(3, "peak_month", pk.month)
        t.insert(4, "first_cdl_year", pk.year if pk.month <= 6 else pk.year + 1)
        rows.append(t)
        print(f"  {ev} (peak {pk:%Y-%m-%d}): {int((t.tide_share >= fieldflood.SHARE).sum())} fields >= "
              f"{fieldflood.SHARE:.0%} tide only, {int((t.rain_share >= fieldflood.SHARE).sum())} with rain", flush=True)  # fmt: skip
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def motf_share(g: gpd.GeoDataFrame) -> pd.Series:
    """Share of each field's MOTF pixels flooded, of those in MOTF's NJ-valid area."""
    with rasterio.open(MOTF) as r:
        gg = g.to_crs(r.crs)
        win = from_bounds(*gg.total_bounds, transform=r.transform).round_offsets().round_lengths()
        tr, shape = r.window_transform(win), (int(win.height), int(win.width))
        wet = r.read(1, window=win, boundless=True, fill_value=0) == 1
    with rasterio.open(MOTF_VALID) as r:
        valid = r.read(1, window=win, boundless=True, fill_value=0) == 1
    ids = rasterize(zip(gg.geometry, gg.field_id), out_shape=shape, transform=tr, fill=0, dtype="uint32")
    n = len(g) + 1
    nv = np.bincount(ids[valid], minlength=n).astype(float)
    nw = np.bincount(ids[valid & wet], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return pd.Series((nw / nv)[1:], index=g.field_id.values, name="motf_share")


def soil_columns(g: gpd.GeoDataFrame) -> pd.DataFrame:
    """hsg_* and drain_* (docstring) by area of SSURGO map-unit polygons."""
    bbox = tuple(g.to_crs(4326).total_bounds)
    mu = gpd.read_file(config.SOILS_DIR / "ssurgo_mapunits.gpkg", bbox=bbox, columns=["mukey", "hsg"])
    mu = mu.to_crs(g.crs)
    dr = pd.read_csv(config.SOILS_DIR / "ssurgo_drainage.csv", dtype={"mukey": str}, keep_default_na=False)
    mu = mu.merge(dr[["mukey", "drainagecl"]], on="mukey", how="left", validate="many_to_one")
    mu["hsg"] = mu.hsg.fillna("").replace("", "none")
    mu["drain"] = mu.drainagecl.fillna("").replace("", "none")
    x = gpd.overlay(g[["field_id", "geometry"]], mu[["hsg", "drain", "geometry"]], how="intersection",
                    keep_geom_type=True)  # fmt: skip
    x["a"] = x.area
    out = {}
    for col, shares in [("hsg", {"wet": WET_HSG}), ("drain", {"poor": POOR_DRAIN, "spoor": SPOOR_DRAIN})]:
        a = x.groupby(["field_id", col]).a.sum().reset_index()
        tot = a.groupby("field_id").a.sum()
        dom = a.sort_values(["field_id", "a"], ascending=[True, False]).drop_duplicates("field_id")
        out[f"{col}_dominant"] = dom.set_index("field_id")[col]
        for name, vals in shares.items():
            out[f"{col}_{name}_share"] = a[a[col].isin(vals)].groupby("field_id").a.sum().reindex(tot.index).fillna(0) / tot
    return pd.DataFrame(out).reindex(g.field_id.values)


def cdl_panel(g: gpd.GeoDataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[int]]:
    """Per field: n_cdl_px, cdl_px_fallback. Per field x year: group shares, cropland,
    dom_code, dom_name. Also the CDL years not on disk."""
    with rasterio.open(cdl.path(2025)) as c:
        gg = g.to_crs(c.crs)
        win = from_bounds(*gg.total_bounds, transform=c.transform).round_offsets().round_lengths()
        tr, shape = c.window_transform(win), (int(win.height), int(win.width))
    zone, flat, fallback = cdl.polygon_pixels(gg.geometry, shape, tr)
    n, fid = len(g), g.field_id.values
    crop_cols = [f"share_{k}" for k in ("corn", "soybeans", "other_grains", "hay", "idle", "other_crops")]
    rows, missing = [], []
    for y in YEARS:
        if not cdl.path(y).exists():
            missing.append(y)
            continue
        t = cdl.zone_cover(zone, cdl.read(y, win).ravel()[flat], n)
        t.insert(0, "field_id", fid)
        t.insert(1, "year", y)
        t["cropland"] = t[crop_cols].sum(axis=1, min_count=1)
        t["dom_name"] = t.dom_code.map(lambda c: cdl.name(c) if c >= 0 else "")
        rows.append(t)
    fy = pd.concat(rows, ignore_index=True)
    fy = fy[[c for c in fy.columns if c not in ("dom_code", "dom_name")] + ["dom_code", "dom_name"]]
    static = pd.DataFrame({"n_cdl_px": rows[0].n_px.values, "cdl_px_fallback": False}, index=fid)
    static.loc[fid[fallback - 1], "cdl_px_fallback"] = True
    return static, fy.drop(columns="n_px"), missing


def _shift(fy: pd.DataFrame, f: pd.DataFrame) -> str:
    """A few product-level jumps in the field-average CDL shares, for the caveats."""
    w = fy.merge(f[["field_id", "n_cdl_px"]], on="field_id")
    cols = ["cropland", "share_developed", "share_idle", "share_pasture"]
    m = w[cols].mul(w.n_cdl_px, axis=0).groupby(w.year).sum().div(w.groupby("year").n_cdl_px.sum(), axis=0)
    p = lambda c, y: f"{100 * m.loc[y, c]:.0f}" if y in m.index else "?"  # noqa: E731
    return (f"cropland {p('cropland', 2023)}% in 2023 vs {p('cropland', 2024)}% in 2024; developed "
            f"{p('share_developed', 2023)}% vs {p('share_developed', 2024)}%; idle {p('share_idle', 2011)}% "
            f"in 2011 but {p('share_idle', 2016)}% from 2016; pasture {p('share_pasture', 2012)}% in 2012, "
            f"{p('share_pasture', 2013)}% in 2013")  # fmt: skip


def readme(f: pd.DataFrame, fy: pd.DataFrame, missing: list[int], fe: pd.DataFrame) -> str:
    groups = "\n".join(
        f"| share_{k} | {', '.join(str(c) for c in sorted(v)) if len(v) <= 12 else 'see note'} |"
        for k, v in cdl.GROUPS.items()
    )
    other_crops = ", ".join(str(c) for c in sorted(cdl.GROUPS["other_crops"]))
    grains = ", ".join(str(c) for c in sorted(cdl.GROUPS["other_grains"]))
    rain = "sandy_rain_share" in f
    yrs = f"{fy.year.min()}-{fy.year.max()}" + (f" (missing: {missing})" if missing else "")
    evs = ", ".join(f"{e} ({p[:10]})" for e, p in fe.groupby("event").peak.first().sort_values().items()) if len(fe) else "none yet"
    gone = [e for e in STORMS if e not in set(fe.get("event", []))]
    return f"""# Sandy panel: per-field Sandy flooding, height and CDL land use 2008-2025

Data table for testing whether modelled Hurricane Sandy (October 2012) flooding explains farm
land-use change better than ground height alone. Built by `scripts/build_sandy_panel.py`; no
model fits here.

- `fields.csv`: {len(f):,} fields, one row each (static attributes).
- `field_year.csv`: {len(fy):,} rows, one per field per CDL year {yrs}.

Join on `field_id`; the polygons are in `fields.gpkg` (EPSG:32618). These ids are NOT those
of `data/analysis/field_flood_classes.*`.

## Fields

Every NJDEP Land Use/Land Cover polygon that was **farmland in 2012** (codes 2100 / 2140 /
2200 / 2300 / 2400; spring 2012 photography, before Sandy) in Salem, Cumberland and
Gloucester, inside the model's bounding box. Fields that later left farming stay in the table;
`lulc2015` / `lulc2020` say where they went. NJDEP cuts the 2012 polygons where the 2015 code
differs, so a field that partly left farming by 2015 appears as two pieces (one changed, one
not). Fields first farmed after 2012 are not in the table.

## `fields.csv`

| column | meaning |
|---|---|
| field_id | field id |
| county | Salem, Cumberland or Gloucester |
| ha | field area, hectares |
| behind_levee | at least half the field inside a USACE National Levee Database leveed area |
| lulc2012 | NJDEP LU/LC 2012 farm code; 2140 = agricultural wetland (farmed mapped wetland) |
| lulc2015 | LU/LC 2015 code of the same piece (farm codes are 2000-2999; e.g. 2150 = former agricultural wetland, 4xxx forest, 6xxx wetland, 1xxx urban) |
| lulc2020 | LU/LC 2020 code with the largest overlap; blank when the piece was not farm in 2015 (the 2015-2020 layer holds only 2015 farm) |
| m_above_mhhw | median ground height of the field above recent high tide (MHHW of 2021-25 observed bay gauges, spread between gauges), metres; 30 m cells of the lidar bed |
| leveed_share | share of the field's 30 m cells inside an NLD leveed area |
| sandy_share | share of the field's 10 m pixels deeper than 5 cm at Sandy's peak (modelled, SFINCS run `sandy2012_intact_slr000`: dikes as built, today's sea level, tide and surge only, no rain) |
| sandy_maxd_m | mean peak depth over those flooded pixels, metres (blank when none flooded) |
| | sandy_* are blank for the {int(f.sandy_share.isna().sum())} fields with no pixel in the model grid (outside the model domain) |
| sandy_flooded | sandy_share > 0 (any pixel > 5 cm; blank when sandy_share is). The repo's usual rule elsewhere is share >= 0.10 |
| sandy_nodikes_share, _maxd_m, _flooded | the same with every dike removed (`sandy2012_removed_slr000`): what the banks kept off |
{"| sandy_rain_share, sandy_rain_maxd_m, sandy_rain_flooded | the same for the run with Sandy's rain added (Stage IV radar, `sandy2012_intact_slr000_rain`) |" if rain else ""}
| motf_share | share of the field inside FEMA's Modeling Task Force Sandy surge extent (15 m; of the pixels in MOTF's NJ-valid area; blank if none). MOTF lays the bay's peak (~1.9-2.0 m NAVD88) flat over lidar with no dikes: a bathtub rival to the model, wetter on flat fields (FINDINGS §33) |
| hsg_dominant | SSURGO hydrologic soil group covering most of the field (dominant soil component of each map unit); `none` = no group (water, urban, pits) |
| hsg_wet_share | share of the field in soil group D or a dual group (A/D, B/D, C/D); dual groups mark a seasonal high water table when undrained |
| drain_dominant | SSURGO natural drainage class covering most of the field (dominant soil component of each map unit); `none` = no class (water, urban, pits) |
| drain_poor_share | share of the field poorly or very poorly drained (natural drainage; see caveats) |
| drain_spoor_share | share of the field somewhat poorly drained |
| n_cdl_px | number of 30 m CDL pixels whose centre lies in the field |
| cdl_px_fallback | True when the field holds no pixel centre: its CDL values come from the ONE pixel under the field's representative point (n_cdl_px = 1) |

## `field_year.csv`

Per field and year: the share of the field's CDL pixels (30 m, pixel centre in the field) in
each group below, then `cropland`, `dom_code`, `dom_name`. The shares of a row sum to 1.

| column | CDL codes |
|---|---|
{groups}
| share_other | every code in no group (mostly barren 131) |
| cropland | sum of the six crop groups = all CDL cropland codes (`agri_sfincs.cdl.CROPLAND`; grass/pasture excluded) |
| dom_code, dom_name | the CDL class with the most pixels in the field (ties: lowest code) |

- share_other_grains: sorghum, barley, the wheats, other small grains, rye, oats, millet,
  speltz, triticale, and every double crop (codes {grains}). Double crops containing corn or
  soybeans are counted here, not as corn or soybeans.
- share_other_crops: the rest of CDL cropland (codes {other_crops}): vegetables, fruit,
  orchards, berries, sod, clover, switchgrass and so on.
- share_hay = alfalfa (36) + other hay (37); share_pasture = grass/pasture (176);
  share_idle = fallow/idle cropland (61).

## `field_event.csv`

One row per field and storm tide, for fields the storm wet in either run (a missing pair means
dry). Storms in this file: {evs}.{f" Not yet run or finished: {', '.join(gone)}." if gone else ""}
All are SFINCS runs with the dikes as built and today's sea level; Sandy's rows repeat the
`sandy_*` / `sandy_rain_*` columns of `fields.csv`.

| column | meaning |
|---|---|
| field_id, event | field and storm (run name prefix) |
| peak | hour of the storm tide's peak at Ship John Shoal (UTC) |
| peak_month | its month: planting season is roughly Mar-Jun, harvest Sep-Nov |
| first_cdl_year | the first CDL season whose planting can respond: the peak's year for Jan-Jun peaks, the next year for Jul-Dec peaks (a June flood after planting may show as replanting or a switch the same season) |
| tide_share, tide_maxd_m | tide-only run: share of the field's 10 m pixels deeper than 5 cm at the peak, mean peak depth over them (m) |
| rain_share, rain_maxd_m | the same with the storm's rain (Stage IV before 2016, MRMS from 2016) |

## Sources

- Fields and land use: NJDEP LU/LC 2012-2015 and 2015-2020 layers, `data/landuse/`
  (`scripts/fetch_njlulc.py`).
- Sandy flooding: the SFINCS runs on scratch (`agri_sfincs.fieldflood.run_stats`); MOTF from
  `nj_bight_sfincs/data/validation_v4/` (FINDINGS §33).
- Height above MHHW, leveed share: `agri_sfincs.exposure.add_exposure` (FINDINGS §21).
- Soil group: `data/soils/ssurgo_mapunits.gpkg` (`scripts/fetch_ssurgo.py`, USDA SSURGO).
- Drainage class: `data/soils/ssurgo_drainage.csv` (`scripts/fetch_ssurgo_drainage.py`, USDA SSURGO).
- Land use: USDA NASS Cropland Data Layer, NJ, `data/cdl/` (`scripts/fetch_cdl.py`).

## Caveats

- **Sandy is modelled, not observed.** Dikes and banks are as they stand in today's model
  (NLD alignments, lidar crests), not as they stood in 2012; banks that failed or were
  repaired since are not represented as of 2012. Depth is the peak over the event; flood
  DURATION (wet days) is left out because the model's ponded water does not drain properly
  between storms yet (FINDINGS §16). No MOTF / gate operations beyond the model's check valves.
- **CDL accuracy varies by year and class.** NJ CDL is less accurate in the early years
  (2008-2010) and for minor crops, hay, pasture, idle and wetland classes than for corn and
  soybeans. Classes jump at product refreshes (notably 2019 and 2024 here, FINDINGS §21), and
  CDL calls abandoned grassy fields "Other Hay" (FINDINGS §24). Visible in this table
  (pixel-weighted over all fields, {_shift(fy, f)}). Year-to-year changes in a
  single field are noisy; small fields and field edges are mixed pixels.
- **Small fields.** About {int(f.cdl_px_fallback.sum()):,} fields hold no 30 m pixel centre
  and get one pixel; {int((f.n_cdl_px < 5).sum()):,} have fewer than 5 pixels.
- **Soil drainage class is the soil's NATURAL drainage.** Many fields here are ditched or tiled,
  so a "poorly drained" field may farm like a better-drained one. Classes are for each map
  unit's dominant soil component; minor wetter soils inside a map unit are not counted.
- **Height.** {int(f.m_above_mhhw.isna().sum())} fields have no height. High tide is spread
  between bay gauges, so tide amplification up the creeks is missing.
"""


def main() -> None:
    t0 = time.time()
    g = load_fields()
    print(f"{len(g):,} fields ({time.time() - t0:.0f} s); Sandy runs and MOTF ...", flush=True)
    px = fieldflood.field_pixels(g.to_crs(rasterio.open(runs.subgrid_dep()).crs))
    sandy = sandy_columns(g, px).join(motf_share(g))
    print(f"  {time.time() - t0:.0f} s; storms ...", flush=True)
    fe = event_table(g, px)
    print(f"  {time.time() - t0:.0f} s; height and leveed share ...", flush=True)
    g = exposure.add_exposure(g)
    print(f"  {time.time() - t0:.0f} s; soils ...", flush=True)
    soil = soil_columns(g)
    print(f"  {time.time() - t0:.0f} s; CDL ...", flush=True)
    static, fy, missing = cdl_panel(g)
    f = pd.DataFrame(g.drop(columns="geometry")).set_index("field_id")
    f = f.join(sandy.set_axis(f.index)).join(soil.set_axis(f.index))
    f = f.join(static).reset_index()
    f["ha"] = f.ha.round(4)

    OUT.mkdir(parents=True, exist_ok=True)
    f.to_csv(OUT / "fields.csv", index=False, float_format="%.6g")
    g[["field_id", "geometry"]].to_file(OUT / "fields.gpkg", driver="GPKG")
    fy.to_csv(OUT / "field_year.csv", index=False, float_format="%.6g")
    fe.to_csv(OUT / "field_event.csv", index=False, float_format="%.6g")
    (OUT / "README.md").write_text(readme(f, fy, missing, fe))

    # sanity counts
    print(f"\nfields.csv {len(f):,} rows; field_year.csv {len(fy):,} rows "
          f"({fy.year.nunique()} years); missing CDL years: {missing or 'none'}")  # fmt: skip
    print(f"NaN m_above_mhhw: {int(f.m_above_mhhw.isna().sum())}; NaN hsg: {int(f.hsg_dominant.isna().sum())}; "
          f"CDL fallback fields: {int(f.cdl_px_fallback.sum())}")  # fmt: skip
    # rounded as written, so 1/3 + 1/6 counts as 0.5 here as in the csv
    c11 = fy[fy.year == 2011].set_index("field_id").cropland.reindex(f.field_id).round(6).values
    low = f[(c11 >= 0.5) & (f.m_above_mhhw < 1.5)]
    print(f">= 50% cropland 2011 and < 1.5 m above MHHW: {len(low)} fields; "
          f"sandy_flooded {int((low.sandy_flooded == True).sum())}, not {int((low.sandy_flooded == False).sum())}; "  # noqa: E712
          f"share >= 0.10: {int((low.sandy_share >= 0.10).sum())}; no Sandy value: "
          f"{int(low.sandy_share.isna().sum())}")  # fmt: skip
    left = ~f.lulc2015.map(landuse.is_farmed) | (f.lulc2020.notna() & ~f.lulc2020.map(landuse.is_farmed))
    print(f"  of those, left farming by LU/LC 2020: flooded {int(left[low.index][low.sandy_flooded == True].sum())}, "  # noqa: E712
          f"dry {int(left[low.index][low.sandy_flooded == False].sum())}")  # noqa: E712
    if "sandy_rain_flooded" in low:
        print(f"  with rain: flooded {int((low.sandy_rain_flooded == True).sum())}")  # noqa: E712
    print(f"wrote {OUT} in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
