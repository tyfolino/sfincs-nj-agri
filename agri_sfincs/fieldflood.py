"""Per-field flooding in the dike x sea-level scenario runs: the per-pixel stats read from a
run (``field_pixels``, ``run_stats``) and the class rules (pure pieces).

A field "floods" in a run when at least ``SHARE`` of its 10 m pixels see a month-max depth
above 5 cm. For each field we know, per dike scenario, the lowest sea-level rise (of
``LEVELS``) at which it floods: ``first_level``. ``classify`` turns the as-built and
dikes-removed answers into one class, earliest threat first:

  flooded today          floods with today's dikes at today's sea level
  dike-dependent today   floods today only if the dikes are removed
  dike-dependent +L      first floods at +L, and only without the dikes there
  overtopped +L          first floods at +L even with the dikes; behind an NLD levee
  exposed +L             the same, not behind a levee (no dike to help)
  safe to +1.0 m         dry in every run

Removing the dikes can (rarely) leave a field drier, when a bank held water in. Then the
as-built level decides and the class is overtopped / exposed.
"""

from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.features import rasterize

from agri_sfincs import dikes, domain, region, runs
from agri_sfincs.events import EVENTS

LEVELS = (0.0, 0.3, 0.6, 1.0)
SHARE = 0.10
SAFE = "safe to +1.0 m"


def first_level(shares, levels=LEVELS, share: float = SHARE) -> float:
    """Lowest level whose flooded share is >= ``share``; NaN if none. ``shares`` aligns with
    ``levels``; a NaN share (run missing) never counts as flooded."""
    for lev, s in zip(levels, shares):
        if s is not None and np.isfinite(s) and s >= share:
            return float(lev)
    return math.nan


def _lev(x: float) -> str:
    return f"+{x:.1f} m"


def classify(with_dikes: float, without_dikes: float, behind_levee: bool) -> str:
    w, wo = with_dikes, without_dikes
    if w == 0.0:
        return "flooded today"
    if wo == 0.0:
        return "dike-dependent today"
    if math.isnan(w) and math.isnan(wo):
        return SAFE
    if math.isnan(w) or (not math.isnan(wo) and wo < w):
        return f"dike-dependent {_lev(wo)}"
    return f"{'overtopped' if behind_levee else 'exposed'} {_lev(w)}"


def class_order() -> list[str]:
    """Every class, earliest threat first (for tables and legends)."""
    out = ["flooded today", "dike-dependent today"]
    for lev in LEVELS[1:]:
        out += [f"dike-dependent {_lev(lev)}", f"overtopped {_lev(lev)}", f"exposed {_lev(lev)}"]
    return out + [SAFE]


def longest_run(wet) -> int:
    """Longest run of consecutive True values in a 1-D boolean sequence (days)."""
    best = cur = 0
    for w in wet:
        cur = cur + 1 if w else 0
        best = max(best, cur)
    return best


def add_county_levee(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """``g`` (polygons, any projected crs) cut to the study counties, plus ``county`` (by
    representative point) and ``behind_levee`` (at least half the polygon inside an NLD leveed
    area). Index reset."""
    cty = region.load_counties().to_crs(g.crs)
    cty = cty[cty.fips.isin(domain.COUNTIES)][["name", "geometry"]].rename(columns={"name": "county"})
    pts = g[["geometry"]].copy()
    pts["geometry"] = g.representative_point()
    g = g.copy()
    g["county"] = gpd.sjoin(pts, cty, how="left", predicate="within").groupby(level=0).county.first()
    g = g[g.county.notna()].reset_index(drop=True)
    lev = dikes.leveed_areas(g.crs)
    inter = gpd.overlay(g[["geometry"]].reset_index(names="fid"), lev[["geometry"]], how="intersection")
    share = inter.assign(a=inter.area).groupby("fid").a.sum() / g.area
    g["behind_levee"] = share.reindex(g.index).fillna(0).values >= 0.5
    return g


def field_pixels(g, model: str = runs.MODEL):
    """Every 10 m subgrid pixel of every field (``g.field_id``, 1..N): (flat model-cell index,
    ground elevation, field_id), for pixels inside the model grid with a finite ground."""
    with rasterio.open(runs.subgrid_dep(model)) as d:
        dep = d.read(1, masked=True).filled(np.nan)
        tr, shape = d.transform, d.shape
    ids = rasterize(zip(g.geometry, g.field_id), out_shape=shape, transform=tr, fill=0, dtype="uint32")
    with xr.open_dataset(runs.run_dir("tide2024oct", "intact", 0, model=model) / "sfincs_map.nc") as mp:
        grid = runs.MapGrid.from_map(mp)
    return runs.pixel_cells(ids, tr, dep, grid)


def run_stats(run, f_sel, d_sel, fid, nfield, event: str) -> pd.DataFrame:
    """Per field: share of pixels flooded (> 5 cm month max), mean wet days, mean max depth
    over flooded pixels, over ``event``'s focus period."""
    with xr.open_dataset(run / "sfincs_map.nc") as mp:
        focus = EVENTS[event].in_focus(runs.block_days(mp))
        maxd = np.zeros(f_sel.size, "float32")
        wet = np.zeros(f_sel.size, "uint16")
        for k in np.flatnonzero(focus):
            h = runs.depth(mp, k, f_sel, d_sel)
            maxd = np.maximum(maxd, h)
            wet += h > runs.THRESH
    npx = np.bincount(fid, minlength=nfield + 1).astype(float)
    fl = maxd > runs.THRESH
    nfl = np.bincount(fid, weights=fl, minlength=nfield + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return pd.DataFrame({
            "share": nfl / npx,
            "wetdays": np.bincount(fid, weights=wet, minlength=nfield + 1) / npx,
            "maxd": np.bincount(fid, weights=np.where(fl, maxd, 0), minlength=nfield + 1) / nfl,
        }).iloc[1:].set_index(np.arange(1, nfield + 1))  # fmt: skip
