"""Per-field flooding in the Hurricane Sandy scenario runs: the field_flood_classes.py numbers
(share / wetdays / maxd per NJDEP LU/LC 2020 farm field) for sandy2012 instead of the
ordinary tide month.

Runs: sandy2012 x {intact, removed, breach_all_farm} x SLR {0, 0.3, 0.6, 1.0} m (tide only),
plus sandy2012_intact_slr000_rain (tide + Stage IV rain). Same fields, field ids, pixels and
rules as scripts/field_flood_classes.py, which must have run first (its gpkg holds the
fields). The period is the event's focus (Oct-Nov 2012, i.e. the whole Oct 15 - Nov 4 run).

Writes data/analysis/field_flood_sandy2012.csv: field_id, then share_<dikes>_slr<cm>,
wetdays_..., maxd_... per run (the rain run as <dikes> = intact_rain, slr000).
Usage:  python scripts/field_flood_sandy.py
"""

from __future__ import annotations

import geopandas as gpd

import field_flood_classes as ffc
import plot_scenarios as ps
from agri_sfincs import fieldflood

EVENT = "sandy2012"
RUNS = [(dk, s, "") for dk in ffc.DIKES for s in ffc.SLR_CM] + [("intact", 0, "_rain")]


def main() -> None:
    g = gpd.read_file(ffc.OUT / "field_flood_classes.gpkg")[["field_id", "geometry"]]
    f_sel, d_sel, fid = ffc.field_pixels(g)
    out = g[["field_id"]].copy()
    for dk, s, suffix in RUNS:
        run = ps.RUNS / f"{EVENT}_{dk}_slr{s:03d}{suffix}"
        st = ffc.run_stats(run, f_sel, d_sel, fid, len(g), event=EVENT)
        for c in st:
            out[f"{c}_{dk}{suffix}_slr{s:03d}"] = st[c].values
        print(f"{run.name}: {int((st.share >= fieldflood.SHARE).sum())} fields flood")
    out.to_csv(ffc.OUT / f"field_flood_{EVENT}.csv", index=False)


if __name__ == "__main__":
    main()
