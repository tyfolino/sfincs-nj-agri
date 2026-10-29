"""Stage (and optionally submit) the dike x sea-level scenario matrix (plan §2.4).

Runs, on the v1 model (dikes as weirs, check-valve gates, burned beds), TIDE-ONLY unless noted:
  tide2024oct  x {intact, removed, breach_all_farm}  x SLR {0, 0.3, 0.6, 1.0} m
               (breach_all_farm added 2026-10-06: one Sandy is too short for a 100 m gap to fill
               a polder, FINDINGS §27)
  sandy2012    x {intact, removed, breach_all_farm}  x SLR {0, 0.3, 0.6, 1.0} m
  sandy2012    intact, SLR 0, WITH Stage IV rain     (how much rain adds behind the banks)
  --storms:    the other Sandy-class storm tides (storm2012dec, storm2016jan, storm2021oct) x
               {intact, removed} at SLR 0, plus intact WITH rain: repeated exposure for the
               land-use test (FINDINGS §34); and the planting-season / harvest storm tides
               (SPRING_STORMS) x intact, tide only and WITH rain (flood timing); and, the same way,
               the rest of the storm tides >= 1.68 m 2008-25 (OTHER_STORMS: Irene 2011, Oct 2018,
               Isaias 2020, Jan 2024, Aug 2025), so every such storm has a run with its month
  --breaches:  sandy2012 x each farm system breached alone (data/structures/scenarios/breach/)
  --restore:   farm -> wetland phase 1 (2026-10-06, scripts/make_restore_scenarios.py): per site,
               the outlet re-opened to MLLW over 100 / 300 m and its gate removed, tide2024oct x
               SLR {0, 0.6}, sandy2012 (100 m); the marsh-level breach (breach/<slug>.weir) on
               tide2024oct for the sill-depth contrast; and tide2024oct_intact_slr000_rep, an
               identical repeat of the intact run (the noise floor for small differences); and the
               Middle Neck set-back (non-farmed seaward land restored, farms behind an inner dike)
               on tide2024oct x SLR {0, 0.6} and sandy2012.
"intact" = the static model's own weirs; "removed" / "breach_*" swap in the weir files of
scripts/make_dike_scenarios.py. Run names: <event>_<dikes>_slr<cm>[_rain][_era5|_hrrr]
(agri_sfincs.runs.run_dir).

Wind: ``--wind SCALE`` adds 10 m wind x SCALE from ``--wind-source`` (era5 default, or hrrr;
agri_sfincs.wind; FINDINGS §48) and appends ``_<source>`` to every name, so wind runs sit
beside the windless ones.

Writes each run not yet staged to config.MODELS/<model>/runs/<name> (scripts/setup_event.py's
setup_event). ``--submit`` sbatches hpc/sfincs_run.slurm for every run without a sfincs_map.nc.

Boundary: every run staged so far used v1's "gauges" boundary, so this script keeps it by
default and a run added to the matrix stays comparable with its siblings. ``--boundary chain``
(FINDINGS §41) is for re-staging a whole set, under new names or after the old runs are moved.

Creek links: the scenario weir files are cut from dikes.weir, whose banks close some tidal
creeks at 100 m (FINDINGS §40). A model built on dikes_open.weir (e9_100m and later) takes
``--open``: every scenario weir file is swapped for its ``<stem>_open.weir`` twin, made with
``scripts/open_creek_links.py --weir <file> --out <stem>_open.weir``.

Usage:  python scripts/setup_scenarios.py [--model v1_100m] [--breaches] [--restore] [--storms] [--submit] [--only NAME...]
            [--boundary gauges|chain] [--open] [--wind SCALE [--wind-source era5|hrrr]]
"""

from __future__ import annotations

import argparse
import subprocess

from agri_sfincs import config
from agri_sfincs.events import EVENTS, setup_event

SC = config.STRUCT_DIR / "scenarios"
SLR = [0.0, 0.3, 0.6, 1.0]
DIKES = {"intact": None, "removed": SC / "dikes_removed.weir", "breach_all_farm": SC / "breach_all_farm.weir"}


STORMS = ["storm2012dec", "storm2016jan", "storm2021oct"]
SPRING_STORMS = ["storm2010mar", "storm2011apr", "storm2012jun", "storm2014apr", "storm2018sep",
                 "storm2022apr", "storm2023jun", "storm2024spr"]
OTHER_STORMS = ["storm2011aug", "storm2018oct", "storm2020aug", "storm2024jan", "storm2025aug"]
RESTORE = SC / "restore"
RESTORE_SITES = ["middle_neck", "durham"]


def restore_runs() -> list[dict]:
    runs = []
    for site in RESTORE_SITES:
        gate = RESTORE / f"{site}_nogate.drn"
        for w in (100, 300):
            weir = RESTORE / f"{site}_mllw{w}.weir"
            for s in (0.0, 0.6):
                runs.append({"event": "tide2024oct", "dikes": f"restore_{site}_mllw{w}", "weir": weir,
                             "drn": gate, "slr": s, "precip": "none"})  # fmt: skip
        runs.append({"event": "sandy2012", "dikes": f"restore_{site}_mllw100", "weir": RESTORE / f"{site}_mllw100.weir",
                     "drn": gate, "slr": 0.0, "precip": "none"})  # fmt: skip
        runs.append({"event": "tide2024oct", "dikes": f"breach_{site}", "weir": SC / "breach" / f"{site}.weir",
                     "slr": 0.0, "precip": "none"})  # fmt: skip
    # set-back (managed realignment): restore the non-farmed seaward land, inner dike protects the farms
    sb = "middle_neck"
    for ev, s in (("tide2024oct", 0.0), ("tide2024oct", 0.6), ("sandy2012", 0.0)):
        runs.append({"event": ev, "dikes": f"restore_{sb}_setback", "weir": RESTORE / f"{sb}_setback.weir",
                     "drn": RESTORE / f"{sb}_setback.drn", "slr": s, "precip": "none"})  # fmt: skip
    runs.append({"event": "tide2024oct", "dikes": "intact", "weir": None, "slr": 0.0, "precip": "none", "suffix": "_rep"})
    return runs


def matrix(breaches: bool, restore: bool = False, storms: bool = False, wind: str = "") -> list[dict]:
    runs = []
    for ev, dk in (("tide2024oct", ["intact", "removed", "breach_all_farm"]), ("sandy2012", ["intact", "removed", "breach_all_farm"])):
        for d in dk:
            for s in SLR:
                runs.append({"event": ev, "dikes": d, "weir": DIKES[d], "slr": s, "precip": "none"})
    runs.append({"event": "sandy2012", "dikes": "intact", "weir": None, "slr": 0.0, "precip": None})
    if breaches:
        for f in sorted((SC / "breach").glob("*.weir")):
            runs.append({"event": "sandy2012", "dikes": f"breach_{f.stem}", "weir": f, "slr": 0.0,
                         "precip": "none"})  # fmt: skip
    if restore:
        runs += restore_runs()
    if storms:
        for ev in STORMS:
            for d in ("intact", "removed"):
                runs.append({"event": ev, "dikes": d, "weir": DIKES[d], "slr": 0.0, "precip": "none"})
            runs.append({"event": ev, "dikes": "intact", "weir": None, "slr": 0.0, "precip": None})
        for ev in SPRING_STORMS + OTHER_STORMS:
            runs.append({"event": ev, "dikes": "intact", "weir": None, "slr": 0.0, "precip": "none"})
            runs.append({"event": ev, "dikes": "intact", "weir": None, "slr": 0.0, "precip": None})
    for r in runs:
        r["name"] = (f"{r['event']}_{r['dikes']}_slr{int(round(100 * r['slr'])):03d}"
                     + ("_rain" if r["precip"] is None else "") + r.get("suffix", "") + (f"_{wind}" if wind else ""))  # fmt: skip
    return runs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="v1_100m")
    ap.add_argument("--breaches", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--storms", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--boundary", default="gauges", choices=["gauges", "chain"])
    ap.add_argument("--open", action="store_true", help="use the <stem>_open.weir twin of every scenario weir file")
    ap.add_argument("--wind", type=float, default=None, metavar="SCALE",
                    help="wind x SCALE (agri_sfincs.wind); names get _<source>")
    ap.add_argument("--wind-source", choices=("era5", "hrrr"), default="era5")  # fmt: skip
    a = ap.parse_args()
    static = config.MODELS / a.model
    for r in matrix(a.breaches, a.restore, a.storms, wind=a.wind_source if a.wind is not None else ""):
        if a.only and r["name"] not in a.only:
            continue
        if a.open and r.get("weir"):
            r["weir"] = r["weir"].with_name(f"{r['weir'].stem}_open.weir")
            if not r["weir"].exists():
                raise SystemExit(f"{r['weir']} missing: scripts/open_creek_links.py --weir <closed file> --out {r['weir']}")
        run = static / "runs" / r["name"]
        if not run.exists():
            setup_event(static, EVENTS[r["event"]], r["name"],
                        structures={k: r[v] for k, v in (("weirfile", "weir"), ("drnfile", "drn")) if r.get(v)} or None,
                        precip=r["precip"], wl_offset=r["slr"], boundary=a.boundary, wind_scale=a.wind,
                        wind_source=a.wind_source)  # fmt: skip
        if a.submit and not (run / "sfincs_map.nc").exists():
            out = subprocess.run(["sbatch", "-J", f"agri-{r['name'][:20]}", "hpc/sfincs_run.slurm", str(run)],
                                 capture_output=True, text=True, check=True).stdout.strip()  # fmt: skip
            print(f"{r['name']}: {out}")
        else:
            print(f"{r['name']}: staged {run}")


if __name__ == "__main__":
    main()
