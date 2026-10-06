"""Imagery spot-check of the CDL "cropland -> wetland" signal below MHHW + 1 m (FINDINGS §21).

Change pixel  cropland in >= 3 of CDL 2008-12, wetland (87, 190, 195) in >= 2 of CDL 2023-25,
              ground below recent MHHW + 1 m (scripts/bayshore_exposure.py's grid and surface)
Samples       N_CHANGE change pixels drawn at random (seeded), so each km² of the signal is
              equally likely: the share judged real estimates the share of AREA that is real;
              plus N_CONTROL low pixels CDL calls cropland throughout (to see what CDL "cropland"
              looks like down here)
Imagery       NAIP (USDA, public domain) summer 2010 and 2023, read as windows from the
              Microsoft Planetary Computer COGs (anonymous SAS token), 1 m

Writes data/imagery/spotcheck_samples.csv (the samples, CDL history 2008-12|13-22|23-25,
chip paths),
data/imagery/chips/*.png, and reports/figs/imagery_spotcheck_<k>.png (contact sheets: per
sample 2010 | 2023, the sampled 30 m pixel in yellow). The judging is by eye and goes in
reports/imagery_spotcheck.md. Also reports/figs/imagery_sites.png: 2 km NAIP time series at
the clusters the samples pointed to (SITES).

Usage:  python scripts/imagery_spotcheck.py
"""

from __future__ import annotations

import json
import os
import urllib.request

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

import bayshore_exposure as be
from agri_sfincs import cdl, config

OUT = config.DATA / "imagery"
N_CHANGE, N_CONTROL, SEED = 36, 12, 20261005
YEARS_IMG = (2010, 2023)
HALF_M = 120  # chip half-width
WET = (87, 190, 195)
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/naip"
SITES = {"Greenwich south (Cumberland)": (-75.293, 39.352),
         "Logan Twp, Raccoon Cr. (Gloucester)": (-75.3636, 39.8048)}  # fmt: skip
SITE_YEARS = (2010, 2013, 2017, 2019, 2023)
LETTER = {**{c: "C" for c in cdl.CROPLAND}, 176: "g", **{c: "W" for c in WET}, 83: "~",
          111: "~", **{c: "d" for c in (82, 121, 122, 123, 124)},
          **{c: "f" for c in (63, 64, 141, 142, 143, 152)}}  # fmt: skip

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")


def http_json(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})  # fmt: skip
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def naip_item(lon, lat, year) -> str | None:
    """HREF of the NAIP image covering (lon, lat) flown in ``year`` (None if none)."""
    d = http_json(STAC, {"collections": ["naip"], "limit": 50,
                         "intersects": {"type": "Point", "coordinates": [lon, lat]},
                         "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z"})  # fmt: skip
    f = d.get("features", [])
    return f[0]["assets"]["image"]["href"] if f else None


def chip(href, token, lon, lat, half=HALF_M, res=1.0) -> np.ndarray:
    """RGB at ``res`` m, a 2*``half`` m square centred on (lon, lat), in UTM 18N."""
    utm = "EPSG:26918"
    x, y = Transformer.from_crs(4326, utm, always_xy=True).transform(lon, lat)
    n = int(2 * half / res)
    tr = rasterio.transform.from_origin(x - half, y + half, res, res)
    with rasterio.open(f"/vsicurl/{href}?{token}") as s, \
            WarpedVRT(s, crs=utm, transform=tr, width=n, height=n,
                      resampling=Resampling.bilinear) as v:  # fmt: skip
        return np.moveaxis(v.read([1, 2, 3]), 0, -1)


def site_timelines(token) -> None:
    """2 km NAIP time series at the clusters the samples pointed to."""
    fig, axs = plt.subplots(len(SITES), len(SITE_YEARS), figsize=(4 * len(SITE_YEARS), 4.2 * len(SITES)))
    for i, (name, (lon, lat)) in enumerate(SITES.items()):
        for j, yr in enumerate(SITE_YEARS):
            ax = axs[i, j]
            ax.axis("off")
            href = naip_item(lon, lat, yr)
            if href:
                ax.imshow(chip(href, token, lon, lat, half=1000, res=2.0))
            ax.set_title(f"{name}, {yr}" if j == 0 else str(yr), fontsize=10)
    fig.suptitle("NAIP time series, 2 km squares", fontsize=12)
    fig.tight_layout()
    out = config.REPORTS / "figs" / "imagery_sites.png"
    fig.savefig(out, dpi=80)
    print(f"wrote {out}")


def history(win, rows, cols) -> list[str]:
    seqs = [""] * len(rows)
    for y in range(2008, 2026):
        a = be.read_cdl(y, win)[rows, cols]
        for i, c in enumerate(a):
            seqs[i] += LETTER.get(int(c), "o")
    return [s[:5] + "|" + s[5:15] + "|" + s[15:] for s in seqs]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "chips").mkdir(exist_ok=True)
    G = be.load_grid()
    win, tr, crs, shape, hab = G.win, G.tr, G.crs, G.shape, G.hab
    early = sum(np.isin(be.read_cdl(y, win), list(cdl.CROPLAND)).astype(int) for y in range(2008, 2013))
    late_w = sum(np.isin(be.read_cdl(y, win), WET).astype(int) for y in range(2023, 2026))
    late_c = sum(np.isin(be.read_cdl(y, win), list(cdl.CROPLAND)).astype(int) for y in range(2023, 2026))
    low = np.isfinite(hab) & (hab < 1.0) & (early >= 3)
    change, stable = low & (late_w >= 2), low & (late_c == 3)
    print(f"change {change.sum() * be.PX_KM2:.2f} km², stable low cropland {stable.sum() * be.PX_KM2:.2f} km²")

    rng = np.random.default_rng(SEED)
    picks = []
    for kind, m, n in (("change", change, N_CHANGE), ("control", stable, N_CONTROL)):
        idx = rng.choice(np.flatnonzero(m), size=n, replace=False)
        r, c = np.unravel_index(idx, shape)
        picks.append(pd.DataFrame({"kind": kind, "row": r, "col": c}))
    s = pd.concat(picks, ignore_index=True)
    x, y = tr.c + tr.a * (s.col + 0.5), tr.f + tr.e * (s.row + 0.5)
    s["lon"], s["lat"] = Transformer.from_crs(crs, 4326, always_xy=True).transform(x.values, y.values)
    s["m_above_mhhw"] = hab[s.row, s.col].round(2)
    s["cdl_history"] = history(win, s.row.values, s.col.values)
    s.insert(0, "id", [f"{'X' if k == 'change' else 'K'}{i:02d}" for i, k in enumerate(s.kind)])

    token = http_json(SAS)["token"]
    for yr in YEARS_IMG:
        paths = []
        for r in s.itertuples():
            p = OUT / "chips" / f"{r.id}_{yr}.png"
            if not p.exists():
                href = naip_item(r.lon, r.lat, yr)
                if href is None:
                    paths.append("")
                    continue
                plt.imsave(p, chip(href, token, r.lon, r.lat))
            paths.append(str(p.relative_to(config.ROOT)))
        s[f"naip_{yr}"] = paths
    s.to_csv(OUT / "spotcheck_samples.csv", index=False)

    # contact sheets: 4 rows x 3 samples, each sample = 2010 | 2023
    per = 12
    for k in range(0, len(s), per):
        sub = s.iloc[k : k + per]
        fig, axs = plt.subplots(4, 6, figsize=(18, 13))
        for ax in axs.flat:
            ax.axis("off")
        for j, r in enumerate(sub.itertuples()):
            for t, yr in enumerate(YEARS_IMG):
                ax = axs[j // 3, (j % 3) * 2 + t]
                f = getattr(r, f"naip_{yr}")
                if f:
                    ax.imshow(plt.imread(config.ROOT / f))
                    ax.add_patch(plt.Rectangle((HALF_M - 15, HALF_M - 15), 30, 30, fill=False,
                                               ec="yellow", lw=1.5))  # fmt: skip
                ax.set_title(f"{r.id} {yr}" + (f"  {r.m_above_mhhw:+.1f} m" if t == 0 else ""),
                             fontsize=9)  # fmt: skip
                if t == 0:
                    ax.text(0, 2 * HALF_M + 18, "CDL " + r.cdl_history, fontsize=7, family="monospace",
                            va="top")  # fmt: skip
        fig.suptitle("NAIP 2010 | 2023, 240 m chips; yellow = sampled CDL pixel. "
                     "History: C crop, W wetland, g grass, f forest, d developed, ~ water", fontsize=11)  # fmt: skip
        fig.tight_layout()
        out = config.REPORTS / "figs" / f"imagery_spotcheck_{k // per + 1}.png"
        fig.savefig(out, dpi=90)
        plt.close(fig)
        print(f"wrote {out}")
    print(s.drop(columns=["row", "col"]).to_string())
    site_timelines(token)


if __name__ == "__main__":
    main()
