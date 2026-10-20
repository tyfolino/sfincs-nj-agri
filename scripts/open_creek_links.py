"""Reopen the tidal creeks that bank weirs close at the model's resolution (FINDINGS §40).

SFINCS puts a weir on every cell link one of its segments crosses, so a meadow bank within
half a cell of a creek can land on the links the creek itself flows through. On v1_100m this
closes Alloway Creek ~3 km above Hancocks Bridge: the upper 13 km never sees a tide. This
drops every weir segment that crosses a link along a tidal centreline
(data/elevation/riverbed_centrelines.gpkg, kind "tidal"; agri_sfincs.runs.centreline_links,
agri_sfincs.dikes.drop_crossings). On a uniform 100 m grid both cells of such a link hold the
channel, so no bank between channel and field is lost that the grid could represent.

Writes data/structures/dikes_open.weir (from dikes.weir) and prints what it removed.
Usage:  python scripts/open_creek_links.py [--weir data/structures/dikes.weir] [--out ...] [--model v1_100m]
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
    ap.add_argument("--model", default=runs.MODEL)
    a = ap.parse_args()
    with xr.open_dataset(runs.run_dir("tide2024oct", "intact", 0, model=a.model) / "sfincs_map.nc") as mp:
        grid = runs.MapGrid.from_map(mp)
    c = gpd.read_file(config.ELEV_DIR / "riverbed_centrelines.gpkg")
    links = []
    for r in c[c.kind == "tidal"].itertuples():
        links += runs.centreline_links(grid, r.geometry)
    lines = dikes.read_weir(Path(a.weir))
    out, n = dikes.drop_crossings(lines, links)
    before = {name for name, *_ in lines}
    split = sorted({name.rsplit("_", 1)[0] for name, *_ in out if name not in before})
    nv = dikes.write_weir(Path(a.out), out)
    print(f"{len(links)} creek links; removed {n} weir segments; split: {', '.join(split) or 'none'}")
    print(f"wrote {a.out}: {len(out)} polylines, {nv} vertices")


if __name__ == "__main__":
    main()
