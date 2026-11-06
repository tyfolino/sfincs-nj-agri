"""Are the dike leak routes of check_dike_seal.py (FINDINGS §66) real on the ground, or model artefacts?
(STATUS plan check, 2026-11-06.)

check_dike_seal.py finds the lowest bay level that can reach each farm system's leveed area through the
model's faces, with every weir face closed (`wall`). A face there costs its subgrid ``uv_zmin``: it opens
once ANY strip of it is wet, so a pond or ditch on one side of a road opens the face although the road
runs right across it. This script asks the same question with the lidar's ridges put back:

  lidar face crest  per face near the 18 systems (midpoint within ``PAD_M`` of a leveed area), from the NJ
                    10 ft (3 m) lidar DEM read in place (``config.BIGHT_DATA``): the lowest level at which
                    lidar ground at or below it connects the two cells across the face, inside their joint
                    footprint (``face_crest``). A ridge or road right across the face raises it; a creek that
                    crosses the face at any angle keeps it low (a straight along-the-link maximum does not:
                    it seals diagonal creeks).
  wall + lidar      check_dike_seal's `wall` spill again (seeds = the model's water-level boundary, every weir
                    face closed), each other face costing max(uv_zmin, lidar face crest).
  model route       the model's own path (wall) into the cell at the median spill (the bulk of the interior):
                    the highest lidar face crest on it, i.e. the level at which THAT route opens on the ground.

Read: if wall + lidar reaches the system at about the model's level, the opening is on the ground (a gap,
a low road, a ditch or creek, or a gate, which the lidar cannot tell from a gap); if it is clearly higher,
the model's route goes over ground the lidar shows high (artefact) and the new level is where the
next route opens. Lidar limits: it cannot see culverts, pipes and gates (it can seal what really drains or
leaks), a narrow crest is smoothed at 3 m, and hydro-flattened water can cut a bank at a bridge or gate.
The `wall + lidar` route's bottleneck is located and set against the model's gates (sfincs.drn) and the NLD
pipe gates; NAIP 2023 chips (Planetary Computer, ``agri_sfincs.naip``) at it are for the eye.

Also: pieces of data/structures/dikes.weir the model dropped (open_creek_links.py, FINDINGS §40), within
300 m of a system: their lidar crest (highest pixel within +-20 m, every 5 m), relative to MHHW.

Writes data/analysis/dike_leaks_<model>.csv, reports/dike_leaks_<model>.md and, for ``--figs`` systems
(default: the priority four), reports/figs/dike_leak_<slug>.png.
Usage:  python scripts/check_dike_leaks.py [--model e3v2a30brm65_100m] [--inset 50] [--no-naip]
"""

from __future__ import annotations

import argparse
import re
import warnings

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
import xarray as xr  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402
from scipy import ndimage  # noqa: E402

from agri_sfincs import config, dikes, domain, exposure  # noqa: E402
from agri_sfincs.faces import bottleneck, path_faces, spill, uv_links, weir_on_faces  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

LIDAR = config.BIGHT_DATA / "elevation_v4/nj_10ft_dem_v4.tif"
PAD_M = 1500.0  # faces this close to a leveed area get a lidar crest
STEP_PX = 3.0  # m, lidar sample spacing in a face footprint
DROP_MIN_M = 2.0  # weir vertices are 5 m apart; open_creek_links drops single segments
PRIORITY = ["Gibbstown", "Richard Wood", "Middle Neck", "Henby Creek"]
ABOVE = (0.0, 0.3, 0.6, 1.0)

TO_LL = Transformer.from_crs(domain.EPSG, 4326, always_xy=True).transform


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


class Dem:
    """A window of the lidar (geographic grid), sampled at UTM points."""

    def __init__(self, src, bounds_utm):
        x0, y0, x1, y1 = bounds_utm
        lon, lat = TO_LL(np.array([x0, x1, x0, x1]), np.array([y0, y0, y1, y1]))
        w = from_bounds(min(lon), min(lat), max(lon), max(lat), src.transform).round_offsets().round_lengths()
        self.tr = src.window_transform(w)
        z = src.read(1, window=w, masked=True)
        self.z = np.where(np.ma.getmaskarray(z) | (z.data < -100), np.nan, z.data).astype("float64")

    def sample(self, x, y) -> np.ndarray:
        lo, la = TO_LL(np.asarray(x, float), np.asarray(y, float))
        c, r = ~self.tr * (lo, la)
        r, c = np.floor(r).astype(int), np.floor(c).astype(int)
        ok = (r >= 0) & (r < self.z.shape[0]) & (c >= 0) & (c < self.z.shape[1])
        out = np.full(np.shape(r), np.nan)
        out[ok] = self.z[r[ok], c[ok]]
        return out


def face_crest(dem, ax, ay, bx, by, da, db) -> float:
    """The lowest level at which lidar ground connects cell A to cell B across their face: within the two
    cells' footprint (a frame along the link: A from its far side to the face, B from the face to its far
    side, as wide as the smaller cell), the lowest L such that the pixels at or below L (4-connected,
    sampled every 3 m) join a pixel in A to one in B. Bisection to 1 cm. Lidar NoData counts as water."""
    L = np.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    mx, my = (ax + bx) / 2, (ay + by) / 2
    u = np.arange(-L / 2 - da / 2 + 1.5, L / 2 + db / 2, STEP_PX)
    w = min(da, db)
    v = np.arange(-w / 2 + 1.5, w / 2, STEP_PX)
    U, V = np.meshgrid(u, v)
    z = dem.sample(mx + ux * U - uy * V, my + uy * U + ux * V)
    if np.isnan(z).all():
        return np.nan
    z = np.nan_to_num(z, nan=-10.0)
    side_a, side_b = U < 0, U >= 0

    def joins(level):
        lab, _ = ndimage.label(z <= level)
        la_, lb_ = np.unique(lab[side_a & (lab > 0)]), np.unique(lab[side_b & (lab > 0)])
        return bool(np.intersect1d(la_, lb_).size)

    lo, hi = max(z[side_a].min(), z[side_b].min()) - 0.01, z.max()
    if joins(lo):
        return float(lo)
    while hi - lo > 0.01:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if joins(mid) else (mid, hi)
    return float(hi)


def ridge(dem, line: shapely.LineString, step=dikes.STEP_M, half=dikes.RIDGE_HALF_M) -> np.ndarray:
    """Lidar crest along ``line``: the highest pixel within +-half m across it, every step m."""
    out = []
    for s in np.linspace(0, line.length, max(int(line.length / step), 1) + 1):
        p = line.interpolate(s)
        q, o = line.interpolate(min(s + 1.0, line.length)), line.interpolate(max(s - 1.0, 0.0))
        dx, dy = q.x - o.x, q.y - o.y
        n = np.hypot(dx, dy) or 1.0
        t = np.arange(-half, half + 0.1, 2.0)
        out.append(np.nanmax(np.r_[dem.sample(p.x - dy / n * t, p.y + dx / n * t), -np.inf]))
    return np.array(out)


def dropped_pieces(pre, model) -> list[shapely.LineString]:
    keep = shapely.MultiLineString([np.c_[x, y] for _, x, y, _ in model]).buffer(0.5)
    out = []
    for _, x, y, _ in pre:
        d = shapely.LineString(np.c_[x, y]).difference(keep)
        out += [g for g in getattr(d, "geoms", [d]) if isinstance(g, shapely.LineString) and g.length >= DROP_MIN_M]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="e3v2a30brm65_100m")
    ap.add_argument("--inset", type=float, default=50.0)
    ap.add_argument("--figs", nargs="*", default=PRIORITY)
    ap.add_argument("--no-naip", action="store_true")
    a = ap.parse_args()
    root = config.MODELS / a.model

    # the model's face graph, as check_dike_seal.py
    g = xr.open_dataset(root / "sfincs.nc")
    sg = xr.open_dataset(root / "sfincs_subgrid.nc")
    cx, cy = g["mesh2d_face_x"].values, g["mesh2d_face_y"].values
    mask = g["mask"].values
    dx = float(g.attrs["dx"]) / 2.0 ** (g["level"].values - 1)
    nm, nmu = uv_links(g)
    uvz = sg["uv_zmin"].values.astype(float)
    uvz[~((mask[nm] > 0) & (mask[nmu] > 0))] = np.inf
    seeds = np.flatnonzero(mask == 2)
    model_lines = dikes.read_weir(root / "sfincs.weir")
    crest = weir_on_faces(model_lines, cx[nm], cy[nm], cx[nmu], cy[nmu])
    wall = np.where(np.isfinite(crest), np.inf, uvz)

    seal = pd.read_csv(config.ANALYSIS_DIR / f"dike_seal_{a.model}.csv").set_index("system")
    leak = gpd.read_file(config.ANALYSIS_DIR / f"dike_seal_{a.model}.gpkg", layer="leak_faces").set_index("system")
    la = dikes.leveed_areas(crs=domain.EPSG)
    la = la[la.SYSTEM_NAME.isin(seal.index)].dissolve("SYSTEM_NAME")
    st = exposure.high_water_stations("nj")
    mhhw = exposure.idw(st, "mhhw", cx, cy, domain.EPSG)

    # lidar crest on every open face near a system
    fx, fy = (cx[nm] + cx[nmu]) / 2, (cy[nm] + cy[nmu]) / 2
    near = shapely.contains_xy(la.geometry.buffer(PAD_M).union_all(), fx, fy) & np.isfinite(wall)
    lid = np.full(len(nm), np.nan)
    with rasterio.open(LIDAR) as src:
        for name, r in la.iterrows():
            box = r.geometry.buffer(PAD_M + 200).bounds
            sel = np.flatnonzero(near & np.isnan(lid) & (fx >= box[0]) & (fx <= box[2]) & (fy >= box[1]) & (fy <= box[3]))
            dem = Dem(src, box)
            for f in sel:
                lid[f] = face_crest(dem, cx[nm[f]], cy[nm[f]], cx[nmu[f]], cy[nmu[f]], dx[nm[f]], dx[nmu[f]])
            print(f"{name}: {len(sel)} faces", flush=True)
    wall_lid = np.where(np.isfinite(lid), np.fmax(wall, lid), wall)
    res = {"wall": spill(len(cx), nm, nmu, wall, seeds), "wall+lidar": spill(len(cx), nm, nmu, wall_lid, seeds)}
    print("spills done", flush=True)

    drops = dropped_pieces(dikes.read_weir(config.STRUCT_DIR / "dikes.weir"), model_lines)
    drn = np.loadtxt(root / "sfincs.drn", usecols=(0, 1, 2, 3))
    gates = shapely.points(np.r_[drn[:, :2], drn[:, 2:4]])
    pipe = gpd.read_file(config.STRUCTURES, layer="nld_pipe_gates").to_crs(domain.EPSG).geometry.values
    weirs = shapely.MultiLineString([np.c_[x, y] for _, x, y, _ in model_lines])
    cells = gpd.GeoDataFrame(geometry=gpd.points_from_xy(cx, cy), crs=domain.EPSG)

    naip = None
    if not a.no_naip:
        try:
            from agri_sfincs import naip as naip_mod

            naip = (naip_mod, naip_mod.http_json(naip_mod.SAS)["token"])
        except Exception as e:  # noqa: BLE001
            print(f"NAIP off: {e}")

    rows = []
    with rasterio.open(LIDAR) as src:
        for name, r in la.iterrows():
            idx = cells.sindex.query(r.geometry.buffer(-a.inset), predicate="contains")
            if not len(idx):
                continue
            ha = dx[idx] ** 2 / 1e4
            m = mhhw[idx]
            row = {"system": name, "interior ha": ha.sum(), "MHHW": float(np.median(m)),
                   "model leak kind": seal.loc[name, "leak kind"]}  # fmt: skip
            for k, (lvl, _) in res.items():
                rel = lvl[idx] - m
                row[f"{k} spill median"] = float(np.median(rel))
                for d in ABOVE:
                    row[f"{k} ha @+{d:.1f}"] = float(ha[rel <= d].sum())
            # the model's own route into the median cell, on the lidar
            lvl, par = res["wall"]
            i = idx[np.argsort(lvl[idx])[len(idx) // 2]]
            pf = path_faces(i, par, nm, nmu)
            on_lid = np.fmax(wall[pf], np.nan_to_num(lid[pf], nan=-np.inf))
            row["model route on lidar"] = float(on_lid.max() - mhhw[i])
            fb = pf[int(np.argmax(on_lid))]
            row["model route lidar bottleneck x"], row["model route lidar bottleneck y"] = fx[fb], fy[fb]
            row["model leak face lidar crest"] = np.nan
            lf = leak.loc[name].geometry
            (ax_, ay_), (bx_, by_) = lf.coords
            k = np.flatnonzero(np.isclose(fx, (ax_ + bx_) / 2) & np.isclose(fy, (ay_ + by_) / 2))
            if len(k):
                row["model leak face lidar crest"] = float(lid[k[0]] - mhhw[i])
            # where wall + lidar gets in
            lvl2, par2 = res["wall+lidar"]
            i2 = idx[np.argsort(lvl2[idx])[len(idx) // 2]]
            if np.isfinite(lvl2[i2]):
                f2 = bottleneck(i2, par2, nm, nmu, wall_lid)
                p = shapely.Point(fx[f2], fy[f2])
                row.update({"lidar entry x": p.x, "lidar entry y": p.y,
                            "lidar entry uv_zmin rel MHHW": float(uvz[f2] - mhhw[i2]),
                            "lidar entry crest rel MHHW": float(lid[f2] - mhhw[i2]),
                            "lidar entry to model leak face m": float(lf.distance(p)),
                            "lidar entry to weir m": float(weirs.distance(p)),
                            "lidar entry to gate m": float(min(shapely.distance(gates, p).min(),
                                                               shapely.distance(pipe, p).min()))})  # fmt: skip
            nd = [d for d in drops if d.distance(r.geometry) <= 300.0]
            dem = None
            if nd:
                dem = Dem(src, shapely.MultiLineString([list(d.coords) for d in nd]).buffer(100).bounds)
                cr = np.concatenate([ridge(dem, d) for d in nd]) - row["MHHW"]
                row.update({"dropped m": float(sum(d.length for d in nd)), "dropped crest min": float(np.nanmin(cr)),
                            "dropped crest p50": float(np.nanmedian(cr))})  # fmt: skip
            rows.append(row)
            print(f"{name}: wall {row['wall spill median']:+.2f}, wall+lidar {row['wall+lidar spill median']:+.2f}, "
                  f"model route on lidar {row['model route on lidar']:+.2f}", flush=True)  # fmt: skip
            if name in a.figs:
                figure(src, name, r.geometry, row, model_lines, nd, lf, naip)

    df = pd.DataFrame(rows).sort_values("interior ha", ascending=False)
    out = config.ANALYSIS_DIR / f"dike_leaks_{a.model}.csv"
    df.to_csv(out, index=False)
    t1 = ["system", "interior ha", "model leak kind", "wall spill median", "model leak face lidar crest",
          "model route on lidar", "wall+lidar spill median", "lidar entry uv_zmin rel MHHW", "lidar entry crest rel MHHW",
          "lidar entry to model leak face m", "lidar entry to weir m", "lidar entry to gate m"]  # fmt: skip
    t2 = ["system"] + [f"{k} ha @+{d:.1f}" for d in ABOVE for k in ("wall", "wall+lidar")]
    t3 = ["system", "dropped m", "dropped crest min", "dropped crest p50"]
    dd = df[[c for c in t3 if c in df]].dropna(subset=["dropped m"]) if "dropped m" in df else df.iloc[:0]
    rep = config.ROOT / "reports" / f"dike_leaks_{a.model}.md"
    rep.write_text(
        f"# Dike leak routes against the lidar: `{a.model}`\n\nWritten by `scripts/check_dike_leaks.py` (method in its "
        "docstring). Levels: m relative to local MHHW. `wall`: check_dike_seal.py's spill (every weir face closed, a face "
        "opens at its subgrid uv_zmin). `wall+lidar`: the same with every other face near the systems raised to the lowest "
        "lidar ground a crossing of it must get over. `model route on lidar`: the level at which the model's own route "
        "into the bulk of the system opens on the lidar. Lidar cannot see culverts, pipes or gates.\n\n"
        "## Spill level and route\n\n" + md_table(df[[c for c in t1 if c in df]].set_index("system"), "{:,.2f}") +
        "\n\n## Interior hectares reached at MHHW + d\n\n" + md_table(df[t2].set_index("system"), "{:,.0f}") +
        "\n\n## NLD bank pieces the model dropped (open_creek_links.py): lidar crest, m rel MHHW\n\n" +
        (md_table(dd.set_index("system"), "{:,.2f}") if len(dd) else "(none)") + "\n")  # fmt: skip
    print(f"wrote {out}, {rep}")


def figure(src, name, poly, row, model_lines, drops, lf, naip) -> None:
    """Lidar ground around the system with the model's banks, the model's leak face (magenta) and where
    wall + lidar gets in (cyan); NAIP 2023 at both."""
    b = poly.buffer(400.0).bounds
    dem = Dem(src, b)
    mh = row["MHHW"]
    pts = [("model leak face", "magenta", lf.centroid.x, lf.centroid.y),
           ("wall+lidar entry", "cyan", row.get("lidar entry x"), row.get("lidar entry y"))]
    ncol = 1 + (2 if naip is not None else 0)
    fig, ax = plt.subplots(1, ncol, figsize=(5.6 * ncol, 5.6))
    ax = np.atleast_1d(ax)
    with rasterio.Env():
        im = ax[0].imshow(dem.z - mh, cmap="terrain", vmin=-1.5, vmax=1.5, origin="upper",
                          extent=rasterio.transform.array_bounds(*dem.z.shape, dem.tr)[::2] + rasterio.transform.array_bounds(*dem.z.shape, dem.tr)[1::2])  # fmt: skip
    fig.colorbar(im, ax=ax[0], shrink=0.7, label="lidar ground, m rel MHHW")
    tl = lambda x, y: TO_LL(np.asarray(x), np.asarray(y))  # noqa: E731
    gpd.GeoSeries([poly], crs=domain.EPSG).to_crs(4326).boundary.plot(ax=ax[0], color="k", lw=0.8)
    for _, x, y, _ in model_lines:
        ax[0].plot(*tl(x, y), color="#d62728", lw=1.0)
    for d in drops:
        ax[0].plot(*tl(*d.xy), color="#ff7f0e", lw=2.5)
    for _, c, x, y in pts:
        if x is not None and np.isfinite(x):
            ax[0].plot(*tl(x, y), "x", color=c, ms=12, mew=2.5)
    lo, la = TO_LL(np.array([b[0], b[2]]), np.array([b[1], b[3]]))
    ax[0].set_xlim(lo)
    ax[0].set_ylim(la)
    ax[0].set_aspect(1 / np.cos(np.radians(np.mean(la))))
    ax[0].set_xticks([])
    ax[0].set_yticks([])
    ax[0].set_title(f"{name}: wall {row['wall spill median']:+.2f}, wall+lidar {row['wall+lidar spill median']:+.2f} m "
                    f"rel MHHW\nred model banks, orange dropped, magenta model leak face, cyan wall+lidar entry", fontsize=8)  # fmt: skip
    if naip is not None:
        mod, token = naip
        for k, (title, c, x, y) in enumerate(pts):
            axk = ax[1 + k]
            axk.set_xticks([])
            axk.set_yticks([])
            if x is None or not np.isfinite(x):
                continue
            lon, lat = TO_LL(x, y)
            try:
                axk.imshow(mod.chip(mod.naip_item(lon, lat, 2023), token, lon, lat, half=200, res=1.0),
                           extent=[-200, 200, -200, 200])  # fmt: skip
                axk.plot(0, 0, "x", color=c, ms=12, mew=2.5)
            except Exception as e:  # noqa: BLE001
                axk.text(0.5, 0.5, f"NAIP failed: {e}", transform=axk.transAxes, ha="center", fontsize=7, wrap=True)
            axk.set_title(f"NAIP 2023 at the {title} (400 m square)", fontsize=9)
    fig.tight_layout()
    out = config.ROOT / "reports" / "figs" / f"dike_leak_{slug(name)}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
