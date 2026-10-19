# STATUS: what is happening now

Keep this short and forward-looking. When an item closes, move its durable fact to FINDINGS
and delete it here. History lives in git.

Last updated: **2026-10-17** (all 22 storm runs in; no local tide-gate knowledge exists: public sources only).

## Goal
A map of bayshore farmland: current, threatened by sea-level rise, and dike-dependent. It comes
from SFINCS same-event scenarios (FINDINGS §27, §29-§31); the plan is
`~/.claude/plans/compressed-humming-eclipse.md`.
**Proposed (2026-10-15, ag-econ + advisor):** field-level land-use response to flooding, maybe
NJ-VA, event-based. Gate: does modeled Sandy flooding explain crop change beyond elevation
(Epanchin-Niell et al. 2023, `docs/refs/27000.pdf`)? If yes, Delaware Bay (both shores) next.

## Resume here
- Sandy run validated against the interior gauges (§33). MOTF is a bathtub rival, not truth.
- Panel on 2012 farm fields: `data/analysis/sandy_panel/` (fields.csv/.gpkg, field_year.csv,
  README); first look in `reports/sandy_panel.md` (§34).
- The progress notebook for the ag-econ group: `notebooks/model_progress_agecon.ipynb`.

## Next, in order
0. **Storm-history land-use test: first look done** (§35, §37). Null in fields storms flood
   only sometimes; a weak corn → soy tilt and slow cropland loss in the 100 fields wet on
   ordinary tides today, which flood in every storm. The 2011 corn dip is not confirmed. Next: show the colleague
   and the advisor (`reports/storm_panel.md`; the hand-off table is `data/analysis/storm_panel/`).
   Open choices: model the unmodelled storm tides (Irene 2011, Oct 2018, Isaias 2020, Jan 2024,
   Aug 2025; ~10 min each); or drop the storm-by-storm test and use exposure as one number per
   field (n_storms_tide) in the colleague's model.
1. **Tide gates:** the public-source search is done (§36). No inventory; a few confirmations. The
   leads that need a person are listed in §36 and are the user's call.
2. **Plan checks** (Sandy vs the interior gauges is done, §33):
   - mass balance;
   - where station peaks rise by more than the SLR.
3. **Per-system breach runs** (18 systems), on tide2024oct and with a scoured sill (MLLW). A
   marsh-level gap does almost nothing (§27, §30). This gives the farmland each bank protects,
   for the econ table against repair costs ($0.75-14 M).
4. **Wetness exposure for the conversion model** (§31). Ponding under rain events (sep2023 /
   may2025 / Sandy with rain) per field, plus SSURGO drainage class, joined to
   field_flood_classes.csv → `data/analysis/farm_units.csv`. Decide first whether to switch on
   open-water evaporation (`agri_sfincs/evap.py`, not yet in setup_event): on Sep 2023 it cut
   cropland area-days wet by ~40% (§17).
5. **Farm → wetland options (only if the user wants them):**
   - set-back variants (gate placement, a channel to the western strip, a straighter dike);
   - Middle Neck raised to marsh level;
   - roughness;
   - Sandy with rain;
   - Durham's lidar marsh bias.
6. **NAIP validation of the v2 exits** (~50 per stratum, `exit_spotcheck.py --tag cells_v2`),
   then re-run field_history.py (§24) on the fixed pieces.
7. **Check NLD** for levee condition / inspection fields.

## Waiting on
- **The "South Jersey Levee Inventory"** (NRCS / NJDEP Dam Safety, 2010): the user's supervisor
  is asking their NJDEP contacts (2026-10-17).

## Shared / not yet shared
- Claude Doc "Bayshore farmland and storm flooding: where the story is" (2026-10-17, for Seowoo and
  James; https://claude.ai/code/artifact/b6020269-e82b-413f-9430-59783a9d2828). Private until the
  user shares it. Talk figures: `reports/figs/talk_*.png` (`scripts/plot_talk_figs.py`).
- Claude Doc "Water-related crop-insurance losses, Salem / Cumberland / Gloucester"
  (https://claude.ai/artifact/P62Vj4zoqFzRJy7BDBb7Xy). It is private until the user shares it.
- The per-field sample (§32) is not sent yet; the user shares it.
- Storm panel bundle for Seowoo (2026-10-19): `/cache/home/tpj8/bayshore-storm-panel`
  (`scripts/export_storm_panel.py`; rerun after panel changes). The user makes it a private
  GitHub repo and invites her.

## Operational
- **Bulk data lives on scratch as symlinks into /scratch/tpj8/sfincs-nj-agri/data_bulk:**
  data/elevation/bed_*.tif, data/nwm/grid, data/channels/ehydro, data/{landsat, floodplain,
  prism, rma_states}. If a purge takes them, rebuild with the fetch_* / build_* script that
  writes each one (its docstring says which).
- **Runs take ~1 min per simulated day on 32 threads.** They are bit-reproducible.
- **Tide-only runs have zeroed rain:** the engine segfaults with cnb and no rain file.
- `v1_100m/runs/tide2024oct_intact_slr000_rep` is compare_restore.py's noise floor. Keep it.
- `v1_100m/runs/y2023_zsini{0,m1}` are staged. Do not submit them unless the user asks.
