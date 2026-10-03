"""One figure per event run: county rainfall, daily flooded cropland, and a map of the
focus month's maximum depth on cropland.

Inputs: <run>/summary/{daily_county_crop.csv, focus_max_depth.tif} from
scripts/event_summary.py, and the event's MRMS file. Writes <run>/summary/event.png.

Usage:  python scripts/plot_event.py --run <run dir> --event sep2023
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import xarray as xr  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

from agri_sfincs import config, domain, region  # noqa: E402
from agri_sfincs.events import EVENTS  # noqa: E402

COLORS = {"Salem": "#1f77b4", "Cumberland": "#d62728", "Gloucester": "#2ca02c"}


def county_rain(event) -> pd.DataFrame:
    """Daily county-mean MRMS rain (mm/day), counties rasterized on the 0.01 deg grid."""
    src = {"sep2023": "mrms_2023-09.nc", "may2025": "mrms_2025-05.nc"}[event.name]
    with xr.open_dataset(config.DATA / "precip" / src) as ds:
        p = ds["precip"].load()
    lat, lon = p.lat.values, p.lon.values
    tr = from_origin(lon[0] - 0.005, lat[0] + 0.005, 0.01, 0.01)
    cty = region.load_counties().to_crs(4326)
    out = {}
    for fips, name in domain.COUNTIES.items():
        g = cty[cty.fips == fips].geometry.iloc[0]
        msk = rasterize([(g, 1)], out_shape=(len(lat), len(lon)), transform=tr, fill=0) > 0
        s = p.values[:, msk].mean(axis=1)
        out[name] = pd.Series(s, index=pd.to_datetime(p.time.values))
    # hour-ending totals -> the day they fell in
    return pd.DataFrame(out).shift(-1, freq="h").resample("D").sum()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--event", required=True, choices=sorted(EVENTS))
    a = ap.parse_args()
    ev = EVENTS[a.event]
    s = a.run / "summary"
    daily = pd.read_csv(s / "daily_county_crop.csv", parse_dates=["date"])
    flooded = daily.groupby(["date", "county"]).area_gt_5cm_km2.sum().unstack()
    crop = daily.groupby(["date", "county"]).cropland_km2.sum().unstack().iloc[0]
    rain = county_rain(ev)

    fig = plt.figure(figsize=(13, 7.5))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.5, 1], hspace=0.25, wspace=0.15)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[1, 0], sharex=ax1)
    ax3 = fig.add_subplot(gs[:, 1])
    w = 0.27
    for i, (name, col) in enumerate(COLORS.items()):
        ax1.bar(rain.index + pd.Timedelta(hours=(i - 1) * 8), rain[name], width=w,
                color=col, label=name)  # fmt: skip
        ax2.plot(flooded.index, 100 * flooded[name] / crop[name], color=col, lw=1.6,
                 label=f"{name} ({crop[name]:.0f} km² cropland)")  # fmt: skip
    ax1.set_ylabel("MRMS rain, county mean (mm/day)")
    ax1.legend(fontsize=8)
    ax2.set_ylabel("cropland with daily max depth > 5 cm (%)")
    ax2.legend(fontsize=8)
    f0 = pd.Timestamp(ev.focus + "-01")
    for ax in (ax1, ax2):
        ax.axvspan(f0, f0 + pd.offsets.MonthEnd(1) + pd.Timedelta(days=1), color="0.92", zorder=0)
        ax.tick_params(labelsize=8)
    ax1.set_title(f"{ev.name}: SFINCS v0 (smoke test; no river channels burned yet)",
                  fontsize=10, loc="left")  # fmt: skip

    with rasterio.open(s / "focus_max_depth.tif") as r:
        f = 10  # 10 m pixels -> 100 m block maxima
        full = r.read(1)
        b = r.bounds
    h, w_ = (full.shape[0] // f) * f, (full.shape[1] // f) * f
    md = np.nanmax(full[:h, :w_].reshape(h // f, f, w_ // f, f), axis=(1, 3))
    md = np.where(md > 0.05, md, np.nan)
    im = ax3.imshow(md, extent=(b.left, b.right, b.bottom, b.top), cmap="Blues", vmin=0,
                    vmax=0.5)  # fmt: skip
    region.load_counties().to_crs(r.crs).boundary.plot(ax=ax3, color="0.4", lw=0.6)
    region.load_outline().to_crs(r.crs).boundary.plot(ax=ax3, color="k", lw=0.8)
    ax3.set_xlim(b.left, b.right)
    ax3.set_ylim(b.bottom, b.top)
    ax3.set_xticks([])
    ax3.set_yticks([])
    ax3.set_title(f"max depth on cropland, {ev.focus} (m; > 5 cm, 100 m max)", fontsize=9)
    fig.colorbar(im, ax=ax3, shrink=0.6)
    fig.savefig(s / "event.png", dpi=120, bbox_inches="tight")
    print(f"wrote {s / 'event.png'}")


if __name__ == "__main__":
    main()
