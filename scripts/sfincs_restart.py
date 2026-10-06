"""Resume / finish a preempted SFINCS solve (agri_sfincs.restart has the why and the rules).

    python scripts/sfincs_restart.py plan    <run_dir>   # read-only: fresh | resume | finish
    python scripts/sfincs_restart.py prepare <run_dir>   # retire outputs, rewrite sfincs.inp
    python scripts/sfincs_restart.py finish  <run_dir>   # stitch segments, restore inp, drop rst

``plan`` / ``prepare`` print the action word on their LAST stdout line, so
hpc/sfincs_run.slurm can read it. ``finish`` exits 3 if the outputs do not reach tstop
(nothing is cleaned up then; resubmit to resume). Copied from nj_bight_sfincs
``scripts/sfincs_restart.py`` (2026-10-05), minus its ``enable`` command: every run staged
by agri_sfincs.events already writes daily restarts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agri_sfincs import restart


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("cmd", choices=["plan", "prepare", "finish"])
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--drop-final-rst", action="store_true",
                    help="finish: also delete the restart file at tstop")  # fmt: skip
    a = ap.parse_args()
    if a.cmd == "finish":
        rep = restart.finish(a.run_dir, keep_final_rst=not a.drop_final_rst)
        print(f"finish: {rep}")
        return 0 if rep.get("finished") else 3
    pl = restart.plan(a.run_dir) if a.cmd == "plan" else restart.prepare(a.run_dir)
    extra = f" at {pl.t_resume:%Y-%m-%d %H:%M}" if pl.t_resume else ""
    print(f"{a.cmd}: {pl.reason}{extra}", file=sys.stderr)
    print(pl.action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
