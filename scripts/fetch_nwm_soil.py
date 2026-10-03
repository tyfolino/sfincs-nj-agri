"""National Water Model v3.0 retrospective soil wetness over the study counties: daily
grids and cropland-weighted daily series per county.

Source: NOAA NWM Retrospective v3.0 (WRF-Hydro v5.3 / Noah-MP, AORC forcing), AWS Open
Data, anonymous: s3://noaa-nwm-retrospective-3-0-pds/CONUS/zarr/
  ldasout.zarr  1 km land grid (3840 x 4608), 3-hourly, 1979-02-01T03Z .. 2023-02-01T00Z,
                complete (no missing steps). Variables: ACCET ACSNOM ALBEDO ALBSND ALBSNI
                COSZ EDIR FIRA FSA FSNO HFX LH QRAIN QSNOW SNEQV SNOWH SOIL_M SOIL_W TRAD
                UGDRNOFF (SOIL_M/SOIL_W on 4 Noah-MP layers: 0-10, 10-40, 40-100,
                100-200 cm). There is NO SOILSAT_TOP, SFCRNOFF or soil temperature in the
                v3.0 retrospective output (the netCDF LDASOUT files carry the same 20).
  rtout.zarr    250 m routing grid (15360 x 18432), 3-hourly, same span but MISSING
                2022-12-08T03Z .. 2023-01-04T00Z: sfcheadsubrt (surface head = ponded
                water, mm) and zwattablrt (depth to saturation, rounded to the highest
                saturated layer, m).
Both are int32 zarr v2, zstd, chunks (224 times = 28 days, 350, 350), LCC on a
6370 km sphere. The study window needs 2 spatial chunks (1 km) or 4 (250 m) per time
chunk, ~190 MB per 28 days for everything below: ~5 s per time chunk anonymously.

Daily values. Day D = the 8 instants D 03Z .. D+1 00Z (UTC), so every 28-day chunk
holds whole days. Kept (1 km): soil_m1..4 (daily mean, m3/m3), sneqv (mean, mm),
qrain (mean rate x 86400, mm/d — sampled every 3 h from an hourly model, so only
indicative; use AORC/Stage IV for rain), accet_eod / ugdrnoff_eod (accumulations at
D+1 00Z, mm; daily increments are taken at assembly). Kept (250 m): sfchead_mean /
sfchead_max (mm), zwt_mean / zwt_min (m).

County series: every 30 m CDL cropland pixel (agri_sfincs.cdl.CROPLAND; CDL of the data
year, or the nearest CDL year: 2008 for 2002-2007) inside the county is binned to the
NWM cell holding its centre, so each county's weights are cropland pixel counts per
cell (both grids). Whole counties are used, not just their in-ring part: the losses
are whole-county. Cells the model leaves missing (water) drop out of the weighting.

Writes (data/nwm/):
  grid/nwm_ldas_daily_<year>.nc, grid/nwm_rt_daily_<year>.nc   clipped daily grids
  nwm_cropland_weights.nc     cropland pixel counts per county x CDL year x cell
  nwm_soil_daily_county.csv   date, fips, county, cdl_year, crop_km2 and the series:
      soil_m1..4, soil_m_0_100cm (depth-weighted), sneqv_mm, qrain_mm, accet_mm,
      ugdrnoff_mm (daily increments; NaN where an accumulator resets), sfchead_mean_mm,
      sfchead_max_mm, ponded_frac / ponded10_frac (cropland share whose daily-max head
      is > 0 / >= 10 mm), zwt_mean_m, zwt_min_m, sat_0cm_frac / sat_10cm_frac /
      sat_40cm_frac (cropland share saturated from that depth up at some instant of
      the day), n_ldas / n_rt (3-hourly samples that day; 8 = complete)
Accumulators (ACCET, UGDRNOFF) restart at 0 at 00Z on the first day of each calendar
quarter (seen in 2010: the 03Z value is the 3 h since 00Z), so a quarter's first-day
increment is its end-of-day value. ACCET legitimately falls on dew days; keep its
negative increments.
Years already on disk are skipped; the county CSV is rebuilt from them every run.

Usage:  python scripts/fetch_nwm_soil.py [--years 2002-2023] [--workers 4] [--county-only]
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
import pandas as pd
import xarray as xr

from agri_sfincs import cdl, config, domain

BUCKET = "noaa-nwm-retrospective-3-0-pds/CONUS/zarr"
#: The NWM grids' CRS (from the stores' ``proj4`` attribute).
PROJ4 = (
    "+proj=lcc +units=m +a=6370000.0 +b=6370000.0 +lat_1=30.0 +lat_2=60.0 +lat_0=40.0 "
    "+lon_0=-97.0 +x_0=0 +y_0=0 +k_0=1.0 +nadgrids=@null +wktext +no_defs"
)
GRID_DIR = config.NWM_DIR / "grid"
COUNTY_CSV = config.NWM_DIR / "nwm_soil_daily_county.csv"
WEIGHTS_NC = config.NWM_DIR / "nwm_cropland_weights.nc"
PAD_M = 2000.0  # window margin around the counties + ring
LAYER_CM = [(0, 10), (10, 40), (40, 100), (100, 200)]  # Noah-MP soil layers
#: Ponded-share thresholds on the daily max of sfcheadsubrt (whole mm): > 0 = any.
PONDED_MM = {"ponded_frac": 0.0, "ponded10_frac": 9.5}
#: zwattablrt only takes the soil-layer tops 0, 0.1, 0.4, 1.0 m, or 2.0 (= nothing
#: saturated). Shares of cropland whose daily min is at or above each depth.
SAT_DEPTHS = {"sat_0cm_frac": 0.0, "sat_10cm_frac": 0.1, "sat_40cm_frac": 0.4}
#: CDL years not used for weights (FINDINGS §1: CDL 2010 calls ~100 km2 extra
#: cropland in Gloucester, a classification artifact until shown otherwise).
SKIP_CDL = {2010}
CDL_PX = 30.0 * 30.0
#: Decimal digits kept in the gridded files (the sources are packed at 0.01 m3/m3,
#: 0.01 mm, 1 mm and 0.1 m, so this loses nothing that was there).
LSD = {**{f"soil_m{i}": 4 for i in range(1, 5)}, "sneqv": 2, "qrain": 3,
       "accet_eod": 2, "ugdrnoff_eod": 2, "sfchead_mean": 2, "sfchead_max": 0,
       "zwt_mean": 3, "zwt_min": None}  # fmt: skip
# (zwt_min is left exact: quantizing 0.1 to 1/16 would move it off the layer top.)

#: store -> list of (output name, zarr variable, layer index or None, reducer)
STORES = {
    "ldas": ("ldasout.zarr", [
        *[(f"soil_m{i + 1}", "SOIL_M", i, "mean") for i in range(4)],
        ("sneqv", "SNEQV", None, "mean"),
        ("qrain", "QRAIN", None, "mean"),
        ("accet_eod", "ACCET", None, "last"),
        ("ugdrnoff_eod", "UGDRNOFF", None, "last"),
    ]),
    "rt": ("rtout.zarr", [
        ("sfchead_mean", "sfcheadsubrt", None, "mean"),
        ("sfchead_max", "sfcheadsubrt", None, "max"),
        ("zwt_mean", "zwattablrt", None, "mean"),
        ("zwt_min", "zwattablrt", None, "min"),
    ]),
}  # fmt: skip


# ---------------------------------------------------------------- pure helpers


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


def window(xc: np.ndarray, yc: np.ndarray, bounds) -> tuple[slice, slice, Grid]:
    """Index slices (y, x) into a full grid with cell centres ``xc``, ``yc`` (both
    ascending, regular) covering ``bounds`` = (xmin, ymin, xmax, ymax), and the Grid."""
    dx, dy = float(xc[1] - xc[0]), float(yc[1] - yc[0])
    if dx <= 0 or dy <= 0:
        raise ValueError("expected ascending x and y")
    xmin, ymin, xmax, ymax = bounds
    ix0 = max(int(np.floor((xmin - (xc[0] - dx / 2)) / dx)), 0)
    ix1 = min(int(np.floor((xmax - (xc[0] - dx / 2)) / dx)) + 1, len(xc))
    iy0 = max(int(np.floor((ymin - (yc[0] - dy / 2)) / dy)), 0)
    iy1 = min(int(np.floor((ymax - (yc[0] - dy / 2)) / dy)) + 1, len(yc))
    g = Grid(xc[ix0] - dx / 2, yc[iy0] - dy / 2, dx, dy, ix1 - ix0, iy1 - iy0)
    return slice(iy0, iy1), slice(ix0, ix1), g


def day_label(times) -> pd.DatetimeIndex:
    """The day each 3-hourly instant belongs to: (D 00Z, D+1 00Z] -> D."""
    return (pd.DatetimeIndex(times) - pd.Timedelta("1s")).floor("D")


def daily_reduce(a: np.ndarray, days: pd.DatetimeIndex, how: str):
    """Reduce ``a`` (time, ...) over the instants of each day. NaN-aware; ``last`` is
    the value at the day's last instant (NaN if that instant is missing)."""
    uniq, inv = np.unique(days.values, return_inverse=True)
    out = np.full((len(uniq), *a.shape[1:]), np.nan, dtype=np.float32)
    if how not in ("mean", "max", "min", "last"):
        raise ValueError(how)
    # Written out rather than np.nanmean & co.: no all-NaN warnings (which
    # warnings.catch_warnings cannot silence safely across threads).
    for k in range(len(uniq)):
        sl = a[inv == k]
        if how == "last":
            out[k] = sl[-1]
        elif how == "max":
            out[k] = np.fmax.reduce(sl, axis=0)
        elif how == "min":
            out[k] = np.fmin.reduce(sl, axis=0)
        else:
            ok = np.isfinite(sl)
            n = ok.sum(axis=0)
            tot = np.where(ok, sl, 0).sum(axis=0, dtype=np.float64)
            out[k] = np.where(n > 0, tot / np.maximum(n, 1), np.nan)
    return pd.DatetimeIndex(uniq), out


def is_reset_day(days) -> np.ndarray:
    """True on the first day of a calendar quarter (NWM v3.0 retrospective restarts its
    accumulators at 00Z that day)."""
    d = pd.DatetimeIndex(days)
    return np.asarray((d.day == 1) & d.month.isin([1, 4, 7, 10]))


def accum_increment(eod: np.ndarray, days) -> np.ndarray:
    """Daily increments of an accumulator from its end-of-day values (day, ...) on
    consecutive ``days``: the difference from the day before, or the value itself on a
    reset day. A first day that is not a reset day has no predecessor: NaN."""
    d = np.concatenate([np.full_like(eod[:1], np.nan), np.diff(eod, axis=0)], axis=0)
    gap = np.diff(pd.DatetimeIndex(days).values) != np.timedelta64(1, "D")
    if gap.any():
        raise ValueError("days are not consecutive")
    r = is_reset_day(days)
    d[r] = eod[r]
    return d


def weighted_mean(v: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted mean over the last two axes of ``v`` (day, ny, nx) with ``w`` (ny, nx),
    ignoring NaN cells (their weight drops out). All-NaN -> NaN."""
    ok = np.isfinite(v)
    num = np.where(ok, v, 0.0).astype(np.float64) * w
    den = ok * w
    s = den.sum(axis=(-2, -1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, num.sum(axis=(-2, -1)) / s, np.nan)


def share(v: np.ndarray, cond: np.ndarray) -> np.ndarray:
    """``cond`` as 0/1 where ``v`` is finite, NaN elsewhere (for weighted shares)."""
    return np.where(np.isfinite(v), cond.astype(np.float32), np.nan)


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


def parse_years(s: str) -> list[int]:
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(y) for y in s.split(",")]


# ---------------------------------------------------------------- remote reads


class Store:
    """One NWM zarr v2 store, read chunk by chunk over anonymous S3."""

    def __init__(self, fs, name: str):
        import numcodecs

        self.fs, self.path = fs, f"{BUCKET}/{name}"
        self.meta = json.loads(fs.cat(f"{self.path}/.zmetadata"))["metadata"]
        self.codec = numcodecs.Zstd()
        self.x = self._coord("x")
        self.y = self._coord("y")
        t = self._coord("time")
        units = self.meta["time/.zattrs"]["units"]  # "hours since 1979-02-01T03:00:00"
        step, _, origin = units.partition(" since ")
        if step != "hours":
            raise RuntimeError(f"{name}: unexpected time units {units!r}")
        self.time = pd.Timestamp(origin) + pd.to_timedelta(t, unit="h")

    def _coord(self, v: str) -> np.ndarray:
        za = self.meta[f"{v}/.zarray"]
        n, c = za["shape"][0], za["chunks"][0]
        keys = [f"{self.path}/{v}/{k}" for k in range((n + c - 1) // c)]
        raw = self._cat(keys)
        parts = [self._decode(raw[k], za) for k in keys]
        return np.concatenate(parts)[:n]

    def _decode(self, b: bytes, za: dict) -> np.ndarray:
        if za["compressor"] is None:
            return np.frombuffer(b, za["dtype"])
        if za["compressor"]["id"] != "zstd":
            raise RuntimeError(f"unexpected compressor {za['compressor']}")
        return np.frombuffer(self.codec.decode(b), za["dtype"])

    def _cat(self, keys: list[str]) -> dict:
        delay = 5.0
        for attempt in range(6):
            try:
                out = self.fs.cat(keys, on_error="raise")
                return out if isinstance(out, dict) else {keys[0]: out}
            except (OSError, RuntimeError) as e:
                if attempt == 5:
                    raise
                print(f"    ({type(e).__name__}: {e}; retry in {delay:.0f} s)", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 120.0)
        raise RuntimeError("unreachable")

    def read(self, var: str, kt: int, ys: slice, xs: slice, layer: int | None) -> np.ndarray:
        """Time chunk ``kt`` of ``var`` cropped to (ys, xs), scaled, NaN where missing:
        float32 (time, y, x)."""
        za, at = self.meta[f"{var}/.zarray"], self.meta[f"{var}/.zattrs"]
        ct, cy = za["chunks"][0], za["chunks"][1]
        cx = za["chunks"][-1]
        dims = at["_ARRAY_DIMENSIONS"]
        nt = min(ct, za["shape"][0] - kt * ct)
        jy = range(ys.start // cy, (ys.stop - 1) // cy + 1)
        jx = range(xs.start // cx, (xs.stop - 1) // cx + 1)
        keys = {}
        for a in jy:
            for b in jx:
                idx = [kt, a, layer, b] if len(dims) == 4 else [kt, a, b]
                keys[(a, b)] = f"{self.path}/{var}/" + ".".join(map(str, idx))
        raw = self._cat(list(keys.values()))
        out = np.empty((nt, ys.stop - ys.start, xs.stop - xs.start), np.float32)
        fill = za["fill_value"]
        miss = at.get("missing_value", fill)
        scale = float(at.get("scale_factor", 1.0))
        offset = float(at.get("add_offset", 0.0))
        for (a, b), k in keys.items():
            blk = self._decode(raw[k], za).reshape(za["chunks"])
            if len(dims) == 4:
                blk = blk[:, :, 0, :]  # (time, y, layer, x): one layer per chunk
            # chunk-local index ranges of the overlap
            y0, y1 = max(ys.start, a * cy), min(ys.stop, (a + 1) * cy)
            x0, x1 = max(xs.start, b * cx), min(xs.stop, (b + 1) * cx)
            sub = blk[:nt, y0 - a * cy : y1 - a * cy, x0 - b * cx : x1 - b * cx]
            v = sub.astype(np.float32) * scale + offset
            v[(sub == fill) | (sub == miss)] = np.nan
            out[:, y0 - ys.start : y1 - ys.start, x0 - xs.start : x1 - xs.start] = v
        return out


def study_bounds_lcc():
    """(xmin, ymin, xmax, ymax) in the NWM CRS of the ring + the three study counties."""
    import geopandas as gpd

    from agri_sfincs import region

    c = region.load_counties()
    c = c[c.fips.isin(domain.COUNTIES)]
    shapes = pd.concat([c[["geometry"]], region.load_ring()[["geometry"]].to_crs(c.crs)])
    b = gpd.GeoSeries(shapes.geometry, crs=c.crs).to_crs(PROJ4).total_bounds
    return (b[0] - PAD_M, b[1] - PAD_M, b[2] + PAD_M, b[3] + PAD_M)


def fetch_year(store: Store, key: str, year: int, ys, xs, grid: Grid, workers: int) -> str:
    dest = GRID_DIR / f"nwm_{key}_daily_{year}.nc"
    if dest.exists():
        return f"{key} {year}: have {dest.name}"
    days = day_label(store.time)
    sel = np.nonzero(days.year == year)[0]
    if not len(sel):
        return f"{key} {year}: not in the store ({store.time[0]} .. {store.time[-1]})"
    ct = store.meta[f"{STORES[key][1][0][1]}/.zarray"]["chunks"][0]
    kts = sorted(set(sel // ct))
    t0 = time.time()

    def one(kt):
        ti = np.arange(kt * ct, min((kt + 1) * ct, len(store.time)))
        keep = days[ti].year == year
        d = days[ti][keep]
        cache: dict = {}
        res = {}
        for name, var, layer, how in STORES[key][1]:
            if (var, layer) not in cache:
                cache[(var, layer)] = store.read(var, kt, ys, xs, layer)[keep]
            dd, res[name] = daily_reduce(cache[(var, layer)], d, how)
        counts = pd.Series(1, index=d).groupby(level=0).size()
        return dd, res, counts.reindex(dd).to_numpy()

    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(one, kts))
    dd = pd.DatetimeIndex(np.concatenate([p[0].values for p in parts]))
    if dd.has_duplicates:
        raise RuntimeError(f"{key} {year}: a day straddles two time chunks")
    data = {n: np.concatenate([p[1][n] for p in parts]) for n, *_ in STORES[key][1]}
    nsamp = np.concatenate([p[2] for p in parts])
    if key == "ldas":
        data["qrain"] *= 86400.0  # mm/s -> mm/d
    ds = xr.Dataset(
        {n: (("time", "y", "x"), v) for n, v in data.items()} | {"n_samples": ("time", nsamp)},
        coords={"time": dd, "y": grid.y, "x": grid.x},
        attrs={"source": f"s3://{store.path}", "crs_proj4": PROJ4,
               "day": "D = the 3-hourly instants D 03Z .. D+1 00Z (UTC)",
               "made_by": "scripts/fetch_nwm_soil.py"},
    )  # fmt: skip
    enc = {n: {"zlib": True, "complevel": 4, "shuffle": True, "dtype": "float32"}
           | ({} if LSD[n] is None else {"least_significant_digit": LSD[n]})
           for n in data}  # fmt: skip
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".nc.part")
    ds.to_netcdf(part, encoding=enc)
    part.rename(dest)
    mb = dest.stat().st_size / 1e6
    return (f"{key} {year}: wrote {dest.name} ({len(dd)} days, {len(kts)} chunks, "
            f"{mb:.0f} MB, {time.time() - t0:.0f} s)")  # fmt: skip


# ---------------------------------------------------------------- weights + series


def cropland_weights(grids: dict[str, Grid]) -> xr.Dataset:
    """Cropland CDL pixel counts per county x CDL year x cell for each grid (cached)."""
    import rasterio
    from pyproj import Transformer
    from rasterio.features import rasterize
    from rasterio.windows import Window, from_bounds

    from agri_sfincs import region

    files = sorted(config.CDL_DIR.glob(f"CDL_*_{domain.STATE_FIPS}.tif"))
    if not files:
        raise SystemExit("no CDL files — run scripts/fetch_cdl.py")
    if WEIGHTS_NC.exists() and WEIGHTS_NC.stat().st_mtime > max(f.stat().st_mtime for f in files):
        w = xr.load_dataset(WEIGHTS_NC)
        if all(w.sizes[f"x_{k}"] == g.nx and w.sizes[f"y_{k}"] == g.ny for k, g in grids.items()):
            return w
    fips = list(domain.COUNTIES)
    c = region.load_counties().set_index("fips").loc[fips].reset_index()
    years = [int(f.name.split("_")[1]) for f in files]
    crop_codes = np.array(sorted(cdl.CROPLAND))
    out = {k: np.zeros((len(years), len(fips), g.ny, g.nx), np.int32) for k, g in grids.items()}
    for yi, f in enumerate(files):
        with rasterio.open(f) as src:
            cc = c.to_crs(src.crs)
            win = from_bounds(*cc.total_bounds, transform=src.transform)
            win = Window(np.floor(win.col_off), np.floor(win.row_off),
                         np.ceil(win.width) + 1, np.ceil(win.height) + 1)  # fmt: skip
            a = src.read(1, window=win, boundless=True, fill_value=0)
            tr = src.window_transform(win)
            crs = src.crs
        lab = rasterize(((g, i + 1) for i, g in enumerate(cc.geometry)), out_shape=a.shape,
                        transform=tr, fill=0, dtype="uint8")  # fmt: skip
        r, col = np.nonzero((lab > 0) & np.isin(a, crop_codes))
        px = tr.c + (col + 0.5) * tr.a
        py = tr.f + (r + 0.5) * tr.e
        X, Y = Transformer.from_crs(crs, PROJ4, always_xy=True).transform(px, py)
        for k, g in grids.items():
            out[k][yi] = bin_pixels(X, Y, lab[r, col].astype(np.int64) - 1, g, len(fips))
            lost = len(r) - out[k][yi].sum()
            if lost > 0.001 * len(r):
                raise RuntimeError(f"{f.name}: {lost} cropland pixels fall outside the {k} window")
        print(f"  weights {f.name}: {len(r) * CDL_PX / 1e6:,.0f} km2 cropland", flush=True)
    w = xr.Dataset(
        {f"crop_px_{k}": (("cdl_year", "fips", f"y_{k}", f"x_{k}"), v) for k, v in out.items()},
        coords={"cdl_year": years, "fips": fips}
        | {f"x_{k}": g.x for k, g in grids.items()} | {f"y_{k}": g.y for k, g in grids.items()},
        attrs={"what": "30 m CDL cropland pixels (agri_sfincs.cdl.CROPLAND) per NWM cell, "
                       "binned by pixel centre", "crs_proj4": PROJ4},
    )  # fmt: skip
    config.NWM_DIR.mkdir(parents=True, exist_ok=True)
    w.to_netcdf(WEIGHTS_NC, encoding={n: {"zlib": True} for n in w.data_vars})
    return w


def county_series(weights) -> pd.DataFrame:
    """Cropland-weighted daily series per county from the yearly grids on disk."""
    fips = [str(f) for f in weights.fips.values]
    cdl_years = [int(y) for y in weights.cdl_year.values]
    frames = []
    lfiles = sorted(GRID_DIR.glob("nwm_ldas_daily_*.nc"))
    for lf in lfiles:
        year = int(lf.stem.split("_")[-1])
        cy = nearest_year(year, [y for y in cdl_years if y not in SKIP_CDL])
        ld = xr.load_dataset(lf)
        rf = GRID_DIR / f"nwm_rt_daily_{year}.nc"
        rd = xr.load_dataset(rf) if rf.exists() else None
        # Each year starts on a reset day, so no carry-over between years is needed.
        inc = {v: accum_increment(ld[f"{v}_eod"].values, ld.time.values)
               for v in ("accet", "ugdrnoff")}  # fmt: skip
        bad = np.nansum(inc["ugdrnoff"] < -0.05)
        if bad:
            print(f"  WARNING {year}: {bad} cell-days of negative UGDRNOFF increment "
                  "(an accumulator reset off the quarter starts?)", flush=True)  # fmt: skip
        for f in fips:
            wl = weights.crop_px_ldas.sel(cdl_year=cy, fips=f).values.astype(np.float64)
            df = pd.DataFrame({"date": ld.time.values})
            df["fips"], df["county"], df["cdl_year"] = f, domain.COUNTIES[f], cy
            df["crop_km2"] = round(wl.sum() * CDL_PX / 1e6, 2)
            for j in range(4):
                df[f"soil_m{j + 1}"] = weighted_mean(ld[f"soil_m{j + 1}"].values, wl)
            df["soil_m_0_100cm"] = sum(
                df[f"soil_m{j + 1}"] * (b - a) for j, (a, b) in enumerate(LAYER_CM[:3])
            ) / 100.0
            df["sneqv_mm"] = weighted_mean(ld.sneqv.values, wl)
            df["qrain_mm"] = weighted_mean(ld.qrain.values, wl)
            df["accet_mm"] = weighted_mean(inc["accet"], wl)
            df["ugdrnoff_mm"] = weighted_mean(inc["ugdrnoff"], wl)
            df["n_ldas"] = ld.n_samples.values
            rcols = ["sfchead_mean_mm", "sfchead_max_mm", *PONDED_MM, "zwt_mean_m",
                     "zwt_min_m", *SAT_DEPTHS, "n_rt"]  # fmt: skip
            if rd is None:
                for col in rcols:
                    df[col] = np.nan
            else:
                wr = weights.crop_px_rt.sel(cdl_year=cy, fips=f).values.astype(np.float64)
                r = pd.DataFrame({"date": rd.time.values})
                r["sfchead_mean_mm"] = weighted_mean(rd.sfchead_mean.values, wr)
                hm = rd.sfchead_max.values
                r["sfchead_max_mm"] = weighted_mean(hm, wr)
                for col, thr in PONDED_MM.items():
                    r[col] = weighted_mean(share(hm, hm > thr), wr)
                r["zwt_mean_m"] = weighted_mean(rd.zwt_mean.values, wr)
                zm = rd.zwt_min.values
                r["zwt_min_m"] = weighted_mean(zm, wr)
                for col, dep in SAT_DEPTHS.items():
                    r[col] = weighted_mean(share(zm, zm <= dep + 1e-3), wr)
                r["n_rt"] = rd.n_samples.values
                df = df.merge(r, on="date", how="left")
                df["n_rt"] = df["n_rt"].fillna(0).astype(int)
            frames.append(df)
        print(f"  series {year} (CDL {cy})", flush=True)
    out = pd.concat(frames, ignore_index=True).sort_values(["fips", "date"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", default="2002-2023", help="e.g. 2002-2023 or 2015,2016")
    ap.add_argument("--workers", type=int, default=4, help="time chunks read at once")
    ap.add_argument("--county-only", action="store_true", help="skip fetching")
    a = ap.parse_args()
    import s3fs

    fs = s3fs.S3FileSystem(anon=True)
    bounds = study_bounds_lcc()
    stores, grids, wins = {}, {}, {}
    for key, (name, _) in STORES.items():
        stores[key] = Store(fs, name)
        ys, xs, g = window(stores[key].x, stores[key].y, bounds)
        grids[key], wins[key] = g, (ys, xs)
        print(f"{key}: {name} {stores[key].time[0]} .. {stores[key].time[-1]}, "
              f"window {g.ny} x {g.nx} cells of {g.dx:.0f} m", flush=True)  # fmt: skip
    if not a.county_only:
        failed = []
        for y in parse_years(a.years):
            for key in STORES:
                try:
                    print(fetch_year(stores[key], key, y, *wins[key], grids[key], a.workers),
                          flush=True)  # fmt: skip
                except (OSError, RuntimeError) as e:
                    print(f"{key} {y}: FAILED {type(e).__name__}: {e}", flush=True)
                    failed.append((key, y))
        if failed:
            print(f"failed: {failed} — rerun; finished years are skipped", flush=True)
    w = cropland_weights(grids)
    s = county_series(w)
    part = COUNTY_CSV.with_suffix(".csv.part")
    s.to_csv(part, index=False, float_format="%.5g", date_format="%Y-%m-%d")
    part.rename(COUNTY_CSV)
    print(f"wrote {COUNTY_CSV} ({len(s):,} rows, {s.date.min():%Y-%m-%d} .. "
          f"{s.date.max():%Y-%m-%d})", flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
