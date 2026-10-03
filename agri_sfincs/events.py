"""Event runs: a copy of a static model + one event's forcing, ready to solve.

The first two events are the months the ag-econ collaborators flagged (2026-10-02):
  sep2023  Cumberland, $380k excess-moisture losses (tomato stage 3, corn at harvest)
  may2025  Salem, $66k (wheat at harvest, prevented planting, replant)
Each window starts ~2 weeks early so channels, lakes and the soil store (cnb ``seff``)
spin up before the month that matters.

Forcing: MRMS Pass2 hourly (hour-ending totals -> ``cumulative_input=True``,
``time_label="right"``), and the gap-filled NAVD88 gauge levels on the water-level
boundary. No wind, pressure or discharge: the domain is closed watersheds.
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
#: Restart + max-output lattice (s). dtmaxout must divide dtrstout (bight restart.py).
DAY_S = 86_400.0


@dataclass(frozen=True)
class Event:
    name: str
    tstart: str
    tstop: str
    precip: str  # catalog source
    focus: str  # the month that matters, for reporting


EVENTS = {
    "sep2023": Event("sep2023", "2023-08-15 00:00:00", "2023-10-01 00:00:00",
                     "mrms_2023_09", "2023-09"),
    "may2025": Event("may2025", "2025-04-15 00:00:00", "2025-06-01 00:00:00",
                     "mrms_2025_05", "2025-05"),
}  # fmt: skip


def obs_points() -> gpd.GeoDataFrame:
    """Every USGS gauge inside the ring (inventory) + the NOAA stations, as SFINCS
    observation points named ``<agency>_<id>``."""
    inv = pd.read_csv(config.GAUGE_DIR / "usgs_series.csv", dtype={"site": str})
    inv = inv.drop_duplicates("site")
    pts = [(f"usgs_{r.site}", r.lon, r.lat) for r in inv.itertuples()]
    pts += [(f"noaa_{s['id']}", s["lon"], s["lat"]) for s in domain.NOAA_STATIONS]
    return gpd.GeoDataFrame(
        {"name": [p[0] for p in pts]},
        geometry=[Point(p[1], p[2]) for p in pts], crs=4326,
    )  # fmt: skip


def forcing_gauges():
    """The gap-filled gauge levels as hydromt wants them: INTEGER station index (it
    refuses the NOAA id strings: "gdf index must be unique integers") and no string
    variables. The NOAA ids stay on as a ``noaa_id`` coordinate."""
    import xarray as xr

    ds = xr.open_dataset(config.GAUGE_DIR / "waterlevel_forcing_navd88.nc")
    ds = ds[["waterlevel"]].load()
    ids = ds.stations.values.astype(str)
    ds = ds.assign_coords(stations=np.arange(1, len(ids) + 1), noaa_id=("stations", ids))
    # Without a CRS hydromt takes lon/lat as model (UTM) metres and slices every gauge
    # away ("No data left after spatial slicing").
    import hydromt  # noqa: F401  (registers the .vector accessor)

    ds.vector.set_crs(4326)  # in place
    return ds


def setup_event(static_root: Path, event: Event, run_name: str | None = None) -> Path:
    """Copy ``static_root`` to config.MODELS/<static>/runs/<run_name> and add forcing."""
    from hydromt_sfincs import SfincsModel

    run = static_root / "runs" / (run_name or event.name)
    if run.exists():
        raise FileExistsError(f"{run} exists")
    shutil.copytree(static_root, run, ignore=shutil.ignore_patterns("runs", "gis"))

    sf = SfincsModel(data_libs=[str(config.CATALOG)], root=str(run), mode="r+")
    sf.read()
    t0, t1 = pd.Timestamp(event.tstart), pd.Timestamp(event.tstop)
    sf.config.update(
        {
            "tref": t0.to_pydatetime(),
            "tstart": t0.to_pydatetime(),
            "tstop": t1.to_pydatetime(),
            "tspinup": 3600.0,
            "advection": 1,
            "dtmapout": 3600.0,
            "dtmaxout": DAY_S,  # daily zsmax and twet
            "dtrstout": DAY_S,
            "dthisout": 600.0,
            "storecumprcp": 1,
            "storetwet": 1,
            "twet_threshold": 0.05,
        }
    )
    sf.water_level.create(geodataset=forcing_gauges(), buffer=WL_BUFFER_M, merge=False)
    sf.precipitation.create(precip=event.precip, cumulative_input=True,
                            time_label="right", aggregate=False)  # fmt: skip
    sf.observation_points.create(locations=obs_points(), merge=False)
    sf.write()
    # sf.write() rewrites sfincs.inp from hydromt's config; re-point infiltration.
    from agri_sfincs.build import patch_infiltration_keys

    patch_infiltration_keys(run)
    return run
