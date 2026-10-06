"""NLD levee alignments as a SFINCS weir file, and one-way outlets (check valves) for the
farm dikes (FINDINGS §10; user decision 2026-10-05).

Crest: the lidar ridge along each alignment — the highest pre-merged bed pixel within
±RIDGE_HALF_M of the line (NLD lines are digitised a few metres off the crest), sampled
every STEP_M. Then:
  farm dikes (NLD systems whose leveed area holds > FARM_CROP_KM2 of CDL cropland):
    notches (gates, culverts, creek crossings: > 0.3 m below the 200 m running median)
    are FILLED to the running median — the outlet becomes the check valve below;
  every other system (industrial levees, restored marsh, refuges): the raw ridge, so
    real breaches stay open; only no-data gaps are filled.
Outlets, one check valve (drainage type 3) per farm leveed area:
  at each NLD pipe gate on that area if it has any (Gibbstown), otherwise at the deepest
  notch of its banks (the lowest raw ridge if none is flagged);
  intake = the lowest bed GATE_RMIN..GATE_RMAX m from that point INSIDE the leveed area,
  outfall = the lowest bed in the same ring OUTSIDE it; both ≥ GATE_CLEAR_M from every
  alignment and ≥ GATE_SEP_M apart, so they land in different 100 m cells on either side
  of the weir.
Gate size is an ASSUMPTION, written at two coefficients (q = C·sqrt(Δh), m^2.5/s):
  C_LO 1.5 ≈ one 0.8 m (30") pipe, C_HI 6.0 ≈ four of them or one 1.4 m box.

Writes data/structures/: dikes.weir, dike_gates_lo.drn, dike_gates_hi.drn,
dikes_built.gpkg (layers crest_points, gates); reports/dikes.md.

Usage:  python scripts/build_dikes.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from shapely.geometry import LineString, MultiLineString, Point

from agri_sfincs import config, domain, region
from agri_sfincs.cdl import CROPLAND
from agri_sfincs.dikes import fill_notches, write_drn, write_weir
from agri_sfincs.report import md_table

STRUCT = config.DATA / "structures"
BED = config.DATA / "elevation" / "bed_merged.tif"
STEP_M = 5.0
RIDGE_HALF_M = 20.0
RIDGE_OFFSETS = np.arange(-RIDGE_HALF_M, RIDGE_HALF_M + 0.1, 4.0)
FARM_CROP_KM2 = 0.1
CDL_YEAR = 2023
GATE_RMIN, GATE_RMAX, GATE_GRID = 120.0, 400.0, 20.0
GATE_CLEAR_M, GATE_SEP_M = 60.0, 150.0
C_LO, C_HI = 1.5, 6.0


class Bed:
    """Window reads of the pre-merged bed (EPSG:4326, ~3.9 m) at UTM points."""

    def __init__(self):
        self.src = rasterio.open(BED)
        self.to_ll = Transformer.from_crs(domain.EPSG, self.src.crs, always_xy=True)

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        lon, lat = self.to_ll.transform(x, y)
        pad = 1e-4
        win = from_bounds(lon.min() - pad, lat.min() - pad, lon.max() + pad, lat.max() + pad,
                          self.src.transform).round_offsets().round_lengths()  # fmt: skip
        a = self.src.read(1, window=win, boundless=True, fill_value=np.nan).astype("float64")
        nd = self.src.nodata
        if nd is not None:
            a[a == nd] = np.nan
        tr = self.src.window_transform(win)
        c, r = ~tr * (lon, lat)
        r, c = np.floor(r).astype(int), np.floor(c).astype(int)
        ok = (r >= 0) & (r < a.shape[0]) & (c >= 0) & (c < a.shape[1])
        out = np.full(x.shape, np.nan)
        out[ok] = a[r[ok], c[ok]]
        return out


def lines_of(geom) -> list[LineString]:
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, LineString)]


def ridge_along(line: LineString, bed: Bed):
    """Stations s, points (x, y) every STEP_M, and the ridge = max bed across ±RIDGE_HALF_M."""
    s = np.append(np.arange(0.0, line.length, STEP_M), line.length)
    pts = [line.interpolate(v) for v in s]
    x, y = np.array([p.x for p in pts]), np.array([p.y for p in pts])
    tx, ty = np.gradient(x), np.gradient(y)
    norm = np.hypot(tx, ty)
    norm[norm == 0] = 1.0
    nx, ny = -ty / norm, tx / norm
    X = x[:, None] + nx[:, None] * RIDGE_OFFSETS[None, :]
    Y = y[:, None] + ny[:, None] * RIDGE_OFFSETS[None, :]
    z = bed.sample(X.ravel(), Y.ravel()).reshape(X.shape)
    with np.errstate(all="ignore"):
        ridge = np.where(np.isfinite(z).any(axis=1), np.nanmax(z, axis=1), np.nan)
    return s, x, y, ridge


def cropland_km2(areas: gpd.GeoDataFrame) -> np.ndarray:
    with rasterio.open(config.CDL_DIR / f"CDL_{CDL_YEAR}_{domain.STATE_FIPS}.tif") as c:
        with WarpedVRT(c, crs=f"EPSG:{domain.EPSG}", resolution=30) as v:
            west, south, east, north = areas.total_bounds
            win = from_bounds(west, south, east, north, v.transform).round_offsets().round_lengths()
            a = np.isin(v.read(1, window=win), list(CROPLAND))
            tr = v.window_transform(win)
    lab = rasterize(((g, i + 1) for i, g in enumerate(areas.geometry)), out_shape=a.shape,
                    transform=tr, fill=0, dtype="int32")  # fmt: skip
    return np.bincount(lab[a], minlength=len(areas) + 1)[1:] * 900 / 1e6


def pick_gate(pt: Point, area, banks, outline, bed: Bed, rmax: float = GATE_RMAX):
    """(x_in, y_in, z_in, x_out, y_out, z_out) around ``pt``, or None."""
    g = np.arange(-rmax, rmax + 0.1, GATE_GRID)
    gx, gy = np.meshgrid(pt.x + g, pt.y + g)
    gx, gy = gx.ravel(), gy.ravel()
    r = np.hypot(gx - pt.x, gy - pt.y)
    keep = (r >= GATE_RMIN) & (r <= rmax)
    gx, gy = gx[keep], gy[keep]
    cand = gpd.GeoSeries(gpd.points_from_xy(gx, gy), crs=domain.EPSG)
    clear = cand.distance(banks) >= GATE_CLEAR_M
    inside = cand.within(area) & clear & cand.within(outline)
    outside = ~cand.within(area.buffer(30.0)) & clear & cand.within(outline)
    z = bed.sample(gx, gy)
    best = []
    for m in (inside.values, outside.values):
        m = m & np.isfinite(z)
        if not m.any():
            return None
        i = np.flatnonzero(m)[np.argmin(z[m])]
        best.append((gx[i], gy[i], z[i]))
    (xi, yi, zi), (xo, yo, zo) = best
    if np.hypot(xi - xo, yi - yo) < GATE_SEP_M:
        return None
    return xi, yi, zi, xo, yo, zo


def main() -> None:
    crs = domain.EPSG
    outline = region.load_outline().to_crs(crs).geometry.union_all()
    gpkg = STRUCT / "structures.gpkg"
    al = gpd.read_file(gpkg, layer="nld_alignment").to_crs(crs)
    la = gpd.read_file(gpkg, layer="nld_leveed_areas").to_crs(crs)
    pg = gpd.read_file(gpkg, layer="nld_pipe_gates").to_crs(crs)
    al = al[al.intersects(outline)].copy()
    al["geometry"] = al.geometry.intersection(outline)
    la = la[la.intersects(outline)].reset_index(drop=True)
    pg = pg[pg.within(outline)]
    la["crop_km2"] = cropland_km2(la)
    la["area_km2"] = la.area / 1e6
    farm = la[la.crop_km2 > FARM_CROP_KM2].copy()
    farm_sys = set(farm.SYSTEM_ID)
    print(f"{len(al)} alignments, {len(la)} leveed areas in the model; {len(farm)} farm areas "
          f"({farm.crop_km2.sum():.1f} km² cropland), {len(pg)} NLD pipe gates inside")  # fmt: skip

    bed = Bed()
    weir_lines, pts_rows = [], []
    for _, row in al.iterrows():
        is_farm = row.SYSTEM_ID in farm_sys
        for k, line in enumerate(lines_of(row.geometry)):
            if line.length < 2 * STEP_M:
                continue
            s, x, y, ridge = ridge_along(line, bed)
            if is_farm:
                crest, notch = fill_notches(ridge, s)
            else:
                crest, notch = fill_notches(ridge, s, drop_m=np.inf)  # only no-data gaps
            name = f"nld_{row.ALIGN_ID}_{k}"
            weir_lines.append((name, x, y, crest))
            pts_rows.append(pd.DataFrame({"name": name, "system_id": row.SYSTEM_ID,
                                          "system": row.SYSTEM_NAME, "farm": is_farm, "s": s,
                                          "x": x, "y": y, "ridge": ridge, "crest": crest,
                                          "notch": notch}))  # fmt: skip
    pts = pd.concat(pts_rows, ignore_index=True)
    nv = write_weir(STRUCT / "dikes.weir", weir_lines)
    km = sum(LineString(np.c_[x, y]).length for _, x, y, _ in weir_lines) / 1e3
    print(f"weir: {len(weir_lines)} polylines, {nv:,} vertices, {km:.1f} km")

    # Outlets ---------------------------------------------------------------------
    gates = []
    for _, a in farm.iterrows():
        banks_pts = pts[pts.system_id == a.SYSTEM_ID]
        banks = al[al.SYSTEM_ID == a.SYSTEM_ID].geometry.union_all()
        nld = pg[pg.distance(a.geometry) <= 150.0]
        if len(nld):
            sites = [(p, "nld_pipe_gate", np.nan) for p in nld.geometry]
        else:
            cand = banks_pts[banks_pts.notch & np.isfinite(banks_pts.ridge)]
            if cand.empty:
                cand = banks_pts[np.isfinite(banks_pts.ridge)]
            if cand.empty:
                print(f"  ⚠️ {a.SYSTEM_NAME}: no ridge samples — no outlet")
                continue
            r = cand.loc[cand.ridge.idxmin()]
            sites = [(Point(r.x, r.y), "deepest_notch" if r.notch else "lowest_ridge", r.ridge)]
        for p, kind, zr in sites:
            gsel = pick_gate(p, a.geometry, banks, outline, bed)
            if gsel is None:  # narrow area or bank far from open water: look wider once
                gsel = pick_gate(p, a.geometry, banks, outline, bed, rmax=2 * GATE_RMAX)
            if gsel is None:
                print(f"  ⚠️ {a.SYSTEM_NAME}: no intake/outfall pair near {kind} — skipped")
                continue
            xi, yi, zi, xo, yo, zo = gsel
            gates.append({"system": a.SYSTEM_NAME, "leveed_id": a.LEVEED_ID,
                          "crop_km2": a.crop_km2, "area_km2": a.area_km2, "site": kind,
                          "x_site": p.x, "y_site": p.y, "notch_ridge": zr,
                          "x_in": xi, "y_in": yi, "z_in": zi,
                          "x_out": xo, "y_out": yo, "z_out": zo})  # fmt: skip
    gt = pd.DataFrame(gates)
    rows = list(zip(gt.x_in, gt.y_in, gt.x_out, gt.y_out))
    write_drn(STRUCT / "dike_gates_lo.drn", rows, C_LO)
    write_drn(STRUCT / "dike_gates_hi.drn", rows, C_HI)
    print(f"outlets: {len(gt)} check valves for {gt.leveed_id.nunique()} of {len(farm)} farm areas")

    out = STRUCT / "dikes_built.gpkg"
    gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.x, pts.y), crs=crs).to_file(
        out, layer="crest_points", driver="GPKG")
    gpd.GeoDataFrame(gt, geometry=gpd.points_from_xy(gt.x_site, gt.y_site), crs=crs).to_file(
        out, layer="gates", driver="GPKG")

    # Report ----------------------------------------------------------------------
    f = pts[pts.farm]
    o = pts[~pts.farm]
    sm = lambda d: f"{len(d) * STEP_M / 1e3:.1f}"  # noqa: E731
    lines = [
        "# Dikes as weirs, farm-dike outlets (scripts/build_dikes.py)", "",
        f"Weir file `data/structures/dikes.weir`: {len(weir_lines)} polylines, {nv:,} vertices, "
        f"{km:.1f} km of NLD alignment inside the model outline. Crest = lidar ridge "
        f"(max of the pre-merged bed within ±{RIDGE_HALF_M:.0f} m), cd 0.6.", "",
        md_table(pd.DataFrame({
            "km": [sm(f), sm(o)],
            "crest p5 / p50 / p95 (m NAVD88)": [
                " / ".join(f"{v:.2f}" for v in np.nanpercentile(f.crest, [5, 50, 95])),
                " / ".join(f"{v:.2f}" for v in np.nanpercentile(o.crest, [5, 50, 95]))],
            "km filled": [sm(f[f.notch]), sm(o[o.notch])],
            "km crest < 1.2 m": [sm(f[f.crest < 1.2]), sm(o[o.crest < 1.2])],
        }, index=pd.Index(["farm dikes (notches filled)", "other levees (raw ridge)"],
                          name="banks"))), "",
        f"Farm leveed areas (> {FARM_CROP_KM2} km² CDL {CDL_YEAR} cropland): {len(farm)}, "
        f"{farm.crop_km2.sum():.1f} km² cropland. Check valves (drainage type 3, "
        f"`dike_gates_lo.drn` C = {C_LO}, `dike_gates_hi.drn` C = {C_HI} m^2.5/s): {len(gt)}.", "",
        md_table(gt.set_index("system")[["crop_km2", "area_km2", "site", "notch_ridge", "z_in",
                                         "z_out"]].sort_values("crop_km2", ascending=False),
                 floatfmt="{:.2f}"),
        "",
        "⚠️ Gate sizes and sites are ASSUMPTIONS: no tide-gate inventory exists for these "
        "banks (NLD has 13 pipe gates, all at Chester PA and Gibbstown).",
    ]  # fmt: skip
    missing = sorted(set(farm.SYSTEM_NAME) - set(gt.system))
    if missing:
        lines += ["", f"Farm areas WITHOUT an outlet: {', '.join(map(str, missing))}."]
    (config.REPORTS / "dikes.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {STRUCT / 'dikes.weir'}, the two .drn files, {out}, reports/dikes.md")


if __name__ == "__main__":
    main()
