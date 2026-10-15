"""How much of each county's cropland the model domain covers, by year and crop.

For every CDL year on disk, counts 30 m pixels by (county, HUC12-or-outside, CDL class)
over New Jersey, then reports:

  1. per county (the three study counties + fringe): cropland km2 total, inside the
     ring, and the coverage fraction — the weight the analysis needs, since the loss
     data are whole-county;
  2. Gloucester cropland in its Great Egg Harbor headwater HUC12s — the area the
     "Delaware side only" decision gave up (domain.GREAT_EGG_GLOUCESTER);
  3. the top crops inside the domain per study county (mean over years).

Writes:
  data/cdl/pixel_counts.csv.gz     year, fips, huc12 ("" = outside both sets), code, px
  reports/cropland_coverage.md     the three summaries

Usage:  python scripts/cropland_coverage.py
"""

from __future__ import annotations

import re

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize

from agri_sfincs import cdl, config, domain, region
from agri_sfincs.report import md_table

PX_KM2 = 0.03 * 0.03  # a 30 m CDL pixel


def count_year(path, counties: gpd.GeoDataFrame, hucs: gpd.GeoDataFrame) -> pd.DataFrame:
    with rasterio.open(path) as src:
        a = src.read(1)
        crs, tr, shape = src.crs, src.transform, src.shape
        if abs(tr.a) != 30 or abs(tr.e) != 30:
            raise ValueError(f"{path.name}: expected 30 m pixels, got {tr.a}, {tr.e}")
    c = counties.to_crs(crs)
    h = hucs.to_crs(crs)
    cid = rasterize(
        ((g, i + 1) for i, g in enumerate(c.geometry)), out_shape=shape,
        transform=tr, fill=0, dtype="uint8",
    )  # fmt: skip
    hid = rasterize(
        ((g, i + 1) for i, g in enumerate(h.geometry)), out_shape=shape,
        transform=tr, fill=0, dtype="uint8",
    )  # fmt: skip
    keep = cid > 0
    key = (cid[keep].astype(np.int64) * 256 + hid[keep]) * 256 + a[keep]
    vals, n = np.unique(key, return_counts=True)
    out = pd.DataFrame(
        {"ci": vals // 65536, "hi": (vals // 256) % 256, "code": vals % 256, "px": n}
    )
    out["fips"] = c.fips.to_numpy()[out.ci - 1]
    hcodes = np.concatenate([[""], h.huc12.to_numpy()])
    out["huc12"] = hcodes[out.hi]
    return out[["fips", "huc12", "code", "px"]]


def main() -> None:
    counties = region.load_counties()
    dom = region.load_huc12()
    egg = region.load_huc12("great_egg_gloucester")
    hucs = pd.concat([dom, egg], ignore_index=True)
    if len(hucs) > 255:
        raise ValueError("uint8 HUC index overflow")

    files = sorted(config.CDL_DIR.glob(f"CDL_*_{domain.STATE_FIPS}.tif"))
    if not files:
        raise SystemExit("no CDL files — run scripts/fetch_cdl.py")
    counts = config.CDL_DIR / "pixel_counts.csv.gz"
    fresh = counts.exists() and counts.stat().st_mtime > max(
        f.stat().st_mtime for f in files + [region.HUC12_FILE, region.COUNTIES_FILE]
    )
    frames = [pd.read_csv(counts, dtype={"fips": str, "huc12": str}).fillna("")] if fresh else []
    for f in [] if fresh else files:
        year = int(re.search(r"CDL_(\d{4})_", f.name).group(1))
        t = count_year(f, counties, hucs)
        t.insert(0, "year", year)
        frames.append(t)
        print(f"  {year}: {t.px.sum() * PX_KM2:,.0f} km2 counted", flush=True)
    px = pd.concat(frames, ignore_index=True)
    if not fresh:
        px.to_csv(counts, index=False)
    else:
        print(f"  reusing {counts.name} (newer than every input)")

    px["crop"] = px.code.isin(cdl.CROPLAND)
    px["in_domain"] = px.huc12.isin(domain.HUC12)
    px["great_egg"] = px.huc12.isin(domain.GREAT_EGG_GLOUCESTER)
    crop = px[px.crop]
    names = {**domain.COUNTIES, **domain.COUNTIES_FRINGE}

    # 1. coverage per county x year
    g = crop.groupby(["fips", "year"])
    cov = pd.DataFrame(
        {
            "cropland_km2": g.px.sum() * PX_KM2,
            "in_domain_km2": crop[crop.in_domain].groupby(["fips", "year"]).px.sum()
            * PX_KM2,
        }
    ).fillna(0)
    cov = cov.loc[cov.index.get_level_values("fips").isin(names)]
    cov["coverage"] = cov.in_domain_km2 / cov.cropland_km2
    summ = cov.groupby("fips").agg(
        cropland_km2=("cropland_km2", "mean"),
        in_domain_km2=("in_domain_km2", "mean"),
        coverage_min=("coverage", "min"),
        coverage_mean=("coverage", "mean"),
        coverage_max=("coverage", "max"),
    )
    summ.insert(0, "county", summ.index.map(names))

    # 2. Gloucester's Great Egg cropland
    glo = crop[crop.fips == domain.GLOUCESTER]
    ge = glo[glo.great_egg].groupby("year").px.sum() * PX_KM2
    gt = glo.groupby("year").px.sum() * PX_KM2
    egg_tab = pd.DataFrame({"great_egg_km2": ge, "gloucester_cropland_km2": gt}).fillna(0)
    egg_tab["share"] = egg_tab.great_egg_km2 / egg_tab.gloucester_cropland_km2
    egg_crops = (
        glo[glo.great_egg].groupby("code").px.sum().div(len(files)).mul(PX_KM2)
        .sort_values(ascending=False).head(8)
    )  # fmt: skip

    # 3. top crops inside the domain per study county
    tops = []
    for fips, nm in domain.COUNTIES.items():
        s = (
            crop[(crop.fips == fips) & crop.in_domain].groupby("code").px.sum()
            .div(len(files)).mul(PX_KM2).sort_values(ascending=False).head(10)
        )  # fmt: skip
        tops.append(
            f"**{nm}**: "
            + ", ".join(f"{cdl.name(c)} {v:.1f}" for c, v in s.items())
        )

    years = f"{px.year.min()}–{px.year.max()} ({len(files)} years)"
    md = [
        "# Cropland coverage of the model domain",
        "",
        f"CDL {years}; cropland = `agri_sfincs.cdl.CROPLAND` (Grass/Pasture excluded). "
        "Areas are km², means over the years unless stated.",
        "",
        "## 1. County cropland inside the domain",
        "",
        md_table(summ),
        "",
        "## 2. Gloucester cropland in the Great Egg Harbor headwaters (left out)",
        "",
        md_table(egg_tab),
        "",
        "Main crops there (km², mean/yr): "
        + ", ".join(f"{cdl.name(c)} {v:.1f}" for c, v in egg_crops.items()),
        "",
        "## 3. Top crops inside the domain (km², mean/yr)",
        "",
        *[t + "  " for t in tops],
        "",
    ]
    config.REPORTS.mkdir(exist_ok=True)
    out = config.REPORTS / "cropland_coverage.md"
    out.write_text("\n".join(md))
    print("\n".join(md))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
