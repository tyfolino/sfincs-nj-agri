"""Open-water evaporation as negative net precipitation (P - E) for SFINCS.

SFINCS has no evapotranspiration, so ponded water leaves closed depressions and diked
interiors only by flow (FINDINGS §16). The engine accepts NEGATIVE precipitation and
zeroes it in cells that hold no water (sfincs_meteo.f90:1316-1330); the source audit
(reports/evaporation.md, FINDINGS §17) shows that with ``infiltration_type = cnb`` a
negative rate is treated exactly like a dry hour (sfincs_infiltration.f90:737), never
reaches the CN runoff bookkeeping, and only lowers the ``cumprcp`` output. Two caveats
drive the choices here:

* the sink is applied over the WHOLE cell area once a subgrid cell holds any water
  (sfincs_continuity.f90:469-495, ``dvol += netprcp * a * dt``), so a cell that is 5 %
  wet loses volume 20x faster than open-water physics says;
* a negative value in an hour with light rain would erase that rain and end cnb's
  rain "event" (sfincs_infiltration.f90:737-760). The engine also BLENDS neighbouring
  values: bilinearly in space (1 km nodes -> cell centres) and linearly in time over
  each second half hour (fields are sampled every dtwnd = 1800 s, ampr_block picks the
  hour's value, and prcp = prcp0 (1 - f) + prcp1 f between samples;
  sfincs_lib.f90:495-501, sfincs_meteo.f90:1272, 1312). So a -E node next to a
  raining node in space or time eats into the rain there too.

Hence ``mode="dry_hours"`` (default): E only where P == 0, and with ``buffer=1``
(default) also not within one node / one hour of any rain, so no -E is ever blended
with rain and cnb sees exactly the rain it saw before. ``mode="subtract"`` is plain
P - E.

E = KC_OPEN_WATER x gridMET grass reference ET (scripts/fetch_pet.py), spread over the
daylight hours of each gridMET day in proportion to sin(solar elevation) (ET is
radiation-driven; night-time open-water E in a humid climate is small), bilinearly
interpolated from the ~4 km gridMET grid to the run's precipitation grid.

The netampr file (hydromt_sfincs ``precipitation.create(cumulative_input=True,
time_label="right")``) holds a RATE in mm/h for the hour STARTING at ``time`` (hydromt
divides by the interval and shifts the hour-ending totals left by one step); the engine
applies it as a block from ``time`` (ampr_block, sfincs_meteo.f90:1155-1159) after
bilinear interpolation to cell centres (sfincs_meteo.f90:1176-1236). Its ``units: mm``
and "ending at time" long_name are stale attrs carried from the catalog source.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from agri_sfincs import config

#: FAO-56 (Allen et al. 1998) Table 12: Kc for open water < 2 m deep (or in sub-humid
#: climates / tropics) = 1.05 on grass reference ETo. Ponded fields, ditches and diked
#: interiors here are all shallow.
KC_OPEN_WATER = 1.05
#: gridMET day D runs from D 07Z to D+1 07Z (midnight MST; dataset note5).
GRIDMET_DAY_OFFSET = pd.Timedelta(hours=7)
#: Domain centre for the solar weights (lon, lat); the weights hardly vary over 1 deg.
SUN_LONLAT = (-75.2, 39.45)
PET_FILE = config.EVAP_DIR / "gridmet_pet_2002_2025.nc"
#: Attribute stamped on a rewritten netampr file (so it is never applied twice).
STAMP = "agri_evaporation"


# ----------------------------------------------------------------------------- pure


def sin_solar_elevation(times_utc, lon: float, lat: float) -> np.ndarray:
    """sin(solar elevation) at UTC instants (NOAA / Spencer 1971 approximations:
    declination and equation of time from the fractional year; error < ~0.5 deg)."""
    t = pd.DatetimeIndex(times_utc)
    doy = t.dayofyear.to_numpy()
    hour = (t.hour + t.minute / 60 + t.second / 3600).to_numpy()
    g = 2 * np.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eot = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                    - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))  # fmt: skip
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g)
            - 0.006758 * np.cos(2 * g) + 0.000907 * np.sin(2 * g)
            - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))  # fmt: skip
    solar_time = hour + lon / 15 + eot / 60  # hours
    ha = np.deg2rad(15 * (solar_time - 12))
    phi = np.deg2rad(lat)
    return np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(ha)


def gridmet_day(times_utc) -> pd.DatetimeIndex:
    """The gridMET day (midnight-labelled date) holding each UTC instant."""
    return (pd.DatetimeIndex(times_utc) - GRIDMET_DAY_OFFSET).normalize()


def hourly_weights(hours_utc, lon: float = SUN_LONLAT[0], lat: float = SUN_LONLAT[1],
                   shape: str = "daylight") -> np.ndarray:  # fmt: skip
    """Fraction of its gridMET day's E that falls in each hour STARTING at
    ``hours_utc`` (must be whole, consecutive hours covering whole gridMET days for
    the fractions of a day to sum to 1). ``shape``: "daylight" = sin(solar elevation)
    at the hour's midpoint, clipped at 0; "uniform" = 1/24."""
    t = pd.DatetimeIndex(hours_utc)
    if shape == "uniform":
        return np.full(len(t), 1 / 24)
    if shape != "daylight":
        raise ValueError(shape)
    w = np.clip(sin_solar_elevation(t + pd.Timedelta(minutes=30), lon, lat), 0, None)
    # Normalise by the FULL day's sum (24 hours), not by the hours present, so a
    # window that clips a day keeps the right per-hour rate.
    day = gridmet_day(t)
    full = pd.date_range(day.min() + GRIDMET_DAY_OFFSET,
                         day.max() + GRIDMET_DAY_OFFSET + pd.Timedelta(hours=23), freq="h")  # fmt: skip
    wf = np.clip(sin_solar_elevation(full + pd.Timedelta(minutes=30), lon, lat), 0, None)
    tot = pd.Series(wf, index=gridmet_day(full)).groupby(level=0).sum()
    return w / tot.reindex(day).to_numpy()


def rain_buffer(precip, buffer: int = 1) -> np.ndarray:
    """Boolean mask: rain (P > 0) dilated by ``buffer`` steps along EVERY axis (time,
    and y / x for a grid), i.e. where the engine's interpolation could mix -E with
    rain."""
    from scipy.ndimage import binary_dilation

    wet = np.asarray(precip) > 0
    if buffer <= 0 or not wet.any():
        return wet
    return binary_dilation(wet, structure=np.ones((3,) * wet.ndim, bool), iterations=buffer)


def net_precip(precip, evap, mode: str = "dry_hours", buffer: int = 1):
    """Net precipitation rate from precipitation P and evaporation E (same units,
    E >= 0; for a grid, dims (time, y, x)). "dry_hours": P where P > 0, 0 within
    ``buffer`` steps of rain, else -E (cnb sees the same rain series); "subtract":
    P - E (``buffer`` ignored)."""
    if mode == "subtract":
        return precip - evap
    if mode != "dry_hours":
        raise ValueError(mode)
    near = rain_buffer(precip, buffer)
    if isinstance(precip, xr.DataArray):
        e = xr.where(xr.DataArray(near, dims=precip.dims, coords=precip.coords), 0.0, evap)
        return xr.where(precip > 0, precip, -e)
    p, e = np.asarray(precip), np.asarray(evap)
    return np.where(p > 0, p, np.where(near, 0.0, -e))


# -------------------------------------------------------------------------- data


def load_pet(path: Path = PET_FILE, times=None) -> xr.DataArray:
    """gridMET daily ETo (mm/day; time, lat, lon), optionally only the gridMET days
    covering ``times`` (UTC)."""
    da = xr.open_dataset(path)["pet"]
    if times is not None:
        days = gridmet_day(times)
        da = da.sel(time=slice(days.min(), days.max()))
    return da.load()


def evap_on_grid(precip: xr.DataArray, pet: xr.DataArray | None = None,
                 kc: float = KC_OPEN_WATER, shape: str = "daylight") -> xr.DataArray:  # fmt: skip
    """Open-water E (mm/h, >= 0) on ``precip``'s (time, y, x) grid: the rate for the
    hour starting at each ``time`` (the netampr convention). ``precip`` must carry a
    CRS (``spatial_ref`` / rio) or be in config's UTM 18N (EPSG:32618)."""
    from pyproj import Transformer

    times = pd.DatetimeIndex(precip["time"].values)
    if pet is None:
        pet = load_pet(times=times)
    days = gridmet_day(times)
    missing = days.difference(pd.DatetimeIndex(pet["time"].values))
    if len(missing):
        raise ValueError(f"PET has no data for gridMET days {list(missing[:5])} ...")
    crs = _crs_of(precip)
    xx, yy = np.meshgrid(precip["x"].values, precip["y"].values)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(xx, yy)
    lon_da = xr.DataArray(lon, dims=("y", "x"))
    lat_da = xr.DataArray(lat, dims=("y", "x"))
    # Fill any NaN cell (none expected over this box) before interpolating.
    pet = pet.ffill("lon").bfill("lon").ffill("lat").bfill("lat")
    pet_xy = pet.interp(lon=lon_da, lat=lat_da, method="linear")
    pet_xy = pet_xy.fillna(pet.interp(lon=lon_da, lat=lat_da, method="nearest",
                                      kwargs={"fill_value": None}))  # fmt: skip
    daily = pet_xy.sel(time=xr.DataArray(days, dims="time")).drop_vars(["lon", "lat"])
    w = xr.DataArray(hourly_weights(times, shape=shape), dims="time")
    e = (kc * daily * w).transpose("time", "y", "x")
    e = e.assign_coords(time=precip["time"], y=precip["y"], x=precip["x"])
    return e.astype(np.float32).rename("evaporation")


def _crs_of(da: xr.DataArray):
    if "spatial_ref" in da.coords:
        wkt = da["spatial_ref"].attrs.get("crs_wkt") or da["spatial_ref"].attrs.get(
            "spatial_ref"
        )
        if wkt:
            return wkt
    return "EPSG:32618"


def precip_minus_evap(precip: xr.DataArray, pet: xr.DataArray | None = None,
                      kc: float = KC_OPEN_WATER, mode: str = "dry_hours",
                      shape: str = "daylight", buffer: int = 1) -> xr.DataArray:  # fmt: skip
    """The integration point for ``setup_event``: hourly precipitation as hydromt
    hands it to SFINCS (mm/h, hour starting at ``time``) -> net rate P - E, same
    grid, times, name and attrs."""
    e = evap_on_grid(precip, pet=pet, kc=kc, shape=shape)
    out = net_precip(precip, e, mode=mode, buffer=buffer).astype(np.float32)
    out.name = precip.name
    out.attrs = dict(precip.attrs)
    out.attrs.update({
        "units": "mm/h",
        "long_name": "net precipitation rate (P - open-water E) for the hour starting at time",
        STAMP: f"gridMET ETo x {kc} ({shape} hourly weights), mode={mode}, buffer={buffer}",
    })  # fmt: skip
    return out


def apply_to_run(run: Path, kc: float = KC_OPEN_WATER, mode: str = "dry_hours",
                 shape: str = "daylight", pet: xr.DataArray | None = None,
                 buffer: int = 1) -> dict:  # fmt: skip
    """Rewrite a STAGED run's ``sfincs_netampr.nc`` in place with P - E.

    Keeps the variable name (``Precipitation``, which the engine looks up:
    sfincs_ncinput.F90:834), dims (time, y, x), float32, the time units and the
    spatial_ref. Refuses a file already stamped. Writes to a temp file and renames, so
    a borrowed hard link is broken rather than written through. Returns a summary."""
    run = Path(run)
    fn = run / "sfincs_netampr.nc"
    with xr.open_dataset(fn) as src:
        ds = src.load()
    var = "Precipitation"
    if STAMP in ds[var].attrs:
        raise RuntimeError(f"{fn} already has evaporation: {ds[var].attrs[STAMP]}")
    p = ds[var]
    out = precip_minus_evap(p, pet=pet, kc=kc, mode=mode, shape=shape, buffer=buffer)
    new = ds.copy()
    new[var] = out
    enc = {var: {k: v for k, v in p.encoding.items()
                 if k in ("dtype", "_FillValue", "zlib", "complevel", "chunksizes",
                          "contiguous")}}  # fmt: skip
    enc[var]["dtype"] = "float32"
    tenc = ds["time"].encoding
    enc["time"] = {k: tenc[k] for k in ("units", "calendar", "dtype") if k in tenc}
    tmp = fn.with_suffix(".nc.tmp")
    new.to_netcdf(tmp, encoding=enc)
    os.replace(tmp, fn)
    e = out.where(out < 0, 0)
    hours = float(np.diff(ds["time"].values).astype("timedelta64[s]").mean().astype(float) / 3600)
    return {
        "file": str(fn),
        "mean_E_mm_per_day_applied": float(-e.mean("time").mean()) * 24,
        "mean_P_mm_total": float(p.where(p > 0, 0).sum("time").mean()) * hours,
        "mean_netP_mm_total": float(out.sum("time").mean()) * hours,
        "E_dropped_share": float(1 - (-e).sum() / evap_on_grid(p, pet=pet, kc=kc, shape=shape).sum()),
        "kc": kc, "mode": mode, "shape": shape, "buffer": buffer,
    }  # fmt: skip
