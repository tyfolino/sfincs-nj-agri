"""Farm-dike outlets v2: one-way valves where a mapped creek crosses the bank, with the
outfall on that creek's own downstream path where the MODELLED low tide is low enough
to drain (FINDINGS §16; user 2026-10-05).

Why v2: the v1 outlets (scripts/build_dikes.py) sat at the deepest lidar notch with the
outfall at the lowest bed nearby. Most outfalls landed in marsh creeks whose modelled
low tide stays ABOVE the water inside, so the valve never opened (Silver Lake, Middle
Neck: 0% of hours). Real tide gates sit where the creek crosses the bank.

Per farm leveed area (scripts/build_dikes.py's 18 areas, > 0.1 km² cropland):
  sites    every NHDPlus HR flowline × that system's NLD alignment crossing (deduplicated
           within DEDUP_M); the 6 NLD pipe gates for Gibbstown; if an area has neither, its
           deepest notch (v1 rule).
  intake   the lowest bed on the crossing flowline and the reaches upstream of it, inside
           the leveed area, IN_RMIN..IN_RMAX m along the network from the site and
           ≥ CLEAR_M from every bank; falls back to the lowest bed in a ring inside.
  outfall  on the downstream path (dnhydroseq), up to OUT_MAX_M along the network, outside
           the area and ≥ CLEAR_M from the banks, in a cell WET at low tide in the
           reference run; the point minimising p10(zs) + OUT_KM_PENALTY·km — i.e. walk
           down the creek until the low tide drops. Falls back to the same rule in a ring.
  "drain margin" = intake bed + 0.1 − outfall p10(zs): > 0 means the valve can draw the
  interior down to ~10 cm above its lowest point at an ordinary low tide.
Low tide comes from a reference run's hourly map (``--ref``, default v1_100m sep2023,
last 30 days): tide outside the dikes does not depend on the valves.

Writes data/structures/dike_gates_v2_lo.drn and _hi.drn (C 1.5 / 6.0 m^2.5/s, as v1),
layer gates_v2 in dikes_built.gpkg, and reports/dike_outlets.md.

Usage:  python scripts/build_dike_outlets.py [--ref v1_100m/sep2023]
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import LineString, Point
from shapely.ops import substring

from agri_sfincs import config, domain, region
from agri_sfincs.dikes import write_drn
from agri_sfincs.report import md_table
from build_dikes import C_HI, C_LO, Bed, lines_of

STRUCT = config.DATA / "structures"
DEDUP_M = 150.0
IN_RMIN, IN_RMAX = 120.0, 600.0
OUT_MAX_M = 3000.0
OUT_KM_PENALTY = 0.10  # m of low tide per km of extra creek
CLEAR_M = 60.0
STEP_M = 20.0
WET_LOW_M = 0.02  # p10 depth for "wet at low tide"


class LowTide:
    """p10 of hourly zs (last 30 days) per cell of a uniform reference run, and whether
    the cell is wet then."""

    def __init__(self, run):
        with xr.open_dataset(run / "sfincs_map.nc") as mp:
            zs = mp["zs"].values[-24 * 30:]
            self.zb = mp["zb"].values
            self.x0, self.y0 = float(mp.corner_x.min()), float(mp.corner_y.min())
        self.p10 = np.nanpercentile(zs, 10, axis=0)
        self.wet = (self.p10 - self.zb) > WET_LOW_M

    def at(self, x, y):
        n = np.floor((np.asarray(y) - self.y0) / 100).astype(int)
        m = np.floor((np.asarray(x) - self.x0) / 100).astype(int)
        ok = (n >= 0) & (n < self.zb.shape[0]) & (m >= 0) & (m < self.zb.shape[1])
        p, w = np.full(n.shape, np.nan), np.zeros(n.shape, bool)
        p[ok], w[ok] = self.p10[n[ok], m[ok]], self.wet[n[ok], m[ok]]
        return p, w


def walk(fl: gpd.GeoDataFrame, start: str, pos: float, down: bool, max_m: float):
    """Points every STEP_M along the network from ``pos`` m on flowline ``start``, going
    downstream (dnhydroseq) or upstream (all reaches draining into it), up to ``max_m``.
    Returns (x, y, distance along the network)."""
    by_hs = fl.set_index("hydroseq")
    xs, ys, ds = [], [], []
    stack = [(start, pos, 0.0)]
    seen = set()
    while stack:
        hs, p, d0 = stack.pop()
        if hs in seen or hs not in by_hs.index:
            continue
        seen.add(hs)
        line = by_hs.loc[hs, "geometry"]
        line = line if isinstance(line, LineString) else lines_of(line)[0]
        seg = substring(line, p, line.length) if down else substring(line, 0, p)
        if not down:
            seg = LineString(list(seg.coords)[::-1]) if seg.length > 0 else seg
        L = seg.length
        for s in np.arange(0, L, STEP_M):
            if d0 + s > max_m:
                break
            q = seg.interpolate(s)
            xs.append(q.x), ys.append(q.y), ds.append(d0 + s)
        if d0 + L >= max_m:
            continue
        if down:
            nxt = by_hs.loc[hs, "dnhydroseq"]
            if nxt in by_hs.index:
                stack.append((nxt, 0.0, d0 + L))
        else:
            for up in fl.loc[fl.dnhydroseq == hs, "hydroseq"]:
                ul = by_hs.loc[up, "geometry"]
                stack.append((up, ul.length, d0 + L))
    return np.array(xs), np.array(ys), np.array(ds)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="v1_100m/sep2023", help="<model>/<run> for low tide")
    a = ap.parse_args()
    crs = domain.EPSG
    model, run = a.ref.split("/")
    lt = LowTide(config.MODELS / model / "runs" / run)
    bed = Bed()
    outline = region.load_outline().to_crs(crs).geometry.union_all()

    gpkg = STRUCT / "structures.gpkg"
    al = gpd.read_file(gpkg, layer="nld_alignment").to_crs(crs)
    la = gpd.read_file(gpkg, layer="nld_leveed_areas").to_crs(crs)
    pg = gpd.read_file(gpkg, layer="nld_pipe_gates").to_crs(crs)
    v1 = gpd.read_file(STRUCT / "dikes_built.gpkg", layer="gates")
    crest = gpd.read_file(STRUCT / "dikes_built.gpkg", layer="crest_points")
    farm = la[la.LEVEED_ID.isin(v1.leveed_id)].copy()
    farm = farm.merge(v1.groupby("leveed_id").crop_km2.first().rename("crop_km2"),
                      left_on="LEVEED_ID", right_index=True)  # fmt: skip
    fl = gpd.read_file(config.CHANNELS_DIR / "nhdplus_hr.gpkg", layer="flowline").to_crs(crs)
    fl = fl[fl.intersects(farm.geometry.buffer(OUT_MAX_M).union_all())].copy()
    fl = fl[fl.hydroseq.notna()].drop_duplicates("hydroseq")

    gates = []
    for _, area in farm.iterrows():
        poly = area.geometry
        banks = al[al.SYSTEM_ID == area.SYSTEM_ID].geometry.union_all()
        sites = []  # (point, kind, flowline hydroseq or None, position on it)
        nld = pg[pg.distance(poly) <= 150.0]
        for p in nld.geometry:
            sites.append((p, "nld_pipe_gate", None, None))
        if not sites:
            near = fl[fl.intersects(banks)]
            for _, f in near.iterrows():
                for q in [g for g in getattr(f.geometry.intersection(banks), "geoms",
                                             [f.geometry.intersection(banks)])
                          if isinstance(g, Point)]:  # fmt: skip
                    if all(q.distance(s[0]) > DEDUP_M for s in sites):
                        line = lines_of(f.geometry)[0]
                        sites.append((q, "creek_crossing", f.hydroseq, line.project(q)))
        if not sites:
            c = crest[(crest.system_id == area.SYSTEM_ID) & crest.notch & crest.ridge.notna()]
            if c.empty:
                c = crest[(crest.system_id == area.SYSTEM_ID) & crest.ridge.notna()]
            r = c.loc[c.ridge.idxmin()]
            sites.append((Point(r.x, r.y), "deepest_notch", None, None))

        for p, kind, hs, pos in sites:
            # candidate intakes / outfalls: along the network if on a creek, else a ring
            if hs is not None:
                xi, yi, di = walk(fl, hs, pos, down=False, max_m=IN_RMAX)
                xo, yo, do = walk(fl, hs, pos, down=True, max_m=OUT_MAX_M)
            else:
                xi = yi = di = xo = yo = do = np.array([])
            if xi.size == 0 or xo.size == 0:  # ring fallback
                g = np.arange(-800, 801, STEP_M)
                gx, gy = (v.ravel() for v in np.meshgrid(p.x + g, p.y + g))
                r = np.hypot(gx - p.x, gy - p.y)
                k = (r >= IN_RMIN) & (r <= 800)
                if xi.size == 0:
                    xi, yi, di = gx[k], gy[k], r[k]
                if xo.size == 0:
                    xo, yo, do = gx[k], gy[k], r[k]
            ci = gpd.GeoSeries(gpd.points_from_xy(xi, yi), crs=crs)
            co = gpd.GeoSeries(gpd.points_from_xy(xo, yo), crs=crs)
            zi = bed.sample(xi, yi)
            ok_i = (ci.within(poly) & (ci.distance(banks) >= CLEAR_M)).values & (di >= IN_RMIN) \
                & np.isfinite(zi)
            p10, wet = lt.at(xo, yo)
            ok_o = (~co.within(poly.buffer(30.0)) & (co.distance(banks) >= CLEAR_M)
                    & co.within(outline)).values & wet & np.isfinite(p10)  # fmt: skip
            if not ok_i.any() or not ok_o.any():
                print(f"  ⚠️ {area.SYSTEM_NAME}: {kind} at ({p.x:.0f}, {p.y:.0f}) — no "
                      f"{'intake' if not ok_i.any() else 'wet outfall'}; skipped")  # fmt: skip
                continue
            i = np.flatnonzero(ok_i)[np.argmin(zi[ok_i])]
            score = p10 + OUT_KM_PENALTY * do / 1e3
            o = np.flatnonzero(ok_o)[np.argmin(score[ok_o])]
            gates.append({"system": area.SYSTEM_NAME, "leveed_id": area.LEVEED_ID,
                          "crop_km2": area.crop_km2, "site": kind, "x_site": p.x,
                          "y_site": p.y, "x_in": xi[i], "y_in": yi[i], "z_in": zi[i],
                          "x_out": xo[o], "y_out": yo[o], "out_km": do[o] / 1e3,
                          "out_lowtide": p10[o],
                          "drain_margin": zi[i] + 0.1 - p10[o]})  # fmt: skip
    gt = pd.DataFrame(gates)
    rows = list(zip(gt.x_in, gt.y_in, gt.x_out, gt.y_out))
    write_drn(STRUCT / "dike_gates_v2_lo.drn", rows, C_LO)
    write_drn(STRUCT / "dike_gates_v2_hi.drn", rows, C_HI)
    gpd.GeoDataFrame(gt, geometry=gpd.points_from_xy(gt.x_site, gt.y_site), crs=crs).to_file(
        STRUCT / "dikes_built.gpkg", layer="gates_v2", driver="GPKG")
    n_area = gt.leveed_id.nunique()
    print(f"v2 outlets: {len(gt)} valves for {n_area} of {len(farm)} farm areas; "
          f"drain margin > 0 for {(gt.drain_margin > 0).sum()}")  # fmt: skip

    per = gt.groupby("system").agg(crop_km2=("crop_km2", "first"), valves=("site", "size"),
                                   site=("site", "first"),
                                   best_margin=("drain_margin", "max"),
                                   out_lowtide=("out_lowtide", "min"),
                                   out_km=("out_km", "min")).sort_values("crop_km2",
                                                                          ascending=False)  # fmt: skip
    missing = sorted(set(farm.SYSTEM_NAME) - set(gt.system))
    lines = ["# Farm-dike outlets v2 (scripts/build_dike_outlets.py)", "",
             f"Reference low tide: `{a.ref}` (p10 of hourly zs, last 30 days). "
             f"{len(gt)} check valves for {n_area} of {len(farm)} farm areas "
             f"(`dike_gates_v2_lo.drn` C = {C_LO}, `_hi` C = {C_HI}).", "",
             "drain margin = intake bed + 0.1 − outfall low tide (m); > 0: the valve can "
             "draw the interior down to ~10 cm above its lowest point at an ordinary low tide.",
             "", md_table(per, floatfmt="{:.2f}")]  # fmt: skip
    if missing:
        lines += ["", f"Farm areas WITHOUT a v2 outlet: {', '.join(map(str, missing))}."]
    (config.REPORTS / "dike_outlets.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
