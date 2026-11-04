"""SSURGO natural drainage class per map unit, for the farm-field tables (the land-use panel,
scripts/build_sandy_panel.py). Not a model input.

Same map units and the same DOMINANT-component rule (highest comppct_r) as
scripts/fetch_ssurgo.py, so drainage class, hydrologic soil group and ksat describe the same
soil. Kept separate so the HSG / ksat rasters the model reads are not regenerated (SSURGO is
refreshed each October). Source: USDA Soil Data Access REST API (no auth).

drainagecl is the soil's NATURAL drainage: "Very poorly drained", "Poorly drained", "Somewhat
poorly drained", "Moderately well drained", "Well drained", "Somewhat excessively drained",
"Excessively drained", or blank (water, urban land, pits). Ditched or tiled fields drain
better than their class says.

Writes data/soils/ssurgo_drainage.csv (mukey, drainagecl, comppct_r). Delaware (``--side de``,
2026-11-04): the map units of ssurgo_mapunits_de.gpkg, written to ssurgo_drainage_de.csv.
Usage:  python scripts/fetch_ssurgo_drainage.py [--side de]
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import pandas as pd

from agri_sfincs import config, domain
from agri_sfincs.net import post

SDA = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"


def sda(sql: str) -> list[list]:
    """As scripts/fetch_ssurgo.py."""
    return post(SDA, {"format": "JSON", "query": sql}, timeout=300).json().get("Table", [])


def path(side: str = "nj"):
    """The side's drainage table."""
    return config.SOILS_DIR / f"ssurgo_drainage{domain.side(side).files}.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--side", default="nj", choices=list(domain.SIDES))
    a = ap.parse_args()
    sfx, out_path = domain.side(a.side).files, path(a.side)
    mu = gpd.read_file(config.SOILS_DIR / f"ssurgo_mapunits{sfx}.gpkg", columns=["mukey"], ignore_geometry=True)
    mukeys = sorted(mu.mukey.astype(str).unique())
    rows = []
    for i in range(0, len(mukeys), 500):
        keys = ",".join(f"'{k}'" for k in mukeys[i : i + 500])
        rows += sda(f"SELECT mukey, cokey, comppct_r, drainagecl FROM component WHERE mukey IN ({keys})")
    c = pd.DataFrame(rows, columns=["mukey", "cokey", "comppct_r", "drainagecl"])
    c["comppct_r"] = pd.to_numeric(c.comppct_r)
    dom = c.sort_values("comppct_r", ascending=False).drop_duplicates("mukey")
    dom["drainagecl"] = dom.drainagecl.fillna("")
    out = dom[["mukey", "drainagecl", "comppct_r"]].sort_values("mukey")
    missing = set(mukeys) - set(out.mukey)
    out.to_csv(out_path, index=False)
    print(f"{len(out)} of {len(mukeys)} map units; no component: {len(missing)}")
    print(out.drainagecl.replace("", "(blank)").value_counts().to_string())
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
