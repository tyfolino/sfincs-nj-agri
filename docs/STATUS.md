# STATUS — what is happening now

Edit in place; keep it short. When an item closes, its durable fact moves to FINDINGS.

Last updated: **End of 2026-10-06 (user: wrap up; nothing queued on SLURM; all work staged, the user commits).**
- **Goal (user):** a map of current farmland, farmland threatened by sea-level rise, and
  DIKE-DEPENDENCY. SFINCS same-event scenarios are the main story. The satellite record of
  fields already lost is supporting evidence (FINDINGS §21-§24). Dike crests vs Sandy: §25.
- **Done today:**
  - **Scenario matrix §27:** 25 runs, tide2024oct × {intact, removed, breach_all_farm} × SLR and
    sandy2012. `plot_scenarios.py` → reports/scenario_matrix.md + figs; GIFs from
    `animate_scenarios.py`.
  - **Per-field classes §29 (the user's map):** `field_flood_classes.py` →
    data/analysis/field_flood_classes.csv, figs/field_flood_classes{,_zoom}.png. 1,117 ha are
    dike-dependent today.
  - **Field classifier fixed §28:** OOF accuracy 58.5% → 83.6%.
  - **Farm → wetland phase 1 §30 (Middle Neck, Durham):**
    - full re-opening floods the polder's own farms;
    - the set-back with an inner dike spares them;
    - outside the bank: < 1 mm on daily tides;
    - literature check: reports/literature_restoration_neighbours.md.
    Scripts: make_restore_scenarios.py, setup_scenarios.py --restore, compare_restore.py.
  - **Conversion pathways synthesis §31:** dikes are not the main recent route.
  - Useful facts: SFINCS runs are bit-reproducible (repeat run diff = 0). A run is ~1 min per
    simulated day on 32 threads. Tide-only runs have ZEROED rain (the engine segfaults with cnb
    and no rain file).
- **2026-10-08: sample data for the ag-econ colleague** (one scenario: tide2024oct, dikes intact, +0.6 m):
  `scripts/field_flood_sample.py` → data/analysis/sample_tide2024oct_intact_slr060/ (fields.gpkg/csv,
  daily.csv, README.md). Per field: CDL 2024 crop mix + flooded %, first/last date, flood days,
  longest run (Hazus-style duration: Hazus crop tables use start day + duration, not depth), depth.
  1,273 fields flood (= §29). Not yet sent; the user shares it.
- **2026-10-09: colleague's feedback on the sample, answered in chat (no code changed):**
  - 1,273 is right, but in area it is 2,036 ha flooded (~2.7% of farm polygons). Of the 1,273:
    - 761 are LU/LC 2140;
    - 435 are ≥ 50% cropland (1,159 ha flooded);
    - 236 already flood today;
    - 684 are wet all 31 days.
  - Days per month: October 2024 only. Other months need new runs.
  - Spring salt flood → that season is lost or replanted; years only on heavy or poorly drained
    soil, or where water is trapped behind dikes. RMA treated Rita's salt as prevented planting
    (2006 memo).
  - 2140 = farmland on mapped wetland: ~54% CDL cropland and sticky after abandonment.
  - **Pending, the user decides:**
    - add `cdl2024_pasture_pct` (CDL 176) as a separate column in field_flood_sample.py. Hay
      36/37 is already cropland. Adding pasture gives flooded ≥ 50% fields 435 → 555 and
      1,159 → 1,369 ha.
    - Offered: a Sandy natural experiment. Do fields Sandy flooded in the model show fallow or a
      crop switch in 2013-14 (CDL / Landsat) and prevented planting in RMA 2013?
- **2026-10-12: progress notebook for the ag-econ group** (plots only, viewed on GitHub):
  notebooks/model_progress_agecon.ipynb, figure code in notebooks/progress_figs.py. New
  `scripts/field_flood_sandy.py` → data/analysis/field_flood_sandy2012.csv: the §29 per-field numbers
  for the 13 Sandy runs. Fields flooding (dikes as built, tide only) today / +0.3 / +0.6 / +1.0 m:
  860 / 1,317 / 1,776 / 2,255 (896 / 2,038 / 3,603 / 5,376 ha under water); with Sandy's rain, today:
  2,448 fields but only 1,915 ha.
- **Next, in order:**
  1. Plan checks: Sandy peak vs the observed interior gauges (Bivalve etc.; the Ship John his
     point is outside the active cells, NaN); mass balance; where station peaks rise > SLR.
  2. Per-system breach runs (18 systems), on tide2024oct AND with a scoured sill (MLLW): a
     marsh-level gap does almost nothing (§27, §30). Gives the farmland each bank protects, for
     the econ table against repair costs ($0.75-14 M).
  3. Wetness exposure for the conversion model (§31: the largest recent route is wet-field
     abandonment, not tides). Ponding under rain events (sep2023 / may2025 / Sandy with rain)
     per field, plus SSURGO drainage class, joined to field_flood_classes.csv → the
     plan's data/analysis/farm_units.csv.
  4. Farm → wetland options (only if the user wants them):
     - set-back sensitivity: gate placement, a channel to the western strip, a straighter dike;
     - Middle Neck ground raised to marsh level (subgrid rebuild);
     - roughness sensitivity;
     - Sandy with rain;
     - Durham's lidar marsh bias.
  5. NAIP validation of v2 exits, ~50 per stratum; re-run field_history.py (§24) on the fixed
     pieces.
  6. Check NLD for levee condition / inspection fields.
- **PSEG special issue read (2026-10-06):** yes, PSEG built upland dikes to protect adjacent
  properties (FINDINGS §30). PDFs in docs/refs/ (gitignored).
- **Waiting on the user:**
  - local tide-gate knowledge, in priority order: LOCATION and the creek each gate drains to
    (§16: most synthetic valves cannot drain), invert elevation, condition (leaking / stuck),
    count and size, any pumps. Middle Neck + a few Cumberland necks would do. Not urgent:
    the tide-only scenario comparisons barely depend on gates; post-storm / rain wetness does.
  - the user is asking an NJDEP contact (via family) for the "South Jersey Levee Inventory"
    (NRCS / NJDEP Dam Safety, 2010; cited in the Cumberland Bayshore Recovery Plan 2013).
- **Tomorrow, first (user, 2026-10-06):** a background agent sweeps public sources for tide-gate
  data: NRCS post-Sandy repair documents, the NAACC road-crossing / culvert inventory (tide
  gates), WMA / refuge plans (Abbotts Meadow, Mad Horse Creek, Supawna), Partnership for the
  Delaware Estuary, county documents. Then continue with Next 1.
- **Fork 1 done (agent, §26):** null (b2 = 0.01 ± 0.35). The agent ran `ls data/insurance` once
  (output discarded, no file opened); the user has been told.

**Plan revised and approved 2026-10-05: `~/.claude/plans/compressed-humming-eclipse.md`.**
- **Fork 2 (main): bayshore farm → wetland.**
  1. Outcome inventory from NJDEP LU/LC editions (classes 2150 / 2140, and ag → 6xxx).
  2. Pathway of each conversion: easement / public purchase / mitigation / PSEG / passive.
  3. Exposure covariates per farm unit, static and from SFINCS (typical tide, Sandy 2012,
     Sep 2023).
  4. SFINCS same-event scenarios: farmed vs restored, intact vs breached bank, +SLR.
- **Fork 1 (basic, agent):** cross-county RMA COL × PRISM × static FEMA-floodplain cropland
  share; PPML / two-part; memo `reports/fork1_flood_rain.md`.
- Fork 2 step 1, first pass done (FINDINGS §23): NJDEP LU/LC gives 840 ha farm → wetland 1995-2020,
  mostly inland old fields, and it MISSES recent tidal conversions (sticky class 2140). Next:
  NAIP-dated field histories of the low-lying farmed / 2140 polygons. Fork 1: agent running.
- Landsat field histories built (FINDINGS §24): low ground exits farming 5-7× faster than upland
  (raw); NAIP precision ~40-55% low vs ~12% upland, so roughly 10× after correction, with wide
  uncertainty. Low fields go to marsh / scrub; upland fields go to development. Next: a
  multi-class classifier trained on LU/LC classes and a bigger NAIP validation. Bulk Landsat
  stats live in data/landsat → /scratch.

**Direction change (user, 2026-10-05).** The insurance question is a poor fit for SFINCS:
water losses are 18% of indemnity, 91% "excess moisture", river/coastal flooding ≲ 10–15% of
water dollars (FINDINGS §20), and county-month data can't resolve gains < ~+0.03 AUC (§13).
- **SFINCS's role in the loss study = event-scale ponding only** (no multi-year runs; the staged
  `v1_100m/runs/y2023_zsini{0,m1}` are NOT to be submitted unless the user asks). Diked cropland
  (~15 km², ~2%) to be reported separately / excluded from ponding features (§19).
- **NEW lead the user is excited about: saltwater intrusion / tidal inundation of bayshore farmland
  under sea-level rise and aging meadow banks / tide gates (Cumberland, Salem).** Novel for this
  area. SFINCS: dikes (§14), tide boundary (§6), burned tidal channels (§11), gates; SLR + storm
  tide + breach/overtopping scenarios → per-field saltwater frequency/duration. Outcome to
  measure: cropland → marsh/fallow transitions in CDL 2008–2025 along the bayshore (salinity
  code 76 never appears in these counties' RMA records, so salt shows up as land leaving
  production, not claims). Ag-econ angle: land value lost, dike maintenance vs retreat, who pays,
  easements/buyouts. **Next: look into #1 more deeply** — first quantify bayshore cropland change
  in CDL, and check the literature on Delaware Bay / Delmarva saltwater intrusion and farmland.
- **Saltwater lead, step 1 done (FINDINGS §21, `reports/bayshore_exposure.md`, map
  `reports/figs/bayshore_exposure.png`):** 7 km² of cropland is below today's MHHW (mostly
  behind NLD dikes, Middle Neck first), 28 / 40 km² below MHHW + 1.0 / 1.5 m (mostly OUTSIDE
  levees). Imagery check (`reports/imagery_spotcheck.md`): ~1/3 of CDL's low cropland → wetland
  signal is real (~1.5 km² since 2010). The clearest case is a diked field complex S of Greenwich
  (NLD "Durham") going to marsh 2013-19. Literature survey done: `reports/literature_saltwater.md`
  (NJ farmland side unstudied quantitatively; summary in FINDINGS §21). Next: the Greenwich site's history (breach? buyout?), then the SFINCS scenario set.
- **Colleague (Seowoo, ag-econ) replied 2026-10-05:** no farm-level RMA data exists, and a
  farmer survey needs a grant. Two forks, user agreed: (1) a BASIC test of
  Damage ~ P + P × flooded-cropland share (expect null in 3 counties; a cross-county design with
  a static flood-prone share is the cheap version); (2) the MAIN line: farm-to-wetland via
  Wetland Reserve Easements + saltwater exposure, with SFINCS for same-event counterfactuals
  (farmed vs restored). NRCS easements fetched and overlaid: FINDINGS §22. The plan is being
  rewritten (plan mode).
- **Bulk data moved off /home (user OK'd, 2026-10-05):** data/elevation/bed_merged.tif,
  bed_v1.tif, data/nwm/grid and data/channels/ehydro are now symlinks into
  /scratch/tpj8/sfincs-nj-agri/data_bulk (rebuildable: build_bed.py, merge_bed_v1.py,
  fetch_nwm_soil.py, fetch_channels.py). If scratch purges them, rebuild.
- Evaporation agent finished: FINDINGS §17. Works as a bulk ponded-water loss, NOT integrated
  into `setup_event` (event-scale runs don't need it after the pivot).
- Shared with colleagues: Claude Doc "Water-related crop-insurance losses, Salem / Cumberland /
  Gloucester" (https://claude.ai/artifact/P62Vj4zoqFzRJy7BDBb7Xy; private until the user shares).
  Offered but not done: a one-line AUC gloss and a paragraph on §20 in that doc.
- DROPPED (user, 2026-10-06: not important): the 235 vs 238 / 240 insurance-cell discrepancy
  (report vs FINDINGS §5).

All work staged with `git add` (the user commits). Models/runs on /scratch (purged when idle).

## Done (step 1)

- Repo scaffold: `agri_sfincs/`, `scripts/`, `tests/` (37 tests, OK). The insurance sample
  was moved to `data/insurance/`.
- `fetch_wbd.py`: 38 HUC12s and the ring.
- `fetch_tiger_counties.py`: NJ counties.
- `fetch_cdl.py`: CDL 2008–2025.
- `cropland_coverage.py` (FINDINGS §1).
- `gauge_inventory.py`:
  - USGS done (FINDINGS §3);
  - NOAA hourly 2002–2025 downloaded (FINDINGS §3).

## Done since (2026-10-02, afternoon)

- `fetch_ssurgo.py`: HSG (drained + undrained) and harmonic-mean ksat rasters.
- `fetch_nlcd.py`: NLCD 2021.
- `fetch_structures.py`: NID, NLD (incl. the meadow banks), head of tide, lakes.
- `fetch_rma_col.py`: RMA Cause of Loss 1989–2026 (FINDINGS §4–5).
- `build_waterlevels.py`: 5 forcing gauges, NAVD88, gap-filled and holdout-tested (FINDINGS §6).

## Plan revision (user, 2026-10-02): two tracks

Plan file "REVISION" section. **A**: cheap predictors (NWM retrospective soil moisture, MRMS /
Stage IV rainfall metrics) + an RMA loss-ratio panel, tested first. **B**: the SFINCS grid in
parallel; first target is event simulations of **Sep 2023 (Cumberland)** and **May 2025 (Salem)**,
the two months the ag-econ team flagged.

## v1 to-do (from the v0 event runs, FINDINGS §9)

1. River beds: NOAA ENC soundings in the navigable tidal reaches (Maurice → Millville,
   Cohansey → Bridgeton, Salem River, Alloway Creek); above head of tide, lidar water
   surface minus the USGS `channel-measurements` mean depth (area / width), interpolated
   between gauges.
2. Cross-sections at the stream gauges, so discharge can be compared.
3. Western-Salem persistent water: CDL-vs-marsh check (NJDEP LU/LC 2015 / NLCD), and the
   NLD meadow banks and pipe gates (tide gates) as structures.
4. Then refine: 50 m over cropland (cost is not the constraint: ~70 min per 47-day run at
   100 m on 16 threads).

## Next

- A1 + A3 DONE (FINDINGS §8). A2 (MRMS / Stage IV rainfall metrics per county-month) and
  A4 (the first predictor-vs-loss test, 2003–2022 with NWM) are next for track A.
- B: the bed is pre-merged (`build_bed.py`; CUDEM 0-fill kept out). River beds: v0 = lidar
  water surface (smoke test only); v1 = NOAA ENC soundings in the navigable tidal
  reaches + lidar water surface minus a gauge-derived depth above head of tide (user,
  2026-10-02), as bight's `riverbeds_v4`.
- B: seaward water-level line → data catalog → quadtree build → MRMS Pass2 for
  2023-08-15..2023-10-01 and 2025-04-15..2025-06-01 → the two event runs.

## Waiting on the ag-econ team

Most questions are answered by RMA COL itself (FINDINGS §5): month = month of loss;
negatives are signed corrections; Cape May has no COL rows after 2006. Still for them:
- Whether they want the 31+51 or the broad water definition.
- Whether a research agreement for unit-level data is worth pursuing.
