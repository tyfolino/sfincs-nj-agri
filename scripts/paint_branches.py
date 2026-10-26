"""Deepen a tidal reach's marsh branch channels in a river-bed burn (test, 2026-10-25).

    python scripts/paint_branches.py --tag v2a30 --out v2a30br [--network alloway]
        [--depth 1.5] [--slope 0.1] [--max-halfwidth 40]

The NJ lidar holds marsh creeks as hydro-flattened water at about -1.07 m (FINDINGS §45),
only ~0.2 m below MLLW, so branches that carry tide in real creeks hold almost none for half of
each tide. Lower Alloway: the drawn main channel needs an effective 4.5 m to give Hancocks
Bridge its tide, while the branches reach the river by their own mouths (Abbotts Meadow, Hope
Creek). This tests whether giving the branches depth does the work instead.

Branch pixels, inside ``domain.BRANCH_NETWORKS[network]["bbox"]``: bed_merged at or below
``FLAT_MAX_M`` (the lidar's flat water), not open water (bed_source 3), not already in the burn,
and 8-connected to the burn (the reach's painted channel). Their bed becomes

    max(MLLW - depth, bed - slope * distance to the nearest bank)

never above bed_merged: a V across each channel, flat at MLLW - depth past depth/slope m from the
bank. A bank is any pixel that is neither flat water, open water nor burn. Water wider than
2 x ``max_halfwidth`` (pixels within that of a point farther than it from a bank) is the
river's own shallow edge, a pond or a wide creek mouth: there only a +-``CORRIDOR_M`` strip
along the NHDPlus HR flowlines (not the Delaware River's own) is painted, so the wide lower Hope
Creek and each branch mouth across the river's edge get a channel without the edge itself
being dug out. MLLW is the reach's (riverbed_profiles_<tag>.csv) at the nearest centreline
station.

Writes data/elevation/riverbed_burn_<out>.tif and riverbed_source_<out>.tif: copies of the
<tag> pair with the branch pixels added (source code 11); then ``merge_bed.py --tag <out>``.
"""

from __future__ import annotations

import argparse
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from scipy import ndimage
from scipy.spatial import cKDTree

from agri_sfincs import config, domain

ELEV = config.ELEV_DIR
FLAT_MAX_M = -1.0  # the lidar's hydro-flat water is -1.07 m here
CORRIDOR_M = 15.0
SRC_BRANCH = 11


def branch_bed(bed, src, burned, corridor, mllw, px, depth, slope, max_hw):
    """(mask, new bed) on a window: bed m NAVD88 (nan = nodata), src = bed_source codes,
    burned = in the reach burn, corridor = near an NHD flowline, mllw = per-pixel MLLW,
    px = (dy, dx) pixel size in m."""
    flat = np.isfinite(bed) & (bed <= FLAT_MAX_M) & (src != 3) & ~burned
    lab, _ = ndimage.label(flat, structure=np.ones((3, 3)))
    ids = np.unique(lab[ndimage.binary_dilation(burned, iterations=2) & (lab > 0)])
    net = np.isin(lab, ids)
    d = ndimage.distance_transform_edt(flat | burned | (src == 3), sampling=px)
    ry, rx = (int(np.ceil(max_hw / p)) for p in px)
    yy, xx = np.ogrid[-ry : ry + 1, -rx : rx + 1]
    disk = (yy * px[0]) ** 2 + (xx * px[1]) ** 2 <= max_hw**2
    wide = ndimage.binary_dilation(net & (d > max_hw), structure=disk)
    mask = net & (~wide | corridor)
    z = np.fmin(bed, np.fmax(mllw - depth, bed - slope * d))
    return mask & (z < bed), z


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", required=True, help="the burn to start from (riverbed_burn_<tag>.tif)")
    ap.add_argument("--out", required=True, help="tag of the outputs")
    ap.add_argument("--network", default="alloway", choices=list(domain.BRANCH_NETWORKS))
    ap.add_argument("--depth", type=float, default=1.5, help="floor, m below MLLW")
    ap.add_argument("--slope", type=float, default=0.1, help="m of depth per m from the bank")
    ap.add_argument("--max-halfwidth", type=float, default=40.0, help="m")
    a = ap.parse_args()
    net = domain.BRANCH_NETWORKS[a.network]

    burn_in, src_in = ELEV / f"riverbed_burn_{a.tag}.tif", ELEV / f"riverbed_source_{a.tag}.tif"
    burn_out, src_out = ELEV / f"riverbed_burn_{a.out}.tif", ELEV / f"riverbed_source_{a.out}.tif"
    with rasterio.open(ELEV / "bed_merged.tif") as g:
        w = from_bounds(*net["bbox"], g.transform).round_offsets().round_lengths()
        bed = g.read(1, window=w).astype("float32")
        bed[bed == g.nodata] = np.nan
        T = g.window_transform(w)
    with rasterio.open(ELEV / "bed_source.tif") as g:
        src = g.read(1, window=w)
    with rasterio.open(burn_in) as g:
        burn = g.read(1, window=w)
        burned = np.isfinite(burn) & (burn != g.nodata)

    lat0 = T.f + T.e * bed.shape[0] / 2
    px = (abs(T.e) * 110_574, T.a * 111_320 * np.cos(np.radians(lat0)))
    rows, cols = np.indices(bed.shape)
    lon, lat = T * (cols + 0.5, rows + 0.5)
    prof = pd.read_csv(ELEV / f"riverbed_profiles_{a.tag}.csv", low_memory=False)
    prof = prof[(prof.reach == net["reach"]) & (prof.kind == "tidal")]
    x, y = Transformer.from_crs(4326, 32618, always_xy=True).transform(lon.ravel(), lat.ravel())
    _, i = cKDTree(prof[["x", "y"]].to_numpy()).query(np.c_[x, y])
    mllw = prof.mllw_navd88_m.to_numpy()[i].reshape(bed.shape)
    fl = gpd.read_file(config.CHANNELS_DIR / "nhdplus_hr.gpkg", layer="flowline", bbox=net["bbox"])
    fl = fl[fl.gnis_name.fillna("") != "Delaware River"]
    strips = fl.to_crs(32618).buffer(CORRIDOR_M).to_crs(4326)
    corridor = rasterize([(g, 1) for g in strips], out_shape=bed.shape, transform=T).astype(bool)

    mask, z = branch_bed(bed, src, burned, corridor, mllw, px, a.depth, a.slope, a.max_halfwidth)

    shutil.copy(burn_in, burn_out)
    shutil.copy(src_in, src_out)
    with rasterio.open(burn_out, "r+") as g:
        out = g.read(1, window=w)
        out[mask] = z[mask]
        g.write(out, 1, window=w)
        g.update_tags(branches=f"{a.network}: paint_branches.py --tag {a.tag} --depth {a.depth} "
                               f"--slope {a.slope} --max-halfwidth {a.max_halfwidth}")  # fmt: skip
    with rasterio.open(src_out, "r+") as g:
        s = g.read(1, window=w)
        s[mask] = SRC_BRANCH
        g.write(s, 1, window=w)
        g.update_tags(src_11="tidal branch: lidar flat water, V by distance to bank")

    pa = px[0] * px[1]
    drop = bed[mask] - z[mask]
    print(f"{a.network}: {mask.sum() * pa / 1e6:.2f} km2 of branch channel lowered by p50 "
          f"{np.median(drop):.2f} m (p90 {np.percentile(drop, 90):.2f}), "
          f"{(drop * pa).sum() / 1e6:.2f} Mm3; at the floor (MLLW - {a.depth} m): "
          f"{(z[mask] <= mllw[mask] - a.depth + 1e-3).mean():.0%}; MLLW {mllw[mask].min():.2f}.."
          f"{mllw[mask].max():.2f}")
    print(f"wrote {burn_out} and {src_out.name}")


if __name__ == "__main__":
    main()
