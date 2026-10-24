#!/bin/bash
# SessionStart: report what survived on scratch and what SLURM is doing, so a session
# starts knowing whether models were purged and which jobs finished. Read-only; its
# stdout goes into Claude's context. Paths match agri_sfincs/config.py (MODELS, DATA_BULK).
repo=/cache/home/tpj8/sfincs-nj-agri
models=/scratch/tpj8/sfincs-nj-agri/models
bulk=/scratch/tpj8/sfincs-nj-agri/data_bulk

echo "== session-start check ($(date '+%Y-%m-%d %H:%M'), host $(hostname -s))"
if [ -d "$models" ]; then
    echo "models: $(ls "$models" | wc -l) on scratch: $(ls "$models" | tr '\n' ' ')"
else
    echo "models: $models MISSING (scratch purged? rebuild before running)"
fi
[ -d "$bulk" ] || echo "data_bulk: $bulk MISSING"
broken=$(find "$repo/data" -maxdepth 3 -xtype l 2>/dev/null)
[ -n "$broken" ] && echo "broken data symlinks (bulk purged; rebuild via each docstring):" \
    && echo "$broken" | sed 's/^/  /'

echo "jobs (squeue):"
squeue -u "$USER" -h -o "  %.10i %.20j %.2t %.10M %R" 2>/dev/null | grep -v ' vscode ' \
    || echo "  none besides the vscode node"
echo "jobs ended in the last 24 h (sacct):"
sacct -u "$USER" -X -n -S "$(date -d '-1 day' +%Y-%m-%dT%H:%M)" \
    -o JobID%12,JobName%20,State%12,Elapsed,ExitCode 2>/dev/null \
    | grep -v -e ' vscode ' -e RUNNING -e PENDING | tail -15 || echo "  none"
echo "newest logs:"
ls -t "$repo"/logs/*.out 2>/dev/null | head -3 | while read -r f; do
    echo "  $(basename "$f") ($(date -r "$f" '+%m-%d %H:%M')): $(tail -1 "$f" | cut -c1-120)"
done
exit 0
