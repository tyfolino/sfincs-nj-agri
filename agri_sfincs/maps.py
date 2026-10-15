"""Shared pieces of the scenario maps: colours, the water / county / dike backdrop, and
place labels (names and coordinates in ``domain.PLACES``)."""

from __future__ import annotations

import numpy as np
import xarray as xr
from pyproj import Transformer

from agri_sfincs import dikes, domain, region, runs

CROP_COL, WATER_COL, LAND_COL = "#e2dccb", "#c6dbef", "#f4f4f2"


def backdrop(crs):
    """Water (model cells with bed < 0 m NAVD88: bay, tidal rivers; 100 m), counties, and the dike
    lines the model runs with (sfincs.weir; NLD alignments)."""
    base = runs.run_dir("tide2024oct", "intact", 0)
    with xr.open_dataset(base / "sfincs_map.nc") as mp:
        zb, msk = mp.zb.values, mp.msk.values
        wx0, wy0 = float(mp.corner_x.min()), float(mp.corner_y.min())
    water = np.where((msk > 0) & (zb < 0.0), 1, np.nan)
    wext = (wx0, wx0 + water.shape[1] * 100.0, wy0, wy0 + water.shape[0] * 100.0)
    cty = region.load_counties().to_crs(crs)
    cty = cty[cty.fips.isin(domain.COUNTIES)]
    lev = [(x, y) for _, x, y, _ in dikes.read_weir(base / "sfincs.weir")]
    return water, wext, cty, lev


def label_places(ax, crs, ext=None, color: str = "#0b0b0b") -> None:
    """Dot and name every town of ``domain.PLACES`` (inside ``ext`` = x0, x1, y0, y1, if given)."""
    px, py = Transformer.from_crs(4326, crs, always_xy=True).transform(
        [v[0] for v in domain.PLACES.values()], [v[1] for v in domain.PLACES.values()])  # fmt: skip
    for n, x, y in zip(domain.PLACES, px, py):
        if ext is None or (ext[0] < x < ext[1] and ext[2] < y < ext[3]):
            ax.plot(x, y, ".", color=color, ms=4)
            ax.annotate(n, (x, y), xytext=(3, 3), textcoords="offset points", fontsize=8)
