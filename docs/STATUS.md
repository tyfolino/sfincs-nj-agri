# STATUS: what is happening now

Keep this short and forward-looking. When an item closes, move its durable fact to FINDINGS
and delete it here. History lives in git.

Last updated: **2026-11-02** (§29's rise separated into beds and boundary, §55).

## Goal
A map of bayshore farmland: current, threatened by sea-level rise, and dike-dependent, from
SFINCS same-event scenarios (FINDINGS §27, §29-§31), now on BOTH shores: NJ + Delaware (C&D
Canal to Lewes) as twin grids forced on the same mid-bay state line. Joint ag-econ work: the
**dike pay-off** and Seowoo's **flood → farm exit** paper (AERE abstract, mid-January 2027; her
result holds on 2008-23). Plan: `~/.claude/plans/no-need-to-draft-idempotent-goblet.md`.

## Resume here (plan steps)
- **Step 1, NJ model: `e3v2a30brm65_100m` adopted** (§45, §47, §48); full rerun done with wind (§50,
  §52); storm panel on it (§53). **§29's rise explained (§55):** report flooded hectares and the
  threshold range beside any field-class number. Open: Bivalve's storm-peak scatter (§50); Stow / upper
  Oldmans still short (no data). USGS 2022 Alloway survey email: on hold (user).
- **Step 3, Delaware: `de_v2ap45_100m` adopted** (§51, §54). The line differs from NJ's by ~0.11 m of
  range at 39.0-39.2 N; say so in the bundle notes for Seowoo. **Storm runs:** 17 tide-only done
  (logs clean, linked, no gauge check yet). Rain twins running (`*_rain_{hrrr,era5}`, listed in
  `logs/py_63432921.out` and `py_63432922.out`; daily maps). When done: check logs, compare one rain
  run's daily peaks against an hourly twin (§56 tested tide-only), then a DE gauge check of the storm peaks.
- **Step 5, Delaware exits:** first look done without SFINCS (§44). Next: DE storm panel
  (`build_storm_panel.py` side-aware) → one bundle with a `state` column for Seowoo.

## Next, in order
0. **Storm-history land-use test:** no clear crop response to the 7 spring storms, m65 (§53, §35,
   §37). "Not detectable", not "no effect"; the next-season cropland gap against never-flooded
   fields is unexplained. Reviewed and corrected 2026-11-01; show the colleague and the advisor
   (`reports/storm_panel_m65.md`, `data/analysis/storm_panel_m65/`). User: storm tides only;
   growing season = Apr-Oct. `sandy_panel` / `storm_panel` untagged are still v1.
1. **Tide gates:** public search done (§36); the leads that need a person are the user's call.
2. **Plan checks:** mass balance; where station peaks rise by more than the SLR.
3. **Per-system breach runs** (18 systems × 4 SLR) on tide2024oct with a scoured sill (MLLW): the
   farmland each bank protects, against repair costs ($0.75-14 M). (§27, §30) The dike pay-off's
   input. **Running (2026-11-02):** 68 new runs, `*_restore_<system>_mllw100_slr*_hrrr`, listed in
   `logs/py_63432268.out`; daily maps (§56), 4 older Durham / Middle Neck runs reused. When done:
   check logs, then the farmland per system. Report flooded ha and the threshold range (§55).
   Gibbstown has 6 outlets, cut at one: read it with care.
4. **Wetness exposure for the conversion model** (§31): rain-event ponding per field + SSURGO
   drainage → `data/analysis/farm_units.csv`. Decide first on open-water evaporation
   (`agri_sfincs/evap.py`; −40% cropland area-days wet on Sep 2023, §17).
5. **Farm → wetland options (only if the user wants them):** set-back variants, Middle Neck at
   marsh level, roughness, Sandy with rain, Durham's lidar marsh bias.
5a. **Flood-map check done (§58):** place partly right, extent too wide, field flags barely match satellites. **Next:
   salt tests** (bay position, tide vs rain, recovery), using flooded share too. **Exit measure:** both flags kept;
   noisy on low ground, and over half of flags return (§57). Ask Seowoo her definition; MOD-IV pilot.
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
- **Scratch quota (shared with nj_bight_sfincs):** 1 T soft, about 1005 G on 2026-11-02, about 15 G
  more to come from the running sets. Stage new sets with `--link`, and `--daily-map` where hourly
  maps are not read (§56); `scripts/link_run_inputs.py` for older runs. Never edit a run's linked
  inputs in place. If more room is needed, first `e9_100m` outputs (~18 G), then the
  23 superseded test models (one or two runs each, ~66 G: e2-e6, v2*, e3v2 tests, de_v0, de_v2, de_v2ap30, v1dikes, v1drained).
- **Bulk data is symlinked into /scratch/tpj8/sfincs-nj-agri/data_bulk** (bed_*.tif, nwm grid,
  ehydro, landsat, floodplain, prism, rma_states). After a purge, rebuild with the script named
  in each one's docstring.
- **Runs: ~1 min per simulated day on 32 threads, bit-reproducible.** Always
  `sbatch hpc/sfincs_run.slurm`: the VS Code job has only 4 CPUs.
- **Tide-only runs have zeroed rain:** the engine segfaults with cnb and no rain file.
- `v1_100m/runs/tide2024oct_intact_slr000_rep` is compare_restore.py's noise floor. Keep it.
- `v1_100m/runs/y2023_zsini{0,m1}` are staged. Do not submit them unless the user asks.
