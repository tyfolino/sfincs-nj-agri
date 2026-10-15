"""Screening: how much cropland sits low enough for the tide to reach it, now and with
sea-level rise? (The first check for the saltwater-intrusion lead, STATUS 2026-10-05.)

A bathtub with connectivity, on the 30 m CDL grid:

  high water  recent MHHW (mean daily max of OBSERVED hourly levels, 2021-2025, m NAVD88)
              at the forcing gauges, plus Fortescue and Bivalve from their 1983-2001
              datum sheets shifted by Reedy Point's rise since that epoch; spread over
              the domain by inverse-distance weighting (Cape May left out: ocean side)
  ground      bed_merged averaged to each 30 m cell (z_mean) and its maximum (z_max)
  levels      MHHW + dz, dz = 0, 0.3, 0.6, 1.0, 1.5 m (NJ STAP 2019: 2050 likely
              0.3-0.6 m, 2100 moderate emissions 0.6-1.5 m, both vs 2000), and the
              median annual maximum of 2021-2025 (a typical yearly storm tide) + dz
  low         z_mean < level                         (bathtub)
  connected   low AND reachable from tidal water through cells whose z_max < level
              (4-connected), or next to such a cell. Dikes and road embankments block
              it; tide gates and culverts through them are invisible to the DEM, so
              "low but not connected" = land that stays dry only while a dike/gate holds
  leveed      inside an NLD leveed area
  tidal water CDL open water (83, 111) or outside NJ (0: the bay) with z_mean < 0 m NAVD88

and, for the change check, cropland area per height band for every CDL year 2008-2025.

Writes reports/bayshore_exposure.md and reports/figs/bayshore_exposure.png; prints the
tables.  Usage:  python scripts/bayshore_exposure.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
from pyproj import Transformer
from rasterio.features import rasterize

from agri_sfincs import cdl, config, dikes, domain, exposure, maps, region
from agri_sfincs.report import md_table

YEARS = range(2008, 2026)
DZ = [0.0, 0.3, 0.6, 1.0, 1.5]
BANDS = [-np.inf, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0, np.inf]  # m above recent MHHW


def main() -> None:
    G = exposure.load_grid()
    win, tr, crs, shape, hw, st = G.win, G.tr, G.crs, G.shape, G.hw, G.stations
    z = {"mean": G.z_mean, "max": G.z_max}
    cdl25 = cdl.read(2025, win)
    valid = np.isfinite(z["mean"])

    cty = region.load_counties().to_crs(crs)
    cty = cty[cty.fips.isin(domain.COUNTIES)].reset_index(drop=True)
    county = rasterize([(g, i + 1) for i, g in enumerate(cty.geometry)], out_shape=shape,
                       transform=tr, fill=0, dtype="uint8")  # fmt: skip
    lev = dikes.leveed_areas(crs)
    leveed = rasterize([(g, 1) for g in lev.geometry], out_shape=shape, transform=tr,
                       fill=0, dtype="uint8").astype(bool)  # fmt: skip

    crop = np.isin(cdl25, list(cdl.CROPLAND)) & valid & (county > 0)
    seed = np.isin(cdl25, [0, 83, 111]) & (z["mean"] < 0.0)  # 0 = outside NJ: the bay
    zmax = np.where(valid, z["max"], np.inf)
    zmean = np.where(valid, z["mean"], np.inf)

    rows = []
    for base in ("mhhw", "annmax"):
        for dz in DZ:
            low, con = exposure.connected_low(zmean, zmax, hw[base] + dz, seed)
            for i, name in enumerate(cty["name"], start=1):
                m = crop & (county == i)
                rows.append({"level": f"{'MHHW' if base == 'mhhw' else 'annual max'} + {dz:.1f} m",
                             "county": name, "low_km2": (m & low).sum() * exposure.PX_KM2,
                             "connected_km2": (m & con).sum() * exposure.PX_KM2,
                             "low_leveed_km2": (m & low & leveed).sum() * exposure.PX_KM2})  # fmt: skip
    ex = pd.DataFrame(rows)
    tot = ex.groupby("level", sort=False)[["low_km2", "connected_km2", "low_leveed_km2"]].sum()
    tot.insert(0, "county", "all three")
    ex = pd.concat([ex, tot.reset_index()]).sort_values(["level", "county"], kind="stable")
    crop_tot = {n: (crop & (county == i)).sum() * exposure.PX_KM2 for i, n in enumerate(cty["name"], 1)}

    # cropland per height band, every CDL year (the change check)
    hab = np.where(valid, zmean - hw["mhhw"], np.nan)
    band = np.digitize(hab, BANDS[1:-1])
    labels = [f"< {BANDS[1]:g}"] + [f"{a:g}-{b:g}" for a, b in zip(BANDS[1:-2], BANDS[2:-1])] + [f"> {BANDS[-2]:g}"]
    inc = valid & (county > 0)
    ts = {}
    for y in YEARS:
        a = cdl.read(y, win)
        cm = np.isin(a, list(cdl.CROPLAND)) & inc
        ts[y] = np.bincount(band[cm], minlength=len(labels)) * exposure.PX_KM2
    ts = pd.DataFrame(ts, index=labels).T
    ts.index.name = "year"
    early, late = ts.loc[2008:2012].mean(), ts.loc[2021:2025].mean()
    chg = pd.DataFrame({"2008-12 km²": early, "2021-25 km²": late,
                        "change %": 100 * (late / early - 1)})  # fmt: skip
    chg.index.name = "m above MHHW"

    # where did 2008-12 cropland in the lowest bands go?
    first = {}
    for y in range(2008, 2013):
        first[y] = np.isin(cdl.read(y, win), list(cdl.CROPLAND))
    often = (sum(first.values()) >= 3) & inc  # cropped >= 3 of the 5 early years
    group = {"cropland": cdl.CROPLAND, "grass/pasture": {176}, "wetland": {87, 190, 195},
             "water": {83, 111}, "forest/shrub": {63, 64, 141, 142, 143, 152},
             "developed": {82, 121, 122, 123, 124}}  # fmt: skip
    late = [cdl.read(y, win) for y in range(2023, 2026)]
    fate = {}
    for col, sel in (("< MHHW + 1 m", often & (hab < 1.0)), ("1-3 m", often & (hab >= 1.0) & (hab < 3.0)),
                     ("> 3 m (upland)", often & (hab >= 3.0))):  # fmt: skip
        f = {g: np.mean([np.isin(a[sel], list(c)).mean() for a in late]) * 100
             for g, c in group.items()}  # fmt: skip
        f["other"] = 100 - sum(f.values())
        f["n km²"] = sel.sum() * exposure.PX_KM2
        fate[col] = f
    fate = pd.DataFrame(fate).round(1)
    fate.index.name = "2023-25 class (%)"

    # ── report ──────────────────────────────────────────────────────────────────
    stt = st[["name", "source", "mhhw", "annmax"]].rename(
        columns={"mhhw": "MHHW m NAVD88", "annmax": "median annual max"}).round(2)  # fmt: skip
    lines = [
        "# Bayshore cropland below the tide: a screening (2026-10-05)", "",
        "Map: `figs/bayshore_exposure.png`.", "",
        "Generated by `scripts/bayshore_exposure.py` (method in its docstring). Bathtub "
        "with connectivity on the 30 m CDL grid, CDL 2025 cropland (`agri_sfincs.cdl."
        "CROPLAND`; pasture excluded), Delaware-side model domain only.", "",
        "## High-water levels used (m NAVD88)", "", md_table(stt, floatfmt="{:.2f}"), "",
        "Cropland in the domain, by county (km²): "
        + ", ".join(f"{k} {v:.0f}" for k, v in crop_tot.items()) + ".", "",
        "## CDL 2025 cropland below each level (km²)", "",
        "`low` = ground below the level; `connected` = of that, reachable from tidal "
        "water over the DEM (dikes block); `low_leveed` = of `low`, inside an NLD leveed "
        "area.", "",
        md_table(ex.set_index(["level", "county"]).round(2), floatfmt="{:.2f}"), "",
        "## Cropland by height above recent MHHW, early vs late CDL years", "",
        md_table(chg.round(1), floatfmt="{:.1f}"), "",
        "## What 2008-12 cropland is now (CDL 2023-25 mean), by height above MHHW", "",
        "Cropland = cropped in at least 3 of 2008-12.", "", md_table(fate, floatfmt="{:.1f}"), "",
        "## Cropland by band, every year (km²)", "", md_table(ts.round(1), floatfmt="{:.1f}"), "",
    ]  # fmt: skip
    text = "\n".join(lines)
    (config.REPORTS / "bayshore_exposure.md").write_text(text + "\n")
    print(text)

    # ── map ─────────────────────────────────────────────────────────────────────
    cls = np.full(shape, np.nan)
    cm = crop
    cls[cm] = np.digitize(hab[cm], [0.0, 0.6, 1.5, 3.0])
    fig, ax = plt.subplots(figsize=(9, 11))
    ext = (tr.c, tr.c + tr.a * shape[1], tr.f + tr.e * shape[0], tr.f)
    ax.imshow(np.where(valid & (county > 0), 1, np.nan), extent=ext, cmap=ListedColormap(["#eeeeee"]))
    ax.imshow(np.where(seed, 1, np.nan), extent=ext, cmap=ListedColormap(["#a6cee3"]))
    cols = ["#b2182b", "#ef8a62", "#fddbc7", "#d9d9a0", "#bdbdbd"]
    ax.imshow(cls, extent=ext, cmap=ListedColormap(cols), vmin=-0.5, vmax=4.5, interpolation="nearest")
    lev.boundary.plot(ax=ax, color="k", lw=0.6)
    cty.boundary.plot(ax=ax, color="#555555", lw=1.0, ls="--")
    maps.label_places(ax, crs, color="k")
    wx, wy = Transformer.from_crs(4326, crs, always_xy=True).transform(
        [v[0] for v in domain.WATERS.values()], [v[1] for v in domain.WATERS.values()])  # fmt: skip
    for n, x, y in zip(domain.WATERS, wx, wy):
        ax.annotate(n, (x, y), fontsize=8, color="#1f5f8b", style="italic", ha="center")
    for i, n in enumerate(cty["name"]):
        c = cty.geometry.iloc[i].representative_point()
        ax.annotate(n.upper(), (c.x, c.y), fontsize=10, color="#555555", ha="center")
    names = ["cropland below today's MHHW", "0-0.6 m above (≈ 2050 rise)",
             "0.6-1.5 m above (≈ 2100 rise)", "1.5-3 m above", "> 3 m above"]  # fmt: skip
    for c, n in zip(cols, names):
        ax.plot([], [], "s", color=c, ms=9, label=n)
    ax.plot([], [], "-", color="k", lw=0.8, label="NLD leveed area")
    ax.plot([], [], "s", color="#a6cee3", ms=9, label="tidal water")
    ax.legend(loc="lower left", fontsize=8, framealpha=0.9)
    ax.set_xlim(ext[0], ext[1]), ax.set_ylim(ext[2], ext[3])
    ax.set_xticks([]), ax.set_yticks([])
    ax.set_title("CDL 2025 cropland by height above recent high tide (MHHW 2021-25)")
    fig.tight_layout()
    out = config.REPORTS / "figs" / "bayshore_exposure.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
