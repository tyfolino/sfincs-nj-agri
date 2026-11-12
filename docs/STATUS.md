# STATUS: what is happening now

Keep this short and forward-looking. When an item closes, move its durable fact to FINDINGS
and delete it here. History lives in git.

Last updated: **2026-11-12** (final DE model checked, §73; bundle pushed: DE `dek`, dike tables, short README; Seowoo's reply; hay lag test, §74; `/wrapup` skill added).

## Goal
A map of bayshore farmland: current, threatened by sea-level rise, and dike-dependent, from
SFINCS same-event scenarios (FINDINGS §27, §29-§31), now on BOTH shores: NJ + Delaware (C&D
Canal to Lewes) as twin grids forced on the same mid-bay state line. Joint ag-econ work: the
**dike pay-off** (main line, user + Seowoo, 11-12) and Seowoo's **flood → farm exit** paper (AERE
abstract, mid-January 2027). Plan: `~/.claude/plans/no-need-to-draft-idempotent-goblet.md`.

## Resume here
- **Models:** NJ `e3v2a30brm65_100m` (§45-§55), DE `de_v2ap45mk45o_100m` (§69, §73). Report flooded hectares and the
  threshold range beside any field-class number (§55). Open: Bivalve's storm-peak scatter (§50); Stow / upper Oldmans
  short (no data); Frederica's rain response (Irene +0.7 m, Sandy +0.3 m); USGS 2022 Alloway survey email on hold (user).
- **Cape May bed (fix, user):** the bay east of ~75.0 W is a flat 0.0 m bed in both grids' subgrid (DE ~40 km² of
  active cells; likely a bathymetry tile edge), so those mouth cells are not open boundary. NJ land there is fine.
  Find the source, refill, rebuild, recheck the gauges; then re-export the bundle (its README warns of this).
- **Seowoo (11-12):** bundle pushed (`/cache/home/tpj8/bayshore-storm-panel`); the user sends her the link. She is busy
  until Thanksgiving and will ask Salem farmers about the dikes. Her county data show a shift to hay with a ~3-year
  lag; our test (§74, kept out of the bundle, user): nothing timed to floods, a possible slow drift on the most-flooded
  NJ fields. Ask her hay definition and whether her lag is to one flood or to repeated flooding. Exit tests all null
  (§53, §57, §70-§72).

## Next, in order
1. **Tide gates:** public search done (§36); the leads that need a person are the user's call.
2. **Plan checks:** mass balance; where station peaks rise by more than the SLR. Dike seal done (§66, §68). Left:
   **Gibbstown** (286 ha of bay water in the intact run through an unbanked swamp side; DVRPC 2004 says Repaupo is
   not tidal above its gates) needs someone who knows the site (user).
3. **Dike pay-off** (§59, §60): banks keep ~300 ha of water off fields today and at +0.3 m, ~90 ha at +0.6 m; Middle
   Neck 43%. Costs: 5 of 18 systems have a figure, mostly gates; scale banks by length. Gibbstown cut at 1 of 6 outlets.
4. **Wetness exposure for the conversion model** (§31): rain-event ponding per field + SSURGO drainage →
   `data/analysis/farm_units.csv`. Decide first on open-water evaporation (`agri_sfincs/evap.py`, §17).
5. **Farm → wetland options (only if the user wants them):** set-back variants, Middle Neck at marsh level,
   roughness, Sandy with rain, Durham's lidar marsh bias.
6. **Open from the checks:** why flooded DE fields keep MORE cropland than DE prone-dry (§64; rerun without the fields
   beside Bowers / Slaughter Beach after the DE lower-bay peaks are fixed, user 11-04). Exit measure noisy on low
   ground (§57): ask Seowoo her definition; MOD-IV pilot; NAIP check of exits (`exit_spotcheck.py`), NJ and DE.
7. **Check NLD** for levee condition / inspection fields.

## Shared / not yet shared (all private until the user shares)
- Claude Doc "Bayshore farmland and storm flooding: where the story is" (for Seowoo and James):
  https://claude.ai/code/artifact/b6020269-e82b-413f-9430-59783a9d2828; talk figures
  `reports/figs/talk_*.png` (`scripts/plot_talk_figs.py`).
- Claude Doc "Water-related crop-insurance losses": https://claude.ai/artifact/P62Vj4zoqFzRJy7BDBb7Xy
- The per-field sample (§32).
- Storm panel bundle: `/cache/home/tpj8/bayshore-storm-panel` (`scripts/export_storm_panel.py`), private GitHub, pushed 11-12.

## Operational
- **Scratch (quota shared with nj_bight_sfincs, 1 T soft):** this repo 173 G on 11-12. Models: m65, DE `mk45o` (36
  `_m70` runs), v1 (sep2023 + variants, may2025 + gatehi, y2023 staged, _rep: user keeps the variants). Stage new sets
  with `--link`, and `--daily-map` where hourly maps are not read (§56); `scripts/link_run_inputs.py` for older runs.
  Never edit a run's linked inputs in place. Next lever: thin m65 hourly maps to daily (check readers first).
- **Bight data** (`config.BIGHT_DATA`, 7 inputs): all read fine after the 11-10/11 maintenance (checked 11-12).
- **Bulk data is symlinked into /scratch/tpj8/sfincs-nj-agri/data_bulk** (bed_*.tif, nwm grid, ehydro, landsat,
  floodplain, prism, rma_states). After a purge, rebuild with the script named in each one's docstring.
- **Runs: ~1 min per simulated day on 32 threads, bit-reproducible.** Always `sbatch hpc/sfincs_run.slurm`: the VS
  Code job has only 4 CPUs. Slurm 25.11 since 11-11: `srun --overlap` needs `-n 1`; no backgrounded `salloc`.
- **Tide-only runs have zeroed rain:** the engine segfaults with cnb and no rain file.
- `v1_100m/runs/tide2024oct_intact_slr000_rep` is compare_restore.py's noise floor. Keep it.
- `v1_100m/runs/y2023_zsini{0,m1}` are staged. Do not submit them unless the user asks.
