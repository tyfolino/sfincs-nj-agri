# sfincs-nj-agri — read this first

A watershed-bounded **SFINCS** model of the Delaware-draining side of **Salem, Cumberland
and Gloucester counties, NJ**, built to turn historical rain and tide into flood
characteristics per **county × month (× crop)** for a Rutgers ag-econ crop-insurance study.
**Since 2026-10-05 the main line is bayshore farmland → wetland** (tidal exposure, dikes and
tide gates, sea-level rise; which pathway: passive failure, easement, purchase, mitigation).
SFINCS's job there is the same event under different conditions (farmed vs restored, intact
vs breached bank, today vs sea-level rise). The insurance question is kept as a basic
cross-county flood × rain test without SFINCS (done, null; archived 2026-10-15).

The plan is `~/.claude/plans/no-need-to-draft-idempotent-goblet.md` (approved 2026-10-23:
cleanup, v2 creek beds, a Delaware twin model, the Delaware exit check; it supersedes
`compressed-humming-eclipse.md`, 2026-10-05). What is happening now is in [docs/STATUS.md](docs/STATUS.md); what is believed true is in
[docs/FINDINGS.md](docs/FINDINGS.md).

## Decisions (user, 2026-10-02)

- **Whole watersheds.** The domain is 38 WBD HUC12s from Big Timber Creek (the
  Camden/Gloucester line) to West Creek (the Cumberland/Cape May line). Area outside
  the three counties stays in the model and is clipped out at analysis time.
- **Delaware-draining side only.** Gloucester's Great Egg Harbor headwaters are out. They hold
  ~10% of Gloucester cropland (`reports/cropland_coverage.md`).
- **Downstream boundary:** observed NOAA Delaware River/Bay gauges. Flooding is
  expected to be mostly pluvial/fluvial.
- **Rain:** MRMS where it exists (gauge-corrected hourly from mid-2015; Pass2 from
  October 2020), Stage IV before that. Whether sub-hourly (flash-flood) rain matters
  is TESTED on a few convective events, not assumed.

## Decisions (user, 2026-10-23)

- **Delaware state joins as a TWIN grid**, C&D Canal south to Lewes (Appoquinimink …
  Broadkill; no Christina / Brandywine, no PA). Its bay edge is the same mid-bay state line
  NJ is forced on; one region, one analysis, two SFINCS grids. **Amended 2026-10-29:** each
  grid's line is forced to fit its OWN shore (NJ: the NJ-shore chain; DE: the DE rail Lewes →
  Brandywine → Mahon → Ship John, `waterlevel.CHAINS`), so the two differ by ~0.11 m of range
  at 39.0-39.2 N (FINDINGS §51). Nothing may treat the line as one water level.
- **Defunct scripts are deleted** (git keeps them), not archived.

## Layout

```
agri_sfincs/   the package. domain.py = ALL geography; config.py = ALL paths;
               runs.py = run dirs + pixel->cell mapping; exposure.py = tide/ground grid;
               maps.py = map backdrop; precip.py = MRMS / Stage IV rain forcing
scripts/       one job each; the docstring says what it writes. Scripts NEVER import
               scripts: shared code goes in agri_sfincs/ (exception: the grib-env pair
               fetch_mrms / fetch_precip_hourly, which cannot import the package)
tests/         stdlib unittest, no network:  python -m unittest discover -s tests
.claude/       hooks/guard.py (blocks pkill -f, insurance leaving; asks on installs),
               hooks/session_start.sh (scratch + jobs), skills/sfincs-run, agents/claims-reviewer
archive/       FROZEN side lines (insurance track, Fork 1): scripts, their
               own modules, tests and reports. Read archive/README.md before reviving any.
data/          bulk is gitignored; data/region/ring.geojson + data/gauges/*.csv tracked
  insurance/   the ag-econ loss tables — NEVER commit, publish or send anywhere
reports/       generated summaries (markdown)
```

## Environment

The env is borrowed from the Sandy toolchain (hydromt 1.4.1, hydromt_sfincs
2.0.0rc2). Do not install into it; it is shared with nj_bight_sfincs.

```bash
export PATH=$HOME/nj_sandy_sfincs/micromamba/envs/sfincs/bin:$PATH PYTHONPATH=$PWD
```

The env has no `tabulate`, so use `agri_sfincs.report.md_table`, not
`DataFrame.to_markdown`.

It also has no GRIB driver. MRMS / Stage IV decoding runs in a SEPARATE env made for
this repo, `/cache/home/tpj8/agri-micromamba/envs/grib` (cfgrib + eccodes): see
`scripts/fetch_mrms.py`.

Models and runs live on scratch, under `config.MODELS` =
`/scratch/tpj8/sfincs-nj-agri/models` (purged when idle; rebuildable). The SFINCS engine
is `config.SFINCS_BIN`, the native main-branch build. Short runs go on the interactive
node; long ones go through `hpc/sfincs_run.slurm`.

🔴 Never `pkill -f <pattern>` with a pattern that also appears in your own command line:
it kills the shell running it.

## Relationship to nj_bight_sfincs

That repo is the Sandy coastal hindcast. This one **copies** small pieces from it,
with attribution in each docstring, and **never imports** it: `nj_sfincs` is keyed to
`NJ_DOMAIN` and the Sandy window, and it changes under active work. Its raster
**data** (the NJ 10 ft lidar DEM, CUDEM Delaware, 3DEP, GMRT) are read in place via
`config.BIGHT_DATA` and never modified.

Bight traps that apply here:
- Fake flat lake beds: Union Lake and Sunset Lake are in this domain.
- Every dry edge cell is free outflow; here the divide ring must be CLOSED.
- `storecumprcp=1` is required for curve-number infiltration, and water must be CN 100.
- Never prepend a burn raster to the elevation list.
- Call `break_hardlinks()` before `sf.write()` on a borrowed subgrid.

## Git

The user commits; Claude may `git add`.
