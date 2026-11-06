"""Do the Delaware creeks drain to the observed low tide, or does a sill in the bed hold them up?
(STATUS Step 3, 2026-11-06: the DE creek lows run 0.3-0.4 m high at Odessa, Frederica and
Slaughter Beach and are right at Bowers; FINDINGS §61, §63, §65.)

nj_bight_sfincs's bed audit (its logs/bed_audit_2026-11-05/) is wired to its own model box (its
VDatum surface, NHD region 0203, its Sandy run), so on this bed it would find nothing. This
script asks the question behind the high lows directly instead.

Drain level of a cell = the minimax, over face paths to the open-water boundary (mask 2), of
max(subgrid ``uv_zmin``, weir crest) (``agri_sfincs.faces.spill``): the lowest level the cell
can drain to through the model's faces, however slowly. At each DE tide gauge's cell it is set
against the observed lows of every storm run on disk (after ``--spinup`` h; matched as
validate_storm_gauges.py matches them) and the model's lows at the same times:
  model low ~ drain level > observed low  -> a SILL holds the creek up. The faces on the
                                            gauge's path that are above the observed low
                                            are listed, with what set the bed there.
  drain level well below the observed low -> no sill: the creek drains too SLOWLY (too
                                            shallow, narrow or rough along its length).
Also reported: the gauge cell's own lowest subgrid bed (``z_zmin``), which the cell's level
cannot go below either.

Bed sources at a sill (sampled within +-``WIN_M`` m of the face midpoint): bed_source_de.tif
(scripts/build_bed.py codes: 1 lidar, 2 CUDEM under lidar, 3 CUDEM, 4 3DEP, 5 GMRT; the DE
lidar is hydro-flattened, so a code-1 creek carries its WATER SURFACE unless burned) and
riverbed_source_<bed tag>.tif (scripts/build_riverbeds.py codes, 0 = not burned).

Writes reports/de_creek_drain_<model>.md, reports/figs/de_creek_drain_<model>.png and
data/analysis/de_creek_drain_<model>.gpkg (layers ``path``: every face on each gauge's path;
``sills``).
Usage:  python scripts/check_de_creek_drain.py [--model de_v2ap45o_100m] [--bed-tag de_v2ap45] [--spinup 24]
"""

from __future__ import annotations

import argparse
import re

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
import xarray as xr  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

from agri_sfincs import config, dikes, domain, waterlevel  # noqa: E402
from agri_sfincs.faces import path_faces, spill, uv_links, weir_on_faces  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

#: DE tidal gauges on NAVD88, site -> (name, USGS parameter); the same as
#: validate_storm_gauges.DE_GAUGES (scripts never import scripts)
DE_GAUGES = {"01483158": ("Odessa (Appoquinimink)", "62620"), "01484085": ("Bowers (Murderkill)", "00065"),
             "01484080": ("Frederica (Murderkill)", "62620"), "01484235": ("Slaughter Beach (Cedar Cr.)", "62620")}  # fmt: skip
WIN_M = 30.0
RUN_RE = re.compile(r"^(?P<storm>[a-z]+\d{4}[a-z]*)_intact_slr000_(era5|hrrr)$")
BLUE, ORANGE, INK, MUTED, RED = "#2a78d6", "#eb6834", "#222222", "#6b6b6b", "#c8102e"


def gauge_cell(x: float, y: float, cx, cy, size, active) -> int:
    """The active cell whose square contains (x, y); else the nearest active centre."""
    inside = (np.abs(cx - x) <= size / 2) & (np.abs(cy - y) <= size / 2) & active
    if inside.any():
        return int(np.flatnonzero(inside)[0])
    d = np.hypot(cx - x, cy - y)
    d[~active] = np.inf
    return int(np.argmin(d))


def lows(root, site: str, param: str, spinup_h: float) -> pd.DataFrame:
    """Observed and model lows at ``site`` over every DE storm run on disk with an observed record."""
    from agri_sfincs.events import EVENTS

    out = []
    for rd in sorted((root / "runs").iterdir()):
        m = RUN_RE.match(rd.name)
        if not m or not (rd / "sfincs_his.nc").exists() or m["storm"] not in EVENTS:
            continue
        o = waterlevel.usgs_event_series(m["storm"], site, param)
        if o is None:
            continue
        o = o[pd.Timestamp(EVENTS[m["storm"]].tstart) + pd.Timedelta(hours=spinup_h) :]
        mt = waterlevel.gauge_series(rd, f"usgs_{site}", "de")[0]
        d = waterlevel.match_extremes(o, mt, lows=True)
        if len(d):
            out.append(d.assign(storm=m["storm"]))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["obs_m", "model_m", "storm"])


class Sampler:
    """Window statistics of the bed rasters (EPSG:4326) around UTM points."""

    def __init__(self, tag: str):
        e = config.ELEV_DIR
        self.paths = {"merged": e / "bed_merged_de.tif", "src": e / "bed_source_de.tif",
                      "burn": e / f"riverbed_burn_{tag}.tif", "burn_src": e / f"riverbed_source_{tag}.tif"}  # fmt: skip
        self.to_ll = Transformer.from_crs(domain.EPSG, 4326, always_xy=True).transform

    def at(self, x: float, y: float) -> dict:
        lon0, lat0 = self.to_ll(x - WIN_M, y - WIN_M)
        lon1, lat1 = self.to_ll(x + WIN_M, y + WIN_M)
        r = {}
        for k, p in self.paths.items():
            if not p.exists():
                r[k] = np.nan
                continue
            with rasterio.open(p) as s:
                a = s.read(1, window=from_bounds(lon0, lat0, lon1, lat1, s.transform), boundless=True,
                           fill_value=s.nodata if s.nodata is not None else 0).astype(float)  # fmt: skip
                if s.nodata is not None and k in ("merged", "burn"):
                    a[a == s.nodata] = np.nan
            if k in ("src", "burn_src"):
                v, c = np.unique(a[np.isfinite(a)].astype(int), return_counts=True)
                r[k] = ",".join(f"{int(i)}:{n / c.sum():.0%}" for i, n in sorted(zip(v, c), key=lambda t: -t[1])[:3])
            else:
                r[k] = float(np.nanmin(a)) if np.isfinite(a).any() else np.nan
        return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default="de_v2ap45o_100m")
    ap.add_argument("--bed-tag", default="de_v2ap45", help="riverbed_burn_<tag>.tif / riverbed_source_<tag>.tif")
    ap.add_argument("--spinup", type=float, default=24.0)
    a = ap.parse_args()
    root = config.MODELS / a.model

    g = xr.open_dataset(root / "sfincs.nc")
    sg = xr.open_dataset(root / "sfincs_subgrid.nc")
    cx, cy = g["mesh2d_face_x"].values, g["mesh2d_face_y"].values
    mask = g["mask"].values
    size = float(g.attrs["dx"]) / 2.0 ** (g["level"].values - 1)
    nm, nmu = uv_links(g)
    assert len(nm) == sg.sizes["npuv"], (len(nm), sg.sizes["npuv"])
    uvz = sg["uv_zmin"].values.astype(float)
    on = (mask[nm] > 0) & (mask[nmu] > 0)
    uvz[~on] = np.inf
    crest = weir_on_faces(dikes.read_weir(root / "sfincs.weir"), cx[nm], cy[nm], cx[nmu], cy[nmu])
    cost = np.fmax(uvz, np.nan_to_num(crest, nan=-np.inf))
    lvl, par = spill(len(cx), nm, nmu, cost, np.flatnonzero(mask == 2))
    print(f"{len(cx)} cells, {len(nm)} faces, {np.isfinite(crest).sum()} weir faces; drain levels done")

    with xr.open_dataset(next((root / "runs").glob("*_intact_slr000_hrrr")) / "sfincs_his.nc") as h:
        names = [s.strip() for s in h["station_name"].values.astype(str)]
        pos = {n: (float(h["station_x"][i]), float(h["station_y"][i])) for i, n in enumerate(names)}

    smp = Sampler(a.bed_tag)
    to_ll = Transformer.from_crs(domain.EPSG, 4326, always_xy=True).transform
    rows, path_rows, sill_rows, prof = [], [], [], {}
    for site, (name, param) in DE_GAUGES.items():
        c = gauge_cell(*pos[f"usgs_{site}"], cx, cy, size, mask > 0)
        lw = lows(root, site, param, a.spinup)
        obs_low, mod_low = float(lw.obs_m.median()), float(lw.model_m.median())
        fs = path_faces(c, par, nm, nmu)
        fx, fy = (cx[nm[fs]] + cx[nmu[fs]]) / 2, (cy[nm[fs]] + cy[nmu[fs]]) / 2
        dist = np.r_[0.0, np.cumsum(np.hypot(np.diff(fx), np.diff(fy)))] + np.hypot(fx[0] - cx[c], fy[0] - cy[c])
        fc = cost[fs]
        prof[name] = (dist, fc, obs_low, mod_low, float(lvl[c]), float(sg["z_zmin"].values[c]))
        for k, f in enumerate(fs):
            path_rows.append({"gauge": name, "order": k, "dist_m": dist[k], "cost": fc[k], "weir": bool(np.isfinite(crest[f])),
                              "geometry": shapely.LineString([(cx[nm[f]], cy[nm[f]]), (cx[nmu[f]], cy[nmu[f]])])})  # fmt: skip
        above = fc > obs_low
        # contiguous stretches of the path above the observed low = sills
        edges = np.flatnonzero(np.diff(np.r_[0, above.astype(int), 0]))
        for s0, s1 in zip(edges[::2], edges[1::2]):
            k = s0 + int(np.argmax(fc[s0:s1]))
            lon, lat = to_ll(fx[k], fy[k])
            sill_rows.append({"gauge": name, "from gauge km": dist[s0] / 1e3, "length m": dist[s1 - 1] - dist[s0] + size[c],
                              "crest m": fc[k], "above obs low m": fc[k] - obs_low, "weir": bool(np.isfinite(crest[fs[k]])),
                              "lon": lon, "lat": lat, **{f"bed {kk}": v for kk, v in smp.at(fx[k], fy[k]).items()},
                              "geometry": shapely.Point(fx[k], fy[k])})  # fmt: skip
        rows.append({"gauge": name, "lows matched": len(lw), "storms": lw.storm.nunique(),
                     "obs low (median)": obs_low, "model low (median)": mod_low, "model - obs": mod_low - obs_low,
                     "drain level": float(lvl[c]), "drain - obs low": float(lvl[c]) - obs_low,
                     "cell z_zmin": float(sg["z_zmin"].values[c]), "path km": dist[-1] / 1e3 if len(dist) else 0.0,
                     "sills above obs low": int(sum(1 for r in sill_rows if r["gauge"] == name))})  # fmt: skip

    df = pd.DataFrame(rows)
    sills = gpd.GeoDataFrame(sill_rows, crs=domain.EPSG) if sill_rows else gpd.GeoDataFrame(columns=["gauge"], geometry=[], crs=domain.EPSG)  # fmt: skip
    out = config.ANALYSIS_DIR / f"de_creek_drain_{a.model}.gpkg"
    gpd.GeoDataFrame(path_rows, crs=domain.EPSG).to_file(out, layer="path")
    if len(sills):
        sills.to_file(out, layer="sills")

    fig, axs = plt.subplots(len(prof), 1, figsize=(8, 2.4 * len(prof)), sharex=False)
    for ax, (name, (dist, fc, ol, ml, dl, zc)) in zip(np.atleast_1d(axs), prof.items()):
        ax.step(dist / 1e3, fc, where="mid", color=INK, lw=1, label="face bed (uv_zmin / weir crest)")
        ax.axhline(ol, color=BLUE, lw=1.2, label=f"observed low (median) {ol:+.2f}")
        ax.axhline(ml, color=ORANGE, lw=1.2, label=f"model low (median) {ml:+.2f}")
        ax.axhline(dl, color=RED, lw=1, ls="--", label=f"drain level {dl:+.2f}")
        ax.set_ylim(min(dl, ol) - 5.0, max(ml, ol) + 1.0)  # the creek, not the bay's shipping channel
        ax.set_title(name, loc="left", fontsize=10, color=INK)
        ax.set_ylabel("m NAVD88")
        ax.legend(fontsize=7, loc="lower right", frameon=True, framealpha=0.9)
        ax.grid(alpha=0.2)
    np.atleast_1d(axs)[-1].set_xlabel("distance along the drain path from the gauge to the open-water boundary (km)")
    fig.tight_layout()
    figp = config.REPORTS / "figs" / f"de_creek_drain_{a.model}.png"
    fig.savefig(figp, dpi=130)

    show_s = [c for c in sills.columns if c != "geometry"]
    rep = config.REPORTS / f"de_creek_drain_{a.model}.md"
    rep.write_text(
        f"# Do the Delaware creeks drain to the observed low tide? `{a.model}`\n\n"
        f"Written by `scripts/check_de_creek_drain.py --model {a.model} --bed-tag {a.bed_tag} --spinup {a.spinup:g}`. "
        "Drain level = the lowest level the gauge's cell can drain to through the model's faces (minimax of subgrid "
        "`uv_zmin` / weir crest over paths to the open boundary). Lows: every observed low of the storm runs on disk "
        "(`<storm>_intact_slr000_<wind>`) matched with the model's, medians. m NAVD88.\n\n"
        "Reading: model low near the drain level and both above the observed low = a sill holds the creek up; drain "
        "level well below the observed low = no sill, the creek drains too slowly.\n\n"
        + md_table(df.round(2)) + "\n\n## Faces on each path above the observed low\n\n"
        "Bed codes, share of pixels within ±30 m: `bed src` (build_bed: 1 lidar, hydro-flattened; 2 CUDEM under lidar; "
        "3 CUDEM; 4 3DEP; 5 GMRT), `bed burn_src` (build_riverbeds, 0 = not burned); `bed merged` / `bed burn` = the "
        "lowest pre-burn / burned pixel there.\n\n"
        + (md_table(pd.DataFrame(sills[show_s]).round(3)) if len(sills) else "(none)")
        + f"\n\n![](figs/{figp.name})\n")  # fmt: skip
    print(df.round(2).to_string(index=False))
    if len(sills):
        print(pd.DataFrame(sills[show_s]).round(2).to_string(index=False))
    print(f"wrote {rep}, {figp}, {out}")


if __name__ == "__main__":
    main()
