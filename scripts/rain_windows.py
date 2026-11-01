"""Print the event windows Delaware's rain is fetched for (scripts/fetch_precip_hourly.py --side de):
every storm-tide event and the two tide months, as CSV name, start, end, padded by 6 h each way so
the 6-h Stage IV files that fill hourly gaps cover the run.

Usage:  python scripts/rain_windows.py > data/precip/windows_de.csv
"""

from __future__ import annotations

import pandas as pd

from agri_sfincs.events import EVENTS

PAD = pd.Timedelta(hours=6)
NAMES = [k for k in EVENTS if k.startswith(("storm", "sandy", "tide"))]


def main() -> None:
    print("name,start,end")
    for k in NAMES:
        e = EVENTS[k]
        print(f"{k},{pd.Timestamp(e.tstart) - PAD},{pd.Timestamp(e.tstop) + PAD}")


if __name__ == "__main__":
    main()
