#!/usr/bin/python3
"""PreToolUse guard: enforce CLAUDE.md's hard rules before a tool runs.

Reads the hook payload on stdin and answers with a permission decision:
  deny  `pkill -f` / `killall` (a pattern in Claude's own command line kills its shell);
  deny  sending anything under data/insurance/ out (git add -f, network copies, Artifact,
        claude.ai connectors, WebFetch): the ag-econ loss tables never leave this machine;
  ask   any pip / conda / mamba / micromamba install or removal: the sfincs env is shared
        with nj_bight_sfincs, and other installs need the user's OK.

It matches PATHS, not content: a page built from numbers copied out of the insurance
tables does not name data/insurance and is not caught. Stdlib only (system python 3.9).
"""
import json
import re
import sys

INSURANCE = re.compile(r"data/insurance|insurance\.csv|README_insurance", re.I)
PKILL = re.compile(r"\bkillall\b|\bpkill\b[^|;&\n]*\s-[A-Za-z]*f")
INSTALL = re.compile(
    r"\b(pip3?|conda|mamba|micromamba)\b[^|;&\n]*\b(install|uninstall|remove|update|upgrade)\b"
)
# Bash verbs that move a file off the machine (or into git).
SENDS = re.compile(
    r"\bgit\s+(add|commit|push|stash)\b|\b(curl|wget|scp|sftp|rsync|rclone|gh|mail|mailx|"
    r"sendmail|aws|gsutil|globus)\b"
)


def decide(decision, reason):
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "permissionDecision": decision,
                                      "permissionDecisionReason": reason}}, sys.stdout)
    sys.exit(0)


def main():
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}

    if tool == "Bash":
        cmd = inp.get("command", "")
        if PKILL.search(cmd):
            decide("deny", "Blocked by .claude/hooks/guard.py: `pkill -f` / `killall` can kill "
                           "the shell running it (CLAUDE.md). Kill by PID (`ps -u tpj8`, "
                           "`kill <pid>`) or `scancel <jobid>` instead.")
        if INSURANCE.search(cmd) and SENDS.search(cmd):
            decide("deny", "Blocked by .claude/hooks/guard.py: data/insurance/ must never be "
                           "committed, published or sent anywhere (CLAUDE.md).")
        if INSTALL.search(cmd):
            decide("ask", "guard.py: package install/removal. The sfincs env is shared with "
                          "nj_bight_sfincs; installs need the user's OK.")
    elif INSURANCE.search(json.dumps(inp)):
        # Artifact, WebFetch and claude.ai connectors: anything that publishes or uploads.
        decide("deny", f"Blocked by .claude/hooks/guard.py: {tool} would send a "
                       "data/insurance/ file out; those tables never leave this machine.")
    sys.exit(0)


if __name__ == "__main__":
    main()
