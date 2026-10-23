"""Finished SFINCS runs: where they live, whether they finished, and how a 10 m subgrid
pixel maps onto the model's map output.

Every model here is a UNIFORM quadtree, so SFINCS writes its map output on the regular
(n, m) grid, row 0 = south. A pixel belongs to the cell its centre falls in.
Daily maxima: with dtmaxout = 1 day, the ``zsmax`` block ending at ``timemax`` = D 00:00
covers day D - 1 (``block_days``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from agri_sfincs import config

#: A pixel is flooded when the water over it is deeper than this (m).
THRESH = 0.05
#: The model every scenario run uses.
MODEL = "v1_100m"
#: Dike scenarios (scripts/setup_scenarios.py) -> label, and the sea-level rises run (cm).
DIKES = {"intact": "dikes as built", "removed": "dikes removed", "breach_all_farm": "100 m breach in every farm bank"}
SLR_CM = (0, 30, 60, 100)


def model_side(model) -> str:
    """The side a static model was built for: <model>/side.txt (scripts/build_model.py
    --side), "nj" for models built before 2026-10-23. ``model``: a name or a path."""
    root = model if isinstance(model, Path) else config.MODELS / model
    f = Path(root) / "side.txt"
    return f.read_text().strip() if f.exists() else "nj"


def run_dir(event: str, dikes: str, slr_cm: int, suffix: str = "", model: str = MODEL) -> Path:
    """A scenario run (scripts/setup_scenarios.py): ``<event>_<dikes>_slr<cm><suffix>``."""
    return config.MODELS / model / "runs" / f"{event}_{dikes}_slr{slr_cm:03d}{suffix}"


def resolve(spec: str) -> Path:
    """``"<model>/<run>"`` (e.g. ``v1_100m/sep2023``), or a bare ``"<run>"`` of ``MODEL``
    -> the run directory."""
    model, run = spec.split("/") if "/" in spec else (MODEL, spec)
    return config.MODELS / model / "runs" / run


def finished(run: Path) -> bool:
    """The run's log says it ended normally (not run yet, still running or crashed: False)."""
    log = run / "sfincs_log.txt"
    return log.exists() and "Total time" in log.read_text(errors="ignore")


def subgrid_dep(model: str = MODEL) -> Path:
    """The model's 10 m subgrid ground (m NAVD88), row 0 = north."""
    return config.MODELS / model / "subgrid" / "dep_subgrid_lev0.tif"


@dataclass(frozen=True)
class MapGrid:
    """The regular grid of a uniform quadtree's map output: SW corner, cell size, shape."""

    x0: float
    y0: float
    dx: float
    n: int
    m: int

    @classmethod
    def from_map(cls, mp) -> MapGrid:
        """From an open sfincs_map.nc (xarray)."""
        cx = mp["corner_x"].values
        dx = float(np.diff(np.unique(cx.round(3)))[0])
        return cls(float(cx.min()), float(mp["corner_y"].min()), dx, mp.sizes["n"], mp.sizes["m"])

    def index(self, x, y) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Row ``nn``, column ``mm`` of the cell holding each point, and whether it is inside."""
        nn = np.floor((y - self.y0) / self.dx).astype(np.int64)
        mm = np.floor((x - self.x0) / self.dx).astype(np.int64)
        inside = (nn >= 0) & (nn < self.n) & (mm >= 0) & (mm < self.m)
        return nn, mm, inside

    def face(self, x, y) -> np.ndarray:
        """Flat cell index (``nn * m + mm``) of each point; -1 outside the grid."""
        nn, mm, inside = self.index(x, y)
        return np.where(inside, nn * self.m + mm, -1)


def pixel_centres(tr, rows, cols) -> tuple[np.ndarray, np.ndarray]:
    """x, y of the centres of pixels (``rows``, ``cols``) of a raster with transform ``tr``."""
    return tr.c + (cols + 0.5) * tr.a, tr.f + (rows + 0.5) * tr.e


def pixel_cells(ids: np.ndarray, tr, dep: np.ndarray, grid: MapGrid):
    """Every pixel with a nonzero label in ``ids`` that falls inside ``grid`` and has a finite
    ground: (flat cell index, ground elevation, label)."""
    rr, cc = np.nonzero(ids)
    face = grid.face(*pixel_centres(tr, rr, cc))
    ok = (face >= 0) & np.isfinite(dep[rr, cc])
    return face[ok], dep[rr, cc][ok], ids[rr, cc][ok].astype(np.int64)


def block_days(mp) -> pd.DatetimeIndex:
    """The day each daily ``zsmax`` block covers."""
    return pd.to_datetime(mp["timemax"].values) - pd.Timedelta(days=1)


def depth(mp, k: int, face: np.ndarray, dep: np.ndarray) -> np.ndarray:
    """Water depth over each pixel at its cell's max level in ``zsmax`` block ``k``: float32,
    0 where dry or unknown."""
    h = mp["zsmax"][k].values.ravel()[face] - dep
    return np.where(np.isfinite(h) & (h > 0), h, 0).astype("float32")


def centreline_links(grid: MapGrid, line, step: float = 10.0) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Cell-centre to cell-centre links a channel along ``line`` (shapely, model CRS) must
    flow through on the uniform ``grid``: one per step between the consecutive cells the line
    visits, and, where it steps diagonally, the four links of the two detours through the
    side cells (flow between cells only crosses shared faces)."""
    cells: list[tuple[int, int]] = []
    for d in np.arange(0.0, line.length + step / 2, step):
        p = line.interpolate(min(d, line.length))
        nn, mm, inside = grid.index(np.array([p.x]), np.array([p.y]))
        if inside[0] and (not cells or cells[-1] != (int(nn[0]), int(mm[0]))):
            cells.append((int(nn[0]), int(mm[0])))

    def centre(c):
        return (grid.x0 + (c[1] + 0.5) * grid.dx, grid.y0 + (c[0] + 0.5) * grid.dx)

    links = []
    for a, b in zip(cells[:-1], cells[1:]):
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
            links.append((centre(a), centre(b)))
        else:  # diagonal (or a jump of a long step): both L-shaped detours
            for side in ((a[0], b[1]), (b[0], a[1])):
                links += [(centre(a), centre(side)), (centre(side), centre(b))]
    return links
