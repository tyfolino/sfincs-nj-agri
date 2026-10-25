#!/usr/bin/python3
"""Collect the facts for /checkin: node, SLURM jobs since the last session, git state,
and how the previous Claude session ended. Read-only; prints plain text for Claude.

Usage: gather.py [SESSION_ID]   (the current session, skipped when finding the previous one)

Jobs are tagged by WorkDir, so nj_bight_sfincs jobs show up but are not dug into. Logs are
found as logs/*_<jobid>.out (stdout and stderr are merged in hpc/*.slurm). The job window
starts at the previous session's last write, or 24 h ago if that is later.
Stdlib only (system python 3.9).
"""
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime

REPO = "/cache/home/tpj8/sfincs-nj-agri"
MODELS = "/scratch/tpj8/sfincs-nj-agri/models"
TRANSCRIPTS = os.path.expanduser("~/.claude/projects/-cache-home-tpj8-sfincs-nj-agri")
USER = os.environ.get("USER", "tpj8")
BAD = ("FAILED", "TIMEOUT", "OUT_OF_ME", "NODE_FAIL", "PREEMPTED", "CANCELLED", "BOOT_FAIL")


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=60).stdout.rstrip()
    except subprocess.TimeoutExpired:
        return "(timed out: %s)" % cmd


def tail(path, n):
    with open(path, errors="replace") as f:
        return [ln.rstrip()[:160] for ln in f.readlines()[-n:]]


def repo_tag(workdir):
    return "agri" if workdir.startswith(REPO) else os.path.basename(workdir.rstrip("/")) or "?"


def text_of(content):
    if isinstance(content, str):
        return content
    return " ".join(c.get("text", "") for c in content or []
                    if isinstance(c, dict) and c.get("type") == "text")


def previous_session(current):
    files = sorted(glob.glob(os.path.join(TRANSCRIPTS, "*.jsonl")), key=os.path.getmtime)
    if current and not current.startswith("$"):
        files = [f for f in files if os.path.basename(f) != current + ".jsonl"]
    elif files:
        files = files[:-1]  # no session id: assume the newest file is this session
    if not files:
        return None
    path = files[-1]
    users, last_reply = [], ""
    for line in open(path, errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("isMeta") or d.get("isSidechain"):
            continue
        msg = d.get("message") or {}
        txt = text_of(msg.get("content")).strip()
        if not txt:
            continue
        if d.get("type") == "user" and not txt.startswith("<"):
            users.append(txt)
        elif d.get("type") == "assistant":
            last_reply = txt
    return path, users, last_reply


def main():
    current = sys.argv[1] if len(sys.argv) > 1 else ""
    now = datetime.now()
    print("== checkin facts (%s, host %s)" % (now.strftime("%Y-%m-%d %a %H:%M"),
                                              sh("hostname -s")))

    # Node: the session should be on the vscode job's node (reference memory).
    vs = sh("squeue -u %s -n vscode -h -o '%%N %%L'" % USER).split()
    host = sh("hostname -s")
    if not vs:
        print("node: no vscode job in squeue (login node?)")
    elif vs[0] != host:
        print("node: MISMATCH: on %s but the vscode job is on %s (ProxyCommand missing -n vscode?)"
              % (host, vs[0]))
    else:
        print("node: on the vscode node, %s left" % vs[1])
    print("models on scratch: %s" % (len(os.listdir(MODELS)) if os.path.isdir(MODELS)
                                     else "MISSING (purged?)"))

    prev = previous_session(current)
    since = time.time() - 86400
    if prev:
        since = min(since, os.path.getmtime(prev[0]))
    since_s = datetime.fromtimestamp(since).strftime("%Y-%m-%dT%H:%M")

    print("\n== queued / running")
    rows = sh("squeue -u %s -h -o '%%i|%%j|%%T|%%M|%%l|%%R|%%Z'" % USER).splitlines()
    rows = [r.split("|") for r in rows if r and r.split("|")[1] != "vscode"]
    for jid, name, state, used, limit, reason, wd in rows:
        dep = sh("scontrol show job -o %s | grep -o 'Dependency=[^ ]*'" % jid)
        dep = "" if "(null)" in dep else " " + dep
        print("  %s %-16s %-8s %s/%s %s [%s]%s" % (jid, name, state, used, limit, reason,
                                                 repo_tag(wd), dep))
    if not rows:
        print("  none")

    print("\n== ended since %s" % since_s)
    ended = sh("sacct -u %s -X -n -P -S %s -o JobID,JobName,State,Elapsed,End,WorkDir"
               % (USER, since_s)).splitlines()
    n = 0
    for row in ended:
        jid, name, state, elapsed, end, wd = (row.split("|") + [""] * 6)[:6]
        if name == "vscode" or state in ("RUNNING", "PENDING", "REQUEUED"):
            continue
        n += 1
        tag = repo_tag(wd)
        print("  %s %-16s %-10s %s ended %s [%s]" % (jid, name, state.split()[0], elapsed,
                                                    end[5:16], tag))
        if tag != "agri":
            continue
        logs = glob.glob(os.path.join(REPO, "logs", "*_%s.out" % jid))
        if not logs:
            print("      (no logs/*_%s.out)" % jid)
        for lg in logs:
            lines = tail(lg, 8 if state.startswith(BAD) else 1)
            for ln in lines:
                print("      %s: %s" % (os.path.basename(lg), ln))
    if not n:
        print("  none")

    print("\n== git")
    print(sh("git -C %s status --short --branch" % REPO))
    print("last commits:")
    print(sh("git -C %s log --format='  %%h %%ad %%s' --date=format:'%%m-%%d %%H:%%M' -6"
             % REPO))
    print("STATUS.md: last updated %s, last committed %s" % (
        sh("grep -m1 -o 'Last updated: \\*\\*[0-9-]*' %s/docs/STATUS.md | tr -d '*'"
           % REPO).replace("Last updated: ", ""),
        sh("git -C %s log -1 --format=%%ad --date=short -- docs/STATUS.md" % REPO)))

    print("\n== previous session")
    if not prev:
        print("  none found")
        return
    path, users, last_reply = prev
    print("  %s, last write %s" % (os.path.basename(path), datetime.fromtimestamp(
        os.path.getmtime(path)).strftime("%m-%d %H:%M")))
    if users:
        print("  opened with: %s" % users[0][:400].replace("\n", " "))
        for u in users[-3:] if len(users) > 1 else []:
            print("  user, late: %s" % u[:250].replace("\n", " "))
    print("  Claude's last message:\n    %s" % last_reply[-1500:].replace("\n", "\n    "))


if __name__ == "__main__":
    main()
