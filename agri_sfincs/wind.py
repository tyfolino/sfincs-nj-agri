"""Wind forcing for a staged run: ERA5 or HRRR 10 m wind, bilinear onto a 5 km grid, engine-ready.

Why (FINDINGS §48): without wind, Bivalve's storm peaks run 0.06-0.20 m high in NE storms
and up to 0.25 m low in S-SE ones. The boundary is observed water level, so it already
holds what wind does to the bay as a whole; wind inside the grid adds the setup across the
NJ (or DE) half of the bay and over the flooded marsh. No waves (user, 2026-10-27).

Sources (``SOURCES``; ``scale`` multiplies both components, its value from
scripts/check_wind.py against the bay lights):
  era5  ``scripts/fetch_era5_wind.py`` year files (0.25 deg lon / lat). Its ~28 km cells are
        part land over the bay: ~0.75x the lights (reports/era5_wind.md).
  hrrr  ``scripts/fetch_hrrr_wind.py`` window files (3 km, from 2014-07-30), already
        earth-relative, on HRRR's Lambert conformal grid: ``hrrr_axes`` recovers its regular
        x / y from the 2-D lat / lon and the projection in the file's attributes.

🔴 Grid convention (copied from nj_bight_sfincs nj_sfincs/meteo_grid.py, 2026-10-27, and
checked in this engine's source, sfincs_ncinput.F90 / sfincs_meteo.f90): the engine reads
the first ``x`` / ``y`` of ``sfincs_netamuv.nc`` as a cell CORNER (``xll = x(1) + dx/2`` is
the first column's centre). So the file carries ``centre - step/2`` on both axes, ``y``
ASCENDING. Writing centres puts every value half a step off (12.5 km on ERA5's grid; 2.5 km
on this 5 km one). The engine zeroes wind at points within one cell of the grid edge, so
the grid overhangs the model by PAD_CELLS.

The file (``write_forcing``): dims ``time`` x ``y`` x ``x``, ``eastward_wind`` /
``northward_wind`` (m/s), ``time`` in whole minutes since the run's start (the engine's
FEWS reader wants "minutes since YYYY-MM-DD HH:MM:SS"), and ``netamuamvfile`` in
sfincs.inp. Written after hydromt's ``sf.write()``, which would otherwise re-grid it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from agri_sfincs import config

FILE = "sfincs_netamuv.nc"
RES_M = 5000.0  # forcing grid step; ERA5 is ~21 x 28 km here, interpolated bilinear
PAD_CELLS = 3  # the engine zeroes wind within one cell of the grid edge
ORIGIN_ATTR = "grid_origin"
ORIGIN_VALUE = "engine-corner: written x/y = cell centre - step/2 (agri_sfincs.wind)"
SOURCES = ("era5", "hrrr")
#: HRRR's sphere (GRIB2 shape of the earth 6); lat_0 does not matter for the axes.
HRRR_PROJ = "+proj=lcc +lat_1={Latin1} +lat_2={Latin2} +lat_0={Latin1} +lon_0={LoV} +R=6371229 +units=m +no_defs"
#: Longest run of hours without HRRR (no analysis, no f01) filled linearly in time.
HRRR_MAX_GAP_H = 3


def year_file(year: int) -> Path:
    return config.WIND_DIR / "era5" / f"era5_wind_{year}.nc"


def load_era5(t0, t1):
    """ERA5 ``u10`` / ``v10`` for t0..t1 inclusive (hourly), from the year files."""
    import xarray as xr

    t0, t1 = pd.Timestamp(t0), pd.Timestamp(t1)
    files = [year_file(y) for y in range(t0.year, t1.year + 1)]
    missing = [f for f in files if not f.is_file()]
    if missing:
        raise FileNotFoundError(f"no ERA5 wind for {missing} (scripts/fetch_era5_wind.py)")
    ds = xr.open_mfdataset(files, combine="by_coords") if len(files) > 1 else xr.open_dataset(files[0])
    ds = ds[["u10", "v10"]].sel(time=slice(t0, t1)).load()
    want = pd.date_range(t0, t1, freq="h")
    if len(ds.time) != len(want) or (ds.time.values != want.values).any():
        raise ValueError(f"ERA5 wind for {t0}..{t1} has {len(ds.time)} of {len(want)} hours")
    return ds


def hrrr_axes(ds) -> tuple[np.ndarray, np.ndarray, str]:
    """(x, y, proj string) of a fetch_hrrr_wind file: its regular Lambert conformal axes
    (m), from the 2-D lat / lon; raises if they are not regular within 1 m."""
    from pyproj import Transformer

    from agri_sfincs.precip import regular_axis

    proj = HRRR_PROJ.format(**{k: ds.attrs[k] for k in ("Latin1", "Latin2", "LoV")})
    X, Y = Transformer.from_crs("EPSG:4326", proj, always_xy=True).transform(
        ds["longitude"].values, ds["latitude"].values)  # fmt: skip
    x0, dx = regular_axis(X, axis=1, tol=1.0)
    y0, dy = regular_axis(Y, axis=0, tol=1.0)
    return x0 + dx * np.arange(X.shape[1]), y0 + dy * np.arange(X.shape[0]), proj


def load_hrrr(t0, t1):
    """HRRR ``u10`` / ``v10`` for t0..t1 inclusive (hourly) from the window file that covers
    it, on its regular x / y (``attrs["proj"]``). Up to HRRR_MAX_GAP_H missing hours in a
    row are filled linearly in time (``attrs["filled_hours"]``)."""
    import xarray as xr

    t0, t1 = pd.Timestamp(t0), pd.Timestamp(t1)
    for f in sorted((config.WIND_DIR / "hrrr").glob("hrrr_wind_*.nc")):
        with xr.open_dataset(f) as ds:
            if ds.time.values[0] <= t0 and ds.time.values[-1] >= t1:
                ds = ds.sel(time=slice(t0, t1)).load()
                break
    else:
        raise FileNotFoundError(f"no HRRR wind file covers {t0}..{t1} (scripts/fetch_hrrr_wind.py)")
    want = pd.date_range(t0, t1, freq="h")
    if len(ds.time) != len(want) or (ds.time.values != want.values).any():
        raise ValueError(f"HRRR wind for {t0}..{t1} has {len(ds.time)} of {len(want)} hours")
    x, y, proj = hrrr_axes(ds)
    ds = ds.drop_vars(["latitude", "longitude"]).assign_coords(x=x, y=y)
    gap = np.isnan(ds.u10.values).all(axis=(1, 2))
    ds = ds[["u10", "v10"]].interpolate_na("time", max_gap=pd.Timedelta(hours=HRRR_MAX_GAP_H + 1))
    if np.isnan(ds.u10.values).any() or np.isnan(ds.v10.values).any():
        raise ValueError(f"HRRR wind for {t0}..{t1}: a gap longer than {HRRR_MAX_GAP_H} h")
    ds.attrs.update(proj=proj, filled_hours=int(gap.sum()))
    return ds


def load(source: str, t0, t1):
    """``u10`` / ``v10`` (earth-relative, m/s) for t0..t1 hourly from ``source``."""
    if source == "era5":
        return load_era5(t0, t1)
    if source == "hrrr":
        return load_hrrr(t0, t1)
    raise ValueError(f"wind source {source!r}; known: {SOURCES}")


def at_point(ds, lon: float, lat: float) -> tuple[np.ndarray, np.ndarray]:
    """(u, v) per time at (lon, lat), bilinear, from ``load``'s output."""
    if "longitude" in ds.dims:
        e = ds.interp(longitude=lon, latitude=lat)
    else:
        from pyproj import Transformer

        x, y = Transformer.from_crs("EPSG:4326", ds.attrs["proj"], always_xy=True).transform(lon, lat)
        e = ds.interp(x=x, y=y)
    return e.u10.values, e.v10.values


def model_bounds(root: Path) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) of the model's quadtree nodes, m."""
    import xarray as xr

    with xr.open_dataset(Path(root) / "sfincs.nc") as q:
        x, y = q["mesh2d_node_x"].values, q["mesh2d_node_y"].values
    return float(x.min()), float(y.min()), float(x.max()), float(y.max())


def grid_centres(bounds, res: float = RES_M, pad: int = PAD_CELLS) -> tuple[np.ndarray, np.ndarray]:
    """Cell centres (x, y ascending) of a ``res`` grid covering ``bounds`` + ``pad`` cells."""
    x0, y0, x1, y1 = bounds
    nx = int(np.ceil((x1 - x0) / res)) + 2 * pad
    ny = int(np.ceil((y1 - y0) / res)) + 2 * pad
    xc = x0 - (pad - 0.5) * res + res * np.arange(nx)
    yc = y0 - (pad - 0.5) * res + res * np.arange(ny)
    return xc, yc


def regrid(ds, xc: np.ndarray, yc: np.ndarray, epsg: int):
    """``ds`` (u10, v10 on latitude / longitude, or on regular x / y in ``attrs["proj"]``
    as load_hrrr gives) bilinear at the UTM centres: (u, v) as float32 arrays (time, y, x).
    Components are interpolated separately, never speed."""
    import pyproj
    import xarray as xr

    X, Y = np.meshgrid(xc, yc)
    if "longitude" in ds.dims:
        lon, lat = pyproj.Transformer.from_crs(epsg, 4326, always_xy=True).transform(X, Y)
        at = {"longitude": lon, "latitude": lat}
    else:
        px, py = pyproj.Transformer.from_crs(epsg, ds.attrs["proj"], always_xy=True).transform(X, Y)
        at = {"x": px, "y": py}
    out = ds.interp({k: xr.DataArray(v, dims=("row", "col")) for k, v in at.items()}, method="linear")
    u, v = out["u10"].values.astype("f4"), out["v10"].values.astype("f4")
    if np.isnan(u).any() or np.isnan(v).any():
        raise ValueError("wind grid reaches outside the fetched box (fetch_*_wind.BOX)")
    return u, v


def write_file(path: Path, times: pd.DatetimeIndex, xc, yc, u, v, t_ref, epsg: int, attrs: dict) -> None:
    """Write the engine's netamuamv file; x / y carry the corner convention (see module doc)."""
    import xarray as xr

    dx, dy = float(xc[1] - xc[0]), float(yc[1] - yc[0])
    if dy <= 0 or dx <= 0:
        raise ValueError("wind grid axes must ascend")
    minutes = ((times - pd.Timestamp(t_ref)) / pd.Timedelta("1min")).values
    if not np.allclose(minutes, np.round(minutes)):
        raise ValueError("wind times must be whole minutes after the reference")
    xa = {"units": "m", ORIGIN_ATTR: ORIGIN_VALUE, "first_cell_centre": float(xc[0])}
    ya = {"units": "m", ORIGIN_ATTR: ORIGIN_VALUE, "first_cell_centre": float(yc[0])}
    ds = xr.Dataset(
        {"eastward_wind": (("time", "y", "x"), u, {"units": "m s-1"}),
         "northward_wind": (("time", "y", "x"), v, {"units": "m s-1"})},
        coords={"time": ("time", minutes.astype("f8"),
                         {"units": f"minutes since {pd.Timestamp(t_ref):%Y-%m-%d %H:%M:%S}"}),
                "y": ("y", yc - dy / 2, ya), "x": ("x", xc - dx / 2, xa)},
        attrs={ORIGIN_ATTR: ORIGIN_VALUE, "epsg": epsg, **attrs},
    )  # fmt: skip
    enc = {k: {"_FillValue": None} for k in ("time", "x", "y")}
    ds.to_netcdf(path, encoding=enc)


def write_forcing(run: Path, t0, t1, scale: float = 1.0, res: float = RES_M,
                  source: str = "era5") -> Path:  # fmt: skip
    """``source`` wind for run window t0..t1 on the run's model, ``scale`` x both
    components; writes ``FILE`` and points sfincs.inp at it."""
    from agri_sfincs import domain
    from agri_sfincs.restart import inp_set

    run = Path(run)
    ds = load(source, t0, t1)
    xc, yc = grid_centres(model_bounds(run), res)
    u, v = regrid(ds, xc, yc, domain.EPSG)
    times = pd.DatetimeIndex(ds.time.values)
    write_file(run / FILE, times, xc, yc, u * scale, v * scale, t0, domain.EPSG,
               {"source": f"{source} 10 m wind (agri_sfincs.wind)", "scale": float(scale)})  # fmt: skip
    inp = run / "sfincs.inp"
    inp.write_text(inp_set(inp.read_text(), {"netamuamvfile": FILE}))
    return run / FILE


def engine_sample(path: Path, x: float, y: float,
                  names: tuple[str, ...] = ("eastward_wind", "northward_wind")) -> np.ndarray:  # fmt: skip
    """``names`` per time at point (x, y) as the ENGINE reads ``path`` (sfincs_meteo.f90
    update_amuv_data, and the same for netampr: rows flipped, corner origin, SIGNED dy,
    bilinear), for tests and checks. Returns (time, len(names))."""
    import xarray as xr

    with xr.open_dataset(path, decode_times=False) as ds:
        wx, wy = ds["x"].values, ds["y"].values
        fields = [ds[n].values[:, ::-1, :] for n in names]  # engine row 1 = last file row
    nrows = len(wy)
    dx, dy = wx[1] - wx[0], wy[1] - wy[0]
    yul = wy[0] + (nrows - 1) * dy + 0.5 * dy
    xll = wx[0] + 0.5 * dx
    iy = int((yul - y) / dy) + 1
    dj = (yul - (iy - 1) * dy - y) / dy
    ix = int((x - xll) / dx) + 1
    di = (x - (xll + (ix - 1) * dx)) / dx
    r, c = iy - 1, ix - 1  # 0-based
    out = []
    for F in fields:
        f = ((1 - di) * (1 - dj) * F[:, r, c] + di * (1 - dj) * F[:, r, c + 1]
             + di * dj * F[:, r + 1, c + 1] + (1 - di) * dj * F[:, r + 1, c])  # fmt: skip
        out.append(f)
    return np.stack(out, axis=1)
