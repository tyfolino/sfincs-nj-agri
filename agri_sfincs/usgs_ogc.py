"""USGS Water Data OGC API client for the gauge downloaders (daily + continuous values).

Copied from ``nj_bight_sfincs/nj_sfincs/usgs_ogc.py`` (2026-10-02); only the
User-Agent changed. Keep it in step by hand if the original gains a fix.

The legacy ``waterservices.usgs.gov/nwis`` service is being decommissioned (it returned
503 on every call 2026-09-24/25; it answered again on 09-26). This module is the ONE
place the replacement is spoken to, so the gauge scripts cannot drift apart on
paging, retries or units.

    daily       one row per (time series, day) — the old ``/nwis/dv`` service.
                ``parameter_code=00060`` + ``statistic_id=00003`` = daily-mean discharge.
    continuous  one row per (time series, instant) — the old ``/nwis/iv`` service.
                ``time`` is RFC 3339 with an explicit ``+00:00`` offset, i.e. UTC.
    monitoring-locations   name, WGS84 point, ``drainage_area`` (mi2).

Values come back as STRINGS in ``unit_of_measure`` units (``ft^3/s``, ``ft``): nothing
here converts, the callers do, after asserting the unit they expect.

⚠️ A site can carry more than one time series for the same parameter/statistic (a
replaced sensor, a second method). The legacy iv call silently took ``timeSeries[0]``.
``one_series`` keeps the series with the most values in the window and SAYS SO when it
had to choose, rather than repeating that silently.

Politeness: requests are sequential, spaced by ``PAUSE_S``, and 429/5xx are retried with
exponential backoff honouring ``Retry-After``. An API key is optional (anonymous access
is rate-limited per IP); set ``API_USGS_PAT`` to send one (the name ``dataretrieval``
uses). The key is never logged.
"""

from __future__ import annotations

import os
import time

import pandas as pd
import requests

BASE = "https://api.waterdata.usgs.gov/ogcapi/v1"
PAUSE_S = 0.5
RETRIES = 6
TIMEOUT_S = 90
RETRY_STATUS = {429, 500, 502, 503, 504}

_session = requests.Session()
_session.headers["User-Agent"] = "sfincs-nj-agri (research; Rutgers ag flood-loss study)"
if os.environ.get("API_USGS_PAT"):
    _session.headers["X-Api-Key"] = os.environ["API_USGS_PAT"]


def _get(url: str, params: dict | None) -> dict:
    """GET → JSON with polite spacing and backoff on 429 / 5xx / connection errors."""
    delay = 5.0
    for attempt in range(RETRIES + 1):
        time.sleep(PAUSE_S)
        try:
            r = _session.get(url, params=params, timeout=TIMEOUT_S)
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == RETRIES:
                raise
            print(f"    ({type(e).__name__}; retry in {delay:.0f} s)")
        else:
            if r.status_code not in RETRY_STATUS:
                r.raise_for_status()
                return r.json()
            if attempt == RETRIES:
                r.raise_for_status()
            wait = r.headers.get("Retry-After")
            wait_s = float(wait) if wait and wait.isdigit() else delay
            print(f"    (HTTP {r.status_code}; retry in {wait_s:.0f} s)")
            delay = wait_s
        time.sleep(delay)
        delay = min(delay * 2, 300.0)
    raise RuntimeError("unreachable")


def items(collection: str, **params) -> list[dict]:
    """Every feature's ``properties`` (+ ``lon``/``lat`` if it has a point), all pages."""
    params = {"f": "json", "limit": 10000, **params}
    url = f"{BASE}/collections/{collection}/items"
    out: list[dict] = []
    while url:
        j = _get(url, params)
        for f in j.get("features", []):
            p = dict(f["properties"])
            p.setdefault("id", f.get("id"))
            g = f.get("geometry") or {}
            if g.get("type") == "Point":
                p["lon"], p["lat"] = g["coordinates"][:2]
            out.append(p)
        url = next(
            (ln["href"] for ln in j.get("links", []) if ln.get("rel") == "next"), None
        )
        params = None  # the next link carries the query
    return out


def one_series(rows: list[dict], site: str, what: str) -> list[dict]:
    """Keep ONE time series per site: the one with the most non-null values."""
    by_ts: dict[str, list[dict]] = {}
    for p in rows:
        by_ts.setdefault(p["time_series_id"], []).append(p)
    if len(by_ts) <= 1:
        return rows
    n = {k: sum(p["value"] not in (None, "") for p in v) for k, v in by_ts.items()}
    best = max(n, key=n.get)
    print(f"    ⚠️ {site} {what}: {len(by_ts)} time series {n}; keeping {best}")
    return by_ts[best]


def _to_series(rows: list[dict], unit: str, site: str) -> tuple[pd.Series, pd.Series]:
    """(value, approval_status) indexed by timestamp, in ``unit``. Nulls dropped."""
    units = {p["unit_of_measure"] for p in rows}
    if units - {unit}:
        raise ValueError(f"{site}: expected unit {unit!r}, API says {sorted(units)}")
    rows = [p for p in rows if p["value"] not in (None, "")]
    val = pd.Series({p["time"]: float(p["value"]) for p in rows}, dtype="float64")
    appr = pd.Series({p["time"]: p["approval_status"] for p in rows}, dtype="object")
    return val, appr


def daily_mean_discharge(site: str, begin: str, end: str) -> pd.DataFrame:
    """Daily-mean discharge (cfs, as served) for ``USGS-<site>``, ``begin``..``end``.

    Columns ``cfs`` and ``approval``; the index is the (naive) calendar date, exactly
    what the legacy ``/nwis/dv`` RDB ``datetime`` column held.
    """
    rows = items(
        "daily",
        monitoring_location_id=f"USGS-{site}",
        parameter_code="00060",
        statistic_id="00003",
        time=f"{begin}/{end}",
    )
    rows = one_series(rows, site, "00060/00003")
    val, appr = _to_series(rows, "ft^3/s", site)
    df = pd.DataFrame({"cfs": val, "approval": appr})
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def continuous(site: str, parameter_code: str, unit: str, begin: str, end: str):
    """Instantaneous values for ``USGS-<site>`` as a DataFrame (``value``, ``approval``)
    indexed by NAIVE UTC timestamps — what the legacy iv fetch produced after its
    ``tz_convert("UTC").tz_localize(None)``. ``begin``/``end`` are RFC 3339 instants."""
    rows = items(
        "continuous",
        monitoring_location_id=f"USGS-{site}",
        parameter_code=parameter_code,
        time=f"{begin}/{end}",
    )
    rows = one_series(rows, site, parameter_code)
    val, appr = _to_series(rows, unit, site)
    df = pd.DataFrame({"value": val, "approval": appr})
    idx = pd.to_datetime(df.index, utc=True)
    df.index = idx.tz_convert("UTC").tz_localize(None)
    return df.sort_index()


def locations(sites: list[str]) -> pd.DataFrame:
    """monitoring-locations metadata (name, lon, lat, drainage_area mi2), one call each."""
    recs = []
    for s in sites:
        rows = items("monitoring-locations", id=f"USGS-{s}")
        if not rows:
            raise KeyError(f"USGS-{s}: no monitoring location")
        p = rows[0]
        recs.append(
            {
                "site": s,
                "name": p.get("monitoring_location_name"),
                "lon": p.get("lon"),
                "lat": p.get("lat"),
                "drainage_area_mi2": p.get("drainage_area"),
                "site_type": p.get("site_type"),
            }
        )
    return pd.DataFrame(recs).set_index("site")
