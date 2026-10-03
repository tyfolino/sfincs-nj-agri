"""Pre-merge ONE bed raster for the model, with explicit rules instead of a first-wins
elevation list — so CUDEM's flat ~0 m "beds" never leak into inland water.

Why (user, 2026-10-02; bight FINDINGS §54a): CUDEM stores non-tidal water as a flat
~0 m surface — sampled here: Union Lake -0.20 (lidar surface 7.56), Alloway Lake 0.00
(3.96), Laurel Lake -0.02 (1.81), Salem River at Woodstown 0.53 (8.68). The NJ 2021 lidar
is hydro-flattened: lakes and rivers carry their WATER SURFACE, and open bay/river
water is NoData (no exact zeros over this domain). A plain list with the lidar at
``zmin 0.001`` would also hand every NEGATIVE lidar pixel (tidal water, low marsh,
4.6% of the box) to CUDEM, and in 0-filled tidal creeks that RAISES the bed (Cohansey
at Greenwich: lidar -0.43, CUDEM +0.17).

Rules, per pixel on the lidar's own grid (3.505e-5 deg, ~3.9 m):
  1  lidar wherever it has data (negatives included)                       src=1
  2  ... unless lidar < LOW_M and CUDEM is deeper by >= DEEPER_M: then CUDEM
     (real channel bathymetry, e.g. Maurice at Bivalve -6.47 under -0.99)  src=2
     It can only LOWER the bed, and never touches water surfaces above LOW_M (the
     inland lakes), so a fake 0 cannot come in that way. Residual risk: a 0-filled
     tidal creek whose lidar surface is between DEEPER_M and LOW_M is lowered to ~0.
  3  lidar NoData: CUDEM (bay, river, banks)                              src=3
  4  ... else 3DEP 1/3" (PA/DE land; blanks tidal water)                  src=4
  5  ... else GMRT ~100 m                                                  src=5
Other sources are resampled bilinearly onto the lidar grid.

Writes data/elevation/bed_merged.tif (float32, m NAVD88, nodata -9999) and
data/elevation/bed_source.tif (uint8 codes above), both over the model outline bbox +
1 km, tiled and compressed, then prints the area per source.

Usage:  python scripts/build_bed.py [--overwrite]
"""

from __future__ import annotations

import argparse

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window, from_bounds

from agri_sfincs import config, domain, region

LOW_M = 1.0
DEEPER_M = 0.5
TILE = 4096
NODATA = -9999.0
OUT_DIR = config.DATA / "elevation"
LIDAR = config.BIGHT_DATA / "elevation_v4/nj_10ft_dem_v4.tif"
OTHERS = {  # src code -> path, in fall-through order
    3: config.BIGHT_DATA / "elevation_v4/cudem_delaware_v4.vrt",
    4: config.BIGHT_DATA / "elevation_v4/dep3_v4.vrt",
    5: config.BIGHT_DATA / "elevation_v4/gmrt_v4.tif",
}


def merge_tile(lidar: np.ndarray, others: dict[int, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Apply the rules (module docstring) to one tile. NaN = no data in every array."""
    bed = np.full(lidar.shape, np.nan, dtype="float32")
    src = np.zeros(lidar.shape, dtype="uint8")
    have = np.isfinite(lidar)
    bed[have], src[have] = lidar[have], 1
    cudem = others[3]
    deeper = have & np.isfinite(cudem) & (lidar < LOW_M) & (cudem <= lidar - DEEPER_M)
    bed[deeper], src[deeper] = cudem[deeper], 2
    for code in (3, 4, 5):
        fill = ~np.isfinite(bed) & np.isfinite(others[code])
        bed[fill], src[fill] = others[code][fill], code
    return bed, src


def _read(ds, win, shape) -> np.ndarray:
    a = ds.read(1, window=win, out_shape=shape, masked=True).astype("float32")
    a = a.filled(np.nan)
    a[(a < -1e4) | (a > 1e4)] = np.nan  # stray fill values (e.g. -3.4e38, -999999)
    return a


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    out_bed, out_src = OUT_DIR / "bed_merged.tif", OUT_DIR / "bed_source.tif"
    if out_bed.exists() and not a.overwrite:
        raise SystemExit(f"{out_bed} exists; pass --overwrite")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with rasterio.open(LIDAR) as li:
        b = region.load_outline().to_crs(domain.EPSG).buffer(1000).to_crs(li.crs).total_bounds
        full = from_bounds(*b, transform=li.transform).round_offsets().round_lengths()
        tr = li.window_transform(full)
        prof = dict(driver="GTiff", width=full.width, height=full.height, count=1,
                    crs=li.crs, transform=tr, tiled=True, blockxsize=512,
                    blockysize=512, compress="deflate", predictor=2, BIGTIFF="YES")  # fmt: skip
        vrts = {
            c: WarpedVRT(rasterio.open(p), crs=li.crs, transform=tr, width=full.width,
                         height=full.height, resampling=Resampling.bilinear,
                         src_nodata=None)  # fmt: skip
            for c, p in OTHERS.items()
        }
        counts = np.zeros(6, dtype=np.int64)
        with (rasterio.open(out_bed, "w", dtype="float32", nodata=NODATA, predictor=3,
                            **{k: v for k, v in prof.items() if k != "predictor"}) as db,
              rasterio.open(out_src, "w", dtype="uint8", nodata=0, **prof) as dsrc):  # fmt: skip
            for r0 in range(0, full.height, TILE):
                for c0 in range(0, full.width, TILE):
                    w = Window(c0, r0, min(TILE, full.width - c0), min(TILE, full.height - r0))
                    lw = Window(full.col_off + c0, full.row_off + r0, w.width, w.height)
                    shape = (int(w.height), int(w.width))
                    lidar = _read(li, lw, shape)
                    others = {c: _read(v, w, shape) for c, v in vrts.items()}
                    bed, src = merge_tile(lidar, others)
                    counts += np.bincount(src.ravel(), minlength=6)
                    db.write(np.where(np.isfinite(bed), bed, NODATA).astype("float32"), 1, window=w)
                    dsrc.write(src, 1, window=w)
                print(f"  row {r0 // TILE + 1}/{-(-full.height // TILE)}", flush=True)
        for v in vrts.values():
            v.close()

    px_km2 = (abs(tr.a) * 111_320 * np.cos(np.radians((b[1] + b[3]) / 2))) * (abs(tr.e) * 110_574) / 1e6
    names = {0: "no data", 1: "lidar", 2: "CUDEM deeper (tidal channels)", 3: "CUDEM (lidar NoData)",
             4: "3DEP", 5: "GMRT"}  # fmt: skip
    for k, n in enumerate(counts):
        print(f"  src {k} {names[k]:32s} {n * px_km2:9.1f} km2")
    print(f"wrote {out_bed} and {out_src} ({full.width}x{full.height})")


if __name__ == "__main__":
    main()
