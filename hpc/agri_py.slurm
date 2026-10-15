#!/bin/bash
# Run one repo Python script as a batch job (staging, analysis), so it survives the
# interactive node timing out.
#   sbatch -J agri-stage hpc/agri_py.slurm scripts/setup_scenarios.py --submit
#   sbatch -J agri-classes --mem=96G hpc/agri_py.slurm scripts/field_classes.py
# The job may itself call sbatch (setup_scenarios.py --submit does).
#SBATCH -p main
#SBATCH --exclude=halk[0001-0159]
#SBATCH -c 8
#SBATCH --mem=48G
#SBATCH -t 06:00:00
#SBATCH -J agri-py
#SBATCH -o logs/py_%j.out
#SBATCH -e logs/py_%j.out
#SBATCH --open-mode=append
#SBATCH --requeue

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$PWD}"
PY="${AGRI_PYTHON:-$HOME/nj_sandy_sfincs/micromamba/envs/sfincs/bin/python}"
export PYTHONPATH="$PWD"
export PROJ_DATA="$HOME/nj_sandy_sfincs/micromamba/envs/sfincs/share/proj"
echo "host $(hostname)  job ${SLURM_JOB_ID:-local}  restart# ${SLURM_RESTART_COUNT:-0}  $(date -Is)"
echo "run  $*"
"$PY" "$@"
echo "end  $(date -Is)"
