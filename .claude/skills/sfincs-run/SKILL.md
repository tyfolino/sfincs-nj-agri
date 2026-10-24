---
name: sfincs-run
description: Stage, submit, wait for, check and post-process SFINCS runs in this repo (setup_event / setup_scenarios -> sbatch hpc/sfincs_run.slurm -> logs -> compare / check scripts -> STATUS). Use whenever a task involves running or re-running SFINCS events or scenario sets, resubmitting a preempted or failed run, or reading run output.
---

# SFINCS run cycle

The scripts' docstrings are the source of truth for flags; this is the order and the traps.

## 0. Where am I
- `hostname` must match `squeue -u tpj8 -n vscode -o %N`. If not, the session landed on
  another job's node (laptop ProxyCommand missing `-n vscode`): tell the user before going on.
- Runs live on the **Piscataway** /scratch (hal* nodes, partition `main`). Camden halc*
  nodes mount a different /scratch where `config.MODELS` looks empty. It is not purged.
- The SessionStart hook already printed the models on scratch, queued jobs and newest logs.
  If a model is missing, it was purged: rebuild it with `scripts/build_model.py` (see its
  docstring) before staging.

## 1. Stage
- One event: `python scripts/setup_event.py --model <model> --event <event> [--name RUN] ...`
- Scenario / storm sets: `python scripts/setup_scenarios.py --model <model> [--storms]
  [--breaches] [--restore] [--boundary chain] [--open] [--only NAME...]`.
  On v2 models: `--boundary chain --open` (STATUS). A run added to an existing set must keep
  that set's boundary, or it is not comparable with its siblings.
- Long staging goes through `sbatch -J agri-stage hpc/agri_py.slurm scripts/setup_scenarios.py ... --submit`
  so it survives the interactive node timing out.
- Tide-only runs need ZEROED rain, not no rain: the engine segfaults with cnb and no rain file.
- Rain forcing is clipped to NJ's `RAIN_BBOX`; a Delaware run needs the event window
  refetched over the union first.

## 2. Submit
- ALWAYS `sbatch hpc/sfincs_run.slurm <run dir>` (32 threads, `main`, requeue + resume).
  Never run the engine on the VS Code node: it has 4 CPUs whatever `nproc` says.
- ~1 min per simulated day on 32 threads; a month ~30-40 min; bit-reproducible.
- Do not submit `v1_100m/runs/y2023_zsini{0,m1}` unless the user asks.

## 3. Wait (don't poll)
Use the Monitor tool with an until-loop on the job ids, e.g.
`until ! squeue -h -j <id1>,<id2> | grep -q .; do sleep 60; done`, and do other work
meanwhile. One check per job's expected length, not a squeue every minute.

## 4. Check each run
- `sacct -j <id> -o JobID,State,Elapsed,ExitCode`. COMPLETED 0:0 alone is not proof.
- The log `logs/sfincs_<jobid>.out` must end with
  `finish: {'finished': True, ...}`. `finish` exits 3 when outputs stop short of tstop:
  resubmit the same run dir and it resumes from the newest daily restart.
- A preempted-and-resumed run is close to, not bit-identical with, a straight run (FINDINGS §18).
  Say so if a resumed run is compared against the noise floor.
- `sfincs_map.nc` and `sfincs_his.nc` exist in the run dir; `sfincs_log.txt` has no NaN /
  instability lines.

## 5. Post-process
Pick the script whose docstring matches the question (they write `reports/*.md`):
`check_creek_tides.py` (tides; `--side de` for Delaware), `validate_storm_gauges.py`,
`validate_storm_landsat.py`, `compare_restore.py` / `compare_runs.py` (scenario
differences), `build_storm_panel.py` (field x season exposure), `event_summary.py`.
- A scenario difference smaller than the noise floor
  (`v1_100m/runs/tide2024oct_intact_slr000_rep` vs `..._slr000`) is not a result. Never
  delete the `_rep` run.

## 6. Record
- Update docs/STATUS.md (keep it ~50-70 lines, forward-looking). A closed item's durable
  fact becomes a FINDINGS section with its source (script, report, run names).
- Results going to colleagues: have the `claims-reviewer` agent read the draft first.
