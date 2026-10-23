"""SSURGO hydrologic soil group + saturated hydraulic conductivity for the ring, for
SFINCS curve-number-with-recovery infiltration (``inftype = cnb``).

Extends nj_bight_sfincs ``scripts/build_cn_nj.py`` (2026-10-02), which fetched HSG
only, to also get ksat. Source: USDA Soil Data Access REST API (no auth), tiled at
0.25 deg because SDA answers HTTP 413 on large boxes.

Per map unit, from its DOMINANT component (highest comppct_r, the same rule bight
used for HSG, so HSG and ksat describe the same soil):
  hsg              SSURGO hydgrp letter(s), e.g. "B", "B/D"; missing -> "" (water,
                   urban land, pits)
  ksat_hmean_um_s  depth-weighted HARMONIC mean of ksat_r over 0-100 cm, um/s. Layers
                   in series: the restrictive horizon controls how fast a soil drains,
                   which is what the recovery term models
  ksat_surf_um_s   ksat_r of the top horizon, um/s (reference only)

Integer HSG codes as hydromt_sfincs' ``lulc/NLCD_HSG.csv`` columns expect them:
A=1, B=6, C=5, D=3, A/D=2, B/D=7, C/D=8, none=4 (-9999 CN, i.e. no infiltration).
Two variants, the drained-vs-undrained sensitivity in the plan:
  undrained  dual groups stay dual (the table gives them the D curve number)
  drained    dual groups take their first letter (A/D -> A ...): the soil as it
             behaves where the field is ditched or tiled, which is common here

Writes data/soils/:
  ssurgo_mapunits.gpkg       polygons + the attributes above (EPSG:4326)
  hsg_undrained.tif          uint8 codes, 30 m, EPSG:32618, ring bbox + 1 km
  hsg_drained.tif            uint8 codes, same grid
  ksat_um_s.tif              float32, harmonic-mean ksat, same grid (nodata -9999)

Delaware (``--side de``): the same over the DE ring, every file with a _de suffix.

Usage:  python scripts/fetch_ssurgo.py [--side de] [--overwrite]
"""

from __future__ import annotations

import argparse
import itertools

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely import wkt as shapely_wkt

from agri_sfincs import config, domain, region
from agri_sfincs.net import post

SDA = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
TILE_DEG = 0.25
RES_M = 30.0
PAD_M = 1000.0
DEPTH_CM = 100.0

HSG_CODE = {"A": 1, "B": 6, "C": 5, "D": 3, "A/D": 2, "B/D": 7, "C/D": 8}
NO_HSG = 4
SOILS = config.SOILS_DIR


def sda(sql: str) -> list[list]:
    return post(SDA, {"format": "JSON", "query": sql}, timeout=300).json().get("Table", [])


def fetch_polygons(bbox) -> gpd.GeoDataFrame:
    w, s, e, n = bbox
    xs = list(np.arange(w, e, TILE_DEG)) + [e]
    ys = list(np.arange(s, n, TILE_DEG)) + [n]
    seen, rows = set(), []
    for (x0, x1), (y0, y1) in itertools.product(
        zip(xs[:-1], xs[1:]), zip(ys[:-1], ys[1:])
    ):
        poly = f"POLYGON(({x0} {y0}, {x1} {y0}, {x1} {y1}, {x0} {y1}, {x0} {y0}))"
        sql = (
            "SELECT g.mukey, g.mupolygongeo.STAsText() AS wkt FROM mupolygon g "
            f"WHERE g.mupolygongeo.STIntersects(geometry::STGeomFromText('{poly}',4326))=1"
        )
        for mukey, wk in sda(sql):
            if wk is None or (mukey, wk) in seen:
                continue  # a polygon straddling two tiles comes back twice
            seen.add((mukey, wk))
            rows.append((str(mukey), wk))
        print(f"  tile {x0:.2f},{y0:.2f}: {len(rows)} polygons so far", flush=True)
    return gpd.GeoDataFrame(
        {"mukey": [m for m, _ in rows]},
        geometry=[shapely_wkt.loads(w) for _, w in rows],
        crs=4326,
    )


def harmonic_ksat(hz: pd.DataFrame, depth_cm: float = DEPTH_CM) -> float:
    """Depth-weighted harmonic mean of ksat_r over 0..depth_cm for ONE component.

    Horizons are clipped to the window; horizons with no ksat are skipped (their
    thickness is not counted). NaN if nothing usable lies in the window.
    """
    top = hz.hzdept_r.clip(upper=depth_cm)
    bot = hz.hzdepb_r.clip(upper=depth_cm)
    th = (bot - top).where(lambda t: t > 0)
    ok = th.notna() & hz.ksat_r.notna() & (hz.ksat_r > 0)
    if not ok.any():
        return float("nan")
    return float(th[ok].sum() / (th[ok] / hz.ksat_r[ok]).sum())


def fetch_attributes(mukeys: list[str]) -> pd.DataFrame:
    """Dominant component's hydgrp + ksat per map unit (chunked IN lists)."""
    comps, hzs = [], []
    for i in range(0, len(mukeys), 500):
        keys = ",".join(f"'{k}'" for k in mukeys[i : i + 500])
        comps += sda(
            "SELECT mukey, cokey, comppct_r, hydgrp FROM component "
            f"WHERE mukey IN ({keys})"
        )
        hzs += sda(
            "SELECT c.cokey, h.hzdept_r, h.hzdepb_r, h.ksat_r FROM component c "
            f"JOIN chorizon h ON h.cokey=c.cokey WHERE c.mukey IN ({keys})"
        )
    c = pd.DataFrame(comps, columns=["mukey", "cokey", "comppct_r", "hydgrp"])
    c["comppct_r"] = pd.to_numeric(c.comppct_r)
    dom = c.sort_values("comppct_r", ascending=False).drop_duplicates("mukey")
    h = pd.DataFrame(hzs, columns=["cokey", "hzdept_r", "hzdepb_r", "ksat_r"])
    for k in ("hzdept_r", "hzdepb_r", "ksat_r"):
        h[k] = pd.to_numeric(h[k])
    h = h[h.cokey.isin(dom.cokey)].sort_values(["cokey", "hzdept_r"])
    g = h.groupby("cokey")
    ks = pd.DataFrame(
        {
            "ksat_hmean_um_s": g.apply(harmonic_ksat, include_groups=False),
            "ksat_surf_um_s": g.ksat_r.first(),
        }
    )
    out = dom.set_index("cokey").join(ks).reset_index()
    out["hsg"] = out.hydgrp.fillna("")
    return out[["mukey", "hsg", "ksat_hmean_um_s", "ksat_surf_um_s"]].set_index("mukey")


def hsg_codes(hsg: pd.Series, drained: bool) -> pd.Series:
    letters = hsg.str.split("/").str[0] if drained else hsg
    return letters.map(HSG_CODE).fillna(NO_HSG).astype("uint8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--side", default="nj", choices=list(domain.SIDES))
    a = ap.parse_args()
    sfx = domain.side(a.side).files
    gpkg = SOILS / f"ssurgo_mapunits{sfx}.gpkg"
    if gpkg.exists() and not a.overwrite:
        raise SystemExit(f"{gpkg} exists; pass --overwrite")
    SOILS.mkdir(parents=True, exist_ok=True)

    ring = region.load_ring(a.side)
    bbox = tuple(ring.to_crs(domain.EPSG).buffer(1000).to_crs(4326).total_bounds)
    polys = fetch_polygons(bbox)
    attrs = fetch_attributes(sorted(polys.mukey.unique()))
    mu = polys.join(attrs, on="mukey")
    mu["hsg"] = mu.hsg.fillna("")
    mu["hsg_undrained"] = hsg_codes(mu.hsg, drained=False)
    mu["hsg_drained"] = hsg_codes(mu.hsg, drained=True)
    mu.to_file(gpkg, driver="GPKG")

    # Rasters on a 30 m UTM grid over the ring (+ pad)
    w, s, e, n = ring.to_crs(domain.EPSG).total_bounds
    w, s = np.floor((w - PAD_M) / RES_M) * RES_M, np.floor((s - PAD_M) / RES_M) * RES_M
    e, n = np.ceil((e + PAD_M) / RES_M) * RES_M, np.ceil((n + PAD_M) / RES_M) * RES_M
    shape = (int((n - s) / RES_M), int((e - w) / RES_M))
    tr = from_origin(w, n, RES_M, RES_M)
    mu_u = mu.to_crs(domain.EPSG)
    prof = dict(driver="GTiff", width=shape[1], height=shape[0], count=1,
                crs=f"EPSG:{domain.EPSG}", transform=tr, compress="deflate")  # fmt: skip
    for col in ("hsg_undrained", "hsg_drained"):
        arr = rasterize(zip(mu_u.geometry, mu_u[col]), out_shape=shape, transform=tr,
                        fill=NO_HSG, dtype="uint8")  # fmt: skip
        with rasterio.open(SOILS / f"{col}{sfx}.tif", "w",
                           dtype="uint8", nodata=0, **prof) as dst:  # fmt: skip
            dst.write(arr, 1)
    ks = mu_u[mu_u.ksat_hmean_um_s.notna()]
    arr = rasterize(zip(ks.geometry, ks.ksat_hmean_um_s), out_shape=shape,
                    transform=tr, fill=-9999, dtype="float32")  # fmt: skip
    with rasterio.open(SOILS / f"ksat_um_s{sfx}.tif", "w", dtype="float32", nodata=-9999,
                       **prof) as dst:  # fmt: skip
        dst.write(arr, 1)

    # Summary, area-weighted over the ring
    inside = gpd.clip(mu_u, ring.to_crs(domain.EPSG))
    inside["km2"] = inside.area / 1e6
    print(f"\n{len(mu)} polygons, {mu.mukey.nunique()} map units; ring area by HSG (km2):")
    print(inside.groupby("hsg").km2.sum().round(1).to_string())
    k = inside[inside.ksat_hmean_um_s.notna()]
    print(f"harmonic ksat 0-100 cm, area-weighted mean "
          f"{np.average(k.ksat_hmean_um_s, weights=k.km2):.2f} um/s; "
          f"median map unit {k.ksat_hmean_um_s.median():.2f}")  # fmt: skip
    print(f"wrote {gpkg} and 3 rasters {shape[1]}x{shape[0]} @ {RES_M:.0f} m")


if __name__ == "__main__":
    main()
