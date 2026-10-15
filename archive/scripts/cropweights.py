"""County cropland weights on a coarse regular grid (NWM 1 km, Stage IV / MRMS): every 30 m CDL
cropland pixel is binned to the cell holding its centre, per county. Used by
archive/scripts/fetch_nwm_soil.py and archive/scripts/rain_metrics.py."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: CDL years not used for weights (FINDINGS §1: CDL 2010 calls ~100 km2 extra
#: cropland in Gloucester, a classification artifact until shown otherwise).
SKIP_CDL = {2010}
CDL_PX = 30.0 * 30.0


@dataclass(frozen=True)
class Grid:
    """A window of a regular grid with ascending y: cell (iy, ix) spans
    [x0 + ix*dx, x0 + (ix+1)*dx) x [y0 + iy*dy, y0 + (iy+1)*dy)."""

    x0: float  # west edge of the window
    y0: float  # south edge of the window
    dx: float
    dy: float
    nx: int
    ny: int

    @property
    def x(self) -> np.ndarray:
        return self.x0 + (np.arange(self.nx) + 0.5) * self.dx

    @property
    def y(self) -> np.ndarray:
        return self.y0 + (np.arange(self.ny) + 0.5) * self.dy


def weighted_mean(v: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted mean over the last two axes of ``v`` (day, ny, nx) with ``w`` (ny, nx),
    ignoring NaN cells (their weight drops out). All-NaN -> NaN."""
    ok = np.isfinite(v)
    num = np.where(ok, v, 0.0).astype(np.float64) * w
    den = ok * w
    s = den.sum(axis=(-2, -1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, num.sum(axis=(-2, -1)) / s, np.nan)


def nearest_year(year: int, years) -> int:
    """The available year nearest ``year`` (ties go to the earlier year)."""
    ys = sorted(years)
    return min(ys, key=lambda y: (abs(y - year), y))


def bin_pixels(xs, ys, county_idx, grid: Grid, n_county: int) -> np.ndarray:
    """Counts of points per (county, cell); points outside the grid are dropped."""
    ix = np.floor((np.asarray(xs) - grid.x0) / grid.dx).astype(np.int64)
    iy = np.floor((np.asarray(ys) - grid.y0) / grid.dy).astype(np.int64)
    ok = (ix >= 0) & (ix < grid.nx) & (iy >= 0) & (iy < grid.ny)
    flat = (np.asarray(county_idx)[ok] * grid.ny + iy[ok]) * grid.nx + ix[ok]
    n = np.bincount(flat, minlength=n_county * grid.ny * grid.nx)
    return n.reshape(n_county, grid.ny, grid.nx)
