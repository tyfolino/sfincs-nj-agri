# STATUS — what is happening now

Edit in place; keep it short. When an item closes, its durable fact moves to FINDINGS.

Last updated: **2026-10-02, end of day.**

## ▶ Resume here

Stopped after the v0 event runs (FINDINGS §9). The user had not yet picked what comes
first:
- **Track B v1:** river channels first; see the "v1 to-do" list below.
- **Track A:** MRMS / Stage IV rainfall metrics per county-month, then the first
  predictor-vs-loss test for 2003–2022 with NWM + the loss panel.

Ask before starting. Nothing is running; all work is staged with `git add` (the user
commits). The v0 model and runs live on /scratch (purged when idle; rebuildable with
`scripts/build_model.py` + `scripts/setup_event.py`).

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
