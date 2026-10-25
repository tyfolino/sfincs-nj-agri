---
name: checkin
description: Morning check-in for this repo. Covers what ran on SLURM since the last session (finished, failed, queued), where the previous session left off, uncommitted work, and today's to-do list from STATUS.md and the plan. Use when the user types /checkin, or opens with a status update / "what came in overnight" / "where did we leave off" / "today's to-do list".
allowed-tools: Bash(/cache/home/tpj8/sfincs-nj-agri/.claude/skills/checkin/gather.py *), Read
---

# Morning check-in

Facts collected when the command ran (node, jobs since the last session, git, how the last
session ended):

!`/cache/home/tpj8/sfincs-nj-agri/.claude/skills/checkin/gather.py ${CLAUDE_SESSION_ID}`

If the block above is empty or shows the command instead of its output, run
`.claude/skills/checkin/gather.py` yourself.

## Steps
1. Read [docs/STATUS.md](../../../docs/STATUS.md). Open the plan it names only if a step needs
   detail that STATUS doesn't give.
2. For each agri job that ended: say what it was for (match the job name or log name to a
   STATUS item, e.g. `e3a30` = an E3 test). If a run finished but nothing has read its output
   yet, the next step is the compare / check script (see the sfincs-run skill), not a resubmit.
   Failed or preempted: give the log lines and the likely cause. Read more of the log only
   when the tail does not say.
3. Jobs from other repos (`[nj_bight_sfincs]`): one line, no digging.
4. Where we left off: the previous session's last user asks and Claude's last message, plus
   uncommitted changes in git. If that session stopped mid-task (a wait that never reported,
   a half-done edit), say so plainly: that comes first today.
5. Flag anything that blocks work: node mismatch or under ~1 h left, models missing on scratch,
   STATUS older than the work in git or the finished jobs.

## Reply (plain language, short; the user reads it over coffee)
- **Overnight**: finished / failed / still queued, one line each, grouped when they are siblings.
- **Where we left off**: 2-3 lines.
- **Today**: a numbered to-do list of 3-6 items from STATUS "Resume here" / "Next", reordered
  by what came in. Mark the one you'd start with and why.
- **Waiting on / to nudge**: only if STATUS lists something, or something has waited a while.
- Proposed STATUS edits, if any, as a short list (don't edit STATUS until the user agrees).

This is read-only: don't submit, stage or edit anything until the user picks a task.
