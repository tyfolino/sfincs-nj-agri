---
name: wrapup
description: End-of-day wrap-up for this repo. Stages the day's work in this repo and the storm-panel bundle (git add, git rm for files deleted or retired; never commits), brings docs/STATUS.md up to date and compact, moves closed items to FINDINGS, checks script hygiene, ruff and tests, lists running jobs and idle holders to scancel, updates the to-do panel and memory, and ends with ready-to-paste commit commands. Use when the user types /wrapup, says "wrap up", "let's wrap up", "closing housekeeping", or is stepping away for the day.
allowed-tools: Bash(/cache/home/tpj8/sfincs-nj-agri/.claude/skills/wrapup/gather.py *), Read
---

# Wrap-up

Facts collected when the command ran (git in this repo and the bundle, insurance / large-file
alarms, root strays, script hygiene, STATUS and FINDINGS, ruff, jobs, models on scratch):

!`/cache/home/tpj8/sfincs-nj-agri/.claude/skills/wrapup/gather.py`

If the block above is empty or shows the command instead of its output, run
`.claude/skills/wrapup/gather.py` yourself.

The user asked for this housekeeping, so do it; don't stop to ask about routine steps.
Ask (AskUserQuestion, a "(Recommended)" default) only for a real decision: deleting something
you did not create this session (a model on scratch, a report, a script), or a STATUS /
FINDINGS claim you are unsure of.

## 0. Before touching anything
- **Background agents still running?** Don't stage or tidy their files mid-edit. Wait for
  their reports, or leave their files out and say so.
- **Jobs that will read files** (a staged SFINCS run reads its run dir, not the repo, but a
  pending post-processing step may run a script): don't change a script a pending job calls.

## 1. Git: stage, never commit (CLAUDE.md "Git": the user commits)
- 🔴 Nothing under `data/insurance/` is ever staged, copied or sent. If the facts show an
  insurance path, unstage it and tell the user.
- `git add` each modified or new file that belongs in version control: code, tests, docs,
  reports and their figures, skills, hooks, and the small un-ignored data (`data/region/*.geojson`,
  `data/gauges/*.csv`). Name the files; never `git add -A` or `git add .` here.
- `git rm` each tracked file deleted from disk. Retired scripts are deleted, not archived
  (user, 2026-10-23), once nothing reads them: grep `agri_sfincs/ scripts/ hpc/ tests/` first.
- Untracked, not ignored: add it (source), delete it (a one-off you made this session that is
  now pointless), or list it for the user. Never stage a file ≥ 5 MB, a run output or a raster.
- **The bundle** (`/cache/home/tpj8/bayshore-storm-panel`) is written wholesale by
  `scripts/export_storm_panel.py`; if it changed today, stage what the export wrote (there
  `git add -A` is fine after checking the list holds no insurance path). Big CSVs there are
  expected (`field_year.csv` ~53 MB; GitHub warns at 50, refuses at 100).
- Show `git diff --cached --stat` for each repo in the reply.

## 2. docs/STATUS.md and FINDINGS
- STATUS is short and forward-looking: ~50-70 lines, no dated logs. Update the
  `Last updated:` line (today's date, what the day did in a few words) and **Resume here** /
  **Next, in order**: what is done today, what is running (job ids, what each is for), the
  user's decisions today ("user, MM-DD"), and the next steps in order.
- An item that closed today: its durable fact goes to `docs/FINDINGS.md` (a new numbered
  section, or a line in the one it belongs to) and the item leaves STATUS. If STATUS is over
  ~70 lines, compress the oldest closed items into one-line pointers to their § numbers.
- FINDINGS holds what is believed true, stated at its narrowest, with the conditions that
  make it true (model / run tag, threshold, sample). No claim there that a report does not back.
- Fix any line in CLAUDE.md that today's work made false (model names, paths, decisions).

## 3. Tidy and check
- Repo-root strays: move each where it belongs or delete it if you made it this session.
- Scripts: one job each, the docstring says what it writes (and its usage); shared code goes in
  `agri_sfincs/`, scripts never import scripts (the fetch_mrms / fetch_precip_hourly pair is the
  exception). The facts list breaks of either rule; fix the ones from today.
- `ruff check` the changed .py files only. Do NOT `ruff format`: the repo is hand-wrapped at
  120 columns and the formatter would reflow untouched code.
- Tests, if code changed today (light, fine on the vscode node):
  `export PATH=$HOME/nj_sandy_sfincs/micromamba/envs/sfincs/bin:$PATH PYTHONPATH=$PWD; python -m unittest discover -s tests`
- Scratchpad and `logs/` (gitignored): leave them. Never delete a model, run dir, panel build
  or report without asking.

## 4. Jobs
- Idle holders or allocations in this repo (a `sleep` job, an `agents_*` holder): give the
  exact `scancel <id>` line; Claude does not scancel them in auto mode.
- Jobs running or pending overnight: one line each in STATUS and the reply (what it's for, when
  it should end). Claim a watcher only if a tool result confirmed one.
- Jobs from nj_bight_sfincs: leave them, no digging.
- Models on scratch no longer read by anything: list them for the user to approve deleting.
- Slurm 25.11: `srun --overlap` always with `-n 1`; hold an allocation with
  `sbatch --wrap "sleep N"`, not a backgrounded `salloc`.

## 5. To-do panel and memory
- `todo_set` with the FULL list: today's items done, waiting (with a job id or who it waits
  on), or pending. Put tomorrow's first item at the top.
- Memory: save only new user preferences, feedback or where-things-are learned today; no
  measurements (the repo owns those). Update an existing memory rather than adding a duplicate.

## 6. Other sessions
- If today changed something the **nj_bight_sfincs** session reads or shares (its data read in
  place via `config.BIGHT_DATA`, the shared sfincs env, cluster facts), send it a short note
  (`ListAgents`, then `SendMessage`). Skip it otherwise.

## Reply (plain language, short)
- **Staged**: `git diff --cached --stat` per repo, one line per group of files.
- **Cleaned**: what moved or was deleted.
- **STATUS**: the new "Resume here" in two or three lines.
- **Overnight**: running jobs; `scancel` lines for idle holders.
- **Needs you**: decisions, files left alone, anything that refused.
- Commit commands to paste, safe in bash and fish (double quotes, no `$`, `!` or backticks in
  the message), one block per repo with staged changes, the message summarizing the day; the
  attribution line from the system reminder, if one is given, goes in a second `-m`:
  `cd /cache/home/tpj8/sfincs-nj-agri; git commit -m "…" -m "Co-Authored-By: …"; git push`
