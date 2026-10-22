"""Does Landsat see water on the farm fields the spring storm-tide runs flood? A satellite check of
the storm panel's exposure (FINDINGS §37, §38), for the three storms with a clear scene within
about a day of the peak.

Cases (storm, scene day, reference day): a clear scene before the storm is the reference, so
water already there (ponds, wet winter ground) is not scored.
  storm2011apr  2011-04-17 (Landsat 7, ~13 h after the peak, near the next high tide)  ref 2011-03-08
  storm2012jun  2012-06-06 (Landsat 7, ~1.5 days after)                                  ref 2012-04-19
  storm2023jun  2023-06-05 (Landsat 9, ~1.5 days after)                                  ref 2023-05-26

Observed water (30 m Landsat pixel): clear (QA bits 0-5 unset) and MNDWI > MNDWI_WATER. Scored
pixels: inside a farm field (sandy_panel/fields.gpkg, the LU/LC 2012 farm polygons, inset
INSET_M so ditches and creeks along the edges stay out), clear in both scenes, and not water
in the reference. New water = water in the storm scene.

Model water: the run's hourly ``zs`` at the hour nearest the overpass, minus the 10 m subgrid
ground; a 10 m pixel is wet when deeper than runs.THRESH; a 30 m Landsat pixel is model-wet
when at least half of its 10 m pixels are. Also the run's peak (max ``zsmax``), which is what the
storm panel uses. Runs: <storm>_intact_slr000 (tide only) and _rain (tide + the storm's rain).

Scores per case, run and time (overpass / peak), over the scored pixels: observed and model
wet area, overlap; "found" = overlap / observed (how much observed water the model has),
"confirmed" = overlap / model (how much model water Landsat sees). Per field (>= MIN_PX scored
pixels): observed-flooded = >= SHARE of its scored pixels new water; model-flooded likewise.
By depth (low fields, tide only, overpass): the model's mean depth over each Landsat pixel's
10 m pixels, binned; per bin the share Landsat calls water and the mean MNDWI rise from the
reference. If deep model water is mostly seen, missed shallow water is a sensor limit; if not,
the model puts water where there is none.

Writes reports/storm_landsat.md and reports/figs/storm_landsat_<storm>.png (the N_ZOOM
TILE_M tiles holding the most observed or model water on low fields); with ``--model`` other
than runs.MODEL, storm_landsat_<model>.md and figs/storm_landsat_<storm>_<model>.png.
Usage:  python scripts/validate_storm_landsat.py [--model v1_100m]
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import xarray as xr  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

from agri_sfincs import config, domain, runs  # noqa: E402
from agri_sfincs import landsat as ls  # noqa: E402
from agri_sfincs import landsat_stac as stac  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

SANDY = config.ANALYSIS_DIR / "sandy_panel"
CASES = [("storm2011apr", "2011-04-17", "2011-03-08"),
         ("storm2012jun", "2012-06-06", "2012-04-19"),
         ("storm2023jun", "2023-06-05", "2023-05-26")]  # fmt: skip
INSET_M, RES = 15.0, 30.0
MNDWI_WATER = 0.0
SHARE, MIN_PX = 0.10, 3
DEPTH_BINS = [0, 0.05, 0.15, 0.30, 0.60, np.inf]  # m
N_ZOOM, TILE_M = 3, 6000.0
CRS = f"EPSG:{domain.EPSG}"
GREY, BLUE, ORANGE, AQUA = "#d9d9d9", "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED = "#222222", "#6b6b6b"


def landsat_grid(bounds):
    """30 m grid aligned to Landsat (pixel edges at 15 m mod 30) covering ``bounds``."""
    x0, y0, x1, y1 = bounds
    x0 = np.floor((x0 - 15) / RES) * RES + 15
    y1 = np.ceil((y1 - 15) / RES) * RES + 15
    w, h = int(np.ceil((x1 - x0) / RES)), int(np.ceil((y1 - y0) / RES))
    return from_origin(x0, y1, RES, RES), (h, w)


def water(items, tr, shape):
    """(clear, water, mndwi) arrays on the grid."""
    a = stac.mosaic(items, ["green", "swir16"], tr, shape, CRS)
    ok = (a["qa_pixel"] != 0) & ls.clear(a["qa_pixel"])
    g, s = ls.reflectance(a["green"]), ls.reflectance(a["swir16"])
    with np.errstate(divide="ignore", invalid="ignore"):
        mndwi = (g - s) / (g + s)
    ok &= np.isfinite(mndwi)
    return ok, ok & (mndwi > MNDWI_WATER), mndwi


def field_pixels(fields: gpd.GeoDataFrame):
    """10 m subgrid pixels inside the inset fields: x, y, ground z, field_id."""
    with rasterio.open(runs.subgrid_dep()) as d:
        dep, tr, shape = d.read(1, masked=True).filled(np.nan), d.transform, d.shape
    inset = fields.geometry.buffer(-INSET_M)
    keep = ~inset.is_empty
    ids = rasterize(zip(inset[keep], fields.field_id[keep]), out_shape=shape, transform=tr, fill=0, dtype="uint32")
    rr, cc = np.nonzero(ids)
    x, y = runs.pixel_centres(tr, rr, cc)
    z = dep[rr, cc]
    ok = np.isfinite(z)
    return x[ok], y[ok], z[ok], ids[rr, cc][ok].astype(np.int64)


def model_depth(run, when: pd.Timestamp | None, face: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Water depth (m, 0 where dry) per 10 m pixel at the hour nearest ``when``, or at the run's
    peak if None."""
    with xr.open_dataset(run / "sfincs_map.nc") as mp:
        if when is None:
            zs = mp["zsmax"].max("timemax").values.ravel()
        else:
            k = int(np.abs(pd.to_datetime(mp["time"].values) - when).argmin())
            zs = mp["zs"].isel(time=k).values.ravel()
    h = zs[face] - z
    return np.where(np.isfinite(h) & (h > 0), h, 0.0)


def to_landsat(px: np.ndarray, vals: np.ndarray, n: int) -> np.ndarray:
    """Mean of ``vals`` over each Landsat pixel's 10 m pixels (for booleans: the share True;
    NaN where none)."""
    cnt = np.bincount(px, minlength=n).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.bincount(px, weights=vals, minlength=n) / np.where(cnt > 0, cnt, np.nan)


def scores(obs: np.ndarray, mod: np.ndarray) -> dict:
    both = int((obs & mod).sum())
    return {"observed_ha": obs.sum() * 0.09, "model_ha": mod.sum() * 0.09, "both_ha": both * 0.09,
            "found": both / obs.sum() if obs.sum() else np.nan,
            "confirmed": both / mod.sum() if mod.sum() else np.nan}  # fmt: skip


def field_table(fid, obs, mods: dict, height: pd.Series) -> pd.DataFrame:
    """Per field: scored pixels, observed and model wet shares (from Landsat-pixel values)."""
    d = pd.DataFrame({"field_id": fid, "obs": obs, **mods})
    g = d.groupby("field_id")
    t = g.mean().add_suffix("_share")
    t["n_px"] = g.size()
    t = t[t.n_px >= MIN_PX]
    t["m_above_mhhw"] = height.reindex(t.index)
    return t


def zoom_tiles(tr, shape, lpx, hot) -> list[tuple[float, float, float, float]]:
    """The N_ZOOM TILE_M squares holding most ``hot`` pixels (bounds, EPSG:32618)."""
    xs = tr.c + (lpx[hot] % shape[1] + 0.5) * RES
    ys = tr.f - (lpx[hot] // shape[1] + 0.5) * RES
    k = pd.Series(1, index=pd.MultiIndex.from_arrays([xs // TILE_M, ys // TILE_M])).groupby(level=[0, 1]).size()
    return [(i * TILE_M, j * TILE_M, (i + 1) * TILE_M, (j + 1) * TILE_M) for i, j in k.nlargest(N_ZOOM).index]


def figure(storm, day, tr, shape, lpx, obs, mod, tiles, tag) -> None:
    """Scored field pixels in the zoom tiles: dry in both, model only, observed only, both."""
    cat = np.full(shape[0] * shape[1], np.nan)
    cat[lpx] = 0 + 1 * (mod & ~obs) + 2 * (obs & ~mod) + 3 * (obs & mod)
    cat = cat.reshape(shape)
    ext = [tr.c, tr.c + shape[1] * RES, tr.f - shape[0] * RES, tr.f]
    fig, axes = plt.subplots(1, len(tiles), figsize=(4.2 * len(tiles), 4.9), squeeze=False)
    for ax, b in zip(axes[0], tiles):
        ax.imshow(np.ma.masked_invalid(cat), cmap=ListedColormap([GREY, ORANGE, AQUA, BLUE]), vmin=-0.5, vmax=3.5,
                  extent=ext, interpolation="nearest")  # fmt: skip
        ax.set_xlim(b[0], b[2])
        ax.set_ylim(b[1], b[3])
        ax.set_xticks([])
        ax.set_yticks([])
        for sp_ in ax.spines.values():
            sp_.set_color("#cccccc")
        ax.set_title(f"{b[0] / 1000:.0f}-{b[2] / 1000:.0f} km E, {b[1] / 1000:.0f}-{b[3] / 1000:.0f} km N",
                     fontsize=8, color=MUTED)  # fmt: skip
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (BLUE, AQUA, ORANGE, GREY)]
    fig.legend(handles, ["water in both", "water seen by Landsat only", "water in the model only",
                         "dry in both"], fontsize=8, frameon=False, loc="lower center", ncol=4)  # fmt: skip
    fig.suptitle(f"{storm}: Landsat {day} vs the model (tide only) at the overpass hour, farm-field interiors "
                 f"clear in both scenes, 30 m pixels ({TILE_M / 1000:.0f} km tiles with the most water)",
                 fontsize=9, color=INK)  # fmt: skip
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    out = config.REPORTS / "figs" / f"storm_landsat_{storm}{tag}.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=runs.MODEL)
    a = ap.parse_args()
    tag = "" if a.model == runs.MODEL else f"_{a.model}"
    attrs = pd.read_csv(SANDY / "fields.csv").set_index("field_id")
    fields = gpd.read_file(SANDY / "fields.gpkg")[["field_id", "geometry"]].to_crs(CRS)
    x, y, z, fid = field_pixels(fields)
    tr, shape = landsat_grid(fields.total_bounds)
    col = np.floor((x - tr.c) / RES).astype(np.int64)
    row = np.floor((tr.f - y) / RES).astype(np.int64)
    lp10 = row * shape[1] + col  # Landsat pixel of each 10 m pixel
    n = shape[0] * shape[1]
    lpx = np.unique(lp10)  # Landsat pixels holding field interior
    # one field per Landsat pixel: the one holding most of its 10 m pixels
    lf = pd.DataFrame({"lp": lp10, "fid": fid}).groupby(["lp", "fid"]).size().reset_index(name="k")
    lf = lf.sort_values("k").groupby("lp").tail(1).set_index("lp").fid.reindex(lpx).values
    bbox_ll = fields.to_crs(4326).total_bounds
    with xr.open_dataset(runs.run_dir("tide2024oct", "intact", 0, model=a.model) / "sfincs_map.nc") as mp:
        face = runs.MapGrid.from_map(mp).face(x, y)
    inside = face >= 0
    low = attrs.m_above_mhhw < 1.5
    rows, frows, drows = [], [], []
    for storm, day, ref in CASES:
        it, rf = stac.items_on(day, bbox_ll), stac.items_on(ref, bbox_ll)
        when = pd.Timestamp(it[0]["properties"]["datetime"]).tz_convert(None)
        clear_s, water_s, mndwi_s = water(it, tr, shape)
        clear_r, water_r, mndwi_r = water(rf, tr, shape)
        scored = (clear_s & clear_r & ~water_r).ravel()[lpx] & (to_landsat(lp10, inside, n)[lpx] == 1)
        obs = water_s.ravel()[lpx]
        mods = {}
        for run_name, sfx in (("tide", ""), ("tide + rain", "_rain")):
            run = runs.run_dir(storm, "intact", 0, suffix=sfx, model=a.model)
            for t_name, t in (("overpass", when), ("peak", None)):
                h = np.zeros(len(z))
                h[inside] = model_depth(run, t, face[inside], z[inside])
                mod = to_landsat(lp10, h > runs.THRESH, n)[lpx] >= 0.5
                if (run_name, t_name) == ("tide", "overpass"):
                    depth_lp = to_landsat(lp10, h, n)[lpx]
                mods[f"{run_name}, {t_name}"] = mod
                for subset, m in (("all fields", np.ones(len(lpx), bool)),
                                  ("low fields (< 1.5 m above MHHW)", low.reindex(lf).fillna(False).values)):  # fmt: skip
                    s = scored & m
                    rows.append({"storm": storm, "scene": f"{day} {when:%H:%M} UTC", "run": run_name, "model at": t_name,
                                 "fields": subset, "scored_ha": s.sum() * 0.09, **scores(obs[s], mod[s])})  # fmt: skip
        lowpx = low.reindex(lf).fillna(False).values
        s = scored & lowpx
        rise = (mndwi_s - mndwi_r).ravel()[lpx]
        b = pd.cut(depth_lp[s], DEPTH_BINS, right=False)
        g = pd.DataFrame({"bin": b, "seen": obs[s], "rise": rise[s]}).groupby("bin", observed=False)
        drows.append(pd.DataFrame({"storm": storm, "model depth, m": [str(i) for i in g.size().index],
                                   "pixels": g.size().values, "Landsat water": g.seen.mean().values,
                                   "MNDWI rise": g.rise.mean().values}))  # fmt: skip
        ft = field_table(lf[scored], obs[scored], {k: v[scored] for k, v in mods.items()}, attrs.m_above_mhhw)
        for k in mods:
            o, m = ft.obs_share >= SHARE, ft[f"{k}_share"] >= SHARE
            frows.append({"storm": storm, "model": k, "fields scored": len(ft), "observed flooded": int(o.sum()),
                          "model flooded": int(m.sum()), "both": int((o & m).sum()),
                          "observed only": int((o & ~m).sum()), "model only": int((m & ~o).sum())})  # fmt: skip
        hot = scored & lowpx & (obs | mods["tide, overpass"])
        if hot.any():
            tiles = zoom_tiles(tr, shape, lpx, hot)
            figure(storm, day, tr, shape, lpx[scored], obs[scored], mods["tide, overpass"][scored], tiles, tag)
        print(storm, when, f"scored {scored.sum() * 0.09:.0f} ha", flush=True)
    d, f, dep = pd.DataFrame(rows), pd.DataFrame(frows), pd.concat(drows, ignore_index=True)
    print(md_table(d, floatfmt="{:,.2f}"))
    print(md_table(f))
    print(md_table(dep))
    figs = "\n".join(f"![](figs/storm_landsat_{s}{tag}.png)" for s, _, _ in CASES
                     if (config.REPORTS / "figs" / f"storm_landsat_{s}{tag}.png").exists())
    md = f"""# Spring storm tides: does Landsat see the water the model puts on the fields? ({a.model})

Generated by `scripts/validate_storm_landsat.py --model {a.model}` (method in its docstring). Three storms have
a clear Landsat scene within about a day and a half of the peak. Water = MNDWI > {MNDWI_WATER}
on farm-field interiors clear in both the storm scene and a pre-storm reference, and not water
in the reference. "found" = share of the water Landsat sees that the model also has;
"confirmed" = share of the model's water that Landsat sees. Model water at the overpass hour is
the fair comparison; the peak is what the storm panel uses.

## Pixels (30 m)

{md_table(d, floatfmt="{:,.2f}")}

## Fields (>= {SHARE:.0%} of the field's scored pixels wet; >= {MIN_PX} scored pixels)

{md_table(f)}

## By model depth (low fields, tide only, at the overpass hour)

The model's mean depth over each 30 m pixel; "Landsat water" = share of those pixels Landsat
calls water; "MNDWI rise" = mean MNDWI change from the reference scene (wetter = higher).

{md_table(dep)}

## Maps (tide-only run at the overpass hour)

{figs}

## Caveats

- MNDWI sees open water. Water under a crop canopy or in dense stubble is missed, so "found"
  and "confirmed" are lower bounds where fields are vegetated (June more than April).
- Landsat 7 (2011, 2012) has stripes of missing data; those pixels are not scored.
- The scene is hours to a day and a half after the peak; water that drained is gone, water
  that ponds behind banks stays. The model's drainage after the peak is not validated (§16).
- Saturated bare soil can read as water at MNDWI > 0.
"""
    out = config.REPORTS / f"storm_landsat{tag}.md"
    out.write_text(md)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
