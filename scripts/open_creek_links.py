"""Reopen the tidal creeks that bank weirs close at the model's resolution (FINDINGS §40).

SFINCS puts a weir on every cell link one of its segments crosses, so a meadow bank within
half a cell of a creek can land on the links the creek itself flows through. On v1_100m this
closes Alloway Creek ~3 km above Hancocks Bridge: the upper 13 km never sees a tide. This
drops every weir segment that crosses a link along a tidal centreline
(data/elevation/riverbed_centrelines.gpkg, kind "tidal"; agri_sfincs.runs.centreline_links,
agri_sfincs.dikes.drop_crossings). On a uniform 100 m grid both cells of such a link hold the
channel, so no bank between channel and field is lost that the grid could represent.

The links come from the map grid of ``--grid`` (a run, runs.resolve). Every ``_open`` weir so far
was made on the 100 m v1 grid; the default, v1's identical repeat run, is that grid (2026-11-03:
the v1 tide2024oct_intact_slr000 used before was deleted). m65's map grid is 25 m and drops nothing.

Delaware (2026-11-04): ``--centrelines`` names the side's centreline file, e.g.
riverbed_centrelines_de_v2ap45.gpkg with ``--weir data/structures/dikes_de.weir --out
data/structures/dikes_de_open.weir --grid de_v2ap45_100m/storm2022apr_intact_slr000_hrrr``: the NWI
impoundment perimeters (build_dikes_nwi.py) close the Murderkill and Little River the same way
(the storm gauge check, Frederica).

Writes data/structures/dikes_open.weir (from dikes.weir) and prints what it removed.
Usage:  python scripts/open_creek_links.py [--weir data/structures/dikes.weir] [--out ...] [--grid v1_100m/tide2024oct_intact_slr000_rep]
            [--centrelines riverbed_centrelines.gpkg]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import xarray as xr

from agri_sfincs import config, dikes, runs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--weir", default=str(config.STRUCT_DIR / "dikes.weir"))
    ap.add_argument("--out", default=str(config.STRUCT_DIR / "dikes_open.weir"))
    ap.add_argument("--grid", default="v1_100m/tide2024oct_intact_slr000_rep", help="run whose map grid sets the links")
    ap.add_argument("--centrelines", default="riverbed_centrelines.gpkg", help="file in config.ELEV_DIR (kind 'tidal' used)")
    a = ap.parse_args()
    with xr.open_dataset(runs.resolve(a.grid) / "sfincs_map.nc") as mp:
        grid = runs.MapGrid.from_map(mp)
    c = gpd.read_file(config.ELEV_DIR / a.centrelines)
    links, per_reach = [], {}
    for r in c[c.kind == "tidal"].itertuples():
        lk = runs.centreline_links(grid, r.geometry)
        links += lk
        per_reach[getattr(r, "reach", r.Index)] = lk
    lines = dikes.read_weir(Path(a.weir))
    out, n = dikes.drop_crossings(lines, links)
    for reach, lk in per_reach.items():  # which creeks were closed, and by what
        _, k = dikes.drop_crossings(lines, lk)
        if k:
            hit = sorted({nm for nm, *_ in lines} - {nm for nm, *_ in dikes.drop_crossings(lines, lk)[0]})
            print(f"  {reach}: {k} segments ({', '.join(hit[:6])}{' ...' if len(hit) > 6 else ''})")
    before = {name for name, *_ in lines}
    split = sorted({name.rsplit("_", 1)[0] for name, *_ in out if name not in before})
    nv = dikes.write_weir(Path(a.out), out)
    print(f"{len(links)} creek links; removed {n} weir segments; split: {', '.join(split) or 'none'}")
    print(f"wrote {a.out}: {len(out)} polylines, {nv} vertices")


if __name__ == "__main__":
    main()
