"""Structure files for the farm -> wetland restoration runs (plan §2.4a), phase 1: hydraulic
restoration of one dike system = re-open it to the tide the way restorations do it.

Why not reuse breach/<slug>.weir (scripts/make_dike_scenarios.py): those cut a 100 m gap at
the bank's lowest crest vertex down to MARSH level (MHHW - 0.2 m). Several farm banks are
already at about that height, and in the tide month one such gap in every farm bank floods
almost nothing more than the intact dikes (FINDINGS §27). A restoration (or a scoured
breach) opens the old creek mouth to below low tide.

Per site (a farm system), at its outlet (dikes_built.gpkg ``gates``: the NLD pipe gate or
the deepest notch of its banks, i.e. the old creek crossing):
  restore/<slug>_mllw100.weir   100 m gap, sill at local MLLW (2021-25 mean daily low, IDW
                                between the forcing gauges)
  restore/<slug>_mllw300.weir   the same, 300 m wide
  restore/<slug>_nogate.drn     the gate file without that system's check valve(s)
All other banks and gates stay as built. Sites: SITES below.

Set-back (managed realignment; Middle Neck only, 2026-10-06): restore the system's NON-FARMED
seaward land and protect its farms behind a new inner dike.
  restored area R = the part of the leveed area farther than SETBACK_BUF_M from every 2020
                    farm field (scripts/field_flood_classes.py), the piece that holds the outlet
  inner dike      = R's boundary away from the leveed-area edge, simplified by SETBACK_SIMPLIFY_M,
                    crest SETBACK_CREST_M (the outer banks' median)
  new gate        = one check valve through the inner dike (farm side -> R), at the lowest
                    farm-side ground within GATE_SEARCH_M of the dike, so the farms keep draining
  restore/<slug>_setback.weir = <slug>_mllw100.weir + the inner dike
  restore/<slug>_setback.drn  = <slug>_nogate.drn + the new gate
  restore/<slug>_setback.gpkg = R and the inner dike (for maps)

Writes data/structures/scenarios/restore/* and restore/sites.csv.
Usage:  python scripts/make_restore_scenarios.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

import bayshore_exposure as be
import make_dike_scenarios as mds
from agri_sfincs import config, dikes

STRUCT = config.DATA / "structures"
OUT = STRUCT / "scenarios" / "restore"
CRS = "EPSG:32618"
#: Middle Neck (Salem): the system behind the most dike-dependent farmland (FINDINGS §29) and
#: around NRCS RCPP-WRE 330636 (§22). Durham (Cumberland): went to marsh 2013-19 (§21).
SITES = ["Middle Neck", "Durham"]
WIDTHS_M = (100.0, 300.0)
GATES_DRN = STRUCT / "dike_gates_lo.drn"  # what the v1 runs use
SETBACK_SITES = ["Middle Neck"]
SETBACK_BUF_M, SETBACK_SIMPLIFY_M, SETBACK_CREST_M = 50.0, 30.0, 2.0
GATE_SEARCH_M, GATE_C = 150.0, 1.5  # GATE_C as dike_gates_lo


def mllw_stations() -> pd.DataFrame:
    """Forcing gauges with MLLW = mean daily minimum of observed levels 2021-25 (m NAVD88)."""
    rows = []
    with xr.open_dataset(config.DATA / "gauges" / "waterlevel_forcing_navd88.nc") as ds:
        for s in ds.stations.values:
            w = ds.waterlevel.sel(stations=s).to_series()
            src = ds.source.sel(stations=s).to_series()
            x = w[(w.index.year >= 2021) & (src == "obs")]
            d = x.resample("D").min()[x.resample("D").count() >= 20]
            rows.append({"id": str(s), "lon": float(ds.lon.sel(stations=s)),
                         "lat": float(ds.lat.sel(stations=s)), "mllw": d.mean()})  # fmt: skip
    return pd.DataFrame(rows).set_index("id").loc[be.FORCING]


def setback(system: str, gates, st) -> dict:
    import rasterio
    from shapely.geometry import LineString, Point

    sl = mds.slug(system)
    lev = gpd.read_file(STRUCT / "structures.gpkg", layer="nld_leveed_areas").to_crs(CRS)
    L = lev[lev.SYSTEM_NAME == system].union_all()
    fields = gpd.read_file(config.DATA / "analysis" / "field_flood_classes.gpkg").to_crs(CRS)
    farms = fields[fields.representative_point().within(L)]
    g = gates[gates.system == system].iloc[0]
    out = Point(g.x_site, g.y_site)
    parts = L.difference(farms.buffer(SETBACK_BUF_M).union_all())
    R = min(getattr(parts, "geoms", [parts]), key=lambda p: p.distance(out))
    edge = R.boundary.difference(L.boundary.buffer(40.0)).simplify(SETBACK_SIMPLIFY_M)
    segs = [ln for ln in getattr(edge, "geoms", [edge]) if ln.length > 0]
    weir = dikes.read_weir(OUT / f"{sl}_mllw100.weir")
    for k, ln in enumerate(segs):
        x, y = np.asarray(ln.coords).T
        # vertices every <= 20 m, like the built dikes
        s_ = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
        si = np.linspace(0, s_[-1], max(int(s_[-1] // 20) + 2, 2))
        weir.append((f"setback_{sl}_{k}", np.interp(si, s_, x), np.interp(si, s_, y), np.full(si.size, SETBACK_CREST_M)))
    dikes.write_weir(OUT / f"{sl}_setback.weir", weir)
    # new gate: lowest farm-side ground near the dike -> lowest R ground near that point
    with rasterio.open(config.MODELS / "v1_100m" / "subgrid" / "dep_subgrid_lev0.tif") as d:
        zb, tr = d.read(1, masked=True).filled(np.nan), d.transform
    x0, y0, x1, y1 = L.bounds
    gx, gy = np.meshgrid(np.arange(x0, x1, 30.0), np.arange(y0, y1, 30.0))
    pts = gpd.GeoSeries(gpd.points_from_xy(gx.ravel(), gy.ravel()), crs=CRS)
    cols = ((pts.x - tr.c) / tr.a).astype(int).values
    rows_ = ((pts.y - tr.f) / tr.e).astype(int).values
    z = zb[rows_, cols]
    de = pts.distance(edge).values
    farm_side = (de <= GATE_SEARCH_M) & (de >= 60) & pts.within(L.difference(R)).values & np.isfinite(z)
    r_side = (de >= 60) & pts.within(R).values & np.isfinite(z)
    rx, ry, rz = pts.x.values[r_side], pts.y.values[r_side], z[r_side]
    pin = pout = None
    for i in np.flatnonzero(farm_side)[np.argsort(z[farm_side])]:  # lowest farm-side ground first
        d = np.hypot(rx - pts.x.values[i], ry - pts.y.values[i])
        ok = (d >= 120) & (d <= 2 * GATE_SEARCH_M)
        if ok.any():
            j = np.flatnonzero(ok)[np.argmin(rz[ok])]
            pin, pout, z_in, z_out = pts.iloc[i], Point(rx[j], ry[j]), z[i], rz[j]
            break
    if pin is None:
        raise RuntimeError(f"{system}: no gate site found")
    drn = (OUT / f"{sl}_nogate.drn").read_text().rstrip("\n").splitlines()
    drn.append(f"{pin.x:.1f} {pin.y:.1f} {pout.x:.1f} {pout.y:.1f} 3 {GATE_C:.3f}")
    (OUT / f"{sl}_setback.drn").write_text("\n".join(drn) + "\n")
    gpd.GeoDataFrame({"what": ["restored", "inner_dike", "gate_in", "gate_out"]},
                     geometry=[R, edge, pin, pout], crs=CRS).to_file(OUT / f"{sl}_setback.gpkg")  # fmt: skip
    print(f"{system} set-back: restored {R.area / 1e4:.0f} ha, inner dike {edge.length / 1e3:.1f} km in "
          f"{len(segs)} pieces, new gate {z_in:+.2f} -> {z_out:+.2f} m, "
          f"{len(farms)} farm fields ({farms.ha.sum():.0f} ha) behind it")  # fmt: skip
    return {"system": system, "slug": sl, "arm": "setback", "restored_ha": R.area / 1e4,
            "inner_dike_km": edge.length / 1e3, "sill_m": None}  # fmt: skip


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = dikes.read_weir(STRUCT / "dikes.weir")
    cp = gpd.read_file(STRUCT / "dikes_built.gpkg", layer="crest_points")
    sysof = cp.drop_duplicates("name").set_index("name")["system"]
    gates = gpd.read_file(STRUCT / "dikes_built.gpkg", layer="gates")
    drn = GATES_DRN.read_text().splitlines()
    if len(drn) != len(gates):
        raise RuntimeError(f"{GATES_DRN.name}: {len(drn)} rows vs {len(gates)} gates")
    st = mllw_stations()
    rows = []
    for system in SITES:
        g = gates[gates.system == system]
        if g.empty:
            raise KeyError(system)
        xs, ys = float(g.x_site.iloc[0]), float(g.y_site.iloc[0])
        sill = float(be.idw(st, "mllw", np.array([xs]), np.array([ys]), CRS)[0])
        idx = [i for i, ln in enumerate(lines) if sysof.get(ln[0]) == system]
        # the system's crest vertex nearest the outlet
        i_line, j = min(((i, int(np.argmin(np.hypot(lines[i][1] - xs, lines[i][2] - ys)))) for i in idx),
                        key=lambda t: np.hypot(lines[t[0]][1][t[1]] - xs, lines[t[0]][2][t[1]] - ys))  # fmt: skip
        name, x, y, z = lines[i_line]
        dist = float(np.hypot(x[j] - xs, y[j] - ys))
        for w in WIDTHS_M:
            zn = dikes.breach(x, y, z, j, w, sill)
            one = list(lines)
            one[i_line] = (name, x, y, zn)
            dikes.write_weir(OUT / f"{mds.slug(system)}_mllw{int(w)}.weir", one)
            rows.append({"system": system, "slug": mds.slug(system), "arm": f"mllw{int(w)}", "polyline": name,
                         "x": float(x[j]), "y": float(y[j]), "outlet_dist_m": dist, "sill_m": sill,
                         "crest_before_min": float(z[zn < z].min()), "crest_before_max": float(z[zn < z].max()),
                         "vertices_lowered": int((zn < z).sum())})  # fmt: skip
        keep = [ln for ln, s in zip(drn, gates.system) if s != system]
        (OUT / f"{mds.slug(system)}_nogate.drn").write_text("\n".join(keep) + "\n")
        print(f"{system}: outlet {dist:.0f} m from the bank vertex, sill {sill:+.2f} m, "
              f"{len(drn) - len(keep)} gate(s) removed")  # fmt: skip
    for system in SETBACK_SITES:
        rows.append(setback(system, gates, st))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "sites.csv", index=False)
    print(t.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
