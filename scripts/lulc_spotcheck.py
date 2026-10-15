"""NAIP spot-check of NJDEP LU/LC farm -> wetland polygons, both directions.

Two random, area-weighted samples from data/landuse/farm_wetland_transitions.gpkg
(scripts/farm_wetland_transitions.py):
  C (commission)  N_CONV polygons LU/LC calls farm -> wetland in 2007-12 or 2015-20: is
                  the field really out of farming afterwards?
  O (omission)    N_STAY polygons LU/LC calls farmed in both 2015 and 2020, on ground below
                  recent MHHW + 1 m: does it still LOOK farmed in 2023? (the Greenwich-south
                  fields were still "2140 agricultural wetland" in LU/LC 2020 although NAIP
                  2019 shows them dead and channelled: FINDINGS §21.)

NAIP chips (scripts/imagery_spotcheck.py: naip_item, chip) 600 m square at 2 m, before |
after, polygon outlined in yellow. Before/after years: 2010 | 2013 for 2007-12, 2015 | 2023
otherwise. Judging is by eye; verdicts go in reports/lulc_spotcheck.md.

Writes data/imagery/lulc_samples.csv, reports/figs/lulc_spotcheck_<k>.png.
Usage:  python scripts/lulc_spotcheck.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer

from agri_sfincs import config, landuse, naip

N_CONV, N_STAY, SEED = 24, 24, 20261006
HALF, RES = 300, 2.0
YEARS = {2007: (2010, 2013), 2015: (2015, 2023)}


def sample(g: gpd.GeoDataFrame, n: int, rng) -> gpd.GeoDataFrame:
    p = g.ha.values / g.ha.sum()
    return g.iloc[rng.choice(len(g), size=min(n, len(g)), replace=False, p=p)]


def main() -> None:
    g = gpd.read_file(config.LANDUSE_DIR / "farm_wetland_transitions.gpkg")
    rng = np.random.default_rng(SEED)
    conv = g[g.cls.isin(landuse.WETTING) & g.y0.isin([2007, 2015])]
    stay = g[(g.cls == landuse.STAYS) & (g.y0 == 2015) & (g.m_above_mhhw < 1.0)]
    s = pd.concat([sample(conv, N_CONV, rng).assign(kind="C"),
                   sample(stay, N_STAY, rng).assign(kind="O")], ignore_index=True)  # fmt: skip
    s["id"] = [f"{k}{i:02d}" for i, k in enumerate(s.kind)]
    cen = s.to_crs(4326).representative_point()
    s["lon"], s["lat"] = cen.x.values, cen.y.values
    token = naip.http_json(naip.SAS)["token"]
    to_utm = Transformer.from_crs(s.crs, "EPSG:26918", always_xy=True)
    per = 12
    for k in range(0, len(s), per):
        sub = s.iloc[k : k + per]
        fig, axs = plt.subplots(4, 6, figsize=(18, 13))
        for ax in axs.flat:
            ax.axis("off")
        for j, r in enumerate(sub.itertuples()):
            cx, cy = to_utm.transform(*Transformer.from_crs(4326, s.crs, always_xy=True)
                                      .transform(r.lon, r.lat))  # fmt: skip
            geom = gpd.GeoSeries([r.geometry], crs=s.crs).to_crs("EPSG:26918").iloc[0]
            rings = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
            for t, yr in enumerate(YEARS[int(r.y0)]):
                ax = axs[j // 3, (j % 3) * 2 + t]
                href = naip.naip_item(r.lon, r.lat, yr)
                if href:
                    ax.imshow(naip.chip(href, token, r.lon, r.lat, half=HALF, res=RES))
                for poly in rings:
                    if poly.geom_type != "Polygon":
                        continue
                    x, y = poly.exterior.xy
                    ax.plot((np.array(x) - (cx - HALF)) / RES, ((cy + HALF) - np.array(y)) / RES,
                            color="yellow", lw=1.0)  # fmt: skip
                ax.set_xlim(0, 2 * HALF / RES), ax.set_ylim(2 * HALF / RES, 0)
                ax.set_title(f"{r.id} {yr}" + (f" {int(r.prev)}→{int(r.next)} {r.ha:.1f} ha "
                             f"{r.m_above_mhhw:+.1f} m" if t == 0 else ""), fontsize=8)  # fmt: skip
        fig.suptitle("NJDEP LU/LC polygons (yellow), NAIP before | after, 600 m chips. "
                     "C = LU/LC says farm→wetland; O = LU/LC says still farmed, low ground", fontsize=11)  # fmt: skip
        fig.tight_layout()
        out = config.REPORTS / "figs" / f"lulc_spotcheck_{k // per + 1}.png"
        fig.savefig(out, dpi=90)
        plt.close(fig)
        print(f"wrote {out}")
    cols = ["id", "kind", "y0", "y1", "county", "prev", "next", "label_next", "ha", "m_above_mhhw",
            "leveed_share", "lon", "lat"]  # fmt: skip
    s[cols].to_csv(config.IMAGERY_DIR / "lulc_samples.csv", index=False)
    print(s[cols].round(2).to_string())


if __name__ == "__main__":
    main()
