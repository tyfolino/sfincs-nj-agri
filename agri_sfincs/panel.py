"""Shared pieces of the land-use panel analyses (scripts/build_sandy_panel.py,
scripts/build_storm_panel.py, scripts/plot_storm_panel.py): the storm tides and their seasons,
the low-crop-field set, height reweighting and the flooded - comparison estimate against quiet
years. Pure, tested."""

from __future__ import annotations

import numpy as np
import pandas as pd

MAX_H = 1.5  # m above MHHW
PRE = range(2008, 2013)  # CDL years before Sandy
H_BIN = 0.25  # m, height bins for reweighting
QUIET_WINDOW = 5  # years: a storm season is measured against the quiet years this close
CDL_CHANGE = 2024  # CDL product change: cropland drops on every low field from here (FINDINGS §37)
#: Storm tides: Ship John Shoal daily maxima at least this high (m NAVD88); every one 2008-25 has
#: a run (18 peaks in 17 runs: spring 2024 holds two, FINDINGS §48).
STORM_MIN = 1.68
#: Growing season (user, 2026-10-26): April-October of a CDL year; November-March before it is
#: that year's non-growing season.
GROW_MONTHS = range(4, 11)
#: Days of daily zsmax read around a storm tide's peak day: the day before to the day after.
PEAK_DAYS_BEFORE, PEAK_DAYS_AFTER = 1, 1
# land-use classes of sandy_panel/field_year.csv; a field's main class is the largest of them
CLASSES = ["share_corn", "share_soybeans", "share_other_grains", "share_hay", "share_idle", "share_other_crops",
           "share_pasture", "share_herb_wetland", "share_woody_wetland", "share_forest_shrub", "share_developed",
           "share_water", "share_other"]  # fmt: skip


def cdl_year(t: pd.Timestamp) -> int:
    """The first CDL season whose planting can respond: Jan-Jun -> that year, Jul-Dec -> next."""
    return t.year if t.month <= 6 else t.year + 1


def storm_season(t: pd.Timestamp) -> tuple[int, str]:
    """(CDL year, "grow" | "nongrow") of a storm at ``t``: GROW_MONTHS of year t are its
    growing season; November-December count toward the next year's non-growing season."""
    if t.month in GROW_MONTHS:
        return t.year, "grow"
    return (t.year + 1 if t.month > GROW_MONTHS.stop - 1 else t.year), "nongrow"


def storm_tides(sj: pd.Series, lo: float = STORM_MIN) -> pd.DataFrame:
    """Independent storm tides >= lo in an hourly Ship John series: daily maxima, peaks closer
    than 4 days merged into the highest. Columns day, m, cdl_year, spring (Mar-Jun), season_year,
    season."""
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
    s = e.day.map(storm_season)
    e["season_year"] = s.map(lambda x: x[0]).astype(int)
    e["season"] = s.map(lambda x: x[1])
    return e


def peak_window(day: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[start, stop) of the daily zsmax blocks read for a storm tide peaking on ``day``."""
    day = pd.Timestamp(day).normalize()
    return day - pd.Timedelta(days=PEAK_DAYS_BEFORE), day + pd.Timedelta(days=PEAK_DAYS_AFTER + 1)


def low_crop_fields(f: pd.DataFrame, fy: pd.DataFrame, max_h: float = MAX_H, pre=PRE) -> pd.Series:
    """Fields (index of ``f``, sandy_panel/fields.csv) < max_h above MHHW, at least half CDL
    cropland on average over ``pre`` (field_year.csv), with a Sandy value (the §34 set)."""
    crop = fy[fy.year.isin(pre)].groupby("field_id").cropland.mean().reindex(f.index)
    return (f.m_above_mhhw < max_h) & (crop >= 0.5) & f.sandy_share.notna()


def switched(main: pd.DataFrame) -> pd.DataFrame:
    """field x year (consecutive year columns) of the main land-use class: 1.0 where it differs
    from the year before, 0.0 where it is the same, NaN where the year before is missing."""
    prev = main.shift(1, axis=1)
    return (main != prev).astype(float).where(prev.notna() & main.notna())


def left_cropland(crop: pd.DataFrame, thr: float = 0.5) -> pd.DataFrame:
    """field x year (consecutive year columns) of cropland share: 1.0 in year t when the field
    was >= thr cropland in t-1 and is < thr in both t and t+1 (out for at least two seasons),
    else 0.0; NaN where t-1, t or t+1 is missing."""
    prev, nxt = crop.shift(1, axis=1), crop.shift(-1, axis=1)
    out = ((prev >= thr) & (crop < thr) & (nxt < thr)).astype(float)
    return out.where(prev.notna() & crop.notna() & nxt.notna())


def height_weights(height: pd.Series, ha: pd.Series, target: pd.Series, comp: pd.Series,
                   bin_m: float = H_BIN) -> pd.Series:  # fmt: skip
    """Area weights: ``target`` fields keep their area; ``comp`` fields are rescaled so their
    area share per height bin matches the target's (bins the target lacks get 0). Fields in
    neither get 0."""
    b = np.floor(height / bin_m)
    want = ha[target].groupby(b[target]).sum()
    want = want / want.sum()
    have = ha[comp].groupby(b[comp]).sum()
    have = have / have.sum()
    scale = (want / have).reindex(b[comp]).fillna(0).values
    w = pd.Series(0.0, index=ha.index)
    w[target] = ha[target]
    w[comp] = ha[comp].values * scale
    return w


def deviations(v: pd.DataFrame, year: int, quiet: list[int], k: int, window: int = QUIET_WINDOW) -> pd.Series:
    """field x year table ``v``: each field's value in year + k minus its mean over the quiet
    years within ``window`` of ``year``."""
    base = [t for t in quiet if abs(t - year) <= window]
    return v[year + k] - v[base].mean(axis=1)


def estimate(d: pd.Series, w_t: pd.Series, w_c: pd.Series, boot: np.ndarray, scale: float = 100.0) -> np.ndarray:
    """scale * (flooded - comparison) weighted means of ``d`` for the point (column 0) and each
    bootstrap weight column of ``boot`` (field x draw). Fields where ``d`` is NaN drop out."""
    ok = d.notna().values
    dv, wt, wc = d.fillna(0).values, w_t.values * ok, w_c.values * ok
    W = np.column_stack([np.ones(len(dv)), boot])  # field x draw
    return scale * ((dv * wt) @ W / (wt @ W) - (dv * wc) @ W / (wc @ W))
