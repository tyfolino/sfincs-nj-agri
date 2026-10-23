"""Event runs: a copy of a static model + one event's forcing, ready to solve.

The first two events are the months the ag-econ collaborators flagged (2026-10-02):
  sep2023  Cumberland, $380k excess-moisture losses (tomato stage 3, corn at harvest)
  may2025  Salem, $66k (wheat at harvest, prevented planting, replant)
Each window starts ~2 weeks early so channels, lakes and the soil store (cnb ``seff``)
spin up before the month that matters.

Dike / sea-level scenario events (2026-10-05, plan §2.4): ``sandy2012`` (Hurricane Sandy;
the bay peak ~1.9 m NAVD88 is typical of the largest storm tides of 2002-2025),
``storm2024jan`` (the 2024-01-10 storm tide, ~ a median annual maximum) and ``tide2024oct``
(a month whose maximum ~ the median monthly maximum: ordinary spring tides). Scenario runs
add ``wl_offset`` (sea-level rise on the boundary) and may drop rain (``precip="none"``,
tide-only) or swap in lowered dike crests (``structures``; scripts/make_dike_scenarios.py).

Year runs ``y2003`` .. ``y2025`` (2026-10-05, FINDINGS §16 / §18): the calendar year
plus December of the year before as spin-up; focus = the whole year. Precipitation is
MRMS from 2016 (the first year whose spin-up December has MRMS gauge-corrected QPE;
it starts 2015-05-06) and Stage IV before, built per run window from the hourly year
files by ``agri_sfincs.precip`` (``Event.precip`` = a product name). Output is thinned
for a year: a DAILY map snapshot (zs, Seff) instead of hourly, still daily zsmax / twet /
cumprcp, his every 600 s (``Event.dtmapout``).

``Event.focus`` is the period that matters for reporting: ``"YYYY-MM"`` (one month),
``"YYYY"`` (a year) or ``"YYYY-MM/YYYY-MM"`` (a span of months, both included);
``focus_period`` turns it into [start, stop).

Forcing: hour-ending precipitation totals (``cumulative_input=True``,
``time_label="right"``), and the gap-filled NAVD88 gauge levels on the water-level
boundary. No wind, pressure or discharge: the domain is closed watersheds.

Every run writes DAILY restart files (``dtrstout`` = ``dtmaxout`` = 1 day), which is
what lets hpc/sfincs_run.slurm resume a preempted run (agri_sfincs.restart).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from agri_sfincs import config, domain

#: Gauges within this distance of a water-level boundary face force it (m). Cape May is
#: ~9 km from the southern bay cut, Reedy Point ~4 km from the mid-river edge.
WL_BUFFER_M = 15_000.0
#: The "chain" boundary (FINDINGS §41, the default since 2026-10-20): one point per
#: BND_SPACING_M square of boundary cells, each the lag-aware blend of its two neighbours on
#: waterlevel.CHAIN, at BND_STEP. "gauges" = v1 before that: the 5 observed gauges as points,
#: blended by SFINCS (loses range between gauges an hour or more apart in phase).
BND_SPACING_M = 1000.0
BND_STEP = "6min"
#: Initial water level (m NAVD88). With 0 m every diked field below 0 m started FULL and
#: could leave only through its check valve (v1, 2026-10-05); at -1 m they start drained,
#: and channels / the bay refill from the tide boundary within hours of the 2-week spin-up.
ZSINI = -1.0
#: Restart + max-output lattice (s). dtmaxout must divide dtrstout (agri_sfincs.restart).
DAY_S = 86_400.0
#: First year whose run (from the December before) is all MRMS gauge-corrected QPE.
MRMS_FIRST_YEAR = 2016
#: The gap-filled gauge levels end 2025-12-31T23 (data/gauges/waterlevel_forcing_navd88.nc).
WL_LAST_DAY = "2025-12-31"


def focus_period(focus: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[start, stop) of a focus string: "YYYY-MM", "YYYY" or "YYYY-MM/YYYY-MM"."""
    if "/" in focus:
        a, b = focus.split("/")
        return pd.Period(a, "M").start_time, (pd.Period(b, "M") + 1).start_time
    if len(focus) == 4:
        return pd.Timestamp(f"{focus}-01-01"), pd.Timestamp(f"{int(focus) + 1}-01-01")
    p = pd.Period(focus, "M")
    return p.start_time, (p + 1).start_time


@dataclass(frozen=True)
class Event:
    name: str
    tstart: str
    tstop: str
    #: a data-catalog source, or a product in agri_sfincs.precip.PRODUCTS ("mrms",
    #: "stage4"): then the window is cut from the hourly year files at staging
    precip: str
    focus: str  # the period that matters, for reporting (see focus_period)
    dtmapout: float = 3600.0  # map snapshots (zs, Seff); zsmax etc. are daily regardless

    @property
    def focus_start(self) -> pd.Timestamp:
        return focus_period(self.focus)[0]

    @property
    def focus_stop(self) -> pd.Timestamp:
        return focus_period(self.focus)[1]

    def focus_months(self) -> list[str]:
        """The focus period's months, "YYYY-MM"."""
        return [str(p) for p in pd.period_range(self.focus_start, self.focus_stop - pd.Timedelta("1s"), freq="M")]

    def in_focus(self, t) -> np.ndarray:
        """True where times / dates ``t`` fall in [focus_start, focus_stop)."""
        t = pd.DatetimeIndex(pd.to_datetime(t))
        return np.asarray((t >= self.focus_start) & (t < self.focus_stop))


def year_event(year: int) -> Event:
    """The calendar year ``year`` with December of the year before as spin-up."""
    stop = min(pd.Timestamp(f"{year + 1}-01-01"), pd.Timestamp(WL_LAST_DAY))
    return Event(f"y{year}", f"{year - 1}-12-01 00:00:00", f"{stop:%Y-%m-%d %H:%M:%S}",
                 "mrms" if year >= MRMS_FIRST_YEAR else "stage4", str(year),
                 dtmapout=DAY_S)  # fmt: skip


EVENTS = {
    "sep2023": Event("sep2023", "2023-08-15 00:00:00", "2023-10-01 00:00:00",
                     "mrms_2023_09", "2023-09"),
    "may2025": Event("may2025", "2025-04-15 00:00:00", "2025-06-01 00:00:00",
                     "mrms_2025_05", "2025-05"),
    "sandy2012": Event("sandy2012", "2012-10-15 00:00:00", "2012-11-05 00:00:00",
                       "stage4", "2012-10/2012-11"),
    # the other Sandy-class storm tides of 2002-25 (Ship John 1.90 / 1.92 / 1.87 m, FINDINGS §25),
    # for repeated exposure in the land-use test (§34)
    "storm2012dec": Event("storm2012dec", "2012-12-07 00:00:00", "2012-12-29 00:00:00",
                          "stage4", "2012-12"),
    "storm2016jan": Event("storm2016jan", "2016-01-09 00:00:00", "2016-01-31 00:00:00",
                          "mrms", "2016-01"),
    "storm2021oct": Event("storm2021oct", "2021-10-15 00:00:00", "2021-11-05 00:00:00",
                          "mrms", "2021-10/2021-11"),
    # the largest planting-season (Mar-Jun) storm tides at Ship John 2008-25, and Sep 2018 (1.91 m,
    # harvest): flood timing for the land-use test (§34). Peaks 1.68-1.91 m
    "storm2010mar": Event("storm2010mar", "2010-02-27 00:00:00", "2010-03-21 00:00:00", "stage4", "2010-03"),
    "storm2011apr": Event("storm2011apr", "2011-04-03 00:00:00", "2011-04-25 00:00:00", "stage4", "2011-04"),
    "storm2012jun": Event("storm2012jun", "2012-05-22 00:00:00", "2012-06-13 00:00:00", "stage4", "2012-06"),
    "storm2014apr": Event("storm2014apr", "2014-04-16 00:00:00", "2014-05-08 00:00:00", "stage4",
                          "2014-04/2014-05"),
    "storm2018sep": Event("storm2018sep", "2018-08-27 00:00:00", "2018-09-18 00:00:00", "mrms", "2018-09"),
    "storm2022apr": Event("storm2022apr", "2022-04-05 00:00:00", "2022-04-27 00:00:00", "mrms", "2022-04"),
    "storm2023jun": Event("storm2023jun", "2023-05-21 00:00:00", "2023-06-12 00:00:00", "mrms", "2023-06"),
    "storm2024spr": Event("storm2024spr", "2024-02-25 00:00:00", "2024-04-20 00:00:00", "mrms",
                          "2024-03/2024-04"),
    "storm2024jan": Event("storm2024jan", "2023-12-25 00:00:00", "2024-01-22 00:00:00",
                          "mrms", "2024-01"),
    "tide2024oct": Event("tide2024oct", "2024-09-24 00:00:00", "2024-11-01 00:00:00",
                         "mrms", "2024-10"),
    # creek-tide calibration (FINDINGS §40): ordinary tides before the 2023-06-04 storm, with
    # Greenwich and Hancocks Bridge recording; scored from day 4 (scripts/check_creek_tides.py)
    "tidecal2023may": Event("tidecal2023may", "2023-05-21 00:00:00", "2023-06-01 00:00:00",
                            "mrms", "2023-05"),
}  # fmt: skip
EVENTS |= {f"y{y}": year_event(y) for y in range(2003, 2026)}


def precip_source(event: Event, precip: str | None = None) -> str:
    """The catalog source for ``event``'s precipitation (``precip`` overrides the
    event's choice). A product name builds the window's forcing file and catalog entry
    ``<product>_<event>`` (agri_sfincs.precip.ensure_forcing)."""
    from agri_sfincs import precip as pr

    src = precip or event.precip
    if src not in pr.PRODUCTS:
        return src
    return pr.ensure_forcing(src, event.tstart, event.tstop, f"{src}_{event.name}")


def obs_points(side: str = "nj") -> gpd.GeoDataFrame:
    """Every USGS gauge inside the side's ring (inventory), the NOAA stations, and the CO-OPS
    tidal datum stations (data/channels[/de]/tidal_datum_nodes.csv: published mean ranges up
    the creeks, scripts/check_creek_tides.py), as SFINCS observation points named
    ``<agency>_<id>`` (``coops_<id>`` for the datum stations)."""
    sfx = domain.side(side).files
    inv = pd.read_csv(config.GAUGE_DIR / f"usgs_series{sfx}.csv", dtype={"site": str})
    inv = inv.drop_duplicates("site")
    pts = [(f"usgs_{r.site}", r.lon, r.lat) for r in inv.itertuples()]
    pts += [(f"noaa_{s['id']}", s["lon"], s["lat"]) for s in domain.NOAA_STATIONS]
    nf = config.channels_dir(side) / "tidal_datum_nodes.csv"
    if nf.exists():  # written by build_riverbeds.py
        nodes = pd.read_csv(nf, dtype={"id": str})
        pts += [(f"coops_{r.id}", r.lon, r.lat) for r in nodes.itertuples()]
    return gpd.GeoDataFrame(
        {"name": [p[0] for p in pts]},
        geometry=[Point(p[1], p[2]) for p in pts], crs=4326,
    )  # fmt: skip


def forcing_gauges(ids: list[str] | None = None):
    """The gap-filled gauge levels as hydromt wants them: INTEGER station index (it
    refuses the NOAA id strings: "gdf index must be unique integers") and no string
    variables. The NOAA ids stay on as a ``noaa_id`` coordinate. ``ids``: these stations
    only (default: all in the file, virtual gauges included)."""
    import xarray as xr

    ds = xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc")
    ds = ds[["waterlevel"]]
    if ids is not None:
        ds = ds.sel(stations=list(ids))
    ds = ds.load()
    ids = ds.stations.values.astype(str)
    ds = ds.assign_coords(stations=np.arange(1, len(ids) + 1), noaa_id=("stations", ids))
    # Without a CRS hydromt takes lon/lat as model (UTM) metres and slices every gauge
    # away ("No data left after spatial slicing").
    import hydromt  # noqa: F401  (registers the .vector accessor)

    ds.vector.set_crs(4326)  # in place
    return ds


def boundary_points(root: Path) -> tuple[np.ndarray, np.ndarray]:
    """(x, y) in the model CRS: one water-level boundary face (mask 2 in ``root``/sfincs.nc)
    per BND_SPACING_M square, the first in face order."""
    import xarray as xr

    with xr.open_dataset(Path(root) / "sfincs.nc") as g:
        on = g["mask"].values == 2
        x, y = g["mesh2d_face_x"].values[on], g["mesh2d_face_y"].values[on]
    key = pd.Series(list(zip(np.floor(x / BND_SPACING_M), np.floor(y / BND_SPACING_M))))
    first = (~key.duplicated()).to_numpy()
    return x[first], y[first]


def chain_forcing(root: Path, t0, t1, epsg: int, side: str = "nj"):
    """The chain boundary (BND_STEP, ``root``'s boundary faces) as a hydromt GeoDataset like
    forcing_gauges(): integer stations, lon/lat, a ``pair`` label per point. ``side``'s chain
    (waterlevel.CHAINS)."""
    import hydromt  # noqa: F401  (registers the .vector accessor)
    import xarray as xr
    from pyproj import Transformer

    from agri_sfincs import waterlevel

    chain, lags = waterlevel.CHAINS[side]
    g = forcing_gauges(chain)
    pad = pd.Timedelta("3h")
    lv = g.waterlevel.sel(time=slice(pd.Timestamp(t0) - pad, pd.Timestamp(t1) + pad)).to_pandas()
    lv.columns = g.noaa_id.values
    to_m = Transformer.from_crs(4326, epsg, always_xy=True)
    gx, gy = to_m.transform(g.lon.values, g.lat.values)
    x, y = boundary_points(root)
    index = pd.date_range(t0, t1, freq=BND_STEP)
    zs, pair = waterlevel.chain_boundary(lv, x, y, gx, gy, index, chain, lags)
    if zs.isna().any().any():
        raise ValueError("chain boundary has gaps (forcing file shorter than the event?)")
    lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(x, y)
    ds = xr.Dataset(
        {"waterlevel": (("time", "stations"), zs.to_numpy("float32"))},
        coords={"time": index, "stations": np.arange(1, len(x) + 1), "lon": ("stations", lon),
                "lat": ("stations", lat), "pair": ("stations", pair)},
    )  # fmt: skip
    ds.vector.set_crs(4326)
    return ds


def zero_precip(run: Path) -> None:
    """Rewrite a staged run's ``sfincs_netampr.nc`` with zero rain (same grid, times,
    variable name and encoding; temp file + rename, so a hard link is broken)."""
    import os

    import xarray as xr

    fn = Path(run) / "sfincs_netampr.nc"
    with xr.open_dataset(fn) as src:
        ds = src.load()
    var = "Precipitation"
    enc = {var: {k: v for k, v in ds[var].encoding.items()
                 if k in ("dtype", "_FillValue", "zlib", "complevel", "chunksizes", "contiguous")}}  # fmt: skip
    enc[var]["dtype"] = "float32"
    tenc = ds["time"].encoding
    enc["time"] = {k: tenc[k] for k in ("units", "calendar", "dtype") if k in tenc}
    new = ds.copy()
    new[var] = (ds[var] * 0).astype("float32")
    new[var].attrs = {**ds[var].attrs, "agri_sfincs": "zeroed: tide-only run"}
    tmp = fn.with_suffix(".nc.tmp")
    new.to_netcdf(tmp, encoding=enc)
    os.replace(tmp, fn)


def setup_event(static_root: Path, event: Event, run_name: str | None = None,
                structures: dict | None = None, zsini: float = ZSINI,
                precip: str | None = None, wl_offset: float = 0.0,
                boundary: str = "chain") -> Path:  # fmt: skip
    """Copy ``static_root`` to config.MODELS/<static>/runs/<run_name> and add forcing.

    ``structures`` ({"drnfile": path} ...) REPLACES the static model's structure files in
    this run only (e.g. the high gate coefficient). ``zsini`` is the initial water level
    (m NAVD88; FINDINGS §14 / §16). ``precip`` overrides the event's precipitation
    source (a catalog source or a product, see precip_source); ``"none"`` = no rain
    (a tide-only run). ``wl_offset`` (m) is added to the boundary water levels: sea-level
    rise. ``boundary``: "chain" (default) or "gauges" (v1 before 2026-10-20, to reproduce
    older runs); see BND_STEP."""
    from hydromt_sfincs import SfincsModel

    from agri_sfincs import waterlevel
    from agri_sfincs.runs import model_side

    if boundary not in ("chain", "gauges"):
        raise ValueError(f"boundary must be 'chain' or 'gauges', not {boundary!r}")

    run = static_root / "runs" / (run_name or event.name)
    if run.exists():
        raise FileExistsError(f"{run} exists")
    t0, t1 = pd.Timestamp(event.tstart), pd.Timestamp(event.tstop)
    if (t1 - t0) % pd.Timedelta(seconds=DAY_S):
        raise ValueError(f"{event.name}: the window must be whole days (restart lattice)")
    no_rain = precip == "none"
    # tide-only still WRITES the event's rain file, then zeroes it: the native build
    # segfaults at start-up with cnb infiltration and no precipitation file (2026-10-05)
    precip_src = precip_source(event, None if no_rain else precip)  # may add a catalog entry
    shutil.copytree(static_root, run, ignore=shutil.ignore_patterns("runs", "gis"))

    sf = SfincsModel(data_libs=[str(config.CATALOG)], root=str(run), mode="r+")
    sf.read()
    sf.config.update(
        {
            "tref": t0.to_pydatetime(),
            "tstart": t0.to_pydatetime(),
            "tstop": t1.to_pydatetime(),
            "tspinup": 3600.0,
            "zsini": float(zsini),
            "advection": 1,
            "dtmapout": float(event.dtmapout),
            "dtmaxout": DAY_S,  # daily zsmax and twet
            "dtrstout": DAY_S,
            "dthisout": 600.0,
            "storecumprcp": 1,
            "storetwet": 1,
            "twet_threshold": 0.05,
        }
    )
    if boundary == "chain":
        gauges = chain_forcing(run, t0, t1, domain.EPSG, model_side(static_root))
    else:
        gauges = forcing_gauges(waterlevel.FORCING)
    if wl_offset:
        gauges["waterlevel"] = gauges.waterlevel + float(wl_offset)
    sf.water_level.create(geodataset=gauges, buffer=WL_BUFFER_M, merge=False)
    sf.precipitation.create(precip=precip_src, cumulative_input=True,
                            time_label="right", aggregate=False)  # fmt: skip
    sf.observation_points.create(locations=obs_points(model_side(static_root)), merge=False)
    sf.write()
    # sf.write() rewrites sfincs.inp from hydromt's config; re-point infiltration.
    from agri_sfincs.build import patch_infiltration_keys, stage_structures

    patch_infiltration_keys(run)
    if no_rain:
        zero_precip(run)
    # hydromt also RE-WRITES sfincs.weir on read/write, rounding crests to 0.1 m
    # (2026-10-05): restore the static model's own files, then any per-run override.
    from agri_sfincs.build import STRUCTURE_FILES

    sources = {k: static_root / f for k, f in STRUCTURE_FILES.items()
               if (static_root / f).is_file()}  # fmt: skip
    sources.update(structures or {})
    stage_structures(run, sources)
    return run
