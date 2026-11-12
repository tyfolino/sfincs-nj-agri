#!/usr/bin/python3
"""Collect the facts for /wrapup: what git would need staged or removed (this repo and the
storm-panel bundle), insurance-data and large-file alarms, root strays, script hygiene
(docstring says what it writes; scripts never import scripts), STATUS / FINDINGS state,
ruff on the changed Python files, the queue (idle holders to cancel) and the models on
scratch. READ-ONLY; prints plain text for Claude.

Usage: gather.py

Adapted from nj_bight_sfincs/.claude/skills/wrapup/gather.py (2026-11-12): that repo's
scripts index, logs/<campaign>/ READMEs and md5 guards do not exist here. Stdlib only
(system python 3.9), like checkin/gather.py.
"""

import ast
import glob
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

REPO = "/cache/home/tpj8/sfincs-nj-agri"
BUNDLE = "/cache/home/tpj8/bayshore-storm-panel"  # export_storm_panel.py writes it; private GitHub
MODELS = "/scratch/tpj8/sfincs-nj-agri/models"
USER = os.environ.get("USER", "tpj8")
TOOLBIN = os.path.expanduser("~/nj_sandy_sfincs/micromamba/envs/sfincs/bin")
GIT = shutil.which("git") or os.path.join(TOOLBIN, "git")
RUFF = shutil.which("ruff") or os.path.join(TOOLBIN, "ruff")
BIG = 5 * 1024 * 1024  # an untracked file this size is almost never source
INSURANCE = re.compile(r"data/insurance|insurance\.csv|README_insurance", re.IGNORECASE)
STATUS_LINES = (50, 70)  # keep STATUS compact (user feedback)
#: top-level entries that belong there; anything else at the root is a stray
ROOT_OK = {"agri_sfincs", "archive", "CLAUDE.md", "data", "docs", "hpc", "logs", "reports", "scripts",
           "tests", ".claude", ".git", ".gitignore", ".ruff_cache", "__pycache__"}  # fmt: skip
#: CLAUDE.md's one allowed script-to-script import (the grib-env pair)
IMPORT_OK = {("fetch_precip_hourly", "fetch_mrms"), ("fetch_mrms", "fetch_precip_hourly")}


def sh(cmd: str, cwd: str = REPO, timeout: int = 60) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout,
                              check=False, cwd=cwd).stdout.rstrip()  # fmt: skip
    except subprocess.TimeoutExpired:
        return f"(timed out: {cmd})"


def git_state(repo: str) -> dict:
    """Porcelain v1 -z: staged / modified / deleted / untracked / renamed path lists."""
    out = subprocess.run([GIT, "-C", repo, "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                         capture_output=True, text=True, check=False).stdout  # fmt: skip
    st = {"staged": [], "modified": [], "deleted": [], "untracked": [], "renamed": []}
    parts = out.split("\0")
    i = 0
    while i < len(parts):
        e = parts[i]
        i += 1
        if len(e) < 4:
            continue
        x, y, p = e[0], e[1], e[3:]
        if x in "RC":
            st["renamed"].append(p)
            i += 1  # the original path follows
            continue
        if x == "?":
            st["untracked"].append(p)
            continue
        if x != " ":
            st["staged"].append(f"{x} {p}")
        if y == "M":
            st["modified"].append(p)
        elif y == "D":
            st["deleted"].append(p)
    return st


def mb(repo: str, p: str) -> float:
    f = os.path.join(repo, p)
    return os.path.getsize(f) / 2**20 if os.path.isfile(f) else 0.0


def show_git(repo: str, label: str, limit: int = 60) -> dict:
    st = git_state(repo)
    print(f"\n== git: {label} (never commit: the user does)")
    print("   " + sh(f"{GIT} status -sb | head -1", cwd=repo))
    for k, what in (("staged", "staged already"), ("modified", "modified, NOT staged (git add if it belongs)"),
                    ("deleted", "deleted from disk, still tracked (git rm)"), ("renamed", "renamed (staged)"),
                    ("untracked", "untracked, not ignored (add if source, else move / delete / list)")):  # fmt: skip
        print(f"-- {what}: {len(st[k])}")
        for p in st[k][:limit]:
            size = mb(repo, p[2:] if k == "staged" else p)
            flag = f"   ⚠️ {size:.0f} MB" if size * 2**20 >= BIG else ""
            print(f"   {p}{flag}")
        if len(st[k]) > limit:
            print(f"   … {len(st[k]) - limit} more")
    bad = [p for k in st for p in st[k] if INSURANCE.search(p)]
    if bad:
        print("🔴 INSURANCE PATHS VISIBLE TO GIT (never stage, unstage now): " + ", ".join(bad))
    return st


def module_info(path: str) -> tuple:
    """(docstring, top-level names imported) of a Python file."""
    try:
        tree = ast.parse(Path(path).read_text(errors="replace"))
    except SyntaxError:
        return None, set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return ast.get_docstring(tree), names


def scripts_check(changed: set) -> None:
    scripts = {Path(p).stem: p for p in glob.glob(os.path.join(REPO, "scripts", "*.py"))}
    print(f"\n== scripts/ ({len(scripts)}): docstring says what it writes; scripts never import scripts")
    cross, nodoc = [], []
    for name, p in sorted(scripts.items()):
        doc, imps = module_info(p)
        cross += [f"{name} imports {o}" for o in sorted(imps & set(scripts)) if o != name and (name, o) not in IMPORT_OK]
        rel = os.path.relpath(p, REPO)
        if rel in changed and (not doc or not re.search(r"\bwrit", doc, re.IGNORECASE)):
            nodoc.append(rel)
    print("   script imports a script: " + (", ".join(cross) or "none"))
    print("   changed scripts whose docstring does not say what it writes: " + (", ".join(nodoc) or "none"))


def docs_state(today: str) -> None:
    lines = Path(REPO, "docs", "STATUS.md").read_text(errors="replace").splitlines()
    upd = next((ln for ln in lines if ln.startswith("Last updated")), "(no 'Last updated' line)")
    lo, hi = STATUS_LINES
    flag = f"  ⚠️ over ~{hi}: move closed items to FINDINGS" if len(lines) > hi else ""
    print(f"\n== docs/STATUS.md: {len(lines)} lines (keep ~{lo}-{hi}){flag}")
    print("   " + upd[:160])
    print("   dated today: " + ("yes" if today in upd else "NO"))
    print("   sections: " + " · ".join(ln[3:40] for ln in lines if ln.startswith("## ")))
    heads = [ln for ln in Path(REPO, "docs", "FINDINGS.md").read_text(errors="replace").splitlines()
             if re.match(r"## \d+\.", ln)]  # fmt: skip
    print("== docs/FINDINGS.md: last sections:")
    for h in heads[-3:]:
        print("   " + h[:150])


def ruff_check(py: list) -> None:
    print(f"\n== ruff check on {len(py)} changed .py file(s) (no ruff format: the repo is 120-column, hand-wrapped)")
    if py and os.path.exists(RUFF):
        q = " ".join(f"'{p}'" for p in py)
        print(sh(f"{RUFF} check --output-format concise {q} 2>&1 | tail -15") or "   clean")
    elif py:
        print(f"   (ruff not found at {RUFF})")


def jobs() -> None:
    print("\n== jobs: id | name | state | elapsed | limit | node")
    rows = [r for r in sh(f"squeue -u {USER} -h -o '%i|%j|%T|%M|%l|%N|%Z|%o'").splitlines() if "|vscode|" not in r]
    for r in rows:
        jid, name, state, el, lim, node, wd, cmd = (r.split("|") + [""] * 8)[:8]
        other = "" if wd.startswith(REPO) else f"  [{os.path.basename(wd.rstrip('/'))}]"
        hint = ""
        if not other and ("sleep" in cmd or "wrap" in cmd or name.startswith("agents")):
            hint = f"   ← holder: give the user `scancel {jid}` if nothing uses it"
        print(f"   {jid} | {name} | {state} | {el} | {lim} | {node}{other}{hint}")
    if not rows:
        print("   none besides the vscode node")
    print("== this repo's jobs ended in the last 12 h:")
    ended = sh(f"sacct -u {USER} -X -n -S now-12hours -o JobID%12,JobName%22,State%12,Elapsed,WorkDir%60 "
               f"| grep -v -e ' vscode ' -e RUNNING -e PENDING | grep '{REPO}'")  # fmt: skip
    print("\n".join("   " + ln.strip() for ln in ended.splitlines()[-12:]) or "   none")
    if os.path.isdir(MODELS):
        print("== models on scratch: " + " ".join(sorted(os.listdir(MODELS))))
    else:
        print(f"== models: {MODELS} MISSING (scratch purged?)")


def main() -> None:
    now = datetime.now().astimezone()
    print(f"== wrapup facts ({now:%Y-%m-%d %a %H:%M}, host {sh('hostname -s')})")
    st = show_git(REPO, "sfincs-nj-agri")
    if os.path.isdir(os.path.join(BUNDLE, ".git")):
        show_git(BUNDLE, f"bundle {BUNDLE} (export_storm_panel.py output)", limit=25)
    strays = sorted(set(os.listdir(REPO)) - ROOT_OK)
    print("\n== repo root: entries outside the expected layout: " + (", ".join(strays) or "none"))
    changed = set(st["modified"]) | {s[2:] for s in st["staged"]} | set(st["untracked"])
    scripts_check(changed)
    docs_state(now.date().isoformat())
    ruff_check(sorted(p for p in changed if p.endswith(".py") and os.path.exists(os.path.join(REPO, p))))
    jobs()


if __name__ == "__main__":
    main()
