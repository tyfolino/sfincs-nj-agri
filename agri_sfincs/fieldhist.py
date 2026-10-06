"""Per-field farming history from per-scene Landsat field means (pure pieces).

``yearly_features``: per (unit, year), the median NDVI / MNDWI / BSI / SWIR1 / NIR in three
windows (spring = day 74-166, summer = 167-257, fall = 258-349), the summer max NDVI and
the spring min NDVI, using only scenes where the unit was mostly clear (n >= MIN_CLEAR px
and >= CLEAR_FRAC of its valid pixels) and whose normalised indices lie in [-1, 1] (negative
surface reflectance, mostly over water, gives NDVI down to -107 on ~0.2% of scene rows; until
2026-10-06 these reached the min / max features). What separates farmed fields from marsh here is
summer wetness (MNDWI) and peak greenness, NOT spring bare soil: dormant marsh looks "bare"
to the BSI too (FINDINGS §24).

``exit_year``: from a yearly farmed / not-farmed series, the last farmed year before a run
of at least ``min_run`` not-farmed years that lasts to the end of the record; None if the
unit is farmed at the end, or was never farmed.

``exit_events``: the censoring-safe version for rates. Year y is AT RISK if farmed in y and
the next ``window`` years have at least ``window - 1`` observations; it is an EXIT if all
of those observations are not farmed. Every period is then held to the same test, unlike
``exit_year``, which asks early exits to last to the end of the record.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_CLEAR, CLEAR_FRAC = 3, 0.6
WINDOWS = {"sp": (74, 167), "su": (167, 258), "fa": (258, 350)}
VARS = ["ndvi", "mndwi", "bsi", "swir1", "nir"]


def yearly_features(d: pd.DataFrame) -> pd.DataFrame:
    """``d``: rows of scripts/landsat_field_stats.py (unit, date, n, n_valid, VARS)."""
    ok = (d[["ndvi", "mndwi", "bsi"]].abs() <= 1).all(axis=1)
    d = d[(d.n >= MIN_CLEAR) & (d.n >= CLEAR_FRAC * d.n_valid) & ok].copy()
    d["year"] = d.date.dt.year
    doy = d.date.dt.dayofyear
    parts = []
    for w, (a, b) in WINDOWS.items():
        x = d[(doy >= a) & (doy < b)]
        g = x.groupby(["unit", "year"])[VARS].median().add_prefix(f"{w}_")
        g[f"{w}_nobs"] = x.groupby(["unit", "year"]).size()
        parts.append(g)
    su = d[(doy >= WINDOWS["su"][0]) & (doy < WINDOWS["su"][1])]
    sp = d[(doy >= WINDOWS["sp"][0]) & (doy < WINDOWS["sp"][1])]
    fa = d[(doy >= WINDOWS["fa"][0]) & (doy < WINDOWS["fa"][1])]
    parts.append(su.groupby(["unit", "year"]).ndvi.max().rename("su_ndvi_max"))
    parts.append(su.groupby(["unit", "year"]).ndvi.min().rename("su_ndvi_min"))  # hay cuts
    parts.append(sp.groupby(["unit", "year"]).ndvi.min().rename("sp_ndvi_min"))
    parts.append(fa.groupby(["unit", "year"]).ndvi.min().rename("fa_ndvi_min"))  # harvest
    return pd.concat(parts, axis=1)


def exit_year(years, farmed, min_run: int = 3):
    """Last farmed year followed by >= ``min_run`` not-farmed years to the end of the record.
    ``farmed`` may hold NaN (no data): those years neither break nor extend a run."""
    y = np.asarray(years)
    f = np.asarray(farmed, dtype=float)
    ok = np.isfinite(f)
    y, f = y[ok], f[ok] > 0.5
    if f.size == 0 or not f.any() or f[-1]:
        return None
    last = int(np.flatnonzero(f)[-1])
    return int(y[last]) if (f.size - 1 - last) >= min_run else None


def exit_events(years, farmed, window: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """(at_risk, exit) boolean arrays aligned with ``years`` (see module docstring).
    ``years`` must be consecutive integers; ``farmed`` holds 1 / 0 / NaN."""
    f = np.asarray(farmed, dtype=float)
    n = f.size
    risk, ex = np.zeros(n, bool), np.zeros(n, bool)
    for i in range(n - window):
        if f[i] != 1:
            continue
        nxt = f[i + 1 : i + 1 + window]
        obs = nxt[np.isfinite(nxt)]
        if obs.size >= window - 1:
            risk[i] = True
            ex[i] = bool((obs < 0.5).all())
    return risk, ex
