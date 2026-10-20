"""E9 bed (FINDINGS §42): bed_v1 with MEASURED / CHARTED depths in four tidal creeks.

  oldmans, big_timber, alloway: NOS hydrographic soundings (NCEI HYD93 XYZ: H10027 1982 MLLW,
      H09886 1980 MLW, H10112 1983 MLLW) inside the painted channel, running median +-500 m
      along the centreline (>= 3 soundings, else the 3 nearest within 1.5 km), linear between,
      as build_riverbeds.py does for ENC soundings. H09886's MLW -> MLLW: MLW - MLLW = 0.058 m
      (Philadelphia + Pier 11 planes, nj_bight_sfincs "bigtimber"): depth_MLLW = depth_MLW - 0.058.
  cohansey: 2.13 m (7 ft, Coast Pilot 3 controlling depth at the entrance) below MLLW from the
      mouth to Fairton (FAIRTON_LAT); above Fairton unchanged (1.2 m below MLLW).
  stow: unchanged (no data): the control.
Lower-only: profile = min(v1 profile, new); pixels = the reach's painted tidal strip
(riverbed_source codes 1-3, nearest tidal centreline = this reach, within 300 m), bed =
min(bed_v1, profile(s)).

Inputs: data/channels/nos/<survey>.a93.gz (NCEI NOS hydrographic surveys, HYD93 XYZ, fetched
2026-10-20 from data.ngdc.noaa.gov/platforms/ocean/nos/coast/H<range>/<survey>/GEODAS/; D00081
and H11070 are the Cohansey mouth, kept but unused), data/elevation/bed_v1.tif,
riverbed_source.tif, riverbed_profiles.csv, riverbed_centrelines.gpkg.
Writes config.DATA_BULK/experiments/e9_beds/bed_e9.tif + bed_e9.yml (the hydromt catalog entry
for build_model.py --elevation bed_e9 --catalog ...) and prints per-reach changes.
An EXPERIMENT (models/e9_100m): v2 beds should take the soundings into build_riverbeds.py.

Usage:  python scripts/build_bed_e9.py
"""

import gzip
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from pyproj import Transformer
from rasterio.windows import from_bounds

from agri_sfincs import config, domain, riverbed

OUT_DIR = config.DATA_BULK / "experiments" / "e9_beds"
NOS = config.CHANNELS_DIR / "nos"
SURVEYS = {"oldmans": [("H10027", 0.0)], "big_timber": [("H09886", 0.058)], "alloway": [("H10112", 0.0)]}
COHANSEY_MLLW_DEPTH = 2.13
FAIRTON_LAT = 39.381  # Fairton landing, Cohansey River
TOL_M, HALF_M, MIN_N, MAX_HALF_M, MAXDIST_M = 60.0, 500.0, 3, 1500.0, 300.0
ELEV = config.ELEV_DIR
to_utm = Transformer.from_crs(4326, domain.EPSG, always_xy=True)


def soundings(sid: str, mlw_minus_mllw: float) -> gpd.GeoDataFrame:
    rows = []
    for line in gzip.open(NOS / f"{sid}.a93.gz", "rt"):
        d = int(line[27:33]) / 10
        if d > 9000:
            continue
        rows.append((int(line[17:27]) / 1e6, int(line[9:17]) / 1e6, d - mlw_minus_mllw))
    a = np.array(rows)
    x, y = to_utm.transform(a[:, 0], a[:, 1])
    return gpd.GeoDataFrame({"survey": sid, "depth_m": a[:, 2]}, geometry=shapely.points(x, y), crs=domain.EPSG)


def main():
    prof = pd.read_csv(ELEV / "riverbed_profiles.csv", low_memory=False)
    cl = gpd.read_file(ELEV / "riverbed_centrelines.gpkg").to_crs(domain.EPSG)
    tidal = cl[cl.kind == "tidal"].set_index("reach")
    new = {}
    for reach in ["oldmans", "big_timber", "alloway", "cohansey"]:
        p = prof[prof.reach == reach].sort_values("station_m")
        grid, mllw, old = p.station_m.to_numpy(), p.mllw_navd88_m.to_numpy(), p.bed_profile_m.to_numpy()
        line = tidal.geometry[reach]
        if reach == "cohansey":
            lat = Transformer.from_crs(domain.EPSG, 4326, always_xy=True).transform(p.x.to_numpy(), p.y.to_numpy())[1]
            cand = np.where(lat <= FAIRTON_LAT, mllw - COHANSEY_MLLW_DEPTH, np.nan)
            info = f"7 ft below MLLW over {np.isfinite(cand).sum() * 25 / 1e3:.1f} km"
        else:
            s = pd.concat([soundings(*v) for v in SURVEYS[reach]], ignore_index=True)
            near = s[shapely.dwithin(line, s.geometry.values, TOL_M)]
            ss = shapely.line_locate_point(line, near.geometry.values)
            inner = (ss > 0.5) & (ss < line.length - 0.5)
            near, ss = near[inner], ss[inner]
            z = riverbed.chart_to_navd88(near.depth_m.to_numpy(), np.interp(ss, grid, mllw))
            cand = riverbed.fill_interior(grid, riverbed.running_median(ss, z, grid, HALF_M, MIN_N, MAX_HALF_M))
            info = (f"{len(near)} soundings over {np.isfinite(cand).sum() * 25 / 1e3:.1f} km, "
                    f"depth below MLLW p50 {np.median(near.depth_m):.1f} m")
        nprof = np.where(np.isfinite(cand), np.fmin(old, cand), old)
        lowered = old - nprof
        print(f"{reach:10s} {info}; profile lowered median {np.median(lowered[lowered > 0]) if (lowered > 0).any() else 0:.2f} m "
              f"over {(lowered > 0.05).sum() * 25 / 1e3:.1f} km (old p50 {np.median(old):+.2f}, new p50 {np.median(nprof):+.2f})")
        new[reach] = (grid, nprof)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "bed_e9.tif"
    shutil.copyfile(ELEV / "bed_v1.tif", out)
    src_r = rasterio.open(ELEV / "riverbed_source.tif")
    to_ll = Transformer.from_crs(domain.EPSG, 4326, always_xy=True)
    with rasterio.open(out, "r+") as dst:
        for reach, (grid, nprof) in new.items():
            line = tidal.geometry[reach]
            others = [g for r, g in tidal.geometry.items() if r != reach]
            x0, y0, x1, y1 = line.buffer(MAXDIST_M).bounds
            lo, la = to_ll.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
            win = from_bounds(min(lo), min(la), max(lo), max(la), dst.transform).round_offsets().round_lengths()
            src = src_r.read(1, window=win)
            bed = dst.read(1, window=win)
            r, c = np.nonzero(np.isin(src, [1, 2, 3]))
            xs, ys = rasterio.transform.xy(dst.window_transform(win), r, c)
            ux, uy = to_utm.transform(np.asarray(xs), np.asarray(ys))
            pts = shapely.points(ux, uy)
            d = shapely.distance(line, pts)
            keep = d <= MAXDIST_M
            for g in others:
                keep &= d <= shapely.distance(g, pts)
            s = shapely.line_locate_point(line, pts[keep])
            z = np.interp(s, grid, nprof)
            rk, ck = r[keep], c[keep]
            before = bed[rk, ck].copy()
            bed[rk, ck] = np.fmin(before, z)
            dst.write(bed, 1, window=win)
            ch = before - bed[rk, ck]
            print(f"  painted {reach}: {keep.sum()} pixels, {(ch > 0.05).sum()} lowered, median {np.median(ch[ch > 0.05]) if (ch > 0.05).any() else 0:.2f} m")
    (OUT_DIR / "bed_e9.yml").write_text(f"""bed_e9:
  data_type: RasterDataset
  uri: {out}
  driver: {{name: rasterio, options: {{}}}}
  metadata:
    category: topography
    unit: m+NAVD88
    nodata: -9999.0
""")
    print("wrote", out)


if __name__ == "__main__":
    main()
