"""Merge the river-bed burn into the pre-merged bed: bed_<tag> = fmin(bed_merged, burn).

The burn (scripts/build_riverbeds.py, FINDINGS §11) is on bed_merged's own grid and can
only LOWER the bed; it is merged here, ONCE, rather than stacked in an elevation list
(never prepend a burn raster to the list — bight trap, CLAUDE.md). Burn nodata leaves
the bed as it was.

Writes data/elevation/bed_<tag>.tif (float32, m NAVD88, nodata -9999, tiled + deflate) and
prints the area lowered and by how much. The catalog source is ``bed_<tag>``. Tag v1 (the
default) reads riverbed_burn.tif, which build_riverbeds.py writes without a tag; any other tag
reads riverbed_burn_<tag>.tif (``build_riverbeds.py --tag <tag>``). Was merge_bed_v1.py.

Delaware (``--side de``): bed_merged_de + riverbed_burn_de_<tag> -> bed_de_<tag>.tif.

Usage:  python scripts/merge_bed.py [--tag v2] [--side de] [--overwrite]
"""

from __future__ import annotations

import argparse

import numpy as np
import rasterio

from agri_sfincs import config, domain




def merge(bed: np.ndarray, burn: np.ndarray, nodata: float) -> np.ndarray:
    """fmin where both are valid; the bed where the burn is nodata; nodata stays nodata."""
    b = np.where(bed == nodata, np.nan, bed)
    r = np.where(burn == nodata, np.nan, burn)
    out = np.where(np.isfinite(b) & np.isfinite(r), np.fmin(b, r), b)
    return np.where(np.isfinite(out), out, nodata).astype("float32")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--side", default="nj", choices=list(domain.SIDES))
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    s = domain.side(a.side).files
    BED = config.ELEV_DIR / f"bed_merged{s}.tif"
    BURN = config.ELEV_DIR / ("riverbed_burn.tif" if (a.tag, s) == ("v1", "") else f"riverbed_burn{s}_{a.tag}.tif")
    OUT = config.ELEV_DIR / f"bed{s}_{a.tag}.tif"
    if OUT.exists() and not a.overwrite:
        raise FileExistsError(f"{OUT} exists (--overwrite)")
    with rasterio.open(BED) as sb, rasterio.open(BURN) as sr:
        if (sb.shape, sb.transform, sb.crs) != (sr.shape, sr.transform, sr.crs):
            raise ValueError("burn is not on bed_merged's grid")
        nd = sb.nodata
        prof = sb.profile.copy()
        n_low, drops = 0, []
        with rasterio.open(OUT, "w", **prof) as dst:
            for _, win in sb.block_windows(1):
                b, r = sb.read(1, window=win), sr.read(1, window=win)
                m = merge(b, r, nd)
                low = (b != nd) & (m < b)
                n_low += int(low.sum())
                if low.any():
                    drops.append((b - m)[low])
                dst.write(m, 1, window=win)
    # pixel area on the lon/lat grid at the raster's mid-latitude
    lat0 = np.deg2rad(prof["transform"].f + prof["transform"].e * prof["height"] / 2)
    px_m2 = abs(prof["transform"].a * prof["transform"].e) * 111_320 * 110_574 * np.cos(lat0)
    d = np.concatenate(drops) if drops else np.array([0.0])
    print(f"wrote {OUT}: lowered {n_low * px_m2 / 1e6:.1f} km² (~{n_low:,} px); "
          f"drop p50 {np.median(d):.2f} m, p90 {np.percentile(d, 90):.2f} m")


if __name__ == "__main__":
    main()
