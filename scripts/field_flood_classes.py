"""Per-field flood class for today's farmland: flooded today / dike-dependent / overtopped /
exposed, by sea-level rise (agri_sfincs.fieldflood), from the ordinary-tide-month scenario runs.

Fields = NJDEP LU/LC 2020 farm polygons (codes 2100 / 2140 / 2200 / 2300 / 2400) in Salem,
Cumberland and Gloucester. The LU/LC layer here keeps only polygons farmed in 2015
(scripts/fetch_njlulc.py), so fields first farmed in 2016-20 are missing (rare).

Per run (tide2024oct x {intact, removed, breach_all_farm} x SLR {0, 0.3, 0.6, 1.0} m, tide only):
every 10 m subgrid pixel of every field gets the daily max depth (zsmax of its model cell -
the pixel's ground, as scripts/event_summary.py, but on all field pixels, not CDL cropland),
over the focus month (Oct 2024). Per field:
  share   fraction of pixels whose month-max depth > 5 cm
  wetdays mean over the field's pixels of the days with depth > 5 cm (field-days per month)
  maxd    mean month-max depth over the flooded pixels (m)
A field floods in a run when share >= fieldflood.SHARE (10%). The breach runs, when present,
add first_breach (lowest level flooding with one 100 m gap in every farm bank) but do not
enter the class.
behind_levee = >= 50% of the field inside an NLD leveed area.

Writes data/analysis/field_flood_classes.{gpkg,csv}, reports/field_flood_classes.md and
reports/figs/field_flood_classes{,_zoom}.png.
Usage:  python scripts/field_flood_classes.py
"""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import xarray as xr  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.features import rasterize  # noqa: E402

import plot_scenarios as ps  # noqa: E402
from agri_sfincs import config, domain, fieldflood, landuse, region  # noqa: E402
from agri_sfincs.events import EVENTS  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

EVENT = "tide2024oct"
DIKES = ("intact", "removed", "breach_all_farm")
SLR_CM = (0, 30, 60, 100)
THRESH = 0.05
OUT = config.DATA / "analysis"
COLORS = {"flooded today": "#7f2704",
          "dike-dependent today": "#0d366b", "dike-dependent +0.3 m": "#1c5cab",
          "dike-dependent +0.6 m": "#3987e5", "dike-dependent +1.0 m": "#86b6ef",
          "+0.3 m": "#c4471a", "+0.6 m": "#f08a4b", "+1.0 m": "#f8c39a",
          fieldflood.SAFE: "#e2dccb"}  # fmt: skip


def color(cls: str) -> str:
    """Overtopped and exposed share a colour (both flood even with the dikes)."""
    return COLORS.get(cls, COLORS.get(cls.split(" ", 1)[-1], "#999999"))


def load_fields(crs) -> gpd.GeoDataFrame:
    g = gpd.read_file(config.LANDUSE_DIR / "njlulc_2015_2020.gpkg")
    g = g[g.next.map(landuse.is_farmed)].to_crs(crs).reset_index(drop=True)
    cty = region.load_counties().to_crs(crs)
    cty = cty[cty.fips.isin(domain.COUNTIES)][["name", "geometry"]].rename(columns={"name": "county"})
    pts = g[["geometry"]].copy()
    pts["geometry"] = g.representative_point()
    g["county"] = gpd.sjoin(pts, cty, how="left", predicate="within").groupby(level=0).county.first()
    g = g[g.county.notna()].reset_index(drop=True)
    lev = gpd.read_file(config.DATA / "structures" / "structures.gpkg", layer="nld_leveed_areas").to_crs(crs)
    inter = gpd.overlay(g[["geometry"]].reset_index(names="fid"), lev[["geometry"]], how="intersection")
    share = inter.assign(a=inter.area).groupby("fid").a.sum() / g.area
    g["behind_levee"] = share.reindex(g.index).fillna(0).values >= 0.5
    g["field_id"] = np.arange(1, len(g) + 1)
    g["ha"] = g.area / 1e4
    return g[["field_id", "county", "next", "label_next", "ha", "behind_levee", "geometry"]].rename(
        columns={"next": "lulc2020", "label_next": "lulc2020_label"})  # fmt: skip


def run_stats(run, f_sel, d_sel, fid, nfield, event: str = EVENT) -> pd.DataFrame:
    """Per field: share of pixels flooded (> 5 cm month max), mean wet days, mean max depth
    over flooded pixels, over ``event``'s focus period."""
    with xr.open_dataset(run / "sfincs_map.nc") as mp:
        day = pd.to_datetime(mp["timemax"].values) - pd.Timedelta(days=1)
        focus = EVENTS[event].in_focus(day)
        maxd = np.zeros(f_sel.size, "float32")
        wet = np.zeros(f_sel.size, "uint16")
        for k in np.flatnonzero(focus):
            h = mp["zsmax"][k].values.ravel()[f_sel] - d_sel
            h = np.where(np.isfinite(h) & (h > 0), h, 0).astype("float32")
            maxd = np.maximum(maxd, h)
            wet += h > THRESH
    npx = np.bincount(fid, minlength=nfield + 1).astype(float)
    fl = maxd > THRESH
    nfl = np.bincount(fid, weights=fl, minlength=nfield + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return pd.DataFrame({
            "share": nfl / npx,
            "wetdays": np.bincount(fid, weights=wet, minlength=nfield + 1) / npx,
            "maxd": np.bincount(fid, weights=np.where(fl, maxd, 0), minlength=nfield + 1) / nfl,
        }).iloc[1:].set_index(np.arange(1, nfield + 1))  # fmt: skip


def draw_fields(ax, g, win_ext, bd) -> None:
    water, wext, cty, lev = bd
    ax.set_facecolor(ps.LAND_COL)
    ax.imshow(water, extent=wext, origin="lower", cmap=matplotlib.colors.ListedColormap([ps.WATER_COL]),
              interpolation="nearest")  # fmt: skip
    g.plot(ax=ax, color=g["cls"].map(color), linewidth=0)
    for x, y in lev:
        ax.plot(x, y, color="#0b0b0b", lw=0.7)
    cty.boundary.plot(ax=ax, color="#52514e", lw=0.8, ls="--")
    px, py = Transformer.from_crs(4326, g.crs, always_xy=True).transform(
        [v[0] for v in ps.be.PLACES.values()], [v[1] for v in ps.be.PLACES.values()])  # fmt: skip
    for n, x, y in zip(ps.be.PLACES, px, py):
        if win_ext[0] < x < win_ext[1] and win_ext[2] < y < win_ext[3]:
            ax.plot(x, y, ".", color="#0b0b0b", ms=4)
            ax.annotate(n, (x, y), xytext=(3, 3), textcoords="offset points", fontsize=8)
    ax.set_xlim(win_ext[0], win_ext[1]), ax.set_ylim(win_ext[2], win_ext[3])
    ax.set_xticks([]), ax.set_yticks([])


def legend(ax) -> None:
    for k, c in COLORS.items():
        lab = k if not k.startswith("+") else f"floods even with dikes, {k}"
        ax.plot([], [], "s", color=c, ms=9, label=lab)
    ax.plot([], [], "-", color="#0b0b0b", lw=0.7, label="model dike")
    ax.legend(loc="lower left", fontsize=7.5, framealpha=0.95)


def maps(g, crs) -> None:
    bd = ps.backdrop(crs)
    hit = g[g.cls != fieldflood.SAFE]
    x0, y0, x1, y1 = hit.total_bounds
    pad = 3000
    fig, ax = plt.subplots(figsize=(9, 11))
    draw_fields(ax, g, (x0 - pad, x1 + pad, y0 - pad, y1 + pad), bd)
    legend(ax)
    ax.set_title("Farm fields (NJDEP LU/LC 2020) by when an ordinary tide month first floods them\n"
                 "(SFINCS, Oct 2024 tides + sea-level rise; > 10% of the field > 5 cm)", fontsize=10, loc="left")  # fmt: skip
    fig.tight_layout()
    fig.savefig(config.REPORTS / "figs" / "field_flood_classes.png", dpi=140)
    plt.close(fig)

    to = Transformer.from_crs(4326, crs, always_xy=True)
    fig, axes = plt.subplots(1, 2, figsize=(15, 8.2), gridspec_kw={"width_ratios": [0.85, 1.25]})
    for ax, (name, (lo0, la0, lo1, la1)) in zip(axes, ps.ZOOMS.items()):
        (xa, xb), (ya, yb) = to.transform([lo0, lo1], [la0, la1])
        draw_fields(ax, g, (xa, xb, ya, yb), bd)
        ax.set_title(name, fontsize=10, loc="left")
    legend(axes[0])
    fig.tight_layout()
    fig.savefig(config.REPORTS / "figs" / "field_flood_classes_zoom.png", dpi=130)
    plt.close(fig)


def subgrid_crs():
    with rasterio.open(ps.RUNS.parent / "subgrid" / "dep_subgrid_lev0.tif") as d:
        return d.crs


def field_pixels(g: gpd.GeoDataFrame):
    """Every 10 m subgrid pixel of every field: (flat model-cell index, ground elevation,
    field_id), for pixels inside the model grid with a finite ground."""
    with rasterio.open(ps.RUNS.parent / "subgrid" / "dep_subgrid_lev0.tif") as d:
        dep = d.read(1, masked=True).filled(np.nan)
        tr, shape = d.transform, d.shape
    ids = rasterize(zip(g.geometry, g.field_id), out_shape=shape, transform=tr, fill=0, dtype="uint32")
    with xr.open_dataset(ps.run_dir(EVENT, "intact", 0) / "sfincs_map.nc") as mp:
        zshape = mp["zsmax"].shape
        x0, y0 = float(mp.corner_x.min()), float(mp.corner_y.min())
        dx = float(np.diff(np.unique(mp.corner_x.values.round(3)))[0])
    rr, cc = np.nonzero(ids)
    nn = np.floor((tr.f + (rr + 0.5) * tr.e - y0) / dx).astype(np.int64)
    mm = np.floor((tr.c + (cc + 0.5) * tr.a - x0) / dx).astype(np.int64)
    ok = (nn >= 0) & (nn < zshape[1]) & (mm >= 0) & (mm < zshape[2]) & np.isfinite(dep[rr, cc])
    f_sel = (nn * zshape[2] + mm)[ok]
    d_sel = dep[rr, cc][ok]
    fid = ids[rr, cc][ok].astype(np.int64)
    return f_sel, d_sel, fid


def main() -> None:
    g = load_fields(subgrid_crs())
    f_sel, d_sel, fid = field_pixels(g)
    n = len(g)
    g["model_px_share"] = np.bincount(fid, minlength=n + 1)[1:] / np.maximum(g.ha.values * 100, 1)

    have = {}
    for dk in DIKES:
        for s in SLR_CM:
            run = ps.run_dir(EVENT, dk, s)
            log = run / "sfincs_log.txt"
            if not log.exists() or "Total time" not in log.read_text(errors="ignore"):
                continue  # not run, or still running
            st = run_stats(run, f_sel, d_sel, fid, n)
            for c in st:
                g[f"{c}_{dk}_slr{s:03d}"] = st[c].values
            have[(dk, s)] = True
            print(f"{run.name}: {int((st.share >= fieldflood.SHARE).sum())} fields flood")

    def first(dk):
        cols = [f"share_{dk}_slr{s:03d}" for s in SLR_CM]
        if not all(c in g for c in cols):
            return pd.Series(np.nan, index=g.index)
        return g[cols].apply(lambda r: fieldflood.first_level(r.values), axis=1)

    g["first_intact"], g["first_removed"], g["first_breach"] = first("intact"), first("removed"), first("breach_all_farm")
    g["cls"] = [fieldflood.classify(w, wo, b) for w, wo, b in zip(g.first_intact, g.first_removed, g.behind_levee)]
    g.loc[g.model_px_share < 0.5, "cls"] = "outside model"

    # flooded hectares inside each field, in the run that sets its class
    def defining_share(r):
        if r.cls.startswith("dike-dependent"):
            dk, lev = "removed", r.first_removed
        elif r.cls in (fieldflood.SAFE, "outside model"):
            return 0.0
        else:
            dk, lev = "intact", r.first_intact
        return r[f"share_{dk}_slr{int(round(100 * lev)):03d}"]

    g["flooded_ha_first"] = g.ha * g.apply(defining_share, axis=1)

    OUT.mkdir(exist_ok=True)
    g.to_file(OUT / "field_flood_classes.gpkg", driver="GPKG")
    g.drop(columns="geometry").to_csv(OUT / "field_flood_classes.csv", index=False)

    order = fieldflood.class_order() + ["outside model"]
    t = g.pivot_table(index="cls", columns="county", values="ha", aggfunc="sum", fill_value=0)
    t["total ha"] = t.sum(axis=1)
    t["fields"] = g.groupby("cls").size()
    t["ha flooded in them"] = g.groupby("cls").flooded_ha_first.sum()
    t = t.reindex([c for c in order if c in t.index])
    t.loc["all fields"] = t.sum()
    lev_t = g[g.cls.str.startswith(("dike", "overtopped", "flooded"))].groupby(["cls", "behind_levee"]).ha.sum().unstack(fill_value=0)
    br = ""
    if g.first_breach.notna().any() or ("breach_all_farm", 0) in have:
        b = g.assign(fb=g.first_breach.map(lambda x: "dry to +1.0 m" if math.isnan(x) else f"+{x:.1f} m"),
                     fi=g.first_intact.map(lambda x: "dry to +1.0 m" if math.isnan(x) else f"+{x:.1f} m"))  # fmt: skip
        br = "\n".join(["## Breach in every farm bank vs dikes as built (ha by first flooding level)", "",
                        "Rows: as built; columns: one 100 m gap at each farm system's lowest crest point.", "",
                        md_table(b.pivot_table(index="fi", columns="fb", values="ha", aggfunc="sum", fill_value=0).round(0),
                                 floatfmt="{:,.0f}"), ""])  # fmt: skip
    runs_used = ", ".join(f"{dk}_slr{s:03d}" for dk, s in have)
    lines = ["# Farm fields by when an ordinary tide month first floods them (2026-10-06)", "",
             "Generated by `scripts/field_flood_classes.py` (method in its docstring; rules in "
             "`agri_sfincs/fieldflood.py`). Map: `figs/field_flood_classes{,_zoom}.png`. Per-field table: "
             "`data/analysis/field_flood_classes.csv`.", "",
             f"Fields: {n:,} NJDEP LU/LC 2020 farm polygons, {g.ha.sum():,.0f} ha. Runs used: {runs_used}.", "",
             "A field floods in a run when > 10% of it sees > 5 cm at least once in the month. "
             "'Overtopped' = floods even with the dikes and lies behind an NLD levee; 'exposed' = the same "
             "with no levee. 'Dike-dependent +L' = floods at +L only without the dikes.", "",
             "## Hectares by class and county", "", md_table(t.round(0), floatfmt="{:,.0f}"), "",
             "'ha flooded in them' = the flooded part of those fields, in the run that sets the class.", "",
             "## Hectares by class and LU/LC 2020 code (2140 = agricultural wetland, modified: wet farmed "
             "ground that CDL mostly does not call cropland)", "",
             md_table(g.pivot_table(index="cls", columns="lulc2020", values="ha", aggfunc="sum", fill_value=0)
                      .reindex([c for c in order if c in set(g.cls)]).round(0), floatfmt="{:,.0f}"), "",
             "## Behind an NLD levee? (ha, threatened classes)", "", md_table(lev_t.round(0), floatfmt="{:,.0f}"), "",
             br]  # fmt: skip
    text = "\n".join(lines)
    (config.REPORTS / "field_flood_classes.md").write_text(text + "\n")
    print(text)
    maps(g[g.cls != "outside model"], g.crs)


if __name__ == "__main__":
    main()
