"""Radar rainfall metrics per county x month (and a daily series), cropland-weighted, from
the Stage IV and MRMS hourly clips (scripts/fetch_precip_hourly.py).

Runs in the shared sfincs env (no GRIB needed):  python scripts/rain_metrics.py

Weighting (the same as scripts/fetch_nwm_soil.py, whose helpers are imported): every 30 m
CDL cropland pixel (agri_sfincs.cdl.CROPLAND) inside a county is binned to the precip
cell holding its centre (MRMS: 0.01 deg lon/lat; Stage IV: HRAP polar-stereographic
x/y), so a county's weights are cropland pixel counts per cell. CDL of the data year, or
the nearest year (2008 for 2002-2007; 2010 skipped, FINDINGS §1). WHOLE counties, not
just the in-ring part: the losses are whole-county. NaN cells drop out of the weighting.

Time: the hourly files are UTC, each value the hour ENDING at ``time``. Days and months
are LOCAL (America/New_York, so EST/EDT): an hour belongs to the local day holding its
start (hour ending 2023-07-01T04Z = 23-24 EDT Jun 30 -> June). Local days on DST changes
have 23 or 25 hours.

Per county x local month x product (``rain_county_month.csv``; keys fips, county, year,
month, product):
  cdl_year, crop_km2, n_hours (local calendar), missing_hours (hours with no data on
  any cropland cell, or outside the record), missing_frac (cropland-weighted share of
  cell-hours that are NaN after filling), filled_frac (share filled from 6-h files)
  total_mm             sum of the hourly cropland means (NaN hours count as 0)
  wetdays_1/10/25mm    local days whose cropland-mean total is >= 1 / 10 / 25 mm
  max{1,3,6,24,72}h_mm largest k-hour sum of the cropland-mean series, windows lying
                       wholly inside the month (NaN hours count as 0)
  peakcell_max1h_mm, peakcell_max24h_mm
                       the same 1 h / 24 h maxima per CELL, max over the county's
                       cropland cells
  frac_crop_24h_ge50, frac_crop_24h_ge75
                       cropland share (pixel-weighted) whose cell 24 h max >= 50 / 75 mm
  ante7d_mm, ante14d_mm, ante30d_mm
                       totals over the 7 / 14 / 30 local days before the month starts
                       (NaN if any of those days is outside the product's record)
  prev_month_mm        the previous local month's total_mm (NaN if it misses > 10 %)
Daily (``rain_county_daily.csv``): fips, county, date (local), product, mm, missing_frac.

Stage IV gap fill: the hourly mosaic has whole hours with no data over NJ (MARFC's
hourly field absent, e.g. ~22 % of June-July 2003) while the 6-h files are complete.
Where a cell's hour is NaN, the 6-h total minus the hours present (>= 0) is spread
evenly over the missing hours of that 6-h window (``fill_from_6h``). Totals are then
right; the intensity maxima in filled hours are smoothed (``filled_frac`` says how much).
stage4_hourly_vs_6h.csv compares hourly sums with 6-h totals over complete windows.

Writes data/precip/: rain_county_month.csv, rain_county_daily.csv,
stage4_hourly_vs_6h.csv, precip_cropland_weights.nc (cache, rebuilt when CDL or the grids change).
Then run scripts/rain_compare.py for the Stage IV vs MRMS (vs NWM) comparison report.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from agri_sfincs import cdl, config, domain

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_nwm_soil as nwm  # noqa: E402  (Grid, bin_pixels, nearest_year, SKIP_CDL)

TZ = "America/New_York"
PRODUCTS = ("stage4", "mrms")
MONTH_CSV = config.PRECIP_DIR / "rain_county_month.csv"
DAILY_CSV = config.PRECIP_DIR / "rain_county_daily.csv"
WEIGHTS_NC = config.PRECIP_DIR / "precip_cropland_weights.nc"
STAGE4_CHECK_CSV = config.PRECIP_DIR / "stage4_hourly_vs_6h.csv"
WINDOWS_H = (1, 3, 6, 24, 72)
WET_MM = (1, 10, 25)
CELL24_MM = (50, 75)
ANTE_D = (7, 14, 30)
#: prev_month_mm is NaN when the previous month misses more than this (record edges).
PREV_MAX_MISSING = 0.10


# ---------------------------------------------------------------- pure helpers


def local_hour_start(t_end_utc) -> pd.DatetimeIndex:
    """Local (America/New_York) wall-clock START of each hour ending at ``t_end_utc``
    (naive UTC), tz-naive."""
    t = pd.DatetimeIndex(t_end_utc) - pd.Timedelta("1h")
    return t.tz_localize("UTC").tz_convert(TZ).tz_localize(None)


def month_index(local_start: pd.DatetimeIndex) -> np.ndarray:
    """Integer month id (year * 12 + month - 1) of each local hour start."""
    return (local_start.year * 12 + local_start.month - 1).to_numpy()


def local_month_hours(month_ids) -> np.ndarray:
    """Hours in each local month (744 / 743 in March / 745 in November, ...)."""
    ids = np.asarray(month_ids)
    start = pd.to_datetime(dict(year=ids // 12, month=ids % 12 + 1, day=1))
    end = pd.to_datetime(dict(year=(ids + 1) // 12, month=(ids + 1) % 12 + 1, day=1))
    loc = lambda t: pd.DatetimeIndex(t).tz_localize(TZ)  # noqa: E731
    return ((loc(end) - loc(start)) / pd.Timedelta("1h")).to_numpy().astype(int)


def local_day_hours(days) -> np.ndarray:
    """Hours in each local day (24, or 23 / 25 on the DST changes)."""
    d = pd.DatetimeIndex(days).normalize()
    a, b = d.tz_localize(TZ), (d + pd.Timedelta("1D")).tz_localize(TZ)
    return ((b - a) / pd.Timedelta("1h")).to_numpy().astype(int)


def weighted_means(p: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Weighted means over cells of ``p`` (time, cell) for each weight column of ``w``
    (cell, k), NaN cells dropping out (fetch_nwm_soil.weighted_mean, as a matrix
    product), and the weighted NaN share. Returns (mean (time, k), nan_frac (time, k));
    the mean is NaN where no weighted cell is finite."""
    ok = np.isfinite(p)
    num = np.where(ok, p, 0.0) @ w
    den = ok.astype(np.float64) @ w
    tot = w.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(den > 0, num / den, np.nan)
        nan_frac = np.where(tot > 0, 1.0 - den / tot, np.nan)
    return mean, nan_frac


def window_max(x: np.ndarray, k: int, group: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per group, the largest sum of ``k`` consecutive rows of ``x`` (time, ...) over
    windows lying wholly inside one group. ``group`` (time,) must be sorted (runs). NaN
    counts as 0. Returns (group ids, maxima (n_group, ...)); NaN where a group is
    shorter than ``k``."""
    x = np.nan_to_num(np.asarray(x, dtype=np.float64))
    g = np.asarray(group)
    if len(g) > 1 and (np.diff(g) < 0).any():
        raise ValueError("group must be sorted")
    c = np.concatenate([np.zeros_like(x[:1]), np.cumsum(x, axis=0)])
    n = len(g)
    s = np.full(x.shape, -np.inf)
    if n >= k:
        s[k - 1 :] = c[k:] - c[: n - k + 1]
        same = np.zeros(n, bool)
        same[k - 1 :] = g[k - 1 :] == g[: n - k + 1]
        s[~same] = -np.inf
    ids, starts = np.unique(g, return_index=True)
    m = np.maximum.reduceat(s, starts, axis=0)
    m[np.isneginf(m)] = np.nan
    return ids, m


def antecedent(daily: pd.Series, month_starts, ndays: int) -> np.ndarray:
    """Sum of ``daily`` (index: consecutive local dates; NaN = a day with no data) over
    the ``ndays`` days before each month start; NaN if any of those days is NaN or not
    in the index."""
    d = daily.astype(float)
    idx = pd.DatetimeIndex([d.index[0] - pd.Timedelta("1D"), *d.index])
    c = pd.Series(np.concatenate([[0.0], np.cumsum(d.fillna(0).to_numpy())]), index=idx)
    nn = pd.Series(np.concatenate([[0], np.cumsum(d.isna().to_numpy())]), index=idx)
    out = []
    for m in pd.DatetimeIndex(month_starts):
        a, b = m - pd.Timedelta(days=ndays + 1), m - pd.Timedelta("1D")
        ok = a in c.index and b in c.index and nn[b] == nn[a]
        out.append(c[b] - c[a] if ok else np.nan)
    return np.asarray(out)


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


def check_6h(t_end, p, t6, p6, wall, cells) -> pd.DataFrame:
    """Stage IV hourly vs 6-h totals per UTC year over the 6-h windows whose 6 hours
    are all present, cropland-weighted (all counties and CDL years pooled); written to
    STAGE4_CHECK_CSV."""
    win = six_hour_windows(p, t_end, p6, t6)
    w = wall.values.sum(axis=(0, 1)).ravel()[cells].astype(np.float64)
    ok = (win["nmiss"] == 0) & (win["nh"] == 6)[:, None] & np.isfinite(win["six"])
    year = (win["end"] - pd.Timedelta("1h")).year
    rows = []
    for y in np.unique(year):
        s = year == y
        rows.append({
            "year": int(y),
            "complete_window_frac": float((ok[s] @ w).sum() / (s.sum() * w.sum())),
            "missing_hour_frac": float((win["nmiss"][s] @ w).sum() / (win["nh"][s].sum() * w.sum())),
            "hourly_mm": float((np.where(ok[s], win["have"][s], 0) @ w).sum() / w.sum()),
            "six_hour_mm": float((np.where(ok[s], win["six"][s], 0) @ w).sum() / w.sum()),
        })  # fmt: skip
    df = pd.DataFrame(rows)
    df["ratio"] = df["hourly_mm"] / df["six_hour_mm"]
    df.to_csv(STAGE4_CHECK_CSV, index=False, float_format="%.4g")
    print(f"  wrote {STAGE4_CHECK_CSV.name}: hourly / 6-h over complete windows "
          f"{df.ratio.min():.3f} .. {df.ratio.max():.3f}", flush=True)  # fmt: skip
    return df


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


# ---------------------------------------------------------------- grids + weights


def product_files(product: str) -> list[Path]:
    return sorted((config.PRECIP_DIR / product).glob(f"{product}_[0-9][0-9][0-9][0-9].nc"))


def product_grid(product: str, ds: xr.Dataset):
    """(Grid with ascending y, transformer lon/lat -> grid coords, flip_y) for a year
    file. MRMS rows run north -> south in the files, so they are flipped."""
    from pyproj import Transformer

    if product == "mrms":
        lat, lon = ds.lat.values, ds.lon.values
        d = 0.01
        g = nwm.Grid(float(lon.min()) - d / 2, float(lat.min()) - d / 2, d, d, len(lon), len(lat))
        return g, None, bool(lat[0] > lat[-1])
    tr = Transformer.from_crs("EPSG:4326", ds.attrs["crs_proj4"], always_xy=True)
    X, Y = tr.transform(ds.lon.values, ds.lat.values)
    x0, dx = regular_axis(X, axis=1, tol=60.0)
    y0, dy = regular_axis(Y, axis=0, tol=60.0)
    if dx <= 0 or dy <= 0:
        raise RuntimeError(f"Stage IV axes not ascending ({dx}, {dy})")
    g = nwm.Grid(x0 - dx / 2, y0 - dy / 2, dx, dy, X.shape[1], X.shape[0])
    return g, tr, False


def cropland_weights(grids: dict) -> xr.Dataset:
    """Cropland CDL pixel counts per county x CDL year x cell, per product grid
    (cached in WEIGHTS_NC)."""
    import rasterio
    from pyproj import Transformer
    from rasterio.features import rasterize
    from rasterio.windows import Window, from_bounds

    from agri_sfincs import region

    files = sorted(config.CDL_DIR.glob(f"CDL_*_{domain.STATE_FIPS}.tif"))
    if not files:
        raise SystemExit("no CDL files — run scripts/fetch_cdl.py")
    sig = repr({k: g for k, (g, _, _) in grids.items()})
    if WEIGHTS_NC.exists() and WEIGHTS_NC.stat().st_mtime > max(f.stat().st_mtime for f in files):
        w = xr.load_dataset(WEIGHTS_NC)
        if w.attrs.get("grids") == sig:
            return w
    fips = list(domain.COUNTIES)
    c = region.load_counties().set_index("fips").loc[fips].reset_index()
    years = [int(f.name.split("_")[1]) for f in files]
    crop_codes = np.array(sorted(cdl.CROPLAND))
    out = {k: np.zeros((len(years), len(fips), g.ny, g.nx), np.int32)
           for k, (g, _, _) in grids.items()}  # fmt: skip
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
        lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(px, py)
        ci = lab[r, col].astype(np.int64) - 1
        for k, (g, gtr, _) in grids.items():
            X, Y = (lon, lat) if gtr is None else gtr.transform(lon, lat)
            out[k][yi] = nwm.bin_pixels(X, Y, ci, g, len(fips))
            lost = len(r) - out[k][yi].sum()
            if lost > 0.001 * len(r):
                raise RuntimeError(f"{f.name}: {lost} cropland pixels fall outside the {k} clip")
        print(f"  weights {f.name}: {len(r) * nwm.CDL_PX / 1e6:,.0f} km2 cropland", flush=True)
    w = xr.Dataset(
        {f"crop_px_{k}": (("cdl_year", "fips", f"y_{k}", f"x_{k}"), v) for k, v in out.items()},
        coords={"cdl_year": years, "fips": fips},
        attrs={"what": "30 m CDL cropland pixels (agri_sfincs.cdl.CROPLAND) per precip cell, "
                       "binned by pixel centre; y ascending (south -> north)", "grids": sig},
    )  # fmt: skip
    config.PRECIP_DIR.mkdir(parents=True, exist_ok=True)
    w.to_netcdf(WEIGHTS_NC, encoding={n: {"zlib": True} for n in w.data_vars})
    return w


# ---------------------------------------------------------------- per product


def load_hourly(product: str, flip: bool, cells: np.ndarray, freq: str = "h"):
    """(accumulation-ending times, precip (time, cell) for the flat ``cells``) over all
    year files, reindexed to a gap-free axis of step ``freq`` (absent years -> NaN)."""
    times, arrs = [], []
    for f in product_files(product):
        with xr.open_dataset(f) as ds:
            p = ds.precip.values
            if flip:
                p = p[:, ::-1, :]
            arrs.append(p.reshape(len(p), -1)[:, cells])
            times.append(pd.DatetimeIndex(ds.time.values))
    t = times[0].append(times[1:]) if len(times) > 1 else times[0]
    full = pd.date_range(t[0], t[-1], freq=freq)
    p = np.full((len(full), len(cells)), np.nan, np.float32)
    p[full.get_indexer(t)] = np.concatenate(arrs)
    return full, p


def product_metrics(product: str, weights: xr.Dataset, flip: bool):
    """(monthly DataFrame, daily DataFrame) for one product."""
    fips = [str(f) for f in weights.fips.values]
    cdl_years = [int(y) for y in weights.cdl_year.values if int(y) not in nwm.SKIP_CDL]
    wall = weights[f"crop_px_{product}"]  # (cdl_year, fips, y, x)
    any_w = (wall.values.sum(axis=(0, 1)) > 0).ravel()
    cells = np.nonzero(any_w)[0]
    t_end, p = load_hourly(product, flip, cells)
    print(f"{product}: {len(t_end):,} hours x {len(cells)} cropland cells "
          f"({t_end[0]} .. {t_end[-1]})", flush=True)  # fmt: skip
    filled = np.zeros(p.shape, bool)
    if product == "stage4" and product_files("stage4_6h"):
        t6, p6 = load_hourly("stage4_6h", flip, cells, freq="6h")
        check_6h(t_end, p, t6, p6, wall, cells)
        p, filled = fill_from_6h(p, t_end, p6, t6)
        print(f"  filled {filled.mean():.2%} of cell-hours from the 6-h files", flush=True)
    ls = local_hour_start(t_end)
    mid = month_index(ls)
    lyear = ls.year.to_numpy()
    lday = ls.normalize()

    # County hourly means, weights by the local year of each hour.
    hm = np.full((len(t_end), len(fips)), np.nan)
    hn = np.full((len(t_end), len(fips)), np.nan)
    hf = np.zeros((len(t_end), len(fips)))
    wcell = {}
    cdl_of = {}
    for y in np.unique(lyear):
        cy = nwm.nearest_year(int(y), cdl_years)
        cdl_of[int(y)] = cy
        w = wall.sel(cdl_year=cy).values.reshape(len(fips), -1)[:, cells].T.astype(np.float64)
        wcell[int(y)] = w
        sel = lyear == y
        hm[sel], hn[sel] = weighted_means(p[sel], w)
        hf[sel] = filled[sel].astype(np.float64) @ w / w.sum(axis=0)

    # Per-cell month maxima (1 h, 24 h), in chunks of cells.
    mids = np.unique(mid)
    cmax = {k: np.full((len(mids), len(cells)), np.nan) for k in (1, 24)}
    for j in range(0, len(cells), 1000):
        blk = p[:, j : j + 1000]
        for k in (1, 24):
            cmax[k][:, j : j + 1000] = window_max(blk, k, mid)[1]
    # County series maxima.
    smax = {k: window_max(hm, k, mid)[1] for k in WINDOWS_H}

    rows, drows = [], []
    for ci, f in enumerate(fips):
        name = domain.COUNTIES[f]
        h = pd.DataFrame({"mm": hm[:, ci], "nan": hn[:, ci], "filled": hf[:, ci],
                          "day": lday, "mid": mid})  # fmt: skip
        h["nodata"] = ~np.isfinite(h["mm"])
        day = h.groupby("day").agg(mm=("mm", lambda s: s.fillna(0).sum()),
                                   present=("mm", "size"),
                                   nan_sum=("nan", lambda s: s.fillna(1.0).sum()))  # fmt: skip
        nh = local_day_hours(day.index)
        day["missing_frac"] = (day["nan_sum"] + nh - day["present"]) / nh
        day = day[["mm", "missing_frac"]]
        drows.append(day.reset_index().rename(columns={"day": "date"})
                     .assign(fips=f, county=name, product=product))  # fmt: skip
        mon = h.groupby("mid").agg(present=("mm", "size"), nodata=("nodata", "sum"),
                                   nan_sum=("nan", lambda s: s.fillna(1.0).sum()),
                                   filled_sum=("filled", "sum"),
                                   total_mm=("mm", lambda s: s.fillna(0).sum()))  # fmt: skip
        # Against the calendar: hours outside the hourly axis (record edges) are missing.
        mon["n_hours"] = local_month_hours(mon.index)
        absent = mon["n_hours"] - mon["present"]
        mon["missing_hours"] = mon["nodata"] + absent
        mon["missing_frac"] = (mon["nan_sum"] + absent) / mon["n_hours"]
        mon["filled_frac"] = mon["filled_sum"] / mon["n_hours"]
        dm = (day.index.year * 12 + day.index.month - 1).to_numpy()
        for thr in WET_MM:
            mon[f"wetdays_{thr}mm"] = pd.Series(day["mm"].to_numpy() >= thr).groupby(dm).sum()
        for k in WINDOWS_H:
            mon[f"max{k}h_mm"] = smax[k][:, ci]
        mon["year"], mon["month"] = mon.index // 12, mon.index % 12 + 1
        mon["cdl_year"] = [cdl_of[int(y)] for y in mon["year"]]
        mon["crop_km2"] = [round(wcell[int(y)][:, ci].sum() * nwm.CDL_PX / 1e6, 2)
                           for y in mon["year"]]  # fmt: skip
        pk1, pk24, fr = [], [], {t: [] for t in CELL24_MM}
        for i, y in enumerate(mon["year"]):
            w = wcell[int(y)][:, ci]
            on = w > 0
            pk1.append(np.nanmax(cmax[1][i, on]) if np.isfinite(cmax[1][i, on]).any() else np.nan)
            m24 = cmax[24][i, on]
            pk24.append(np.nanmax(m24) if np.isfinite(m24).any() else np.nan)
            ok = np.isfinite(m24)
            for t in CELL24_MM:
                den = w[on][ok].sum()
                fr[t].append((w[on][ok] * (m24[ok] >= t)).sum() / den if den else np.nan)
        mon["peakcell_max1h_mm"], mon["peakcell_max24h_mm"] = pk1, pk24
        for t in CELL24_MM:
            mon[f"frac_crop_24h_ge{t}"] = fr[t]
        starts = pd.to_datetime(dict(year=mon["year"], month=mon["month"], day=1))
        for n in ANTE_D:
            mon[f"ante{n}d_mm"] = antecedent(day["mm"].where(day["missing_frac"] < 1), starts, n)
        prev = mon["total_mm"].where(mon["missing_frac"] <= PREV_MAX_MISSING)
        mon["prev_month_mm"] = prev.reindex(mon.index - 1).to_numpy()
        mon["fips"], mon["county"], mon["product"] = f, name, product
        rows.append(mon)
    m = pd.concat(rows, ignore_index=True)
    # Keep the years of the files (not the few hours of the first UTC year that fall in
    # the previous local December) and drop months with no data at all (MRMS before
    # 2015-05).
    y0, y1 = t_end[0].year, (t_end[-1] - pd.Timedelta("1h")).year
    m = m[m["year"].between(y0, y1) & (m["missing_hours"] < m["n_hours"])]
    d = pd.concat(drows, ignore_index=True)
    d = d[d["missing_frac"] < 1]
    return m, d


MONTH_COLS = ["fips", "county", "year", "month", "product", "cdl_year", "crop_km2",
              "n_hours", "missing_hours", "missing_frac", "filled_frac", "total_mm",
              *[f"wetdays_{t}mm" for t in WET_MM], *[f"max{k}h_mm" for k in WINDOWS_H],
              "peakcell_max1h_mm", "peakcell_max24h_mm",
              *[f"frac_crop_24h_ge{t}" for t in CELL24_MM],
              *[f"ante{n}d_mm" for n in ANTE_D], "prev_month_mm"]  # fmt: skip


def main() -> None:
    grids, flips = {}, {}
    have = [p for p in PRODUCTS if product_files(p)]
    if not have:
        raise SystemExit("no year files — run scripts/fetch_precip_hourly.py")
    for p in have:
        with xr.open_dataset(product_files(p)[0]) as ds:
            g, tr, flip = product_grid(p, ds)
        grids[p], flips[p] = (g, tr, flip), flip
        print(f"{p}: grid {g.ny} x {g.nx}, d = {g.dx:.4g}", flush=True)
    w = cropland_weights(grids)
    months, days = [], []
    for p in have:
        m, d = product_metrics(p, w, flips[p])
        months.append(m)
        days.append(d)
    m = pd.concat(months, ignore_index=True)[MONTH_COLS].sort_values(
        ["product", "fips", "year", "month"])
    d = pd.concat(days, ignore_index=True)[["fips", "county", "date", "product", "mm",
                                            "missing_frac"]].sort_values(
        ["product", "fips", "date"])  # fmt: skip
    for df, dest in ((m, MONTH_CSV), (d, DAILY_CSV)):
        part = dest.with_suffix(".csv.part")
        df.to_csv(part, index=False, float_format="%.4g", date_format="%Y-%m-%d")
        part.rename(dest)
        print(f"wrote {dest} ({len(df):,} rows)", flush=True)


if __name__ == "__main__":
    main()
