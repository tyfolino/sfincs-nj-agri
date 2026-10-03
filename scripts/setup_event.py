"""Stage an event run: copy a static model and add the event's forcing (agri_sfincs.events).

Usage:  python scripts/setup_event.py --model v0_100m --event sep2023 [--name RUN]
Then:   sbatch hpc/sfincs_run.slurm <printed run dir>
"""

from __future__ import annotations

import argparse

from agri_sfincs import config
from agri_sfincs.events import EVENTS, setup_event


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--event", required=True, choices=sorted(EVENTS))
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    run = setup_event(config.MODELS / a.model, EVENTS[a.event], a.name)
    print(run)


if __name__ == "__main__":
    main()
