"""Farm -> wetland conversions in the model domain from NJDEP LU/LC, 1995-2020.

Reads data/landuse/njlulc_<y0>_<y1>.gpkg (scripts/fetch_njlulc.py), classifies every
farmed-before polygon with agri_sfincs.landuse.transition, clips to the model domain inside
the three study counties, and attaches the screening covariates of FINDINGS §21:
median ground height above recent MHHW and whether the polygon is in an NLD leveed area.

Caveat on the CONTROLS: the 1995-2002, 2002-2007 and 2007-2012 layers are NJDEP's *change*
layers (changed polygons only), so "stays farmed" exists only for 2012-15 and 2015-20.

Writes data/landuse/farm_wetland_transitions.gpkg (every classified polygon; EPSG:32618),
reports/farm_wetland.md and reports/figs/farm_wetland.png.
Usage:  python scripts/farm_wetland_transitions.py
"""

from __future__ import annotations

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rasterio.features import rasterize

import bayshore_exposure as be
from agri_sfincs import config, domain, landuse, region
from agri_sfincs.report import md_table

PERIODS = [(1995, 2002), (2002, 2007), (2007, 2012), (2012, 2015), (2015, 2020)]
OUT = config.LANDUSE_DIR / "farm_wetland_transitions.gpkg"
HA_PER_KM2 = 100.0


def study_area() -> gpd.GeoDataFrame:
    cty = region.load_counties().to_crs(domain.EPSG)
    cty = cty[cty.fips.isin(domain.COUNTIES)][["name", "geometry"]].rename(columns={"name": "county"})
    return gpd.overlay(cty, region.load_outline().to_crs(domain.EPSG)[["geometry"]], how="intersection")


def load() -> gpd.GeoDataFrame:
    parts = []
    area = study_area()
    for y0, y1 in PERIODS:
        g = gpd.read_file(config.LANDUSE_DIR / f"njlulc_{y0}_{y1}.gpkg").to_crs(domain.EPSG)
        g["cls"] = [landuse.transition(p, n, ln) for p, n, ln in zip(g.prev, g.next, g.label_next)]
        g = g[g.cls.notna()]
        g = gpd.overlay(g, area, how="intersection", keep_geom_type=True)
        g["ha"] = g.area / 1e4
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def add_exposure(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Median height above recent MHHW and leveed share, on the 30 m grid of §21."""
    G = be.load_grid()
    gg = g.to_crs(G.crs)
    lab = np.zeros(G.shape, dtype="int64")
    # rasterize in chunks keyed by row number + 1 (small polygons may miss every cell centre)
    for k in range(0, len(gg), 5000):
        sub = gg.iloc[k : k + 5000]
        r = rasterize([(geom, i + 1) for i, geom in zip(range(k, k + len(sub)), sub.geometry)],
                      out_shape=G.shape, transform=G.tr, fill=0, dtype="int64")  # fmt: skip
        lab = np.where(r > 0, r, lab)
    lev = gpd.read_file(be.STRUCT, layer="nld_leveed_areas").to_crs(G.crs)
    leveed = rasterize([(x, 1) for x in lev.geometry], out_shape=G.shape, transform=G.tr,
                       fill=0, dtype="uint8")  # fmt: skip
    ok = (lab > 0) & np.isfinite(G.hab)
    df = pd.DataFrame({"i": lab[ok] - 1, "hab": G.hab[ok], "lev": leveed[ok]})
    agg = df.groupby("i").agg(hab_p50=("hab", "median"), leveed=("lev", "mean"))
    g = g.copy()
    g["m_above_mhhw"] = agg.hab_p50.reindex(range(len(g))).values
    g["leveed_share"] = agg.leveed.reindex(range(len(g))).values
    # polygons that hit no cell centre: sample the grid at a representative point
    miss = g.m_above_mhhw.isna()
    if miss.any():
        pts = gg.loc[miss].representative_point()
        rr = ((pts.y - G.tr.f) / G.tr.e).astype(int).clip(0, G.shape[0] - 1)
        cc = ((pts.x - G.tr.c) / G.tr.a).astype(int).clip(0, G.shape[1] - 1)
        g.loc[miss, "m_above_mhhw"] = G.hab[rr.values, cc.values]
        g.loc[miss, "leveed_share"] = leveed[rr.values, cc.values]
    return g


def main() -> None:
    g = add_exposure(load())
    g.to_file(OUT, driver="GPKG")
    g["period"] = g.y0.astype(str) + "-" + g.y1.astype(str)
    wet = g[g.cls.isin(landuse.WETTING)]

    by_cls = g.pivot_table(index="cls", columns="period", values="ha", aggfunc="sum", fill_value=0)
    by_cls = by_cls.reindex([c for c in landuse.CLASSES if c in by_cls.index])
    by_cty = wet.pivot_table(index="county", columns="period", values="ha", aggfunc="sum",
                             fill_value=0)  # fmt: skip
    bands = pd.cut(wet.m_above_mhhw, [-np.inf, 0, 0.6, 1.5, 3, np.inf],
                   labels=["< 0", "0-0.6", "0.6-1.5", "1.5-3", "> 3"])  # fmt: skip
    by_band = wet.pivot_table(index=bands, columns="cls", values="ha", aggfunc="sum",
                              fill_value=0, observed=False)  # fmt: skip
    by_band.index.name = "m above MHHW"
    lev = wet.assign(behind=np.where(wet.leveed_share > 0.5, "leveed", "not leveed"))
    by_lev = lev.pivot_table(index="behind", columns="period", values="ha", aggfunc="sum",
                             fill_value=0)  # fmt: skip
    big = (wet.sort_values("ha", ascending=False).head(25)
           [["period", "county", "prev", "next", "label_next", "ha", "m_above_mhhw", "leveed_share"]]
           .reset_index(drop=True))  # fmt: skip
    big.index.name = "rank"
    tot = wet.ha.sum()
    lines = [
        "# Farm → wetland in NJDEP Land Use/Land Cover, 1995-2020 (2026-10-05)", "",
        "Generated by `scripts/farm_wetland_transitions.py` from NJDEP's photo-interpreted LU/LC "
        "(`scripts/fetch_njlulc.py`). Model domain inside Salem, Cumberland and Gloucester. "
        "Farmed = 2100/2140/2200/2300/2400; farm → wetland = to 2150 (former ag wetland), any 6xxx "
        "wetland, or 5xxx water other than 5300 artificial lakes (`agri_sfincs.landuse`). Areas in ha (100 ha = 1 km² ≈ 247 ac).", "",
        f"**Farm → wetland, all periods: {tot:,.0f} ha ({tot / HA_PER_KM2:.1f} km²) in "
        f"{len(wet):,} polygons.**", "",
        "Controls (\"stays farmed\") exist only for 2012-15 and 2015-20: the earlier layers are "
        "NJDEP change layers.", "",
        "## Every transition out of farming, by period (ha)", "",
        md_table(by_cls.round(0), floatfmt="{:,.0f}"), "",
        "## Farm → wetland by county and period (ha)", "", md_table(by_cty.round(0), floatfmt="{:,.0f}"), "",
        "## Farm → wetland by ground height above recent MHHW (ha)", "",
        md_table(by_band.round(0), floatfmt="{:,.0f}"), "",
        "## Farm → wetland behind NLD levees (> 50% of the polygon) or not (ha)", "",
        md_table(by_lev.round(0), floatfmt="{:,.0f}"), "",
        "## The 25 largest conversions", "", md_table(big.round(2), floatfmt="{:.2f}"), "",
    ]  # fmt: skip
    text = "\n".join(lines)
    (config.REPORTS / "farm_wetland.md").write_text(text + "\n")
    print(text)

    # map
    fig, ax = plt.subplots(figsize=(9, 11))
    area = study_area()
    area.plot(ax=ax, color="#eeeeee", edgecolor="#777777", lw=0.6)
    g[g.cls == landuse.STAYS].plot(ax=ax, color="#d9d9a0", lw=0)
    cols = {landuse.TO_COASTAL: "#08519c", landuse.TO_WETLAND: "#41ab5d",
            landuse.TO_FORMER: "#fd8d3c", landuse.TO_WATER: "#6baed6"}  # fmt: skip
    for c, col in cols.items():
        d = wet[wet.cls == c]
        if len(d):
            d.plot(ax=ax, color=col, edgecolor=col, lw=0.4)
            ax.plot([], [], "s", color=col, ms=9, label=f"{c[3:]} ({d.ha.sum():,.0f} ha)")
    ax.plot([], [], "s", color="#d9d9a0", ms=9, label="farmed 2012-20 (context)")
    ax.legend(loc="lower left", fontsize=8, framealpha=0.9)
    ax.set_xticks([]), ax.set_yticks([])
    ax.set_title("Farmland → wetland, NJDEP LU/LC 1995-2020")
    fig.tight_layout()
    out = config.REPORTS / "figs" / "farm_wetland.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
