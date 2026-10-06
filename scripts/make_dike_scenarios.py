"""Weir files for the dike scenarios (plan §2.4): what if the meadow banks fail?

From the model's dike weirs (data/structures/dikes.weir, scripts/build_dikes.py):

  dikes_removed.weir      every crest capped at the local marsh level (recent MHHW
                          - MARSH_BELOW_MHHW, IDW between the bay gauges as in
                          scripts/bayshore_exposure.py): the banks are gone. Lowered crests,
                          not deleted weirs: the ridges are partly in the subgrid DEM, and a
                          weir at marsh level overrides them (FINDINGS §10, §14).
  breach_all_farm.weir    one BREACH_M breach in EVERY farm system at once
  breach/<slug>.weir      one BREACH_M breach in ONE farm system (the "what does this bank
                          protect?" runs)

A breach sits at the system's lowest crest vertex (a weak point; we do not know any bank's
real condition) and is cut to the local marsh level. Farm systems = NLD systems protecting
> 0.1 km² of cropland (dikes_built.gpkg crest_points ``farm``).

Writes data/structures/scenarios/{dikes_removed,breach_all_farm}.weir,
data/structures/scenarios/breach/<slug>.weir and data/structures/scenarios/breaches.csv.
Usage:  python scripts/make_dike_scenarios.py
"""

from __future__ import annotations

import re

import geopandas as gpd
import numpy as np
import pandas as pd

import bayshore_exposure as be
from agri_sfincs import config, dikes

STRUCT = config.DATA / "structures"
OUT = STRUCT / "scenarios"
MARSH_BELOW_MHHW, BREACH_M = 0.2, 100.0
CRS = "EPSG:32618"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def main() -> None:
    (OUT / "breach").mkdir(parents=True, exist_ok=True)
    lines = dikes.read_weir(STRUCT / "dikes.weir")
    st = be.high_water_stations()

    def marsh(x, y):
        return be.idw(st, "mhhw", np.asarray(x), np.asarray(y), CRS) - MARSH_BELOW_MHHW

    n = dikes.write_weir(OUT / "dikes_removed.weir", dikes.cap_crests(lines, marsh))
    print(f"dikes_removed.weir: {n} vertices capped at marsh level")

    cp = gpd.read_file(STRUCT / "dikes_built.gpkg", layer="crest_points")
    sysof = cp.drop_duplicates("name").set_index("name")[["system", "farm"]]
    rows, all_farm = [], [list(t) for t in lines]
    for system, names in sysof[sysof.farm].groupby("system").groups.items():
        idx = [i for i, ln in enumerate(lines) if ln[0] in set(names)]
        if not idx:
            continue
        # the system's lowest crest vertex
        i_line, j = min(((i, int(np.argmin(lines[i][3]))) for i in idx), key=lambda t: lines[t[0]][3][t[1]])
        name, x, y, z = lines[i_line]
        zb = float(marsh(x[j : j + 1], y[j : j + 1])[0])
        zb = min(zb, float(z[j]))
        zn = dikes.breach(x, y, z, j, BREACH_M, zb)
        one = list(lines)
        one[i_line] = (name, x, y, zn)
        dikes.write_weir(OUT / "breach" / f"{slug(system)}.weir", one)
        all_farm[i_line][3] = np.minimum(all_farm[i_line][3], zn)
        rows.append({"system": system, "slug": slug(system), "polyline": name, "x": float(x[j]),
                     "y": float(y[j]), "crest_before": float(z[j]), "breach_z": zb,
                     "vertices_lowered": int((zn < z).sum())})  # fmt: skip
    dikes.write_weir(OUT / "breach_all_farm.weir", [tuple(t) for t in all_farm])
    b = pd.DataFrame(rows).sort_values("system")
    b.to_csv(OUT / "breaches.csv", index=False)
    print(f"{len(b)} farm systems: breach/<slug>.weir + breach_all_farm.weir")
    print(b[["system", "crest_before", "breach_z", "vertices_lowered"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
