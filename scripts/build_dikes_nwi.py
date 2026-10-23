"""Delaware's dikes as a SFINCS weir file, from the perimeters of NWI diked / impounded
wetlands (FINDINGS §10, §14; plan step 3). NLD holds almost none of Delaware's banks (2
alignments in the DE ring), so the refuge pools (Bombay Hook, Ted Harvey, Prime Hook) and
diked marsh are found as USFWS NWI polygons with the "h" modifier
(data/structures/structures_de.gpkg, ``nwi_impounded``; scripts/fetch_structures.py --side de):
  estuarine (E...h)                  every polygon of >= MIN_E_ACRES
  palustrine / lake (P...h, L...h)   >= MIN_P_ACRES on low ground (median bed < LOW_M m NAVD88:
                                     the freshwater refuge pools, not the upland mill ponds,
                                     whose dams are in the lidar and the NID)
Each polygon's outer ring is a weir alignment. Crest = the lidar ridge along it
(agri_sfincs.dikes.ridge_along: the highest bed pixel within ±20 m, every 5 m), raw: no
notches are filled, so breaches stay open and pools are filled only over the crest or by rain
(the water-control structures are not modelled). Where a perimeter runs along upland the
"crest" is just the ground, and the weir does nothing there.

Writes data/structures/dikes_de.weir and data/structures/dikes_de.gpkg (the alignments with
their crest statistics) and prints a summary.
Usage:  python scripts/build_dikes_nwi.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from agri_sfincs import config, dikes, domain, region

SIDE = "de"
MIN_E_ACRES = 2.0
MIN_P_ACRES = 20.0
LOW_M = 2.0
OUT = config.STRUCT_DIR / "dikes_de.weir"


def main() -> None:
    g = gpd.read_file(config.structures_file(SIDE), layer="nwi_impounded").to_crs(domain.EPSG)
    outline = region.load_outline(SIDE).to_crs(domain.EPSG).geometry.iloc[0]
    g = g[g.representative_point().within(outline)].reset_index(drop=True)
    g["system"] = g.ATTRIBUTE.str[0]
    bed = dikes.Bed(SIDE)
    pts = g.representative_point()
    g["bed_p"] = bed.sample(pts.x.values, pts.y.values)
    keep = ((g.system == "E") & (g.ACRES >= MIN_E_ACRES)) | (
        g.system.isin(["P", "L"]) & (g.ACRES >= MIN_P_ACRES) & (g.bed_p < LOW_M))
    g = g[keep].reset_index(drop=True)
    lines, rows = [], []
    for i, r in g.iterrows():
        for k, line in enumerate(dikes.lines_of(r.geometry.exterior if r.geometry.geom_type == "Polygon"
                                                else r.geometry.convex_hull.exterior)):  # fmt: skip
            if line.length < 2 * dikes.STEP_M:
                continue
            s, x, y, ridge = dikes.ridge_along(line, bed)
            ok = np.isfinite(ridge)
            if ok.sum() < 2:
                continue
            name = f"nwi_{r.system}{i:04d}_{k}"
            lines.append((name, x[ok], y[ok], ridge[ok]))
            rows.append({"name": name, "attribute": r.ATTRIBUTE, "acres": r.ACRES, "km": line.length / 1e3,
                         "crest_p10": np.nanpercentile(ridge, 10), "crest_p50": np.nanmedian(ridge),
                         "geometry": line})  # fmt: skip
    dikes.write_weir(OUT, lines)
    t = gpd.GeoDataFrame(rows, crs=domain.EPSG)
    t.to_file(OUT.with_suffix(".gpkg"), driver="GPKG")
    s = t.assign(system=t.attribute.str[0]).groupby("system").agg(
        lines=("name", "size"), km=("km", "sum"), crest_p50=("crest_p50", "median"))
    print(pd.DataFrame(s).round(2).to_string())
    print(f"wrote {OUT} ({len(lines)} polylines, {t.km.sum():.0f} km) and {OUT.with_suffix('.gpkg')}")


if __name__ == "__main__":
    main()
