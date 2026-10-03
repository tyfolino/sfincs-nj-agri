"""Inventory the water-level and streamflow gauges the model can be forced and checked with.

NOAA CO-OPS (``domain.NOAA_STATIONS``): downloads verified HOURLY heights, in MLLW
(the one datum every station serves; NAVD88 conversion belongs to the forcing step,
which has the datum-transfer logic), one request per station-year, and keeps them:
  data/gauges/noaa/<id>_hourly_mllw.csv.gz      time (UTC), wl_m_mllw
Then writes the % of hours present per station x year.

USGS: every time series inside the ring for discharge (00060) and water level (00065
gage height; 62620 / 63160 elevation NAVD88; 72279 tidal elevation), from the
``time-series-metadata`` collection (begin/end only — gaps need the data). Daily-mean
discharge IS downloaded (one request per site), so its yearly completeness is real:
  data/gauges/usgs/<site>_dv_cfs.csv.gz

Outputs (data/gauges/):
  noaa_completeness.csv   station x year, % hours present
  usgs_series.csv         one row per USGS time series inside the ring
  usgs_dv_completeness.csv  site x year, % days present

Usage:  python scripts/gauge_inventory.py [--years 2002-2025] [--skip-noaa] [--skip-usgs]
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import pandas as pd

from agri_sfincs import config, domain, region, usgs_ogc
from agri_sfincs.net import get

NOAA_API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
USGS_PARAMS = {
    "00060": "discharge",
    "00065": "gage height",
    "62620": "estuary elevation NAVD88",
    "63160": "stream elevation NAVD88",
    "72279": "tidal elevation",
}


def parse_years(s: str) -> list[int]:
    a, b = s.split("-")
    return list(range(int(a), int(b) + 1))


# ── NOAA ──────────────────────────────────────────────────────────────────────
def _empty() -> pd.Series:
    return pd.Series(dtype="float64", index=pd.DatetimeIndex([], name="time"))


def noaa_year(station: str, year: int) -> pd.Series:
    params = {
        "product": "hourly_height",
        "application": "sfincs-nj-agri",
        "begin_date": f"{year}0101",
        "end_date": f"{year}1231",
        "datum": "MLLW",
        "station": station,
        "time_zone": "gmt",
        "units": "metric",
        "format": "json",
    }
    j = get(NOAA_API, params, timeout=120).json()
    if "data" not in j:  # no data that year is an answer, not an error
        return _empty()
    df = pd.DataFrame(j["data"])
    v = pd.to_numeric(df["v"], errors="coerce")
    v.index = pd.to_datetime(df["t"])
    return v.dropna()


def noaa(years: list[int]) -> None:
    out = config.GAUGE_DIR / "noaa"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for st in domain.NOAA_STATIONS:
        f = out / f"{st['id']}_hourly_mllw.csv.gz"
        have = (
            pd.read_csv(f, index_col=0, parse_dates=True)["wl_m_mllw"]
            if f.exists()
            else _empty()
        )
        parts = [have]
        for y in years:
            if have.index.year.isin([y]).any():
                continue
            s = noaa_year(st["id"], y)
            print(f"  NOAA {st['id']} {st['name']:24s} {y}: {len(s):5d} h", flush=True)
            parts.append(s)
        s = pd.concat(parts).sort_index()
        s = s[~s.index.duplicated()]
        s.rename("wl_m_mllw").rename_axis("time").to_csv(f)
        for y in years:
            n_exp = 24 * (366 if pd.Timestamp(y, 12, 31).dayofyear == 366 else 365)
            rows.append(
                {
                    "id": st["id"],
                    "name": st["name"],
                    "year": y,
                    "pct": round(100 * (s.index.year == y).sum() / n_exp, 1),
                }
            )
    t = pd.DataFrame(rows).pivot(index=["id", "name"], columns="year", values="pct")
    t.to_csv(config.GAUGE_DIR / "noaa_completeness.csv")
    print(t.to_string())


# ── USGS ──────────────────────────────────────────────────────────────────────
def usgs(years: list[int]) -> None:
    ring = region.load_ring().to_crs(4326)
    w, s, e, n = ring.total_bounds
    recs = []
    for pc, what in USGS_PARAMS.items():
        rows = usgs_ogc.items(
            "time-series-metadata", bbox=f"{w},{s},{e},{n}", parameter_code=pc
        )
        for r in rows:
            recs.append({**{k: r.get(k) for k in (
                "monitoring_location_id", "parameter_code", "statistic_id",
                "computation_period_identifier", "begin", "end", "lon", "lat",
                "id")}, "what": what})  # fmt: skip
    df = pd.DataFrame(recs)
    # Keep the series a model can use: daily means and instantaneous values.
    df = df[
        df.computation_period_identifier.isin(["Daily", "Points"])
        & (df.statistic_id.isin(["00003", "00011"]))
    ]
    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    pts = pts[pts.within(ring.geometry.iloc[0])].copy()
    pts["site"] = pts.monitoring_location_id.str.removeprefix("USGS-")
    pts["known"] = pts.site.map(domain.USGS_SITES)
    meta = usgs_ogc.locations(sorted(pts.site.unique()))
    pts = pts.join(meta[["name", "drainage_area_mi2", "site_type"]], on="site")
    pts["begin"] = pts.begin.str[:10]
    pts["end"] = pts.end.str[:10]
    cols = ["site", "name", "site_type", "what", "computation_period_identifier",
            "begin", "end", "drainage_area_mi2", "lon", "lat", "known"]  # fmt: skip
    pts = pts[cols].sort_values(["site", "what"])
    pts.to_csv(config.GAUGE_DIR / "usgs_series.csv", index=False)
    print(pts.drop(columns=["lon", "lat"]).to_string(index=False))

    # Daily-mean discharge: download and measure completeness for the study years.
    out = config.GAUGE_DIR / "usgs"
    out.mkdir(parents=True, exist_ok=True)
    dv = pts[(pts.what == "discharge") & (pts.computation_period_identifier == "Daily")]
    rows = []
    for site in sorted(dv.site.unique()):
        f = out / f"{site}_dv_cfs.csv.gz"
        if f.exists():
            q = pd.read_csv(f, index_col=0, parse_dates=True)
        else:
            q = usgs_ogc.daily_mean_discharge(
                site, f"{years[0]}-01-01", f"{years[-1]}-12-31"
            )
            q.rename_axis("date").to_csv(f)
        for y in years:
            n_exp = 366 if pd.Timestamp(y, 12, 31).dayofyear == 366 else 365
            rows.append(
                {"site": site, "year": y,
                 "pct": round(100 * (q.index.year == y).sum() / n_exp, 1)}
            )  # fmt: skip
    t = pd.DataFrame(rows).pivot(index="site", columns="year", values="pct")
    t.to_csv(config.GAUGE_DIR / "usgs_dv_completeness.csv")
    print(t.to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", default="2002-2025")
    ap.add_argument("--skip-noaa", action="store_true")
    ap.add_argument("--skip-usgs", action="store_true")
    a = ap.parse_args()
    years = parse_years(a.years)
    config.GAUGE_DIR.mkdir(parents=True, exist_ok=True)
    if not a.skip_usgs:
        usgs(years)
    if not a.skip_noaa:
        noaa(years)


if __name__ == "__main__":
    main()
