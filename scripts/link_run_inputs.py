"""Save scratch space: hard-link finished runs' copies of a model's static inputs to the model's
own files (agri_sfincs.runs.link_static_inputs; subgrid tifs, roughness, grid and subgrid tables),
after a byte compare. Results and scenario files (weirs, gates, sfincs.inp) are not touched, and a
run still works as before. Skips runs that have not finished or are in the SLURM queue. Rerun any
time: linked files are skipped. After linking, per-folder ``du`` overstates what a delete frees.

Prints per model what was (or, without ``--apply``, would be) linked. Nothing is written otherwise.
Usage:  python scripts/link_run_inputs.py --model e3v2a30brm65_100m [--model ...] [--apply]
"""

from __future__ import annotations

import argparse
import getpass
import subprocess

from agri_sfincs import config, runs


def queued_runs() -> set[str]:
    """Every word of this user's queued and running jobs' sbatch lines (they name their run folders;
    only sacct keeps the arguments, squeue and scontrol show the script alone)."""
    jobs = subprocess.run(["squeue", "-h", "-u", getpass.getuser(), "-o", "%i"], capture_output=True, text=True, check=True).stdout.split()
    if not jobs:
        return set()
    lines = subprocess.run(["sacct", "-n", "-X", "-P", "-j", ",".join(jobs), "-o", "SubmitLine%2000"],
                           capture_output=True, text=True, check=True).stdout  # fmt: skip
    return set(lines.split())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", action="append", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    queue = queued_runs()
    for model in a.model:
        root = config.MODELS / model
        n = {"runs": 0, "skipped": 0, "linked": 0, "already": 0, "freed": 0}
        for run in sorted((root / "runs").iterdir()):
            if str(run) in queue or not runs.finished(run):
                n["skipped"] += 1
                print(f"  skip {run.name}: not finished or queued", flush=True)
                continue
            r = runs.link_static_inputs(root, run, apply=a.apply)
            n["runs"] += 1
            for k in ("linked", "already", "freed"):
                n[k] += r[k]
            if r["differ"]:
                print(f"  {run.name}: differs, left alone: {', '.join(r['differ'])}", flush=True)
        verb = "freed" if a.apply else "would free"
        print(f"{model}: {n['runs']} runs, {n['skipped']} skipped, {n['linked']} files linked, "
              f"{n['already']} already, {verb} {n['freed'] / 1e9:.1f} GB", flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
