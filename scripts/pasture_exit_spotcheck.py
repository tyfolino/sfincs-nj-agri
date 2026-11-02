"""NAIP check of the two CDL exit measures on low ground (FINDINGS §57): does counting pasture as
farmland (agri_sfincs.panel.farmland) remove false exits, or hide real ones?

Crop fields below MHHW + 1.5 m (data/analysis/exit_history/, scripts/exit_history.py), exits in
2010-2019, area-weighted random draws per state:
  cropland_only   left cropland, and never left farmland before CDL's 2024 change
  both            left farmland (so left cropland too)
Before = the latest NAIP at or before the exit year, after = the first at least 3 years later. IDs
are shuffled so the group is hidden while judging by eye: farmed / kept grass / abandoned /
ambiguous / not farmland, written by hand to data/imagery/pasture_exit_verdicts.csv.

Writes data/imagery/pasture_exit_key.csv (or OUT/key.csv) and sheets reports/figs/pasture_exit_<k>.png
(or OUT/sheet_<k>.png). Usage:  python scripts/pasture_exit_spotcheck.py [--out DIR]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pyproj import Transformer  # noqa: E402

from agri_sfincs import config, fields, naip  # noqa: E402

N = {"NJ": {"cropland_only": 14, "both": 7}, "DE": {"cropland_only": 7, "both": 2}}
LOW_M = 1.5
SEED, SHUFFLE_SEED = 20261102, 7
PER_SHEET = 9


def draw(rng) -> tuple[pd.DataFrame, dict]:
    rows, polys = [], {}
    for state, n in N.items():
        d = config.ANALYSIS_DIR / "exit_history"
        f = pd.read_csv(d / f"fields_{state}.csv", index_col=0, low_memory=False)
        fy = pd.read_csv(d / f"field_year_{state}.csv", low_memory=False)
        polys[state] = fields.load(state).set_index("field_id")
        w = fy[fy.year.between(2010, 2019)]
        crop = w[w.left_cropland == 1].groupby("field_id").year.min()
        farm = w[w.left_farmland == 1].groupby("field_id").year.min()
        ever = fy[(fy.left_farmland == 1) & (fy.year < 2024)].field_id.unique()
        low = f.index[f.crop_field & (f.m_above_mhhw < LOW_M)]
        groups = {"cropland_only": ([i for i in crop.index if i in low and i not in ever], crop),
                  "both": ([i for i in farm.index if i in low], farm)}  # fmt: skip
        for group, (ids, year) in groups.items():
            ha = f.ha.reindex(ids).values
            print(state, group, len(ids), "fields", round(ha.sum()), "ha")
            for j in rng.choice(len(ids), size=min(n[group], len(ids)), replace=False, p=ha / ha.sum()):
                i = ids[j]
                rows.append({"state": state, "group": group, "field_id": i, "year": int(year[i]), "ha": f.ha[i],
                             "m": f.m_above_mhhw[i], "county": f.county[i]})  # fmt: skip
    s = pd.DataFrame(rows).sample(frac=1, random_state=SHUFFLE_SEED).reset_index(drop=True)
    s["id"] = [f"F{i:02d}" for i in range(len(s))]
    return s, polys


def first_item(lon, lat, years):
    for y in years:
        href = naip.naip_item(lon, lat, y)
        if href:
            return y, href
    return None, None


def sheet(sub: pd.DataFrame, polys: dict, token: str, out: Path) -> None:
    to_utm = Transformer.from_crs(4326, 26918, always_xy=True)
    fig, axs = plt.subplots(3, 6, figsize=(18, 9.4))
    for ax in axs.flat:
        ax.axis("off")
    for j, r in enumerate(sub.itertuples()):
        g = gpd.GeoSeries([polys[r.state].geometry[r.field_id]], crs=polys[r.state].crs)
        pt = g.to_crs(4326).representative_point().iloc[0]
        gu = g.to_crs(26918).iloc[0]
        x0, y0, x1, y1 = gu.bounds
        half = max(200, min(1200, 0.65 * max(x1 - x0, y1 - y0)))
        res = half / 250
        cx, cy = to_utm.transform(pt.x, pt.y)
        pair = first_item(pt.x, pt.y, range(r.year, 2008, -1)), first_item(pt.x, pt.y, range(r.year + 3, 2025))
        for t, (yr, href) in enumerate(pair):
            ax = axs[j // 3, (j % 3) * 2 + t]
            if href is None:
                ax.set_title(f"{r.id} none", fontsize=9)
                continue
            ax.imshow(naip.chip(href, token, pt.x, pt.y, half=half, res=res))
            for p in [gu] if gu.geom_type == "Polygon" else gu.geoms:
                x, y = p.exterior.xy
                ax.plot((np.array(x) - (cx - half)) / res, ((cy + half) - np.array(y)) / res, color="yellow", lw=1)
            ax.set_xlim(0, 2 * half / res), ax.set_ylim(2 * half / res, 0)
            ax.set_title(f"{r.id} {yr}" + (f" exit {r.year}" if t == 0 else ""), fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=85)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    s, polys = draw(np.random.default_rng(SEED))
    key = a.out / "key.csv" if a.out else config.IMAGERY_DIR / "pasture_exit_key.csv"
    s.to_csv(key, index=False)
    token = naip.http_json(naip.SAS)["token"]
    for k in range(0, len(s), PER_SHEET):
        n = k // PER_SHEET + 1
        out = a.out / f"sheet_{n}.png" if a.out else config.REPORTS / "figs" / f"pasture_exit_{n}.png"
        sheet(s.iloc[k : k + PER_SHEET], polys, token, out)
        print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
