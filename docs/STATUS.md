# STATUS: what is happening now

Keep this short and forward-looking. When an item closes, move its durable fact to FINDINGS
and delete it here. History lives in git.

Last updated: **2026-10-15** (Sandy validation done; nothing on SLURM).

## Goal
A map of bayshore farmland: current, threatened by sea-level rise, and dike-dependent. It comes
from SFINCS same-event scenarios (FINDINGS §27, §29-§31); the plan is
`~/.claude/plans/compressed-humming-eclipse.md`.
**Proposed (2026-10-15, ag-econ + advisor):** field-level land-use response to flooding, maybe
NJ-VA, event-based. Gate: does modeled Sandy flooding explain crop change beyond elevation
(Epanchin-Niell et al. 2023, `docs/refs/27000.pdf`)? If yes, Delaware Bay (both shores) next.

## Resume here
- Sandy run validated against the interior gauges (§33). MOTF is a bathtub rival, not truth.
- Panel built: `data/analysis/sandy_panel/` (fields.csv, field_year.csv = CDL 2008-25 group
  shares, README). It has a survivorship flaw, though: fields = LU/LC farm in 2015 AND 2020, so
  2013-19 exits are missing.
- The progress notebook for the ag-econ group: `notebooks/model_progress_agecon.ipynb`.

## Next, in order
0. **Sandy land-use test:**
   - Rebuild the panel on fields farmed in 2012 (`data/landuse/njlulc_2007_2012.gpkg` /
     `field_units.gpkg`). They need their own Sandy per-field stats (fieldflood.run_stats on
     the intact, removed and rain runs), plus MOTF share as the bathtub alternative.
   - Then plot corn / idle / exit share by year, flooded vs dry within height bands, and hand
     the table to the colleague. Duration stays out (§16).
1. **Tide gates from public sources** (background agent): NRCS post-Sandy repair documents,
   NAACC culvert inventory, WMA / refuge plans (Abbotts Meadow, Mad Horse Creek, Supawna),
   Partnership for the Delaware Estuary, county documents.
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

## Pending decisions (user)
- Add a `cdl2024_pasture_pct` column to field_flood_sample.py? (§32: 435 → 555 fields.)
- Soil drainage class for the panel? `fetch_ssurgo.py` gets only HSG / ksat; the panel uses HSG D
  share as a stand-in.

## Waiting on
- **The user's local tide-gate knowledge.** In priority order: location and the creek each gate
  drains to (§16), invert, condition, count / size, pumps. Middle Neck plus a few Cumberland necks
  would do.
- **The "South Jersey Levee Inventory"** (NRCS / NJDEP Dam Safety, 2010), via the user's NJDEP
  contact.

## Shared / not yet shared
- Claude Doc "Water-related crop-insurance losses, Salem / Cumberland / Gloucester"
  (https://claude.ai/artifact/P62Vj4zoqFzRJy7BDBb7Xy). It is private until the user shares it.
- The per-field sample (§32) is not sent yet; the user shares it.

## Operational
- **Bulk data lives on scratch as symlinks into /scratch/tpj8/sfincs-nj-agri/data_bulk:**
  data/elevation/bed_*.tif, data/nwm/grid, data/channels/ehydro, data/{landsat, floodplain,
  prism, rma_states}. If a purge takes them, rebuild with the fetch_* / build_* script that
  writes each one (its docstring says which).
- **Runs take ~1 min per simulated day on 32 threads.** They are bit-reproducible.
- **Tide-only runs have zeroed rain:** the engine segfaults with cnb and no rain file.
- `v1_100m/runs/tide2024oct_intact_slr000_rep` is compare_restore.py's noise floor. Keep it.
- `v1_100m/runs/y2023_zsini{0,m1}` are staged. Do not submit them unless the user asks.
