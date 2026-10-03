#!/bin/bash
# Solve one staged SFINCS run dir with the native CPU build.
#   sbatch hpc/sfincs_run.slurm /scratch/tpj8/sfincs-nj-agri/models/<model>/runs/<event>
#
# Lessons carried over from nj_bight_sfincs hpc/sfincs_run.slurm (read it for the long form):
#  * halk* nodes have failed SILENTLY there (COMPLETED 0:0, no output) — excluded;
#  * `main` PREEMPTS: --requeue puts the job back. ⚠️ This script does NOT resume from a
#    restart file yet (bight's nj_sfincs/restart.py does): a requeue re-runs from scratch.
#    Port restart.py before runs get long enough for that to hurt;
#  * the engine is always explicit: SFINCS_BIN (default: config.SFINCS_BIN's path).
#SBATCH -p main
#SBATCH --exclude=halk[0001-0159]
#SBATCH -c 32
#SBATCH --mem=48G
#SBATCH -t 24:00:00
#SBATCH -J agri-sfincs
#SBATCH -o logs/sfincs_%j.out
#SBATCH -e logs/sfincs_%j.out
#SBATCH --requeue

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$PWD}"

RUN="${1:?usage: sbatch hpc/sfincs_run.slurm <run dir>}"
BIN="${SFINCS_BIN:-$HOME/nj_sandy_sfincs/sfincs-native/main-winddir-fix-1-gf11/bin/sfincs}"
[ -x "$BIN" ] || { echo "REFUSING: SFINCS_BIN=$BIN is not executable" >&2; exit 2; }
[ -f "$RUN/sfincs.inp" ] || { echo "REFUSING: $RUN has no sfincs.inp" >&2; exit 2; }

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-32}"
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  restart# ${SLURM_RESTART_COUNT:-0}"
echo "engine $BIN"
echo "run    $RUN"
echo "start  $(date -Is)"
cd "$RUN"
"$BIN" > sfincs_log.txt 2>&1
rc=$?
echo "end    $(date -Is)  rc=$rc"
tail -5 sfincs_log.txt
exit $rc
