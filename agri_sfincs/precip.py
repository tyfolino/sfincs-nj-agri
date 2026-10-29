"""Precipitation forcing for any run window, from the hourly year files.

``scripts/fetch_precip_hourly.py`` keeps one file per product and year,
``data/precip/<product>/<product>_<year>.nc``: ``precip(time, y, x)`` mm in the hour
ENDING at ``time`` (UTC), plus ``status`` / ``n_nan`` per hour. Those files are not in
the shape hydromt wants (MRMS has ``y`` / ``x`` dims with 1-D ``lat`` / ``lon`` beside
them; Stage IV is HRAP polar stereographic with 2-D lat / lon), and they have NaN hours.
``build_forcing`` cuts a window out of them and writes ONE file hydromt reads like the
event files (``data/precip/mrms_2023-09.nc``: hour-ending mm on a regular grid), and
``ensure_catalog_entry`` registers it in the live data catalog.

Products (CLAUDE.md: MRMS where it exists, Stage IV before):
  mrms    0.01 deg lon/lat, written with ``lat`` / ``lon`` dims (north -> south rows, as
          the event files), CRS EPSG:4326. Values identical to the event files'.
  stage4  HRAP ~4.76 km, written on its projected x / y (ascending, regular to < 60 m:
          ``regular_axis``) with the HRAP proj string as CRS.

Gaps (NaN): MRMS hours are filled from Stage IV (the HRAP cell holding each MRMS cell
centre, same hour); Stage IV hours from its 6-h totals (``fill_from_6h``:
the 6-h remainder spread evenly over the missing hours); anything left is 0. The counts
go in the file's attributes and are printed: 2023 MRMS has 6 empty hours (2023-07-09
15-16Z among them) and 2022 has 19.

🔴 Placement (2026-10-29): hydromt writes the staged run's ``sfincs_netampr.nc`` with
cell CENTRES on x / y; the engine reads the first value as a cell CORNER (the convention
in agri_sfincs.wind's module doc). Every run staged before 2026-10-29 has its rain half a
rain cell west and north of where it fell (~2 km on Stage IV, ~0.5 km on MRMS).
``to_engine_origin`` rewrites the staged file's x / y as ``centre - step/2``;
``true_centres`` gives a reader the real centres back.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from agri_sfincs import config
from agri_sfincs.wind import ORIGIN_ATTR, ORIGIN_VALUE

PRODUCTS = ("mrms", "stage4")
FORCING_DIR = config.PRECIP_DIR / "forcing"


def window_hours(t0, t1) -> pd.DatetimeIndex:
    """Hour-ending times a run from ``t0`` to ``t1`` needs: ``t0`` .. ``t1`` inclusive.
    hydromt (cumulative_input, time_label="right") shifts each value back one step, so
    the label ``t0`` carries the hour ending ``t0`` + 1 h; the label ``t0`` itself only
    keeps the time axis covering the run (otherwise SFINCS warns and uses the nearest)."""
    return pd.date_range(pd.Timestamp(t0), pd.Timestamp(t1), freq="h")


def file_years(hours) -> list[int]:
    """Year files holding hour-ending ``hours``: the hour ending Jan 1 00:00 is in the
    previous year's file."""
    return sorted({(t - pd.Timedelta("1h")).year for t in pd.DatetimeIndex(hours)})


def year_files(product: str, hours: pd.DatetimeIndex, required: bool = True) -> list[Path]:
    """Year files holding ``hours`` (a year file holds the hours ending
    <year>-01-01T01 .. <year+1>-01-01T00). ``product`` may be ``stage4_6h``."""
    files = [config.PRECIP_DIR / product / f"{product}_{y}.nc" for y in file_years(hours)]
    missing = [f for f in files if not f.is_file()]
    if missing and required:
        raise FileNotFoundError(f"no hourly {product} file(s): {missing}")
    return [f for f in files if f.is_file()]


def load_window(files: list[Path], hours: pd.DatetimeIndex):
    """(precip (len(hours), y, x) float32, NaN where absent; one file's Dataset without
    its time axis, for coordinates and attributes; None if ``files`` is empty)."""
    import xarray as xr

    arrs, times, ref = [], [], None
    for f in files:
        with xr.open_dataset(f) as ds:
            s = ds.sel(time=slice(hours[0], hours[-1]))
            arrs.append(s.precip.values.astype("float32"))
            times.append(pd.DatetimeIndex(s.time.values))
            ref = ds.drop_vars([v for v in ds.data_vars if v != "precip"]).isel(time=0).load()
    if ref is None:
        return None, None
    t = times[0].append(times[1:]) if len(times) > 1 else times[0]
    p = np.full((len(hours),) + arrs[0].shape[1:], np.nan, np.float32)
    k = hours.get_indexer(t)
    p[k[k >= 0]] = np.concatenate(arrs)[k >= 0]
    return p, ref


def six_hour_windows(p: np.ndarray, t_end, p6: np.ndarray, t6_end) -> dict:
    """Hourly ``p`` (time, cell) grouped into the 6-h windows of ``p6``: window ``end``
    times, each hour's window ``run`` index, and per window x cell the sum of the hours
    present (``have``), the count of NaN hours (``nmiss``), the hours on the axis
    (``nh``) and the 6-h value (``six``, NaN if there is none)."""
    t_end = pd.DatetimeIndex(t_end)
    wend = t_end.ceil("6h")
    if len(wend) > 1 and (np.diff(wend.values) < np.timedelta64(0, "s")).any():
        raise ValueError("t_end must be sorted")
    ends, starts = np.unique(wend.values, return_index=True)
    nh = np.diff(np.append(starts, len(wend)))
    k = pd.DatetimeIndex(t6_end).get_indexer(pd.DatetimeIndex(ends))
    return {
        "end": pd.DatetimeIndex(ends),
        "run": np.repeat(np.arange(len(ends)), nh),
        "nh": nh,
        "have": np.add.reduceat(np.nan_to_num(p, nan=0.0).astype(np.float64), starts, axis=0),
        "nmiss": np.add.reduceat(np.isnan(p).astype(np.int64), starts, axis=0),
        "six": np.where((k >= 0)[:, None], p6[np.maximum(k, 0)], np.nan),
    }


def fill_from_6h(p: np.ndarray, t_end, p6: np.ndarray, t6_end):
    """Fill NaN hours of ``p`` (time, cell; hour-ending ``t_end``) from 6-h totals ``p6``
    (ending ``t6_end`` at 00/06/12/18Z): in each cell's 6-h window, what the 6-h total
    holds beyond the hours present (never below 0) is spread evenly over the missing
    hours. Hours whose window has no 6-h value stay NaN. Returns (filled copy, mask of
    filled values)."""
    win = six_hour_windows(p, t_end, p6, t6_end)
    run, have, nmiss, six = win["run"], win["have"], win["nmiss"], win["six"]
    with np.errstate(invalid="ignore", divide="ignore"):
        per = np.maximum(six - have, 0.0) / nmiss
    fill = np.isnan(p) & np.isfinite(per[run])
    out = p.copy()
    out[fill] = per[run][fill]
    return out, fill


def regular_axis(v: np.ndarray, axis: int, tol: float) -> tuple[float, float]:
    """(first centre, spacing) of 2-D centres ``v`` that vary along ``axis`` only, on
    a regular spacing within ``tol``."""
    d = np.diff(v, axis=axis)
    other = np.ptp(v, axis=1 - axis)
    if np.abs(d - d.mean()).max() > tol or other.max() > tol:
        raise ValueError(f"not a regular axis (spacing {d.min():.2f}..{d.max():.2f}, "
                         f"cross-drift {other.max():.2f})")  # fmt: skip
    return float(np.take(v, 0, axis=axis).mean()), float(d.mean())


def stage4_axes(ds):
    """(x centres, y centres, proj string) of a Stage IV year file's HRAP grid."""
    from pyproj import Transformer

    proj = ds.attrs["crs_proj4"]
    tr = Transformer.from_crs("EPSG:4326", proj, always_xy=True)
    X, Y = tr.transform(ds.lon.values, ds.lat.values)
    x0, dx = regular_axis(X, axis=1, tol=60.0)
    y0, dy = regular_axis(Y, axis=0, tol=60.0)
    return x0 + dx * np.arange(X.shape[1]), y0 + dy * np.arange(X.shape[0]), proj


def nearest_index(centres: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Index of the cell of a REGULAR ascending axis ``centres`` holding each ``v``
    (-1 outside)."""
    d = centres[1] - centres[0]
    i = np.floor((v - (centres[0] - d / 2)) / d).astype(int)
    return np.where((i >= 0) & (i < len(centres)), i, -1)


def fill_stage4_gaps(p: np.ndarray, hours: pd.DatetimeIndex) -> int:
    """Fill NaN Stage IV hours in place from the 6-h totals; returns cells filled."""
    if not np.isnan(p).any():
        return 0
    t6 = pd.date_range(hours[0].ceil("6h"), hours[-1].ceil("6h"), freq="6h")
    p6, _ = load_window(year_files("stage4_6h", t6, required=False), t6)
    if p6 is None:
        return 0
    flat = p.reshape(len(p), -1)
    filled, mask = fill_from_6h(flat, hours, p6.reshape(len(p6), -1), t6)
    flat[:] = filled
    return int(mask.sum())


def build_forcing(product: str, t0, t1, out: Path) -> dict:
    """Write the run window's precipitation to ``out`` (see module docstring); returns
    the gap counts."""
    import xarray as xr

    if product not in PRODUCTS:
        raise ValueError(f"precip product {product!r}; known: {PRODUCTS}")
    hours = window_hours(t0, t1)
    p, ref = load_window(year_files(product, hours), hours)
    info = {"nan_hours": int(np.isnan(p).all(axis=(1, 2)).sum()),
            "nan_cell_hours": int(np.isnan(p).sum())}  # fmt: skip
    if product == "mrms":
        if info["nan_cell_hours"]:
            s4, ref4 = load_window(year_files("stage4", hours), hours)
            info["stage4_filled_from_6h"] = fill_stage4_gaps(s4, hours)
            xs, ys, proj = stage4_axes(ref4)
            from pyproj import Transformer

            lon2, lat2 = np.meshgrid(ref.lon.values, ref.lat.values)
            x, y = Transformer.from_crs("EPSG:4326", proj, always_xy=True).transform(lon2, lat2)
            ix, iy = nearest_index(xs, x), nearest_index(ys, y)
            if (ix < 0).any() or (iy < 0).any():
                raise RuntimeError("an MRMS cell centre falls outside the Stage IV clip")
            gap = np.isnan(p)
            donor = s4[:, iy, ix]
            p[gap] = donor[gap]
            info["filled_from_stage4"] = int((gap & np.isfinite(donor)).sum())
        coords = {"time": hours, "lat": ref.lat.values, "lon": ref.lon.values}
        dims, crs = ("time", "lat", "lon"), "EPSG:4326"
    else:
        info["filled_from_6h"] = fill_stage4_gaps(p, hours)
        xs, ys, proj = stage4_axes(ref)
        coords = {"time": hours, "y": ys, "x": xs}
        dims, crs = ("time", "y", "x"), proj
    info["zero_filled_cell_hours"] = int(np.isnan(p).sum())
    p = np.nan_to_num(p, nan=0.0)
    ds = xr.Dataset({"precip": (dims, p)}, coords=coords)
    ds.precip.attrs = {"units": "mm", "long_name": "1-h accumulation ending at time (UTC)"}
    ds.attrs = {"title": f"{product} hourly precipitation for a run window",
                "made_by": "agri_sfincs.precip.build_forcing", "crs_input": crs,
                **{k: str(v) for k, v in info.items()}}  # fmt: skip
    import hydromt  # noqa: F401  (registers .raster)

    # The CRS goes INTO the file (spatial_ref): hydromt's catalog cannot serialise a CRS
    # without an authority code, which the HRAP proj string has none of.
    ds.raster.set_crs(crs)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".nc.part")
    ds.to_netcdf(tmp, encoding={"precip": {"zlib": True, "complevel": 4}})
    tmp.replace(out)
    print(f"[precip] {product} {hours[0]} .. {hours[-1]} -> {out.name}: {info}")
    return info


def to_engine_origin(path: Path) -> bool:
    """Rewrite a staged meteo file's ``x`` / ``y`` from cell centres (as hydromt writes
    them) to the engine's corner convention: ``centre - step/2`` with each axis's SIGNED
    step, so hydromt's descending ``y`` moves north by half a cell. Only the coordinate
    values change; the file is stamped ``ORIGIN_ATTR`` and a stamped file is left alone
    (returns False). Copy + rename, so a hard link is broken, not written through."""
    import os
    import shutil

    import netCDF4

    path = Path(path)
    with netCDF4.Dataset(path) as nc:
        if ORIGIN_ATTR in nc.ncattrs():
            return False
    tmp = path.with_suffix(".nc.tmp")
    shutil.copyfile(path, tmp)
    with netCDF4.Dataset(tmp, "r+") as nc:
        for ax in ("x", "y"):
            c = np.asarray(nc[ax][:], dtype=np.float64)
            d = np.diff(c)
            if len(c) < 2 or np.abs(d - d[0]).max() > 1e-6 * abs(d[0]):
                raise ValueError(f"{path.name}: {ax} is not a regular axis")
            nc[ax][:] = c - d[0] / 2
            nc[ax].setncatts({ORIGIN_ATTR: ORIGIN_VALUE, "first_cell_centre": float(c[0])})
        nc.setncattr(ORIGIN_ATTR, ORIGIN_VALUE)
    os.replace(tmp, path)
    return True


def true_centres(da) -> tuple[np.ndarray, np.ndarray]:
    """(x, y) cell centres of a meteo Dataset / DataArray: its coordinates as they are,
    or shifted back by half a step if ``to_engine_origin`` (or agri_sfincs.wind) wrote
    them as corners."""
    x, y = da["x"].values.astype(np.float64), da["y"].values.astype(np.float64)
    if ORIGIN_ATTR in da["x"].attrs:
        x = x + (x[1] - x[0]) / 2
    if ORIGIN_ATTR in da["y"].attrs:
        y = y + (y[1] - y[0]) / 2
    return x, y


def catalog_entry(key: str, uri: str, product: str, crs: str, t0, t1) -> str:
    """The YAML block for one forcing file (relative ``uri``, as the other entries). The
    CRS is in the file; EPSG:4326 is repeated here like the event entries'."""
    crs_yaml = "\n    crs: 4326" if crs == "EPSG:4326" else ""
    return (f"\n{key}:\n  data_type: RasterDataset\n  uri: {uri}\n"
            f"  driver: {{name: raster_xarray, options: {{}}}}\n  metadata:\n"
            f"    category: meteo{crs_yaml}\n    unit: mm per hour ending at time\n"
            f"    source: {product} hourly year files, {pd.Timestamp(t0):%Y-%m-%d %H:%M}.."
            f"{pd.Timestamp(t1):%Y-%m-%d %H:%M} (agri_sfincs.precip.build_forcing)\n")  # fmt: skip


def catalog_has(text: str, key: str) -> bool:
    return any(line.rstrip() == f"{key}:" for line in text.splitlines())


def ensure_forcing(product: str, t0, t1, key: str, catalog: Path = config.CATALOG) -> str:
    """Build ``data/precip/forcing/<key>.nc`` (if absent) and add catalog entry ``key``
    (if absent); returns ``key``. A file is reused only if its time axis is the window."""
    import xarray as xr

    out = FORCING_DIR / f"{key}.nc"
    hours = window_hours(t0, t1)
    if out.is_file():
        with xr.open_dataset(out) as ds:
            same = len(ds.time) == len(hours) and pd.Timestamp(ds.time.values[0]) == hours[0]
        if not same:
            raise FileExistsError(f"{out} exists for a different window; delete it or rename")
    else:
        build_forcing(product, t0, t1, out)
    text = catalog.read_text()
    if not catalog_has(text, key):
        with xr.open_dataset(out) as ds:
            crs = ds.attrs["crs_input"]
        uri = out.relative_to(catalog.parent).as_posix()
        catalog.write_text(text.rstrip("\n") + "\n" + catalog_entry(key, uri, product, crs, t0, t1))
        print(f"[precip] catalog entry {key!r} added to {catalog}")
    return key
