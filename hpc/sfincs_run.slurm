#!/bin/bash
# Solve one staged SFINCS run dir with the native CPU build, resuming if preempted.
#   sbatch hpc/sfincs_run.slurm /scratch/tpj8/sfincs-nj-agri/models/<model>/runs/<event>
#
# Lessons carried over from nj_bight_sfincs hpc/sfincs_run.slurm (read it for the long form):
#  * halk* nodes have failed SILENTLY there (COMPLETED 0:0, no output) — excluded;
#  * `main` PREEMPTS. --requeue puts the job back and SLURM re-runs THIS SCRIPT from the
#    top (SLURM_RESTART_COUNT counts it). `sfincs_restart.py prepare` then resumes from the
#    newest complete daily restart file (agri_sfincs.restart; every run staged by
#    agri_sfincs.events writes them): the partial output is parked in restart_segments/
#    and `finish` stitches ONE sfincs_map.nc / sfincs_his.nc back after the solve, so a
#    preemption costs at most a simulated day. ⚠️ A resume is close to, not bit-identical
#    with, a straight run: SFINCS restart files carry cnb's Se but not its event / recovery
#    clocks (FINDINGS §18);
#  * --open-mode=append: the requeued job keeps the preempted attempt's log lines;
#  * the engine is always explicit: SFINCS_BIN (default: config.SFINCS_BIN's path).
#SBATCH -p main
#SBATCH --exclude=halk[0001-0159]
#SBATCH -c 32
#SBATCH --mem=48G
#SBATCH -t 24:00:00
#SBATCH -J agri-sfincs
#SBATCH -o logs/sfincs_%j.out
#SBATCH -e logs/sfincs_%j.out
#SBATCH --open-mode=append
#SBATCH --requeue

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$PWD}"
REPO="$PWD"

RUN="${1:?usage: sbatch hpc/sfincs_run.slurm <run dir>}"
BIN="${SFINCS_BIN:-$HOME/nj_sandy_sfincs/sfincs-native/main-winddir-fix-1-gf11/bin/sfincs}"
PY="${AGRI_PYTHON:-$HOME/nj_sandy_sfincs/micromamba/envs/sfincs/bin/python}"
[ -x "$BIN" ] || { echo "REFUSING: SFINCS_BIN=$BIN is not executable" >&2; exit 2; }
[ -f "$RUN/sfincs.inp" ] || { echo "REFUSING: $RUN has no sfincs.inp" >&2; exit 2; }
export PYTHONPATH="$REPO"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-32}"
ulimit -s unlimited || ulimit -s "$(ulimit -H -s)"
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  restart# ${SLURM_RESTART_COUNT:-0}"
echo "engine $BIN"
echo "run    $RUN"

# fresh | resume | finish (agri_sfincs.restart.plan). "finish" = the outputs already
# reach tstop: on a requeue (or with segments parked) the job died mid-stitch, so only the
# stitch is owed; on a first attempt it is a deliberate re-run of a completed dir.
ACTION=$("$PY" "$REPO/scripts/sfincs_restart.py" prepare "$RUN" | tail -n 1)
if [ "$ACTION" = "finish" ] && [ "${SLURM_RESTART_COUNT:-0}" -eq 0 ] && [ ! -d "$RUN/restart_segments" ]; then
    ACTION=fresh
fi
echo "restart plan: $ACTION"
grep -E '^(tstart|rstfile)' "$RUN/sfincs.inp" || true

rc=0
if [ "$ACTION" != "finish" ]; then
    echo "start  $(date -Is)"
    ( cd "$RUN" && "$BIN" > sfincs_log.txt 2>&1 ) || rc=$?
    echo "end    $(date -Is)  rc=$rc"
    tail -5 "$RUN/sfincs_log.txt"
    [ "$rc" -eq 0 ] || exit "$rc"   # restart files stay: resubmit to resume
fi
"$PY" "$REPO/scripts/sfincs_restart.py" finish "$RUN"
