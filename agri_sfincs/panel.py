"""Shared pieces of the land-use panel analyses (scripts/storm_overlap.py,
scripts/plot_storm_panel.py): the low-crop-field set and height reweighting. Pure, tested."""

from __future__ import annotations

import numpy as np
import pandas as pd

MAX_H = 1.5  # m above MHHW
PRE = range(2008, 2013)  # CDL years before Sandy
H_BIN = 0.25  # m, height bins for reweighting
CDL_CHANGE = 2024  # CDL product change: cropland drops on every low field from here (FINDINGS §37)
# land-use classes of sandy_panel/field_year.csv; a field's main class is the largest of them
CLASSES = ["share_corn", "share_soybeans", "share_other_grains", "share_hay", "share_idle", "share_other_crops",
           "share_pasture", "share_herb_wetland", "share_woody_wetland", "share_forest_shrub", "share_developed",
           "share_water", "share_other"]  # fmt: skip


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
