"""Polite HTTP: retries with backoff, and paged ArcGIS REST feature queries."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

import geopandas as gpd
import pandas as pd
import requests

PAUSE_S = 0.5
RETRY_STATUS = {429, 500, 502, 503, 504}

_session = requests.Session()
_session.headers["User-Agent"] = "sfincs-nj-agri (research; Rutgers ag flood-loss study)"


def get(url: str, params: dict | None = None, timeout: float = 120, retries: int = 5):
    """GET with a pause, retrying 429/5xx and connection errors with backoff."""
    delay = 5.0
    for attempt in range(retries + 1):
        time.sleep(PAUSE_S)
        try:
            r = _session.get(url, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == retries:
                raise
            print(f"    ({type(e).__name__}; retry in {delay:.0f} s)")
        else:
            if r.status_code not in RETRY_STATUS or attempt == retries:
                r.raise_for_status()
                return r
            print(f"    (HTTP {r.status_code}; retry in {delay:.0f} s)")
        time.sleep(delay)
        delay = min(delay * 2, 300.0)
    raise RuntimeError("unreachable")


def post(url: str, payload: dict, timeout: float = 120, retries: int = 5):
    """POST JSON with the same pause/backoff rules as ``get``."""
    delay = 5.0
    for attempt in range(retries + 1):
        time.sleep(PAUSE_S)
        try:
            r = _session.post(url, json=payload, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == retries:
                raise
            print(f"    ({type(e).__name__}; retry in {delay:.0f} s)")
        else:
            if r.status_code not in RETRY_STATUS or attempt == retries:
                r.raise_for_status()
                return r
            print(f"    (HTTP {r.status_code}; retry in {delay:.0f} s)")
        time.sleep(delay)
        delay = min(delay * 2, 300.0)
    raise RuntimeError("unreachable")


def arcgis_query(
    layer_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    bbox: tuple[float, float, float, float] | None = None,
    page_size: int | None = None,
) -> gpd.GeoDataFrame:
    """All features of an ArcGIS MapServer/FeatureServer layer matching ``where`` (and
    intersecting the lon/lat ``bbox`` = w, s, e, n, if given), as EPSG:4326,
    following ``exceededTransferLimit`` paging."""
    frames, offset = [], 0
    while True:
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "geojson",
            "resultOffset": offset,
        }
        if page_size:
            params["resultRecordCount"] = page_size
        if bbox is not None:
            params |= {
                "geometry": ",".join(f"{v:.6f}" for v in bbox),
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
            }
        r = get(f"{layer_url}/query", params, timeout=300)
        if not r.content.strip() or b'"error"' in r.content[:200]:
            raise RuntimeError(
                f"{layer_url}: empty or error response at offset {offset}: "
                f"{r.content[:300]!r} — try a smaller page_size or a narrower where"
            )
        # Parsed in Python, not via gpd.read_file: GDAL's GeoJSON reader rejected the
        # full NID attribute set ("URL rejected: No host present", 2026-10-02).
        j = r.json()
        feats = j.get("features", [])
        gdf = (
            gpd.GeoDataFrame.from_features(feats, crs=4326)
            if feats
            else gpd.GeoDataFrame(geometry=[], crs=4326)
        )
        if len(gdf):
            frames.append(gdf)
        # The geojson flavour reports paging in a top-level property.
        more = j.get("exceededTransferLimit") or (
            j.get("properties", {}).get("exceededTransferLimit")
        )
        if not more or not len(gdf):
            break
        offset += len(gdf)
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326)


def download(url: str, dest, timeout: float = 600, chunk: int = 1 << 20) -> None:
    """Stream ``url`` to ``dest`` through a ``.part`` file, renamed only when complete."""
    from pathlib import Path

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    with _session.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(part, "wb") as f:
            for b in r.iter_content(chunk):
                f.write(b)
    part.rename(dest)


def arcgis_form_query(url: str, params: dict, tries: int = 4) -> dict:
    """One ArcGIS REST ``/query`` as a form POST, GeoJSON back (NJDEP LU/LC services:
    scripts/fetch_njlulc.py, fetch_lulc_training.py)."""
    data = urllib.parse.urlencode({"f": "geojson", **params}).encode()
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url + "/query", data=data),
                                        timeout=300) as r:  # fmt: skip
                return json.load(r)
        except Exception:  # noqa: BLE001 — flaky public service: retry, then raise
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))
    raise RuntimeError("unreachable")
