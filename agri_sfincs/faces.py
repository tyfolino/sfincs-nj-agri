"""Face-graph tools for a SFINCS quadtree model: which faces join which cells, where weirs sit,
and the minimax ("spill") level at which water from the open boundary can reach each cell.

Moved out of scripts/check_dike_seal.py (2026-11-06) so the DE creek-drain check can share them.
The spill level of a cell = the smallest, over all face paths from the seed cells, of the
highest face cost on the path. With cost = subgrid ``uv_zmin`` (water crosses a face once its
lowest strip is wet) it is the lowest level the boundary can fill a cell to, and equally the
lowest level the cell can DRAIN to through the faces.
"""

from __future__ import annotations

import heapq

import numpy as np
import shapely
import xarray as xr


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


def path_faces(i: int, par: np.ndarray, a: np.ndarray, b: np.ndarray) -> list[int]:
    """The faces on cell ``i``'s spill path, from ``i`` back to the seed."""
    out = []
    while par[i] >= 0:
        f = int(par[i])
        out.append(f)
        i = a[f] if b[f] == i else b[f]
    return out
