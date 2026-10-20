"""Stage an event run: copy a static model and add the event's forcing (agri_sfincs.events).

Writes config.MODELS/<model>/runs/<name> (default name = the event) and prints its path.
The first staging of an event window also writes data/precip/forcing/<product>_<event>.nc
and its data_catalog.yml entry.

Usage:  python scripts/setup_event.py --model v1_100m --event sep2023 [--name RUN]
            [--drn data/structures/dike_gates_hi.drn]   (replaces sfincs.drn in this run)
            [--zsini -1.0]                              (initial water level, m NAVD88)
            [--precip stage4]                           (override: product or catalog source;
                                                         "none" = tide-only)
            [--weir data/structures/dikes_removed.weir] (replaces sfincs.weir in this run)
            [--wl-offset 0.6]                           (sea-level rise on the boundary, m)
            [--boundary gauges]                         (v1's boundary before 2026-10-20, to
                                                         reproduce older runs; default chain)
Year runs:  python scripts/setup_event.py --model v1_100m --event y2023 --name y2023_zsini0 --zsini 0
            (the first staging of a window builds data/precip/forcing/<product>_<event>.nc
            and its data-catalog entry, ~1 min for a year)
Then:   sbatch hpc/sfincs_run.slurm <printed run dir>   (resumes itself if preempted)
"""

from __future__ import annotations

import argparse

from agri_sfincs import config
from agri_sfincs.events import EVENTS, ZSINI, setup_event


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--event", required=True, choices=sorted(EVENTS))
    ap.add_argument("--name", default=None)
    ap.add_argument("--drn", default=None, help="drainage file for this run only")
    ap.add_argument("--zsini", type=float, default=ZSINI,
                    help=f"initial water level, m NAVD88 (default {ZSINI})")  # fmt: skip
    ap.add_argument("--precip", default=None,
                    help="precipitation override: mrms | stage4 | a catalog source")  # fmt: skip
    ap.add_argument("--weir", default=None, help="weir file for this run only (dike scenarios)")
    ap.add_argument("--wl-offset", type=float, default=0.0, help="sea-level rise, m")
    ap.add_argument("--boundary", default="chain", choices=["chain", "gauges"],
                    help="water-level boundary (FINDINGS §41)")  # fmt: skip
    a = ap.parse_args()
    structures = {k: v for k, v in (("drnfile", a.drn), ("weirfile", a.weir)) if v}
    run = setup_event(config.MODELS / a.model, EVENTS[a.event], a.name,
                      structures=structures or None, zsini=a.zsini, precip=a.precip,
                      wl_offset=a.wl_offset, boundary=a.boundary)  # fmt: skip
    print(run)


if __name__ == "__main__":
    main()
