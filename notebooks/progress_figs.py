"""Figures for notebooks/model_progress_agecon.ipynb (the progress update for the ag-econ group).

Each public function draws one figure. Inputs (all local, gitignored or on scratch):
data/analysis/field_flood_classes.gpkg (scripts/field_flood_classes.py),
data/analysis/field_flood_sandy2012.csv (scripts/field_flood_classes.py --event sandy2012),
the run summaries <run>/summary/daily_county_crop.csv (scripts/event_summary.py) and the
forcing gauge levels.
A field "floods" when >= 10% of it is > 5 cm deep at some time in the period (agri_sfincs.fieldflood).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402
from matplotlib.dates import DateFormatter  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

from agri_sfincs import (  # noqa: E402  (also sets up PROJ)
    config,
    domain,
    fieldflood,
    region,
    runs,
)

plt.rcParams.update({"figure.dpi": 100, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e1e0d9", "grid.linewidth": 0.6,
                     "axes.edgecolor": "#c3c2b7", "axes.titleweight": "bold",
                     "axes.titlesize": 11, "axes.titlelocation": "left",
                     "axes.labelcolor": "#52514e", "xtick.color": "#52514e",
                     "ytick.color": "#52514e"})  # fmt: skip

UTM = domain.EPSG
SHARE = fieldflood.SHARE
LEVELS = list(runs.SLR_CM)  # sea-level rise, cm
LEVEL_NAME = {0: "Today's sea level", 30: "+0.3 m (1 ft)", 60: "+0.6 m (2 ft)", 100: "+1.0 m (3.3 ft)"}
SLR_SHORT = {0: "today", 30: "+0.3 m", 60: "+0.6 m", 100: "+1.0 m"}
SLR_COL = {0: "#86b6ef", 30: "#3987e5", 60: "#1c5cab", 100: "#0d366b"}  # light -> dark = more rise
DIKE_NAME = {"intact": "dikes as built", "breach_all_farm": "100 m breach in every farm dike",
             "removed": "dikes removed"}
DIKE_COL = {"intact": "#2a78d6", "breach_all_farm": "#1baf7a", "removed": "#eb6834"}
FLOOD, PROTECTED, DRY = "#c4471a", "#3987e5", "#dcdad3"
EVENT_NAME = {"tide2024oct": "ordinary tides of October 2024", "sandy2012": "Hurricane Sandy (Oct 2012)"}
FIELD_NOTE = ("Fields: 13,699 NJDEP Land Use 2020 farm polygons. A field floods when at least 10% of it "
              "is under more than 5 cm (2 in) of water at some time. Tide only, no rain.")

_fields = gpd.read_file(config.ANALYSIS_DIR / "field_flood_classes.gpkg")
_sandy = pd.read_csv(config.ANALYSIS_DIR / "field_flood_sandy2012.csv")
FIELDS = {"tide2024oct": _fields,
          "sandy2012": _fields[["field_id", "county", "ha", "geometry"]].merge(_sandy, on="field_id")}
outline = region.load_outline().to_crs(UTM)
counties = region.load_counties().to_crs(UTM)
states = region.load_states().to_crs(UTM)
_crest = gpd.read_file(config.STRUCT_DIR / "dikes_built.gpkg", layer="crest_points")
dikes = gpd.GeoDataFrame(geometry=[LineString(g.sort_values("s").geometry.tolist())
                                   for _, g in _crest.groupby("name") if len(g) > 1],
                         crs=_crest.crs).to_crs(UTM)  # fmt: skip
gauges = gpd.GeoDataFrame(pd.DataFrame(domain.NOAA_STATIONS),
                          geometry=gpd.points_from_xy([s["lon"] for s in domain.NOAA_STATIONS],
                                                      [s["lat"] for s in domain.NOAA_STATIONS]),
                          crs=4326).to_crs(UTM)  # fmt: skip
with xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc") as _wl:
    tide_sjs = _wl.waterlevel.sel(stations=domain.SHIP_JOHN).to_series()  # Ship John Shoal, m NAVD88


def flooded(event: str, dikes_: str, slr: int) -> pd.Series:
    """True where a field floods in that run."""
    return FIELDS[event][f"share_{dikes_}_slr{slr:03d}"] >= SHARE


def water_ha(event: str, dikes_: str, slr: int) -> float:
    """Area under water inside the flooded fields (ha)."""
    g, hit = FIELDS[event], flooded(event, dikes_, slr)
    return float((g[f"share_{dikes_}_slr{slr:03d}"] * g.ha)[hit].sum())


def daily_cropland_ha(run: str, baseline_run: str) -> pd.Series:
    """CDL cropland under > 5 cm of water each day (ha). The present-day run's first spin-up
    day is subtracted: ponds that CDL calls crops (as scripts/plot_scenarios.py)."""
    def total(r):
        d = pd.read_csv(runs.resolve(r) / "summary" / "daily_county_crop.csv", parse_dates=["date"])
        return d.groupby("date").area_gt_5cm_km2.sum()
    return ((total(run) - total(baseline_run).iloc[0]) * 100).clip(lower=0)


def _bare_map(ax, box) -> None:
    ax.set_facecolor("#dcebf7")  # open water / outside
    states.plot(ax=ax, color="#f4f4f2", edgecolor="#c3c2b7", lw=0.5)
    counties.plot(ax=ax, color="#f4f4f2", edgecolor="#c3c2b7", lw=0.5)
    outline.boundary.plot(ax=ax, color="#52514e", lw=0.8)
    ax.set_xlim(box[0], box[2]), ax.set_ylim(box[1], box[3])
    ax.set_xticks([]), ax.set_yticks([]), ax.grid(False), ax.set_aspect("equal")
    for s in ax.spines.values():
        s.set_visible(True)


def domain_map() -> None:
    box = outline.total_bounds + [-4000, -4000, 4000, 4000]
    fig, ax = plt.subplots(figsize=(6.8, 9.6))
    _bare_map(ax, box)
    _fields.plot(ax=ax, color="#d8c9a3", lw=0)
    dikes.plot(ax=ax, color=FLOOD, lw=1.4)
    gauges.plot(ax=ax, color="#0b0b0b", markersize=30, marker="^", zorder=5)
    for _, g in gauges.iterrows():
        if box[0] < g.geometry.x < box[2] and box[1] < g.geometry.y < box[3]:
            left = g["id"] == domain.SHIP_JOHN  # keep the label off the Cumberland dikes
            ax.annotate(g["name"].split(",")[0], (g.geometry.x, g.geometry.y),
                        xytext=(-6 if left else 6, -3), textcoords="offset points", fontsize=8,
                        ha="right" if left else "left")  # fmt: skip
    for _, c in counties[counties.fips.isin(domain.COUNTIES)].iterrows():
        p = c.geometry.intersection(outline.geometry.iloc[0]).representative_point()
        ax.annotate(c["name"].upper(), (p.x, p.y), ha="center", fontsize=10, color="#52514e",
                    weight="bold")
    ax.legend(handles=[Patch(fc="#f4f4f2", ec="#52514e", label="model area (38 whole watersheds)"),
                       Patch(color="#d8c9a3", label="farm fields (NJDEP Land Use 2020)"),
                       Line2D([], [], color=FLOOD, lw=1.4, label="dikes / meadow banks (USACE)"),
                       Line2D([], [], color="#0b0b0b", marker="^", lw=0, label="NOAA tide gauge")],
              loc="upper left", fontsize=8, framealpha=0.95)  # fmt: skip
    ax.set_title("SFINCS flood model: the Delaware-side watersheds of\n"
                 "Salem, Cumberland and Gloucester (3,460 km²)")
    fig.text(0.02, 0.01,
             "100 m grid with 10 m ground detail (NJ 2021 lidar). Driven by observed NOAA tides and radar\n"
             "rain; soils from USDA SSURGO; 101 km of dikes from the USACE National Levee Database.\n"
             "13,699 farm fields (76,400 ha); crop on each field from the USDA Cropland Data Layer 2024.",
             fontsize=8, color="#52514e", va="bottom")  # fmt: skip
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    plt.show()


def summary_bars() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    w = 0.26
    for ax, ev in zip(axes, ["tide2024oct", "sandy2012"]):
        for i, dk in enumerate(DIKE_NAME):
            ax.bar([j + (i - 1) * w for j in range(4)], [water_ha(ev, dk, s) for s in LEVELS],
                   width=w - 0.03, color=DIKE_COL[dk], label=DIKE_NAME[dk])
        ax.set_xticks(range(4), [SLR_SHORT[s] for s in LEVELS])
        ax.set_xlabel("sea level")
        ax.grid(axis="x", visible=False)
        ax.set_title(EVENT_NAME[ev][0].upper() + EVENT_NAME[ev][1:], fontsize=10)
    axes[0].set_ylabel("farm-field area under water (ha)")
    axes[0].legend(frameon=False, fontsize=9)
    fig.suptitle("Farm-field area the tide puts under water: today's dikes keep ordinary tides off nearly all\n"
                 "fields; with +0.6 m of sea-level rise about 2,000 ha flood in an ordinary month even with them",
                 x=0.01, ha="left", fontweight="bold", fontsize=11)  # fmt: skip
    fig.text(0.01, 0.0, FIELD_NOTE + " 1 ha = 2.47 acres.", fontsize=8, color="#52514e")
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    plt.show()


def field_maps(event: str) -> None:
    """2 x 2 maps, one per sea level: fields that flood with the dikes as built, and the extra
    fields that would flood if the dikes were removed."""
    g = FIELDS[event]
    anyhit = pd.concat([flooded(event, dk, s) for dk in ("intact", "removed") for s in LEVELS], axis=1).any(axis=1)
    x0, y0, x1, y1 = g[anyhit].total_bounds
    box = [x0 - 1500, y0 - 1500, x1 + 1500, y1 + 1500]
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 14.5))
    for ax, s in zip(axes.ravel(), LEVELS):
        with_d, without = flooded(event, "intact", s), flooded(event, "removed", s)
        extra = without & ~with_d
        _bare_map(ax, box)
        g[~with_d & ~extra].plot(ax=ax, color=DRY, lw=0)
        g[extra].plot(ax=ax, color=PROTECTED, lw=0)
        g[with_d].plot(ax=ax, color=FLOOD, lw=0)
        dikes.plot(ax=ax, color="#0b0b0b", lw=0.6)
        ax.set_title(f"{LEVEL_NAME[s]}: {with_d.sum():,} fields flood "
                     f"({water_ha(event, 'intact', s):,.0f} ha under water)\n"
                     f"+ {extra.sum():,} more if the dikes were removed", fontsize=10)
    fig.legend(handles=[Patch(color=FLOOD, label="floods with today's dikes"),
                        Patch(color=PROTECTED, label="floods only if the dikes were removed"),
                        Patch(color=DRY, label="stays dry"),
                        Line2D([], [], color="#0b0b0b", lw=0.6, label="dike")],
               loc="lower center", bbox_to_anchor=(0.5, 0.018), ncol=4, fontsize=9, frameon=False)  # fmt: skip
    head = {"tide2024oct": "Fields flooded by the ordinary tides of October 2024, as the sea rises: dikes hold\n"
                           "today's tides but are overtopped from about +0.6 m",
            "sandy2012": "Fields flooded by Hurricane Sandy's storm tide (Oct 2012), as the sea rises: the same\n"
                         "storm floods about 6 times more field area at +1.0 m than today"}[event]
    fig.suptitle(head, x=0.01, ha="left", fontweight="bold", fontsize=12)
    fig.text(0.01, 0.003, FIELD_NOTE, fontsize=9, color="#52514e")
    fig.tight_layout(rect=[0, 0.035, 1, 0.96])
    plt.show()


def oct_daily() -> None:
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6.2), sharex=True, height_ratios=[1, 1.4])
    t = tide_sjs["2024-10-01":"2024-10-31 23:00"]
    a1.plot(t.index, t, color="#52514e", lw=0.8)
    a1.set_ylabel("water level\n(m NAVD88)")
    a1.set_title("Observed tide at Ship John Shoal (today's sea level)", fontsize=10, fontweight="normal")
    for s in LEVELS:
        d = daily_cropland_ha(f"tide2024oct_intact_slr{s:03d}", "tide2024oct_intact_slr000")
        d = d["2024-10-01":"2024-10-31"]
        a2.plot(d.index + pd.Timedelta(hours=12), d, color=SLR_COL[s], lw=2, marker="o", ms=3,
                label=SLR_SHORT[s])
    a2.set_ylabel("cropland under water\neach day (ha)")
    a2.set_ylim(-100, 2900)
    a2.legend(title="sea level", frameon=False, fontsize=9, ncol=4, loc="upper right")
    a2.xaxis.set_major_formatter(DateFormatter("%b %d"))
    fig.suptitle("Day by day, October 2024, dikes as built: with sea-level rise, fields flood with every\n"
                 "spring tide (around Oct 2 and Oct 18) and partly drain between them",
                 x=0.01, ha="left", fontweight="bold", fontsize=11)  # fmt: skip
    fig.text(0.01, 0.0, "Cropland = USDA Cropland Data Layer 2024 crop pixels (wet farmland that CDL calls grass "
             "or wetland is left out). Each day counts its highest water.", fontsize=8, color="#52514e")
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    plt.show()


def sandy_daily() -> None:
    fig, ax = plt.subplot_mosaic([["tide", "tide"], ["slr", "rain"]], figsize=(11, 6.8),
                                 height_ratios=[1, 1.5], sharex=True)
    win = slice("2012-10-22", "2012-11-04 23:00")
    t = tide_sjs[win]
    ax["tide"].plot(t.index, t, color="#52514e", lw=0.8)
    ax["tide"].set_ylabel("water level\n(m NAVD88)")
    ax["tide"].set_title("Observed tide at Ship John Shoal", fontsize=10, fontweight="normal")
    base = "sandy2012_intact_slr000"
    for s in LEVELS:
        d = daily_cropland_ha(f"sandy2012_intact_slr{s:03d}", base)[win]
        ax["slr"].plot(d.index + pd.Timedelta(hours=12), d, color=SLR_COL[s], lw=2, marker="o", ms=3,
                       label=SLR_SHORT[s])
    ax["slr"].set_title("Tide only, dikes as built, with sea-level rise", fontsize=10)
    ax["slr"].legend(title="sea level", frameon=False, fontsize=9)
    for run, lab, col in [(base, "tide only", "#86b6ef"), (base + "_rain", "tide + Sandy's rain", "#eb6834")]:
        d = daily_cropland_ha(run, base)[win]
        ax["rain"].plot(d.index + pd.Timedelta(hours=12), d, color=col, lw=2, marker="o", ms=3, label=lab)
    ax["rain"].set_title("Today's sea level, dikes as built: adding the rain", fontsize=10)
    ax["rain"].legend(frameon=False, fontsize=9)
    ax["rain"].sharey(ax["slr"])
    ax["slr"].set_ylabel("cropland under water\neach day (ha)")
    for k in ("slr", "rain"):
        ax[k].set_xticks(pd.date_range("2012-10-22", "2012-11-04", freq="3D"))
        ax[k].xaxis.set_major_formatter(DateFormatter("%b %d"))
    fig.suptitle("Day by day, Hurricane Sandy: today its storm tide puts about 730 ha of cropland under water\n"
                 "and its rain more than doubles that; with +1.0 m of sea-level rise the tide alone floods ~4,300 ha",
                 x=0.01, ha="left", fontweight="bold", fontsize=11)  # fmt: skip
    fig.text(0.01, 0.0, "Cropland = USDA Cropland Data Layer 2012 crop pixels. Each day counts its highest water.",
             fontsize=8, color="#52514e")
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    plt.show()
