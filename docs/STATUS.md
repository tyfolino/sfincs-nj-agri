# STATUS: what is happening now

Keep this short and forward-looking. When an item closes, move its durable fact to FINDINGS
and delete it here. History lives in git.

Last updated: **2026-10-23** (cleanup and NJ v2 beds done; Delaware first pass built; DE tide
too large: boundary next).

## Goal
A map of bayshore farmland: current, threatened by sea-level rise, and dike-dependent, from
SFINCS same-event scenarios (FINDINGS §27, §29-§31), now on BOTH shores: NJ + Delaware (C&D
Canal to Lewes) as twin grids forced on the same mid-bay state line. Joint ag-econ work: the
**dike pay-off** and Seowoo's **flood → farm exit** paper (AERE abstract, mid-January 2027; her
result holds on 2008-23). Plan: `~/.claude/plans/no-need-to-draft-idempotent-goblet.md`.

## Resume here (plan steps)
- **Step 1, v2 beds (NJ): done** (§45). Cohansey effective depth 6 m adopted; `v2_100m` being
  rebuilt with it (job `agri-v2final`, logs/v2final_*.out; = `v2c60_100m`, which scored it).
  Next: rerun the storm and scenario sets on `v2_100m` (`setup_scenarios.py --model v2_100m
  --boundary chain --open`); then §29's dike-dependent number. Stow / upper Oldmans still short
  (no data; calibrate like the Cohansey if field flooding there matters).
- **Step 3, Delaware: first pass built** (§46): `de_v2_100m` (bed_de_v2, NWI dike weirs).
  **Blocker: the DE shore gets ~15-20% too much tide** on the shared state-line forcing. Next:
  a DE-shore rail for the boundary (Lewes, Brandywine Shoal 8555889 [hourly cached], DE
  subordinate stations as virtual gauges as in §41), blended by cross-bay position; judge on
  Bowers, Cedar Creek, Odessa and the held-out DE stations (`check_creek_tides.py --side de`).
  Then the Appoquinimink (Odessa 0.26: needs depth like the Cohansey; H10200 covers 0 km of it).
  Rain: forcing is clipped to NJ's `RAIN_BBOX`; refetch event windows over the union first.
- **Step 5, Delaware exits:** first look done without SFINCS (§44): same pattern as NJ (low
  ground ~1.5 %/yr in both). Next, after the DE boundary fix: DE storm runs → DE storm panel
  (`build_storm_panel.py` side-aware) → one bundle with a `state` column for Seowoo.
- E9 preview set (18 runs) is superseded by v2.

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
6. **NAIP validation of the exits**, NJ (`exit_spotcheck.py`, default tag cells_v2) and DE.
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
