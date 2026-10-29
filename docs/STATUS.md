# STATUS: what is happening now

Keep this short and forward-looking. When an item closes, move its durable fact to FINDINGS
and delete it here. History lives in git.

Last updated: **2026-10-29** (m65 rerun under way with HRRR wind; storm panel by month tested; §49-§51).

## Goal
A map of bayshore farmland: current, threatened by sea-level rise, and dike-dependent, from
SFINCS same-event scenarios (FINDINGS §27, §29-§31), now on BOTH shores: NJ + Delaware (C&D
Canal to Lewes) as twin grids forced on the same mid-bay state line. Joint ag-econ work: the
**dike pay-off** and Seowoo's **flood → farm exit** paper (AERE abstract, mid-January 2027; her
result holds on 2008-23). Plan: `~/.claude/plans/no-need-to-draft-idempotent-goblet.md`.

## Resume here (plan steps)
- **Step 1, v2 beds (NJ): done** on the E3 grid; **Alloway adopted: `e3v2a30brm65_100m`**
  (§45, §47). Storm check passed: peaks within ~0.1 m at the three creek gauges, Bivalve storm
  by storm −0.25..+0.20 (§48). All 16 m65 storm runs exist (`--boundary chain --open`).
  **Full m65 rerun under way (2026-10-29)**, `setup_scenarios.py --model e3v2a30brm65_100m
  --boundary chain --open --wind 1 --wind-source hrrr` (names `*_hrrr`; HRRR × 1.0, §50; rain
  placement fixed, §49): the 22 storm runs 2016-25 and the 25-run tide2024oct set (base +
  restore) are submitted (40 jobs). Next: check each log (`finish: ... True`), then the panel
  and scenario compares. The `_open` twin of every scenario weir file was cut on v1's grid like
  `dikes_open.weir` (m65's own). **Waiting on the user:** wind for the 47 pre-2014 runs (Sandy
  set, breaches, 2010-14 storms): ERA5 × ~1.3 (suggested; ERA5 2010-11 on disk, 2012/14 in job 63248098, log `logs/py_63248098.out`) or test
  RAP first. Bivalve's storm-peak scatter: not wind, boundary or gauge drift (§50); open.
  Then §29's number. Stow /
  upper Oldmans still short (no data). USGS 2022 Alloway survey email: on hold (user).
- **Step 3, Delaware: boundary fixed (§51).** DE rail (Lewes → Brandywine → Mahon → Ship
  John) + the held-out yardstick corrected: DE held-out median 1.00, Bowers 1.08. **Adopted
  (user, 2026-10-29)**: each grid fitted to its own shore; the line differs by ~0.11 m of range
  at 39.0-39.2 N; say so in the bundle notes for Seowoo. Next:
  the Appoquinimink (Odessa 0.26: needs depth like the Cohansey; H10200 covers 0 km of it).
  Rain: forcing is clipped to NJ's `RAIN_BBOX`; refetch event windows over the union first.
- **Step 5, Delaware exits:** first look done without SFINCS (§44): same pattern as NJ (low
  ground ~1.5 %/yr in both). Next, after the DE boundary fix: DE storm runs → DE storm panel
  (`build_storm_panel.py` side-aware) → one bundle with a `state` column for Seowoo.

## Next, in order
0. **Storm-history land-use test: first look done** (§35, §37, §38): no detectable crop or NDVI
   response; a weak corn → soy tilt where fields are wet on ordinary tides. The creek-bed fix may
   sharpen this ("not detectable", not "no effect"). Show the colleague and the advisor
   (`reports/storm_panel.md`, `data/analysis/storm_panel/`). **Seowoo asks (2026-10-26): floods
   all year, with the month** (growing vs non-growing season). All 18 Ship John storm tides
   ≥ 1.68 m (2008-25) now have events; Irene 2011, Oct 2018, Isaias 2020, Jan 2024, Aug 2025
   are run on m65 (§48). Field × storm-month layout built and tested on m65
   (`data/analysis/storm_panel_m65test`: one row per storm tide, grow_/nongrow_ columns); the
   bundle for Seowoo is rebuilt after the rerun (`plot_storm_panel.py` hardcodes 12 storm tides:
   update then). User: storm tides only; growing season = Apr-Oct.
1. **Tide gates:** public search done (§36); the leads that need a person are the user's call.
2. **Plan checks:** mass balance; where station peaks rise by more than the SLR.
3. **Per-system breach runs** (18 systems) on tide2024oct × SLR with a scoured sill (MLLW): the
   farmland each bank protects, against repair costs ($0.75-14 M). (§27, §30) Now the dike
   pay-off's input; run once on v2 beds with `--open`. Prep: MLLW-sill weirs for the 16 systems
   that have only marsh-level breaches (only Middle Neck, Durham have them), plus `_open` twins.
4. **Wetness exposure for the conversion model** (§31): rain-event ponding per field + SSURGO
   drainage → `data/analysis/farm_units.csv`. Decide first on open-water evaporation
   (`agri_sfincs/evap.py`; −40% cropland area-days wet on Sep 2023, §17).
5. **Farm → wetland options (only if the user wants them):** set-back variants, Middle Neck at
   marsh level, roughness, Sandy with rain, Durham's lidar marsh bias.
6. **NAIP validation of the exits**, NJ (`exit_spotcheck.py`, default tag cells_v2) and DE.
7. **Check NLD** for levee condition / inspection fields.

## Shared / not yet shared (all private until the user shares)
- Claude Doc "Bayshore farmland and storm flooding: where the story is" (for Seowoo and James):
  https://claude.ai/code/artifact/b6020269-e82b-413f-9430-59783a9d2828; talk figures
  `reports/figs/talk_*.png` (`scripts/plot_talk_figs.py`).
- Claude Doc "Water-related crop-insurance losses": https://claude.ai/artifact/P62Vj4zoqFzRJy7BDBb7Xy
- The per-field sample (§32).
- Storm panel bundle for Seowoo: `/cache/home/tpj8/bayshore-storm-panel`
  (`scripts/export_storm_panel.py`); the user makes it a private GitHub repo.

## Operational
- **Bulk data is symlinked into /scratch/tpj8/sfincs-nj-agri/data_bulk** (bed_*.tif, nwm grid,
  ehydro, landsat, floodplain, prism, rma_states). After a purge, rebuild with the script named
  in each one's docstring.
- **Runs: ~1 min per simulated day on 32 threads, bit-reproducible.** Always
  `sbatch hpc/sfincs_run.slurm`: the VS Code job has only 4 CPUs.
- **Tide-only runs have zeroed rain:** the engine segfaults with cnb and no rain file.
- `v1_100m/runs/tide2024oct_intact_slr000_rep` is compare_restore.py's noise floor. Keep it.
- `v1_100m/runs/y2023_zsini{0,m1}` are staged. Do not submit them unless the user asks.
