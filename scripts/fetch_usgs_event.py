"""15-minute USGS series inside the ring for an event window, for validating event runs.

For every site in data/gauges/usgs_series.csv with an instantaneous ("Points") series
of discharge (00060), gage height (00065) or tidal / NAVD88 elevation (72279, 62620,
63160) that overlaps the window, downloads it via agri_sfincs.usgs_ogc.continuous.

Writes data/gauges/usgs_events/<event>/<site>_<param>.csv (time UTC, value, approval;
units as served: ft3/s or ft) and prints what it got. Existing files are skipped.

Delaware (``--side de``): the sites of usgs_series_de.csv, into the same folders.

Usage:  python scripts/fetch_usgs_event.py --event sep2023 [--side de]
"""

from __future__ import annotations

import argparse

import pandas as pd

from agri_sfincs import config, domain, usgs_ogc
from agri_sfincs.events import EVENTS

PARAMS = {"00060": "ft^3/s", "00065": "ft", "72279": "ft", "62620": "ft", "63160": "ft"}
WHAT = {"discharge": "00060", "gage height": "00065", "tidal elevation": "72279",
        "estuary elevation NAVD88": "62620", "stream elevation NAVD88": "63160"}  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--event", required=True, choices=sorted(EVENTS))
    ap.add_argument("--side", default="nj", choices=list(domain.SIDES))
    a = ap.parse_args()
    ev = EVENTS[a.event]
    t0, t1 = pd.Timestamp(ev.tstart), pd.Timestamp(ev.tstop)
    out = config.GAUGE_DIR / "usgs_events" / ev.name
    out.mkdir(parents=True, exist_ok=True)

    inv = pd.read_csv(config.GAUGE_DIR / f"usgs_series{domain.side(a.side).files}.csv", dtype={"site": str})
    inv = inv[inv.computation_period_identifier == "Points"]
    inv = inv[(pd.to_datetime(inv.begin) <= t1) & (pd.to_datetime(inv.end) >= t0)]
    for r in inv.itertuples():
        pc = WHAT.get(r.what)
        if pc is None:
            continue
        f = out / f"{r.site}_{pc}.csv"
        if f.exists():
            continue
        try:
            df = usgs_ogc.continuous(r.site, pc, PARAMS[pc],
                                     f"{t0:%Y-%m-%dT%H:%M:%SZ}", f"{t1:%Y-%m-%dT%H:%M:%SZ}")  # fmt: skip
        except (KeyError, ValueError) as e:
            print(f"  {r.site} {pc}: skipped ({e})")
            continue
        df.rename_axis("time").to_csv(f)
        print(f"  {r.site} {r.name[:40]:40s} {pc}: {len(df):5d} values, "
              f"{df.value.min():.2f}..{df.value.max():.2f} {PARAMS[pc]}")  # fmt: skip


if __name__ == "__main__":
    main()
