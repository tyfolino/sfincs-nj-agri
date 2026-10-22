# STATUS: what is happening now

Keep this short and forward-looking. When an item closes, move its durable fact to FINDINGS
and delete it here. History lives in git.

Last updated: **2026-10-22** (E9 preview runs submitted; ag-econ direction: dike pay-off).

## Goal
A map of bayshore farmland: current, threatened by sea-level rise, and dike-dependent, from
SFINCS same-event scenarios (FINDINGS §27, §29-§31; plan `~/.claude/plans/compressed-humming-eclipse.md`).
**Proposed (2026-10-15, ag-econ + advisor):** field-level land-use response to flooding, maybe
NJ-VA. Gate: does modeled Sandy flooding explain crop change beyond elevation (Epanchin-Niell
et al. 2023, `docs/refs/27000.pdf`)? If yes, Delaware Bay (both shores) next.

## Resume here
- **E9 preview, 18 runs** (chain boundary, `setup_scenarios.py --open`; submit log
  `models/e9_100m/runs/submit_e9_preview.log`): tide2024oct {intact, removed} × SLR {0, 0.3};
  7 spring storms, tide and rain. Then: does §29's 1,117 ha dike-dependent move (sent to
  Seowoo/James as ~2,760 acres)? And `validate_storm_{gauges,landsat}.py --model e9_100m` vs §39.
- **Ag-econ direction (2026-10-22):** joint project = **dike pay-off** (repair cost vs farmland
  kept farmable, over SLR; input = Next 3). Seowoo's exit result (leave ag 1-2 yr after a flood)
  fails a rough re-check: gone without CDL 2024-25, fields return by yr 2-3. She was asked for
  definitions + a 2008-23 re-run; Delaware model only if it holds. Crop choice, marsh on hold.
- Ag-econ progress notebook: `notebooks/model_progress_agecon.ipynb`.

## In progress: creek beds (§39-§43)
The side creeks carried about half the real tide, which made per-field storm flooding noisy.
Now: bay boundary fixed and adopted ("chain", §41). Measured depths give the measured tide:
Big Timber 0.47 → 0.97, Oldmans fixed as far as its soundings go, Cohansey at 7 ft still short
(Greenwich 0.72, §43). Next:
- **v2 beds:** add the NOS soundings to `build_riverbeds.py` as a sounding source (now only in
  `scripts/build_bed_e9.py`, soundings in `data/channels/nos/`), plus the Alloway weir fix (`dikes_open.weir`);
- **Cohansey, Stow, upper Oldmans:** no data. Options: USACE Philadelphia District condition
  surveys for `CENAP_CO_01_CRC` (needs a person; Claude can draft the email); the 1905-06 RUcore
  sheets read by eye; or calibrate an effective depth on the calm-window gauges, judged on the
  held-out stations, storm peaks and Landsat (§39);
- **then re-run the storm and scenario sets once**, on v2 beds and the chain boundary. Until then
  `setup_scenarios.py` keeps the old boundary so the existing set stays comparable.

## Next, in order
0. **Storm-history land-use test: first look done** (§35, §37, §38): no detectable crop or NDVI
   response; a weak corn → soy tilt where fields are wet on ordinary tides. The creek-bed fix may
   sharpen this ("not detectable", not "no effect"). Show the colleague and the advisor
   (`reports/storm_panel.md`, `data/analysis/storm_panel/`). Open: model the unmodelled storm
   tides (Irene 2011, Oct 2018, Isaias 2020, Jan 2024, Aug 2025), or use exposure as one number
   per field (n_storms_tide).
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
6. **NAIP validation of the v2 exits** (`exit_spotcheck.py --tag cells_v2`), then field_history.py (§24).
7. **Check NLD** for levee condition / inspection fields.

## Waiting on
- **"South Jersey Levee Inventory"** (NRCS / NJDEP Dam Safety, 2010): the user's supervisor is
  asking NJDEP (2026-10-17).

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
