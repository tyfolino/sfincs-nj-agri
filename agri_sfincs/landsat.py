"""Landsat Collection 2 Level-2 surface reflectance: clear mask, indices, per-field stats.

Pure pieces for scripts/landsat_field_stats.py (no network):

* ``clear(qa_pixel)``: QA_PIXEL bits (C2, all sensors) 0 fill, 1 dilated cloud, 2 cirrus,
  3 cloud, 4 cloud shadow, 5 snow. A pixel is clear when none are set.
* ``reflectance(dn)``: C2 L2 SR scaling, 0.0000275 * DN - 0.2, with DN 0 = fill → NaN.
* ``indices``: NDVI = (nir - red)/(nir + red); BSI (bare-soil index) =
  ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue)); MNDWI =
  (green - swir1)/(green + swir1). Tilled bare soil has low NDVI and high BSI; open water or
  flooded ground has MNDWI > 0.
* ``field_means(labels, arrays, ok)``: per-label count of clear pixels and the mean of each
  array over them, via bincount (labels 0 = not a field).

Field units are rasterised INSET from their edges (scripts/landsat_field_stats.py), so mixed
edge pixels — the CDL failure in FINDINGS §21 — stay out.
"""

from __future__ import annotations

import numpy as np

QA_BAD = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
SR_SCALE, SR_OFFSET = 0.0000275, -0.2


def clear(qa: np.ndarray) -> np.ndarray:
    return (np.asarray(qa).astype("uint32") & QA_BAD) == 0


def reflectance(dn: np.ndarray) -> np.ndarray:
    dn = np.asarray(dn, dtype="float32")
    return np.where(dn > 0, dn * SR_SCALE + SR_OFFSET, np.nan).astype("float32")


def _nd(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return ((a - b) / (a + b)).astype("float32")


def indices(blue, green, red, nir, swir1) -> dict[str, np.ndarray]:
    return {"ndvi": _nd(nir, red), "bsi": _nd(swir1 + red, nir + blue), "mndwi": _nd(green, swir1)}


def field_means(labels: np.ndarray, arrays: dict[str, np.ndarray], ok: np.ndarray,
                n_labels: int) -> dict[str, np.ndarray]:  # fmt: skip
    """{"n": clear-pixel count per label, name: mean per label} for labels 1..n_labels
    (index 0 of every output is label 0 and is meaningless). NaN where n == 0; a pixel
    counts only if ``ok`` and every array is finite there."""
    m = ok & (labels > 0)
    for a in arrays.values():
        m &= np.isfinite(a)
    lab = labels[m]
    n = np.bincount(lab, minlength=n_labels + 1).astype("float64")
    out = {"n": n}
    with np.errstate(divide="ignore", invalid="ignore"):
        for k, a in arrays.items():
            out[k] = np.bincount(lab, weights=a[m], minlength=n_labels + 1) / n
    return out
