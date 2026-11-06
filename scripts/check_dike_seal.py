"""Do the farm dikes seal their leveed areas in the model, or does water get round the ends?
(STATUS plan check, 2026-11-05; nj_bight_sfincs found on 2026-11-04 that none of its NLD
weirs sealed without hand tie-ins.)

Method: the lowest bay level that can reach each cell. A cell's "spill level" = the smallest,
over all face paths from the open-water boundary (mask 2), of the highest face on the path. A
face costs its subgrid ``uv_zmin`` (water crosses a face once its lowest strip is wet), raised
to the weir crest where SFINCS puts a weir on it: a weir sits on every face whose centre-to-
centre link crosses a weir segment (sfincs_quadtree.F90 ``find_uv_points_intersected_by_polyline``),
the same rule as ``agri_sfincs.dikes.drop_crossings``. Computed twice:
  wall   every weir face closed (crest = +inf): only openings count (ends that stop short of
         high ground, gaps between alignments, segments open_creek_links.py dropped)
  crest  weirs at their modelled crests: the level at which the system floods from outside
         in a slow rise; check valves are one-way out and not counted.
Also ``wall`` on the weir file before open_creek_links.py (``--pre-weir``), to name the drops.
Generous by design: ``uv_zmin`` lets a face pass once ANY strip of it is wet, so a 4 m ditch
opens a 25 m face. A low wall spill says a path exists, not how much water it carries.

Interior = cell centres inside the system's NLD leveed area shrunk by ``--inset`` m, so the
cells between the polygon edge and a bank drawn a little inside it are not counted. Levels
are read against local MHHW (``exposure.high_water_stations``, 2021-25, IDW). The leak face of
a system is the bottleneck face on the path to its interior cell at the MEDIAN wall spill (the
bulk of the interior): an "end gap" if within END_GAP_M of a weir end, else "no bank" (the
leveed area's edge there has no NLD alignment at all, e.g. a flood-fill polygon side).

The static spill says a path exists; ``--run`` (an intact run with hourly zs) says whether the
tide used it: interior hectares that got bay water (month max within 0.3 m of MHHW) and that
show a tide (median daily range > 0.2 m).

Writes data/analysis/dike_seal_<model>.csv (per system), data/analysis/dike_seal_<model>.gpkg
(layers leak_faces, interior_cells), reports/dike_seal_<model>.md.
Usage:  python scripts/check_dike_seal.py [--model e3v2a30brm65_100m] [--inset 50]
"""

from __future__ import annotations

import argparse
import heapq
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import xarray as xr

from agri_sfincs import config, dikes, domain, exposure
from agri_sfincs.report import md_table

#: the 18 farm systems of the pay-off table (FINDINGS §59)
PAYOFF = config.ANALYSIS_DIR / "restore_payoff_e3v2a30brm65_100m_hrrr.csv"
ABOVE_MHHW = (0.0, 0.3, 0.6, 1.0)
#: a leak face within END_GAP_M of a weir end is an end gap; farther, the leveed area has no bank there
END_GAP_M = 150.0
#: in the run: "bay water" = month-max zs within BAY_BELOW_MHHW of local MHHW; "tidal" = median
#: daily zs range above TIDAL_RANGE_M
BAY_BELOW_MHHW, TIDAL_RANGE_M = 0.3, 0.2


def uv_links(g: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    """(nm, nmu) per uv point, 0-based, in the subgrid file's order
    (hydromt_sfincs subgrid_quadtree_builder: per cell mu1[, mu2], then nu1[, nu2])."""
    mu, nu = g["mu"].values, g["nu"].values
    nb = {k: g[k].values.astype(np.int64) - 1 for k in ("mu1", "mu2", "nu1", "nu2")}
    nm, nmu = [], []
    for ic in range(len(mu)):
        for fine, a, b in ((mu[ic] > 0, "mu1", "mu2"), (nu[ic] > 0, "nu1", "nu2")):
            for k in (a, b) if fine else (a,):
                if nb[k][ic] >= 0:
                    nm.append(ic)
                    nmu.append(nb[k][ic])
    return np.array(nm), np.array(nmu)


def weir_on_faces(lines, x0, y0, x1, y1) -> np.ndarray:
    """Crest per face (nan = no weir): max over the weir segments its link crosses, the crest
    interpolated at the crossing."""
    segs, zc = [], []
    for _, x, y, z in lines:
        for i in range(len(x) - 1):
            segs.append(shapely.LineString([(x[i], y[i]), (x[i + 1], y[i + 1])]))
            zc.append((z[i], z[i + 1]))
    zc = np.array(zc)
    links = shapely.linestrings(np.stack([np.c_[x0, y0], np.c_[x1, y1]], axis=1))
    tree = shapely.STRtree(segs)
    li, si = tree.query(links, predicate="intersects")
    pts = shapely.intersection(links[li], np.array(segs, dtype=object)[si])
    frac = shapely.line_locate_point(np.array(segs, dtype=object)[si], shapely.centroid(pts), normalized=True)
    z = zc[si, 0] + frac * (zc[si, 1] - zc[si, 0])
    crest = np.full(len(x0), np.nan)
    np.fmax.at(crest, li, z)
    return crest


def spill(n: int, a: np.ndarray, b: np.ndarray, cost: np.ndarray, seeds: np.ndarray):
    """Minimax path from ``seeds``: (spill level per cell, parent face per cell)."""
    order = np.argsort(np.r_[a, b], kind="stable")
    nbr = np.r_[b, a][order]
    face = np.r_[np.arange(len(a)), np.arange(len(a))][order]
    ptr = np.searchsorted(np.r_[a, b][order], np.arange(n + 1))
    lvl = np.full(n, np.inf)
    par = np.full(n, -1, dtype=np.int64)
    lvl[seeds] = -np.inf
    heap = [(-np.inf, int(s)) for s in seeds]
    done = np.zeros(n, bool)
    while heap:
        v, i = heapq.heappop(heap)
        if done[i]:
            continue
        done[i] = True
        for k in range(ptr[i], ptr[i + 1]):
            j = nbr[k]
            if done[j]:
                continue
            w = max(v, cost[face[k]])
            if w < lvl[j]:
                lvl[j] = w
                par[j] = face[k]
                heapq.heappush(heap, (w, int(j)))
    return lvl, par


def bottleneck(i: int, par, a, b, cost) -> int:
    """The highest-cost face on cell ``i``'s path back to the boundary."""
    best, best_c = -1, -np.inf
    while par[i] >= 0:
        f = par[i]
        if cost[f] >= best_c:
            best, best_c = f, cost[f]
        i = a[f] if b[f] == i else b[f]
    return best


def run_stats(map_nc, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Month-max zs and median daily zs range at cells ``idx``, one hourly row at a time.

    zs is stored one time row per chunk, so reading whole rows is fast; point-indexing the
    cells across time is not (hours per system)."""
    zs = xr.open_dataset(map_nc)["zs"]
    zmax = np.full(len(idx), -np.inf)
    dmax, dmin, ranges = None, None, []
    for t in range(zs.sizes["time"]):
        z = zs.isel(time=t).values[idx]
        zmax = np.fmax(zmax, z)
        if t % 24 == 0:
            if dmax is not None:
                ranges.append(dmax - dmin)
            dmax, dmin = z.copy(), z.copy()
        else:
            dmax, dmin = np.fmax(dmax, z), np.fmin(dmin, z)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rng = np.nanmedian(np.array(ranges), axis=0)
    return zmax, rng


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default="e3v2a30brm65_100m")
    ap.add_argument("--pre-weir", default=str(config.STRUCT_DIR / "dikes.weir"))
    ap.add_argument("--inset", type=float, default=50.0)
    ap.add_argument("--run", default="tide2024oct_intact_slr000_hrrr",
                    help="the intact run to read the dynamic check from (hourly zs)")
    a = ap.parse_args()
    root = config.MODELS / a.model

    g = xr.open_dataset(root / "sfincs.nc")
    sg = xr.open_dataset(root / "sfincs_subgrid.nc")
    cx, cy = g["mesh2d_face_x"].values, g["mesh2d_face_y"].values
    mask = g["mask"].values
    dx = float(g.attrs["dx"]) / 2.0 ** (g["level"].values - 1)
    nm, nmu = uv_links(g)
    assert len(nm) == sg.sizes["npuv"], (len(nm), sg.sizes["npuv"])
    uvz = sg["uv_zmin"].values.astype(float)
    on = (mask[nm] > 0) & (mask[nmu] > 0)
    uvz[~on] = np.inf
    seeds = np.flatnonzero(mask == 2)
    print(f"{len(cx)} cells, {len(nm)} faces, {len(seeds)} boundary cells")

    xs = (cx[nm], cy[nm], cx[nmu], cy[nmu])
    model_lines = dikes.read_weir(root / "sfincs.weir")
    crest = weir_on_faces(model_lines, *xs)
    crest_pre = weir_on_faces(dikes.read_weir(a.pre_weir), *xs)
    print(f"weir faces: model {np.isfinite(crest).sum()}, pre-drop {np.isfinite(crest_pre).sum()}")

    costs = {
        "wall": np.where(np.isfinite(crest), np.inf, uvz),
        "crest": np.fmax(uvz, np.nan_to_num(crest, nan=-np.inf)),
        "wall_pre": np.where(np.isfinite(crest_pre), np.inf, uvz),
    }
    res = {}
    for k, c in costs.items():
        res[k] = spill(len(cx), nm, nmu, c, seeds)
        print(f"spill {k} done")

    la = dikes.leveed_areas(crs=domain.EPSG)
    systems = pd.read_csv(PAYOFF)["system"].unique()
    la = la[la.SYSTEM_NAME.isin(systems)].dissolve("SYSTEM_NAME").reset_index()
    st = exposure.high_water_stations("nj")
    mhhw = exposure.idw(st, "mhhw", cx, cy, domain.EPSG)
    annmax = exposure.idw(st, "annmax", cx, cy, domain.EPSG)
    cells = gpd.GeoDataFrame(geometry=gpd.points_from_xy(cx, cy), crs=domain.EPSG)

    ends = np.array([[x[e], y[e]] for _, x, y, _ in model_lines for e in (0, -1)])
    ends_pt = shapely.points(ends)
    all_w = shapely.MultiLineString([np.c_[x, y] for _, x, y, _ in model_lines])
    sys_idx = {i: cells.sindex.query(r.geometry.buffer(-a.inset), predicate="contains")
               for i, r in la.iterrows()}  # fmt: skip
    all_idx = np.unique(np.concatenate([v for v in sys_idx.values()]))
    zmax_all, rng_all = run_stats(root / "runs" / a.run / "sfincs_map.nc", all_idx)
    rows, leaks, inner = [], [], []
    for i, r in la.iterrows():
        idx = sys_idx[i]
        if not len(idx):
            continue
        ha = dx[idx] ** 2 / 1e4
        row = {"system": r.SYSTEM_NAME, "interior ha": ha.sum(),
               "MHHW": np.median(mhhw[idx]), "annual max": np.median(annmax[idx])}  # fmt: skip
        for k, (lvl, par) in res.items():
            rel = lvl[idx] - mhhw[idx]
            for d in ABOVE_MHHW:
                row[f"{k} ha @+{d:.1f}"] = ha[rel <= d].sum()
            row[f"{k} spill min"] = np.min(rel)
            row[f"{k} spill median"] = np.median(rel)
        # dynamic: what the intact run did inside (hourly zs)
        pos = np.searchsorted(all_idx, idx)
        zmax, rng = zmax_all[pos], rng_all[pos]
        bay = zmax >= mhhw[idx] - BAY_BELOW_MHHW
        row["run: bay-water ha"] = ha[bay].sum()
        row["run: tidal ha"] = ha[np.nan_to_num(rng) > TIDAL_RANGE_M].sum()
        lvl, par = res["wall"]
        # the leak of the bulk of the interior: the cell at the median wall spill
        i = idx[np.argsort(lvl[idx])[len(idx) // 2]]
        if np.isfinite(lvl[i]):
            f = bottleneck(i, par, nm, nmu, costs["wall"])
            fx, fy = (cx[nm[f]] + cx[nmu[f]]) / 2, (cy[nm[f]] + cy[nmu[f]]) / 2
            p = shapely.Point(fx, fy)
            d_end = float(shapely.distance(ends_pt, p).min())
            d_weir = float(all_w.distance(p))
            pre_lvl = np.median(res["wall_pre"][0][idx] - mhhw[idx])
            row.update({"leak x": fx, "leak y": fy, "leak face z rel MHHW": costs["wall"][f] - mhhw[i],
                        "to weir end m": d_end, "to weir m": d_weir,
                        "leak kind": "end gap" if d_end <= END_GAP_M else "no bank",
                        "dropped segment": bool(pre_lvl > row["wall spill median"] + 0.05)})  # fmt: skip
            leaks.append({"system": r.SYSTEM_NAME, "z_face": costs["wall"][f],
                          "rel_mhhw": costs["wall"][f] - mhhw[i], "to_end_m": d_end,
                          "to_weir_m": d_weir, "geometry": shapely.LineString(
                              [(cx[nm[f]], cy[nm[f]]), (cx[nmu[f]], cy[nmu[f]])])})  # fmt: skip
        for k in ("wall", "crest"):
            inner.append(gpd.GeoDataFrame(
                {"system": r.SYSTEM_NAME, "mode": k, "spill_rel_mhhw": res[k][0][idx] - mhhw[idx],
                 "zmin": sg["z_zmin"].values[idx], "run_zsmax": zmax, "run_bay": bay,
                 "run_daily_range": rng}, geometry=cells.geometry.values[idx], crs=domain.EPSG))  # fmt: skip
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("interior ha", ascending=False)
    out = config.ANALYSIS_DIR / f"dike_seal_{a.model}"
    df.to_csv(out.with_suffix(".csv"), index=False)
    gpkg = out.with_suffix(".gpkg")
    gpd.GeoDataFrame(leaks, crs=domain.EPSG).to_file(gpkg, layer="leak_faces")
    pd.concat(inner).to_file(gpkg, layer="interior_cells")

    show = ["system", "interior ha", "MHHW", "annual max"]
    show += [f"wall ha @+{d:.1f}" for d in ABOVE_MHHW] + ["wall spill min", "crest spill min",
             "crest spill median", "leak face z rel MHHW", "to weir end m", "leak kind", "dropped segment",
             "run: bay-water ha", "run: tidal ha"]  # fmt: skip
    rep = config.REPORTS / f"dike_seal_{a.model}.md"
    rep.write_text(
        f"# Do the farm dikes seal? `{a.model}`\n\n"
        "Written by `scripts/check_dike_seal.py`. Spill = lowest bay level that reaches a cell, m "
        "above local MHHW. `wall`: every weir face closed, only openings count; `crest`: weirs at "
        "their modelled crests. `wall ha @+d`: interior hectares a bay level of MHHW + d reaches "
        "round the banks.\n\n" + md_table(df[show].round(2)) + "\n")  # fmt: skip
    print(df[show].round(2).to_string(index=False))
    print(f"wrote {rep}, {out.with_suffix('.csv')}, {gpkg}")


if __name__ == "__main__":
    main()
