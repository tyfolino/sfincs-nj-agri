"""NAIP check of Landsat-detected exits from farming, LOW vs UPLAND (are low-ground exits
just classifier noise on wet fields?).

From data/landuse/field_exit_events[_<tag>].parquet (scripts/field_history.py), draws at
random (area-weighted) N exits per stratum among exits in EXIT_YEARS, so NAIP brackets them:
  low     cell / unit ground below recent MHHW + 0.6 m
  upland  ground more than 3 m above recent MHHW
Before = the latest NAIP year <= exit year, after = the earliest NAIP year >= exit + 3
(NAIP NJ: 2010, 2013, 2015, 2017, 2019, 2022, 2023). Chips 300 m (cells) or 600 m (units)
with the unit outlined. Judging by eye: farmed before and not after = real.

Writes data/imagery/exit_samples[_<tag>].csv and reports/figs/exit_spotcheck[_<tag>]_<k>.png.
Usage:  python scripts/exit_spotcheck.py [--tag cells] [--n 18]
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer

import imagery_spotcheck as isc
from agri_sfincs import config

NAIP = [2010, 2013, 2015, 2017, 2019, 2022, 2023]
EXIT_YEARS = (2010, 2019)
SEED = 20261009


def bracket(y: int):
    before = max([n for n in NAIP if n <= y], default=None)
    after = min([n for n in NAIP if n >= y + 3], default=None)
    return before, after


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", default="")
    ap.add_argument("--n", type=int, default=18)
    a = ap.parse_args()
    sfx = f"_{a.tag}" if a.tag else ""
    E = pd.read_parquet(config.LANDUSE_DIR / f"field_exit_events{sfx}.parquet")
    E = E[E.exit & E.year.between(*EXIT_YEARS)]
    U = (gpd.read_file(config.LANDUSE_DIR / "field_cells.gpkg").rename(columns={"unit": "parent", "cell": "unit"})
         if a.tag == "cells" else gpd.read_file(config.LANDUSE_DIR / "field_units.gpkg"))  # fmt: skip
    U = U.set_index("unit")
    E = E.join(U[["m_above_mhhw", "county"]], on="unit")
    rng = np.random.default_rng(SEED)
    picks = []
    for name, sel in (("low", E.m_above_mhhw < 0.6), ("upland", E.m_above_mhhw > 3.0)):
        d = E[sel].drop_duplicates("unit")
        w = (d.ha * d.w).values
        i = rng.choice(len(d), size=min(a.n, len(d)), replace=False, p=w / w.sum())
        picks.append(d.iloc[i].assign(stratum=name))
    s = pd.concat(picks, ignore_index=True)
    s["id"] = [f"{'L' if t == 'low' else 'U'}{i:02d}" for i, t in enumerate(s.stratum)]
    geo = gpd.GeoSeries(U.loc[s.unit, "geometry"].values, crs=U.crs)
    cen = geo.to_crs(4326).representative_point()
    s["lon"], s["lat"] = cen.x.values, cen.y.values
    half, res = (150, 1.0) if a.tag == "cells" else (300, 2.0)
    token = isc.http_json(isc.SAS)["token"]
    to_utm = Transformer.from_crs(U.crs, "EPSG:26918", always_xy=True)
    per = 12
    for k in range(0, len(s), per):
        sub = s.iloc[k : k + per]
        fig, axs = plt.subplots(4, 6, figsize=(18, 13))
        for ax in axs.flat:
            ax.axis("off")
        for j, r in enumerate(sub.itertuples()):
            g = U.loc[r.unit, "geometry"]
            cx, cy = to_utm.transform(*gpd.GeoSeries([g.representative_point()], crs=U.crs).iloc[0].coords[0])
            gu = gpd.GeoSeries([g], crs=U.crs).to_crs("EPSG:26918").iloc[0]
            polys = [gu] if gu.geom_type == "Polygon" else list(getattr(gu, "geoms", []))
            for t, yr in enumerate(bracket(int(r.year))):
                ax = axs[j // 3, (j % 3) * 2 + t]
                if yr is None:
                    continue
                href = isc.naip_item(r.lon, r.lat, yr)
                if href:
                    ax.imshow(isc.chip(href, token, r.lon, r.lat, half=half, res=res))
                for p in polys:
                    if p.geom_type != "Polygon":
                        continue
                    x, y = p.exterior.xy
                    ax.plot((np.array(x) - (cx - half)) / res, ((cy + half) - np.array(y)) / res,
                            color="yellow", lw=1.0)  # fmt: skip
                ax.set_xlim(0, 2 * half / res), ax.set_ylim(2 * half / res, 0)
                ax.set_title(f"{r.id} {yr}" + (f"  exit {int(r.year)}  {r.m_above_mhhw:+.1f} m" if t == 0 else ""),
                             fontsize=9)  # fmt: skip
        fig.suptitle("Landsat-detected exits from farming: NAIP before | after (yellow = unit). "
                     "L = ground < MHHW + 0.6 m, U = > 3 m", fontsize=11)  # fmt: skip
        fig.tight_layout()
        out = config.REPORTS / "figs" / f"exit_spotcheck{sfx}_{k // per + 1}.png"
        fig.savefig(out, dpi=90)
        plt.close(fig)
        print(f"wrote {out}")
    s[["id", "stratum", "unit", "year", "ha", "m_above_mhhw", "county", "lon", "lat"]].to_csv(
        config.DATA / "imagery" / f"exit_samples{sfx}.csv", index=False)  # fmt: skip
    print(s[["id", "stratum", "unit", "year", "ha", "m_above_mhhw", "county"]].round(2).to_string())


if __name__ == "__main__":
    main()
