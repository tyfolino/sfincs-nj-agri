"""How well does the sandy2012 run (dikes as built, today's sea level) match what Sandy did?

Two checks, because USGS surveyed no Sandy high-water marks on the NJ bayshore (STN event 24
has 4 marks inside the ring, all on the Delaware at Chester, PA):
  * high tides at the two interior tidal gauges, Maurice River at Bivalve (01412150) and
    Cohansey River at Greenwich (01413038): every observed high (6-min, ft -> m NAVD88) vs the
    model's highest level within +-3 h. Both gauges are out from Oct 29 04:00 to Oct 31 04:00
    UTC, so Sandy's two peak tides themselves are not observed;
  * the FEMA MOTF Sandy surge extent (read in place from nj_bight_sfincs,
    `validation_v4/sandy_motf_extent_v4.tif`, 15 m, with its NJ-valid mask). MOTF is a water
    surface interpolated from HWMs and sensors over lidar: a bathtub with no dikes. So it is a
    check where nothing blocks the water, and behind dikes it shows what a bathtub would say.
    Compared on 10 m subgrid pixels: model wet = peak depth over the run > runs.THRESH.

Observations come from data/gauges/usgs_events/sandy2012/ (fetch_usgs_event.py --event sandy2012).

Writes reports/sandy_validation.md. Usage:  python scripts/validate_sandy.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.features import rasterize
from scipy.signal import find_peaks

from agri_sfincs import config, domain, fieldflood, region, runs
from agri_sfincs.report import md_table

RUN = runs.run_dir("sandy2012", "intact", 0)
GAUGES = {"01412150": "Maurice River at Bivalve", "01413038": "Cohansey River at Greenwich"}
MOTF = config.BIGHT_DATA / "validation_v4" / "sandy_motf_extent_v4.tif"
MOTF_VALID = config.BIGHT_DATA / "validation_v4" / "sandy_motf_valid_nj_v4.tif"
FIELDS = config.ANALYSIS_DIR / "field_flood_classes"
FT = 0.3048
PX_KM2 = 1e-4  # one 10 m pixel


def gauge_highs() -> pd.DataFrame:
    """Every observed high tide 2012-10-20 .. 11-04 vs the model's max within +-3 h."""
    with xr.open_dataset(RUN / "sfincs_his.nc") as h:
        names = [s.strip() for s in h["station_name"].values.astype(str)]
        zs = {n: h["point_zs"].isel(stations=i).to_series() for i, n in enumerate(names)}
    rows = []
    for site, name in GAUGES.items():
        o = pd.read_csv(config.GAUGE_DIR / "usgs_events" / "sandy2012" / f"{site}_72279.csv",
                        parse_dates=["time"]).set_index("time")["value"] * FT  # fmt: skip
        o.index = o.index.tz_convert(None) if o.index.tz is not None else o.index
        o = o["2012-10-20":"2012-11-04"]
        m = zs[f"usgs_{site}"]
        for p in find_peaks(o.values, distance=80)[0]:  # ~8 h apart at 6 min
            t = o.index[p]
            mw = m[t - pd.Timedelta("3h") : t + pd.Timedelta("3h")]
            if len(mw):
                rows.append({"gauge": name, "time": t, "obs_m": o.iloc[p], "model_m": float(mw.max())})
    d = pd.DataFrame(rows)
    d["diff_m"] = d.model_m - d.obs_m
    return d


def peak_from_ship_john(hi: pd.DataFrame) -> pd.DataFrame:
    """Each interior gauge's Sandy peak estimated as Ship John's observed peak plus the gauge's
    offset from Ship John on the two highest tides before the gap (gauge high - Ship John's
    hourly max within +-2 h)."""
    with xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc") as ds:
        sj = ds["waterlevel"].sel(stations=domain.SHIP_JOHN).to_series()["2012-10-20":"2012-11-04"]
    rows = {}
    for name in GAUGES.values():
        top = hi[(hi.gauge == name) & (hi.time < "2012-10-29 06:00")].nlargest(2, "obs_m")
        off = [o - sj[t - pd.Timedelta("2h") : t + pd.Timedelta("2h")].max() for t, o in zip(top.time, top.obs_m)]
        rows[name] = {"offset from Ship John, m": float(np.mean(off)),
                      "estimated peak, m": float(sj.max() + np.mean(off))}  # fmt: skip
    return pd.DataFrame(rows).T


def motf_edge_level() -> pd.DataFrame:
    """Ground height (10 m subgrid) under the MOTF flood edge, by 10 km band of northing: the
    water level MOTF implies."""
    with rasterio.open(MOTF) as r:
        w, t = r.read(1) == 1, r.transform
    edge = w & ~(np.roll(w, 1, 0) & np.roll(w, -1, 0) & np.roll(w, 1, 1) & np.roll(w, -1, 1))
    rr, cc = np.nonzero(edge)
    x, y = runs.pixel_centres(t, rr, cc)
    with rasterio.open(runs.subgrid_dep()) as d:
        dep, tr = d.read(1, masked=True).filled(np.nan), d.transform
    r2, c2 = np.floor((y - tr.f) / tr.e).astype(np.int64), np.floor((x - tr.c) / tr.a).astype(np.int64)
    ok = (r2 >= 0) & (r2 < dep.shape[0]) & (c2 >= 0) & (c2 < dep.shape[1])
    d = pd.DataFrame({"y": y[ok], "z": dep[r2[ok], c2[ok]]}).dropna()
    d = d[(d.z > 0.5) & (d.z < 8)]  # off the water and the uplands' rendering noise
    d["northing, km"] = (d.y // 10000 * 10).astype(int)
    return d.groupby("northing, km").z.describe(percentiles=[0.25, 0.5, 0.75])[["count", "25%", "50%", "75%"]]


def motf_at(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """MOTF flooded (bool) and NJ-valid (bool) at points x, y (EPSG:32618)."""
    out = []
    for f in (MOTF, MOTF_VALID):
        with rasterio.open(f) as r:
            assert r.crs.to_epsg() == 32618
            a = r.read(1)
            t = r.transform
            rr = np.floor((y - t.f) / t.e).astype(np.int64)
            cc = np.floor((x - t.c) / t.a).astype(np.int64)
            ok = (rr >= 0) & (rr < r.height) & (cc >= 0) & (cc < r.width)
            v = np.zeros(len(x), bool)
            v[ok] = a[rr[ok], cc[ok]] == 1
            out.append(v)
    return out[0], out[1]


def main() -> None:
    hi = gauge_highs()

    with rasterio.open(runs.subgrid_dep()) as d:
        dep = d.read(1, masked=True).filled(np.nan)
        tr, shape, crs = d.transform, d.shape, d.crs
    g = gpd.read_file(FIELDS.with_suffix(".gpkg"))[["field_id", "geometry"]].to_crs(crs)
    attrs = pd.read_csv(FIELDS.with_suffix(".csv"), usecols=["field_id", "behind_levee"]).set_index("field_id")
    ids = rasterize(zip(g.geometry, g.field_id), out_shape=shape, transform=tr, fill=0, dtype="uint32")
    ring = rasterize([(region.load_ring().to_crs(crs).union_all(), 1)], out_shape=shape, transform=tr, dtype="uint8")
    # pixels to score: all ground 0-3 m NAVD88 in the ring (the tidal fringe) plus every field pixel
    sel = ((ring == 1) & (dep >= 0) & (dep <= 3)) | (ids > 0)
    rr, cc = np.nonzero(sel)
    del sel, ring
    x, y = runs.pixel_centres(tr, rr, cc)
    z, fid = dep[rr, cc], ids[rr, cc].astype(np.int64)
    del dep, ids
    with xr.open_dataset(RUN / "sfincs_map.nc") as mp:
        grid = runs.MapGrid.from_map(mp)
        zmax = mp["zsmax"].max("timemax").values.ravel()
    face = grid.face(x, y)
    ok = (face >= 0) & np.isfinite(z)
    x, y, z, fid, face = x[ok], y[ok], z[ok], fid[ok], face[ok]
    h = zmax[face] - z
    wet = np.isfinite(h) & (h > runs.THRESH)
    motf, valid = motf_at(x, y)
    keep = valid
    x, z, fid, wet, motf = x[keep], z[keep], fid[keep], wet[keep], motf[keep]

    lev = np.zeros(len(fid), bool)
    inf = fid > 0
    lev[inf] = attrs.behind_levee.reindex(fid[inf]).fillna(False).values.astype(bool)

    def table(mask) -> dict:
        w, m = wet[mask], motf[mask]
        both, mo, mod = (w & m).sum(), (m & ~w).sum(), (w & ~m).sum()
        return {"km² scored": mask.sum() * PX_KM2, "wet in both": both * PX_KM2,
                "MOTF only": mo * PX_KM2, "model only": mod * PX_KM2,
                "agree (of either wet)": both / max(both + mo + mod, 1)}  # fmt: skip

    groups = {
        "ground 0-3 m NAVD88, not a field": (fid == 0) & (z >= 0) & (z <= 3),
        "farm fields, open to the tide": inf & ~lev,
        "farm fields, behind an NLD levee": inf & lev,
    }
    px = pd.DataFrame({k: table(v) for k, v in groups.items()}).T

    # per field: flooded = >= fieldflood.SHARE of its scored pixels wet
    f = pd.DataFrame({"fid": fid[inf], "wet": wet[inf], "motf": motf[inf]}).groupby("fid").mean()
    f["levee"] = attrs.behind_levee.reindex(f.index).fillna(False).values
    f["model"], f["MOTF"] = f.wet >= fieldflood.SHARE, f.motf >= fieldflood.SHARE
    ft = (f.groupby(["levee", "MOTF", "model"]).size().unstack(fill_value=0)
          .rename(columns={False: "model dry", True: "model flooded"}))  # fmt: skip
    ft.index = [f"{'behind levee' if lv else 'open'}, MOTF {'flooded' if m else 'dry'}" for lv, m in ft.index]

    tops = hi.sort_values("obs_m", ascending=False).groupby("gauge").head(5)
    summ = hi.groupby("gauge").agg(highs=("diff_m", "size"), mean_diff_m=("diff_m", "mean"),
                                   rmse_m=("diff_m", lambda s: float(np.sqrt((s**2).mean()))))  # fmt: skip
    summ["top5_mean_diff_m"] = tops.groupby("gauge").diff_m.mean()
    pk = peak_from_ship_john(hi)
    pk["highest observed (before the gap), m"] = [hi[hi.gauge == n].obs_m.max() for n in pk.index]
    with xr.open_dataset(RUN / "sfincs_his.nc") as hh:
        names = [s.strip() for s in hh["station_name"].values.astype(str)]
        mpk = {GAUGES[s]: float(hh["point_zs"].isel(stations=names.index(f"usgs_{s}")).max()) for s in GAUGES}
    pk["model peak, m"] = pd.Series(mpk)
    edge = motf_edge_level()

    lines = [
        "# Sandy (2012) run vs observations",
        "",
        f"Run: `{RUN.parent.parent.name}/runs/{RUN.name}` (dikes as built, today's sea level, tide only). "
        "Written by `scripts/validate_sandy.py`.",
        "",
        "## High tides at the interior gauges",
        "",
        "Each observed high tide (Oct 20 - Nov 4) vs the model's highest level within 3 h. "
        "**Both gauges are out from Oct 29 04:00 to Oct 31 04:00 UTC**, so Sandy's two peak tides "
        "are not observed: the highest recorded tide is the one before the gap.",
        "",
        md_table(summ.round(3)),
        "",
        "Sandy's peak itself, estimated from Ship John Shoal (observed peak "
        "1.90 m NAVD88, Oct 30 04:00 UTC) plus each gauge's offset from Ship John on the two highest "
        "tides before the gap:",
        "",
        md_table(pk.round(2)),
        "",
        "## Flood footprint vs FEMA MOTF",
        "",
        "MOTF interpolates a water surface from high-water marks over lidar, with no dikes: it is a "
        "check where nothing blocks the water; behind levees it is what a bathtub map would show. "
        f"Model wet = peak depth > {runs.THRESH} m on 10 m pixels; MOTF's NJ-valid area only.",
        "",
        md_table(px, floatfmt="{:,.2f}"),
        "",
        f"Per field (flooded = at least {fieldflood.SHARE:.0%} of the field wet):",
        "",
        md_table(ft),
        "",
        "The water level MOTF implies: ground height under its flood edge (m NAVD88), by 10 km band "
        "of UTM northing (4,340 = Bivalve, 4,370 = Greenwich, 4,400 = Gloucester's river front). A flat "
        "surface near the bay peak, carried up the creeks:",
        "",
        md_table(edge, floatfmt="{:,.2f}"),
        "",
    ]
    out = config.REPORTS / "sandy_validation.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
