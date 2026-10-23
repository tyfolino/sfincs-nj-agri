"""River-bed burn: the pure pieces (datums, profiles, hydraulic geometry, the
never-raise rule). No I/O, no network — ``scripts/build_riverbeds.py`` drives them and
``tests/test_riverbeds.py`` pins them.

Profile helpers (``running_median``, ``fill_interior``) follow nj_bight_sfincs
``scripts/build_riverbeds_v4.py`` (``_running_median`` and the interior-gap rule of
``profile``), and ``gauge_mean_depth`` follows its ``build_inland_water_v4.py``
(median area/width of channel measurements in the site's own p25-p75 flow band);
copied 2026-10-03, not imported.

Sign conventions: elevations are m NAVD88 (up positive); chart depths are m BELOW the
chart datum (MLLW, down positive), as S-57 SOUNDG / DEPARE carry them.
"""

from __future__ import annotations

import numpy as np

FT = 0.3048  # US survey vs international foot differ by 2 ppm: irrelevant here


# ── datums ────────────────────────────────────────────────────────────────────
def coops_datum_navd88(row: dict, name: str = "MLLW") -> float:
    """Datum ``name`` in m NAVD88 at a CO-OPS station whose datum sheet (feet, on the
    station datum) carries NAVD88. NaN if it does not."""
    try:
        return (float(row[name]) - float(row["NAVD88"])) * FT
    except (TypeError, ValueError, KeyError):
        return float("nan")


def subordinate_mllw_navd88(ref: dict, kind: str, h_high: float, h_low: float,
                            mtl_navd88_m: float) -> float:  # fmt: skip
    """MLLW (m NAVD88) at a CO-OPS tide-prediction SUBORDINATE station.

    A subordinate station's predictions are on its own MLLW: high = ref high x
    ``h_high`` and low = ref low x ``h_low`` (``kind`` "R", ratios), or + offsets in
    feet (``kind`` "A"), the reference heights being on the reference's MLLW. So the
    station's mean tide level above its MLLW is (MHW' + MLW') / 2 with
    MHW' = f(ref MHW), MLW' = f(ref MLW), and

        MLLW_navd88 = MTL_navd88 - (MHW' + MLW') / 2

    where ``mtl_navd88_m`` (the station's MTL in NAVD88) must be supplied: CO-OPS
    gives subordinate stations no geodetic tie, so the caller borrows it from the
    nearest NAVD88-tied station (an error of a few cm to ~0.1 m upriver).
    """
    mhw = (float(ref["MHW"]) - float(ref["MLLW"]))
    mlw = (float(ref["MLW"]) - float(ref["MLLW"]))
    if kind == "R":
        hi, lo = mhw * h_high, mlw * h_low
    elif kind == "A":
        hi, lo = mhw + h_high, mlw + h_low
    else:
        raise ValueError(f"unknown height adjustment type {kind!r}")
    return mtl_navd88_m - 0.5 * (hi + lo) * FT


def chart_to_navd88(depth_below_mllw, mllw_navd88):
    """Bed elevation (m NAVD88) of a charted depth (m below MLLW)."""
    return np.asarray(mllw_navd88, dtype="float64") - np.asarray(depth_below_mllw, dtype="float64")


def parse_a93(line: str) -> tuple[float, float, float] | None:
    """(lon, lat, depth m below the survey's datum) from one NCEI HYD93 XYZ (.a93) record, or
    None for a no-depth record (depth field > 9000). Columns as nj_bight_sfincs read them:
    lat 9-17 and lon 17-27 in micro-degrees, depth 27-33 in decimetres."""
    d = int(line[27:33]) / 10
    if d > 9000:
        return None
    return int(line[17:27]) / 1e6, int(line[9:17]) / 1e6, d


def csb_depth_mllw(raw_depth, water_level_mllw, draft: float):
    """Crowdsourced (CSB) depth below MLLW: the raw depth is below the transducer, which sits
    ``draft`` m below a sea surface ``water_level_mllw`` m above MLLW at the time."""
    return np.asarray(raw_depth, "float64") + draft - np.asarray(water_level_mllw, "float64")


def stated_floor(prof, mllw, grid, s_from: float, depth_below_mllw: float):
    """Lower ``prof`` to at least ``depth_below_mllw`` below MLLW at stations >= ``s_from``
    (stations run from the head of tide down to the mouth): a charted controlling depth or a
    stated depth is a floor the bed may not sit above. Never raises."""
    prof = np.asarray(prof, "float64").copy()
    sel = np.asarray(grid) >= s_from
    prof[sel] = np.fmin(prof[sel], np.asarray(mllw, "float64")[sel] - depth_below_mllw)
    return prof


def depare_depth(drval1, drval2, mid_max: float = 2.0, shallow_m: float | None = None) -> float:
    """Representative depth (m below chart datum) for one station from the S-57 depth
    areas that touch it, from the DEEPEST interval:

    * with ``shallow_m`` (the rule in use): ``shallow_m`` clipped to [DRVAL1, DRVAL2] —
      1.2 m for "0-1.8 m" and for a coarse "0-5.4 m" class, the lower bound 1.8 m for
      "1.8-9.1 m" (the depth the chart guarantees: such an area at a creek mouth is the
      Delaware's, and its midpoint put Alloway Creek's mouth at -10 m);
    * without: the midpoint of a shallow class (DRVAL2 <= ``mid_max``), else DRVAL1.

    Drying intervals (DRVAL2 <= 0) never count; only drying -> NaN (no burn).
    User, 2026-10-05: shallow classes and uncharted creeks take 1.2 m below MLLW (bight's
    value; the 2023 Maurice survey showed the 0.9 m midpoint was too shallow).
    """
    d1, d2 = np.asarray(drval1, dtype="float64"), np.asarray(drval2, dtype="float64")
    ok = np.isfinite(d1) & np.isfinite(d2) & (d2 > 0)
    if not ok.any():
        return float("nan")
    k = np.argmax(np.where(ok, d2, -np.inf))
    lo = max(d1[k], 0.0)
    if shallow_m is not None:
        return float(np.clip(shallow_m, lo, d2[k]))
    return 0.5 * (lo + d2[k]) if d2[k] <= mid_max else float(lo)


# ── profiles ──────────────────────────────────────────────────────────────────
def running_median(s, z, grid, half: float, min_n: int = 1, max_half: float | None = None) -> np.ndarray:
    """Median of ``z`` over ``s`` in [g - half, g + half] at every ``grid`` station.
    A window holding fewer than ``min_n`` samples (a lone bank sounding must not become
    the bed of a whole window) is widened to the ``min_n`` nearest samples, as long as
    they lie within ``max_half`` (default: ``half``, i.e. no widening); else NaN."""
    s, z, grid = (np.asarray(a, dtype="float64") for a in (s, z, grid))
    ok = np.isfinite(s) & np.isfinite(z)
    s, z = s[ok], z[ok]
    o = np.argsort(s)
    s, z = s[o], z[o]
    out = np.full(grid.shape, np.nan)
    lo = np.searchsorted(s, grid - half)
    hi = np.searchsorted(s, grid + half, side="right")
    need = max(min_n, 1)
    for i, (a, b) in enumerate(zip(lo, hi)):
        if b - a >= need:
            out[i] = np.median(z[a:b])
        elif max_half is not None and max_half > half and s.size >= need:
            d = np.abs(s - grid[i])
            k = np.argsort(d)[:need]
            if d[k].max() <= max_half:
                out[i] = np.median(z[k])
    return out


def fill_interior(grid, prof) -> np.ndarray:
    """Linear fill of NaN gaps BETWEEN finite stations; no extrapolation."""
    grid = np.asarray(grid, dtype="float64")
    out = np.array(prof, dtype="float64")
    ok = np.isfinite(out)
    if ok.sum() >= 2:
        inside = (grid >= grid[ok][0]) & (grid <= grid[ok][-1])
        out[inside] = np.interp(grid[inside], grid[ok], out[ok])
    return out


def taper(grid, s0: float, delta: float, half: float) -> np.ndarray:
    """``delta`` at station ``s0``, falling linearly to 0 at ``s0 +- half``: the
    correction that ties a profile to a gauge and hands back to the rule beyond."""
    g = np.asarray(grid, dtype="float64")
    return delta * np.clip(1.0 - np.abs(g - s0) / half, 0.0, None)


def monotone_downstream(z) -> np.ndarray:
    """``z`` ordered UPSTREAM -> DOWNSTREAM, made non-increasing downstream (a running
    minimum; NaN stays NaN and does not reset it). For the free-surface profile of a
    non-tidal stream: water does not flow uphill, so a bridge deck, a culvert road
    fill or a bank pixel caught by the sampler cannot lift the line."""
    z = np.asarray(z, dtype="float64")
    out = np.full(z.shape, np.nan)
    m = np.inf
    for i, v in enumerate(z):
        if np.isfinite(v):
            m = min(m, v)
            out[i] = m
    return out


# ── hydraulic geometry ────────────────────────────────────────────────────────
def gauge_mean_depth(flow, width, area, lo: float = 25, hi: float = 75) -> dict:
    """Median mean depth (area / width) and width of the channel measurements whose flow
    is inside the site's own p``lo``-p``hi`` measured-flow band. Inputs in ft, ft2,
    ft3/s as USGS serves them; outputs in m and m3/s."""
    q, w, a = (np.asarray(v, dtype="float64") for v in (flow, width, area))
    ok = np.isfinite(q) & np.isfinite(w) & np.isfinite(a) & (q > 0) & (w > 0) & (a > 0)
    q, w, a = q[ok], w[ok], a[ok]
    if q.size == 0:
        return {"n": 0}
    qlo, qhi = np.percentile(q, lo), np.percentile(q, hi)
    band = (q >= qlo) & (q <= qhi)
    if not band.any():  # two or three values can all fall outside an interpolated band
        return {"n": int(q.size), "n_band": 0}
    dep = a[band] / w[band] * FT
    return {
        "n": int(q.size),
        "n_band": int(band.sum()),
        "depth_m": float(np.median(dep)),
        "depth_p10_m": float(np.percentile(dep, 10)),
        "depth_p90_m": float(np.percentile(dep, 90)),
        "width_m": float(np.median(w[band]) * FT),
        "q_lo_cms": float(qlo * FT**3),
        "q_hi_cms": float(qhi * FT**3),
        "q_median_cms": float(np.median(q) * FT**3),
    }


def power_law_fit(x, y) -> tuple[float, float]:
    """(a, b) of y = a x^b by least squares in log-log space."""
    x, y = np.asarray(x, dtype="float64"), np.asarray(y, dtype="float64")
    ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
    if ok.sum() < 2:
        raise ValueError("power_law_fit needs at least two positive pairs")
    b, ln_a = np.polyfit(np.log(x[ok]), np.log(y[ok]), 1)
    return float(np.exp(ln_a)), float(b)


def power_law(x, a: float, b: float) -> np.ndarray:
    return a * np.asarray(x, dtype="float64") ** b


def interp_log_da(da_nodes, values, da) -> np.ndarray:
    """``values`` known at drainage areas ``da_nodes``, interpolated linearly in
    log(DA) and held constant beyond the end nodes (one node: constant)."""
    xn = np.log(np.asarray(da_nodes, dtype="float64"))
    vn = np.asarray(values, dtype="float64")
    o = np.argsort(xn)
    xn, vn = xn[o], vn[o]
    return np.interp(np.log(np.asarray(da, dtype="float64")), xn, vn)


def pick_survey(dates, coverage_km, frac: float = 0.9) -> int:
    """Index of the MOST RECENT survey whose coverage of a reach is at least ``frac`` of
    the best coverage (user, 2026-10-05: "the most recent survey that covers the reach";
    a newer survey of only the entrance channel does not displace a full one). -1 if no
    survey covers anything."""
    c = np.asarray(coverage_km, dtype="float64")
    if c.size == 0 or not np.isfinite(c).any() or np.nanmax(c) <= 0:
        return -1
    ok = np.nan_to_num(c) >= frac * np.nanmax(c)
    d = np.asarray(dates, dtype="datetime64[D]")
    return int(np.flatnonzero(ok)[np.argmax(d[ok])])


# ── the burn ──────────────────────────────────────────────────────────────────
def never_raise(bed, burn, min_drop: float = 0.0) -> np.ndarray:
    """The burn as it may be applied: ``burn`` where it is BELOW ``bed`` by more than
    ``min_drop`` (and ``bed`` exists), NaN everywhere else. Merging is then
    ``np.fmin(bed, result)`` — a burn can only ever lower the bed."""
    bed = np.asarray(bed, dtype="float64")
    burn = np.asarray(burn, dtype="float64")
    out = np.where(np.isfinite(bed) & np.isfinite(burn) & (burn < bed - min_drop), burn, np.nan)
    return out
