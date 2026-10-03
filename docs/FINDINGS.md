# FINDINGS — what is believed true

Durable facts, each with where it came from. STATUS holds what is in progress.

## 1. Domain and coverage (2026-10-02)

- **Ring:** 38 HUC12s, 3,564 km² once dissolved (WBD's own areas sum to 3,567). It is one
  polygon with no holes (`scripts/fetch_wbd.py`). The frontal HUC12s run out to the
  NJ/DE line in the river and bay, so the land area is smaller.
- **Cropland inside the ring** (CDL 2008–2025, `reports/cropland_coverage.md`):

  | County | Cropland (km²/yr) | Share inside the ring |
  |---|---|---|
  | Salem | 317 | 100% |
  | Cumberland | 217 | 99.6% |
  | Gloucester | 161 | 90% (range 88–92%) |

  The Great Egg headwaters left out hold ~10% of Gloucester cropland (8–12% by year),
  mostly soybeans, corn and hay. That is smaller than their ~17% share of Gloucester's
  land area.
- **Dominant crops in all three counties:** soybeans, corn, hay, and double-crop
  wheat/soy. Specialty crops are an order of magnitude smaller by area: peppers,
  peaches, blueberries, sweet corn, potatoes, squash, tomatoes.
- **CDL 2010 Gloucester outlier:** CDL calls 259 km² cropland, against ~160 km² in other
  years. Treat it as a CDL classification artifact until checked.

## 2. Data sources that work, and ones that don't (2026-10-02)

- **CDL:**
  - CropScape *bbox* requests time out.
  - The state-by-FIPS request (`GetCDLFile?year=Y&fips=34`) works.
  - Planetary Computer `usda-cdl` stops at 2021.
- **MRMS:**
  - Iowa State `mtarchive` has `GaugeCorr_QPE_01H` from mid-2015 (2014-10-01 is a 404)
    and 2-minute `PrecipRate` from at least 2016.
  - AWS `noaa-mrms-pds` starts 2020-10-14 (`MultiSensor_QPE_01H_Pass2`, plus the 15-minute
    and 2-minute products).
- **USGS:** the OGC API `time-series-metadata` collection accepts `bbox` and
  `parameter_code`. That is how `gauge_inventory.py` finds every series inside the ring.

## 3. Gauges (2026-10-02, `data/gauges/`)

USGS daily discharge inside the ring:
- **Full 2002–2025 records:** Maurice River at Norma 01411500, Raccoon Creek near
  Swedesboro 01477120.
- **Nearly full:**
  - Salem River at Woodstown 01482500: gap until 2002-09.
  - Cohansey River at Seeley 01412800: gap until 2003-08.
  - Mantua Creek at Pitman 01475001: gap 2006-10 → 2009-11.

  These gaps are real (one time series each, checked); they are not an artifact of picking
  a series.
- **Shorter records:**
  - Menantico Creek 01412000, 2019–2024.
  - Manumuskin River 01412080 and Raccoon Creek at Wrights Mill 01477070, from 2019–2020.
  - Little Ease Run 01411456, to 2016.

USGS tidal water level inside the ring:
- Maurice River at Bivalve 01412150, from 2000.
- Cohansey River at Greenwich 01413038, from 2000.
- Alloway Creek at Hancocks Bridge 01483050, from 2018.

NOAA hourly verified water levels, 2002–2025 (`data/gauges/noaa_completeness.csv`; raw
files in `data/gauges/noaa/`, in MLLW):
- **Complete every year:** Philadelphia 8545240 and Lewes 8557380.
- **Nearly complete:** Reedy Point 8551910 (≥93% every year) and Cape May 8536110
  (complete from 2004; 75% in 2003).
- **Ship John Shoal 8537121** (the only gauge on the Cumberland bay shore): gaps in 2002
  (38%), 2008–2009 (86% / 43%) and 2021 (81%); otherwise complete. It is MLLW-only, and
  bight's NAVD88 transfer for it is uncertain by about 0.1 m (bight
  `download_noaa_sandy_wl.py`).
- **Marcus Hook 8540433:** missing mid-2015 to early 2017 (51% / 0% / 91%).
- **Brandywine Shoal 8555889:** unreliable 2012–2017 (0–54% in 2013, 2014, 2016, 2017).
  Use it only where it is present.

## 4. Soils, land cover, structures (2026-10-02)

- **SSURGO** (`scripts/fetch_ssurgo.py`, `data/soils/`): 819 map units in the ring.
  - Area by soil group (km²): B 1,163; A 496; A/D 432; C 270; C/D 250; B/D 192; D 64;
    none 699 (mostly the river and bay).
  - **About 870 km², a quarter of the ring, is dual-group** (A/D, B/D, C/D). These soils
    get the D curve number unless they are drained, so the drained/undrained switch is a
    first-order sensitivity, not a detail.
  - Harmonic-mean ksat over 0–100 cm: area-weighted 26 µm/s, median map unit 14 µm/s.
- **Land cover:** Annual NLCD is NOT obtainable as single files. The S3 COGs answer 403,
  and the 2023 object is a 42-byte placeholder. NLCD **2021** comes from the MRLC WCS
  (`scripts/fetch_nlcd.py`) and is the static land cover; crop type by year comes from CDL.
- **Structures** (`scripts/fetch_structures.py`, `data/structures/structures.gpkg`):
  - **Dams:** 99 NID dams. The largest are Union Lake, Brown/Munson (Salem), Laurel Lake,
    Willow Grove, Alloway Lake, Sunset Lake, Malaga and Parvin. NID has heights but no
    crest elevations.
  - **Levees:** NLD **does include the bayshore meadow banks / salt-hay dikes**, about
    113 km of alignment in 60 leveed areas. Examples: Jones Island Road, Sayres Neck,
    Port Norris, Locust Island (Thorofare Meadow Bank Co.), Hancocks Bridge, PSEG
    Artificial Island, Gibbstown/Repauno. Most sponsors are private.
  - **Tide gates:** 13 NLD pipe gates, the only tide-gate-like records.
  - **Lakes:** 517 lakes/reservoirs ≥ 1 ha (NJDEP NHD 2015). Their `LEVELELEV` field is
    empty, so lake levels must come from the DEM or the dam heights.
  - **Head of tide:** 96 points (NJDEP).

## 5. Insurance data: RMA Cause of Loss (2026-10-02, `reports/rma_cause_of_loss.md`)

- **The collaborators' sample IS RMA's public Cause of Loss (COL) file:** commodity years
  2022–2025, aggregated to county × year of loss × month of loss. `indemnity_wet` = cause
  codes **31 (Excess Moisture/Precip/Rain) + 51 (Flood)**.
  - Checked independently for the 5 NJ counties: total 238/240 cells within $1; wet
    240/240. Both total misses are commodity-year edge cases at the end of 2025.
  - Negative values and wet > total cells are in COL itself (indemnity is signed).
  - Cape May has no COL rows after 2006, which is why it is all zeros.
- **We can build it ourselves for 1989–2026** (`scripts/fetch_rma_col.py`, `data/rma/`),
  with crop, cause, stage (prevented planting) and month detail. Year of loss is blank
  before 2003.
- **Study counties, all years:**
  - $52.0M all-cause; water losses $8.5M (broad definition) or $7.7M (31 + 51).
  - **Flood (51) is essentially zero ($1.9k).** Water losses are excess moisture: ponding
    and waterlogging, not overbank flooding. This supports making duration, depth on
    fields and infiltration the predictors that matter.
  - County × month × crop cells with water losses: 465 in all years, 428 since 2003,
    230 since 2015. Soybeans, corn and wheat hold ~72% of them; every other crop has
    ≤ 21. About 80% of cells involve only 1–2 paid policies, so the dollar values are noisy.
- **Normalizing:** RMA Summary of Business (`sobcov`, 1989 onward) gives liability, premium
  and acres by county × crop.
- **Unit- or field-level data:** confidential (7 U.S.C. 1502(c)); available only through a
  research agreement with RMA, which the ag-econ collaborators would request.

## 6. Forcing water levels (2026-10-02, `data/gauges/waterlevel_forcing_navd88.nc`)

- Five gauges, hourly 2002–2025, NAVD88, **no station-hour left missing**. Every filled hour
  is flagged in `source`.
- NAVD88 − MLLW offsets (m): Philadelphia 0.945, Marcus Hook 0.908 and Reedy Point 0.905
  (CO-OPS ties); Cape May 0.919 (tie); Ship John Shoal 0.995 (transfer from Lewes + Reedy
  Point, ±~0.1 m).
- Most-filled station-years:
  - Marcus Hook 2016 (100%), 2002 (55%) and 2015 (49%);
  - Ship John Shoal 2002 (62%) and 2009 (58%);
  - Cape May 2003 (25%).
- **Holdout test** (a whole year of observations hidden, then filled, compared to truth):

  | Station | Fill RMSE (m) | Bias (m) | Tide-only RMSE (m) |
  |---|---|---|---|
  | Ship John Shoal | 0.09–0.10 | −0.04 to −0.07 | 0.23–0.30 |
  | Marcus Hook | 0.09–0.10 | ≈ 0 | 0.23–0.30 |
  | Cape May | 0.03–0.04 | ≈ 0 | 0.23–0.30 |

  - At Ship John Shoal the filled values are **low by 0.07–0.13 m in the top 1% of hours**.
    Reedy Point's non-tidal residual is smaller than Ship John Shoal's.
  - A per-pair scale/offset on the donor residual would cut this if it ever matters. For
    a pluvial question it probably does not.

## 7. Model outline, bed and v0 build (2026-10-02)

- **Outline** (`data/region/model_outline.geojson`): the HUC12 ring minus PA and DE LAND
  (Census cartographic states), 3,461 km².
  - North of about Bridgeport the WBD "frontal Delaware River" HUC12s cross to the PA
    bank (81 km² of PA land at 25–120 m); DE adds 22 km².
  - Inside the twelve-mile circle the WBD edge runs mid-river (5–7 m deep), not along the
    NJ shore. WBD is hydrologic, not political.
- **Bed** (`scripts/build_bed.py`): one pre-merged raster, because CUDEM holds flat ~0 m
  "beds" in inland water. Samples: Union Lake −0.20 (lidar surface 7.56), Alloway Lake
  0.00 (3.96), Laurel Lake −0.02 (1.81), Salem River at Woodstown 0.53 (8.68).
  - The NJ 2021 lidar is hydro-flattened and has NO exact zeros here; open bay/river
    water is NoData.
  - Rules: lidar everywhere it has data. CUDEM replaces it only where the lidar is
    < 1 m and CUDEM is ≥ 0.5 m deeper: 82 km² of tidal channels, e.g. Bivalve −6.47
    under lidar −0.99. Otherwise CUDEM / 3DEP / GMRT fill NoData. It can never raise the
    bed (Cohansey at Greenwich keeps lidar −0.43, not CUDEM +0.17).
  - **River beds above head of tide are NOT burned yet**; v0 carries the lidar water
    surface there.
- **v0_100m** (`/scratch/tpj8/sfincs-nj-agri/models/v0_100m`): uniform 100 m quadtree,
  10 m subgrid, 346,156 active faces, 1,353 water-level boundary faces (bed −17.9 to
  −1.0 m), built in ~4 min.
  - **Water-level boundary** = edge faces with bed < −1 m inside OPEN WATER (bed_source
    3, + 300 m). One accepted oddity: a tidal-marsh creek face at (−74.907, 39.176) on the
    West Creek / Dennis Creek divide (lidar surface −1.07 m).
  - **hydromt_sfincs 2.0rc2 bug:** `create_cn_with_recovery` matches land-cover classes
    against `df_map.index`, but the CSV loads with a RangeIndex. Result: smax = 0
    (impervious) on 96% of faces. Fixed by `build.cn_table`, guarded in
    `patch_infiltration_keys`. Fixed result: smax p10/50/90 = 0 / 77 / 208 mm.
  - hydromt also points `infiltration_file` at a non-existent `infiltration.nc`; it is
    re-pointed at `sfincs.nc` (same trap bight found for `cna`).
  - **Cost:** 6 h simulated in 14 s on 32 threads (dt ≈ 3.6 s). The 47-day event windows
    take ~65 min on 16 threads.

## 8. Track A data (2026-10-02, agent; `reports/nwm_soil.md`, `reports/loss_panel.md`)

- **NWM v3.0 retrospective:** anonymous zarr on AWS, **1979-02 → 2023-01-31 only**, so it
  covers NEITHER flagged event (Sep 2023, May 2025).
  - Daily cropland-weighted county series for 2002–2023-01:
    `data/nwm/nwm_soil_daily_county.csv`. Variables: soil moisture by layer, ET, ponded
    head (`sfcheadsubrt`), saturated fractions.
  - No SOILSAT_TOP or SFCRNOFF in the retrospective.
  - First look (in-sample): 0–10 cm soil-moisture anomaly separates wet-loss months at
    AUC 0.72, against 0.67 for NWM rain.
- **Loss panel:** `data/rma/loss_panel_county_month.csv`, 4,140 rows = 3 counties ×
  2003–2025 × 12 months × 5 crop groups, zero-filled.
  - Liability from Summary of Business. Wheat/barley Sep–Dec losses go to the next
    commodity year.
  - "Other"/"all" liability drops ~70% in 2014 (All Other Crops); use corn + soybeans +
    wheat for row-crop loss ratios.

## 9. v0 event runs (2026-10-02; smoke test, NOT for collaborators)

Runs at `/scratch/tpj8/sfincs-nj-agri/models/v0_100m/runs/{sep2023,may2025}`; `summary/`
holds gauges.csv/.png, daily_county_crop.csv, focus_max_depth.tif, event.png.
- Both windows ran clean (rc 0) in 66–73 min on 16 threads; average dt 3.6 s.
- **Tide into the lower Maurice is right:** Bivalve r 0.99, RMSE 0.09–0.10 m, bias +0.02 m
  (USGS 72279 there behaves as NAVD88).
- **Side tidal creeks are wrong because no channel is burned:** Cohansey at Greenwich and
  Alloway Creek at Hancocks Bridge read +0.23 to +0.27 m high (low tide can't drain); r
  0.75 / 0.24.
- **Stream stage is mixed:** Mantua Creek matches (peak −1 to −3 h). Salem at Woodstown
  rises 1.5 m against an observed 0.18 m (Sep 2023). Several peaks land on the wrong
  storm. Stage on a 100 m channel-less cell is not a fair comparison; v1 needs
  cross-sections for discharge.
- **Cropland > 5 cm in the focus month (peak km² / km²·days):**

  | County | Sep 2023 | May 2025 |
  |---|---|---|
  | Salem | 7.6 / 152 | 6.2 / 113 |
  | Cumberland | 2.4 / 34 | 1.2 / 18 |
  | Gloucester | 1.2 / 19 | 0.9 / 16 |

  - Ponding jumps 0.3–1% of cropland after the big rain days, then recedes slowly (no
    ET, no channels).
  - **About half of Salem's figure is a persistent ~1% baseline** from deep cells in
    western Salem (Mannington Meadow / Salem River diked lowlands). Either CDL calls
    marsh cropland there, or diked fields have no drainage (no tide gates or pumps in
    the model). To be resolved before showing anyone.
