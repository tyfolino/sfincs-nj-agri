# FINDINGS — what is believed true

Durable facts, each with where it came from. STATUS holds what is in progress.

**Scripts deleted 2026-10-23** (closed lines; in git at `4c8dd95`): storm_ndvi, plot_sandy_panel,
storm_overlap, imagery_spotcheck, lulc_spotcheck, dike_freeboard, bayshore_exposure (its method is
`agri_sfincs/exposure.py`), field_history (superseded by field_classes), build_dike_outlets,
fetch_preserved_farms; build_bed_e9 (its NOS / stated depths are now sources in
build_riverbeds.py, the v2 beds). Their reports stay where sections below cite them.

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
  - **Tide gates:** 13 NLD pipe gates, the only tide-gate-like records. Only 6 are in NJ
    (Repaupo / Gibbstown); 7 are at Chester, PA (§36).
  - **Lakes:** 517 lakes/reservoirs ≥ 1 ha (NJDEP NHD 2015). Their `LEVELELEV` field is
    empty, so lake levels must come from the DEM or the dam heights.
  - **Head of tide:** 96 points (NJDEP).

## 5. Insurance data: RMA Cause of Loss (2026-10-02, `archive/reports/rma_cause_of_loss.md`)

- **The collaborators' sample IS RMA's public Cause of Loss (COL) file:** commodity years
  2022–2025, aggregated to county × year of loss × month of loss. `indemnity_wet` = cause
  codes **31 (Excess Moisture/Precip/Rain) + 51 (Flood)**.
  - Checked independently for the 5 NJ counties: total 238/240 cells within $1; wet
    240/240. Both total misses are commodity-year edge cases at the end of 2025.
  - Negative values and wet > total cells are in COL itself (indemnity is signed).
  - Cape May has no COL rows after 2006, which is why it is all zeros.
- **We can build it ourselves for 1989–2026** (`archive/scripts/fetch_rma_col.py`, `data/rma/`),
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
- **v0_100m** (`/scratch/tpj8/sfincs-nj-agri/models/v0_100m`; deleted 2026-10-15, rebuild with
  `build_model.py --name v0_100m`): uniform 100 m quadtree,
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

## 8. Track A data (2026-10-02, agent; `archive/reports/nwm_soil.md`, `archive/reports/loss_panel.md`)

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

Runs were at `/scratch/tpj8/sfincs-nj-agri/models/v0_100m/runs/{sep2023,may2025}` (deleted
2026-10-15 with the v0 model; the compare_{sep2023,may2025}.md reports keep their numbers); `summary/`
held gauges.csv/.png, daily_county_crop.csv, focus_max_depth.tif, event.png (from
plot_event.py, retired 2026-10-15).
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

## 10. Western-Salem persistent water is TIDE through leaky meadow banks (2026-10-03)

Diagnostic on the v0 event runs (`summary/focus_wet_days.tif` × hourly `zs` in
`sfincs_map.nc`; pixels wet > 5 cm on EVERY focus-month day):

| Event | County | Persistent (km²) | Tidal (hourly zs std > 5 cm, last week) | In an NLD leveed area |
|---|---|---|---|---|
| May 2025 | Salem | 2.22 | 2.21 | 2.15 |
| May 2025 | Cumberland | 0.21 | 0.21 | 0.19 |
| May 2025 | Gloucester | 0.22 | 0.21 | 0.19 |
| Sep 2023 | Salem | 3.01 | 2.99 | 2.89 |
| Sep 2023 | Cumberland | 0.44 | 0.41 | 0.37 |
| Sep 2023 | Gloucester | 0.32 | 0.32 | 0.27 |

- **It is real farmland, not marsh mislabelled by CDL.** Salem persistent pixels: CDL
  soybeans/corn/dbl-crop, NLCD 2021 class 82 on ~75%. The median pixel is cropland in
  15–17 of 16–18 CDL years. Only ~0.4–0.5 km² is NLCD 95 (emergent wetland) / CDL 37 (hay).
- **The ground is below high tide:** bed p50 ≈ 0.1 m NAVD88, 40–44% below 0 m. Model
  depth there p50 ≈ 1.1 m at daily high water. Hourly zs oscillates with the tide
  (std 0.17–0.44 m), so the `zsini = 0` initial level is NOT the cause (non-tidal
  persistent area ≤ 0.02 km²).
- **Mechanism:** the meadow banks are in the lidar (38 NLD alignments, 40 km in western
  Salem; crest p50 mostly 1.2–2.1 m NAVD88, above typical high water) but a 100 m
  subgrid face does not respect a 10–20 m-wide ridge, so tide flows through. Several
  alignments dip to 0.55–0.9 m (p5) in the lidar: gates, culverts, creek crossings or
  breaches.
- **Size of the error:** ~60% of Salem's cropland wet area-days in both focus months
  (May 2025 69 of 113 km²·days; Sep 2023 90 of 152).
- **Remedy (plan step 2, "dikes as weirs, tide gates as drainage structures"):** NLD
  alignments as a `weirfile` (bight FINDINGS §38: the quadtree engine honors it; the
  hydromt writer drops the inp key, bight `model._ensure_weirfile_key`), and one-way
  outlets. The native main build supports drainage type 3 = check valve (one-way
  culvert, 1 parameter) and 4/5 = controlled gates (`sfincs_discharges.f90`).

## 11. River beds, v1 (2026-10-03, revised 2026-10-05 per user decisions; `reports/riverbeds.md`)

`scripts/fetch_channels.py` → `scripts/build_riverbeds.py` → `data/elevation/riverbed_burn.tif`
(+ `riverbed_source.tif` codes 1–7, `river_table.csv`); checks `scripts/check_riverbeds.py`.
Lower-only; merged ONCE by `scripts/merge_bed_v1.py` = `fmin(bed_merged, burn)` → `bed_v1`.
- **Tidal beds, in order:** USACE eHydro where surveyed (Maurice MA_01_MRC_20230316_XC, 35 of
  37 km to Millville; Salem SA_01_SRC_20260813_XA, newest survey covering ≥ 90% of the best
  one's length; all 22 surveys ft below MLLW 1983–2001, checked per survey) → NOAA ENC
  soundings (running median ±500 m) → ENC "0–1.8 m" depth areas and uncharted reaches at
  **1.2 m below MLLW**.
- **ENC barely reaches into the creeks:** no soundings in the Cohansey, Stow or Oldmans; on the
  Maurice none within 13.6 km of Union Lake dam.
- **VDatum can't do MLLW here** (412 / −999999). MLLW in NAVD88 from CO-OPS sheets with a NAVD88
  tie (Bivalve −1.04, Fortescue −0.98, Reedy Pt −0.905, Marcus Hook −0.91, Philadelphia −0.945,
  Lewes −0.80) and subordinate stations with borrowed MTL (±~0.1 m): Millville −0.93,
  Greenwich Pier −0.90, Salem −0.70, Quinton −0.64, Auburn −0.47.
- **Non-tidal beds:** lidar surface (low decile, non-increasing downstream) minus USGS
  channel-measurement mean depth (area/width at each site's middle-half flows; regional
  depth = 0.091·DA^0.342, width = 1.18·DA^0.482, m, DA km²). Mean depth: Norma 0.42, Seeley
  0.66, Woodstown 0.19, Swedesboro 0.30, Pitman 0.20, Menantico 0.29, Manumuskin 1.06,
  Wrights Mill 0.30, Little Ease 0.25 m. **Pitman and Swedesboro anchored to measured stage**
  (NAVD88 datums; beds 16.97 and 2.02 m, tapering over ±1.5 km): the lidar surface there sits
  ~0.4 m above the median measured stage.
- **Not burned:** lakes ≥ 1 ha, marsh creeks, DA < 10 km², and **66 km of above-head-of-tide
  profile whose lidar surface is < 1 m NAVD88** (Salem River level path, Still Run;
  probably tide-gated). Width floor 10 m.
- **Burned 38.6 km²:** eHydro 9.9 (median lowering 3.4 m), ENC soundings 4.9 (1.6), ENC depth
  areas 12.7 (1.1), uncharted 7.8 (1.8), non-tidal 3.3 (0.4–0.6).
- **Checks:** bed below the lowest observed water at Greenwich (−2.10 vs −1.40), Hancocks
  Bridge (−2.51 vs −1.23), Bivalve (CUDEM −7.64 vs −1.42). Burn − eHydro where eHydro is the
  source: median +0.11 m Maurice, +0.01 m Salem. Stream gauges within 0.15 m of datum + stage
  − depth at Norma, Seeley, Menantico, Wrights Mill, Pitman, Swedesboro. **Unexplained:**
  Woodstown's published datum (+5.7 m vs the lidar surface; unusable) and Manumuskin (lidar
  1.0 m BELOW measured stage). 47 of 120 measurement sites publish NGVD29 datums.

## 12. Radar rainfall, Stage IV + MRMS (2026-10-03, agent; `archive/reports/rain_metrics.md`)

`scripts/fetch_precip_hourly.py` (grib env) → `archive/scripts/rain_metrics.py` → `archive/scripts/rain_compare.py`.
- **Sources:** Stage IV hourly + 6-h from IEM
  `mesonet.agron.iastate.edu/archive/data/YYYY/MM/DD/stage4/ST4.YYYYMMDDHH.{01h,06h}.grib`,
  complete 2002–2025 (mtarchive has NO stage4). GRIB1 to ~2019, GRIB2 after, same HRAP grid
  (4.76 km); file hour = END of accumulation. MRMS GaugeCorr (mtarchive) 2015-05-06T20 →
  2020-10-14T12; AWS Pass2 starts 2020-10-14T20; mtarchive's Pass2 copy bridges the gap.
- **Stage IV hourly has whole missing hours over NJ** although the file exists (2003-06/07
  ~160–170 h each; 2005-01..04 ~200 h/month). Filled from 6-h files (hourly sums = 6-h totals,
  ratio 1.000, where both exist); 0.9% of cropland cell-hours filled (`filled_frac`). Still
  > 5% missing: 2004-02, 2005-02 (12%), 2005-07, 2005-12, 2007-07.
- **MRMS vs Stage IV** (county-month cropland totals): MRMS 3.2% low under GaugeCorr (r 0.979,
  n 183), 2.7% low under Pass2 (r 0.966, n 186): **no step at the 2020-10 switch**; daily r
  0.977. MRMS peak-cell 1 h maxima run 15–20% higher (1 km vs 4.8 km), so peak-cell metrics
  are product-specific. Cropland-mean max-1 h r drops 0.89 → 0.69 under Pass2.
- **Two MRMS artifacts survive gauge correction** (absent from Stage IV; same in Pass1 and
  RadarOnly): 2020-12-25 01–03Z (Salem +83 mm/day) and 2024-08-30 04–05Z (+36–42 mm/day;
  also the record's top MRMS peak cell, 138.5 mm/h).
- **NWM `qrain` is liquid only:** Apr–Oct, Stage IV/NWM 1.004 (r 0.94), MRMS/NWM 0.94 (r 0.92).
- **Series:** `data/precip/rain_county_month.csv`, `rain_county_daily.csv`; local
  (America/New_York) days and months; whole-county CDL cropland weights as NWM. Cumberland
  Sep 2023: 182 mm, 24 h max 54 mm, 60% of cropland ≥ 50 mm in 24 h. Salem May 2025: 177 mm,
  24 h max 32 mm. Wettest county-month: Salem Aug 2011 (Irene) 522 mm.
- **Use Stage IV for 2003–2022** (one homogeneous product); MRMS as a check and for 1 km
  peak intensity.

## 13. A4 first test: cheap predictors vs season + monthly rain (2026-10-03, agent; `archive/reports/a4_first_test.md`)

`archive/scripts/a4_first_test.py` (helpers `agri_sfincs/skill.py`) → `data/analysis/a4_*.csv`.
- **Design:** 3 counties × 2003–2022 × 12 months; 690 county-months (30 dropped: Stage IV
  > 5% missing that month or the one before). Lead target: any wet loss (31+51) > $1k, all
  crops (162 positives). Ridge logistic, leave-one-year-out AUC; 95% CIs from a 2,000-draw
  year bootstrap of out-of-fold predictions (not refit, so somewhat narrow). 47 candidates:
  county × calendar-month normal-score anomalies, same and previous month.
- **Season carries most of the skill; rain adds a clear second step.** AUC 0.742 season only
  (month + county dummies); 0.799 + this month's log rain; **0.809 for B = season + log rain
  this and last month** (+0.067 [+0.022, +0.104]). A log-liability exposure term makes S and B
  WORSE out of sample.
- **Nothing beats B distinguishably from zero.** Selection-aware (chosen inside each fold):
  +0.014 [−0.005, +0.032] with one predictor, +0.002 with three. Pre-specified NWM 0–10 cm
  anomaly (§8): +0.006 [−0.003, +0.014].
- **NWM soil moisture is the only consistent extra signal (~+0.01–0.02 AUC):** previous-month
  0–10 cm mean +0.014 (picked in 20/20 folds); same-month 0–100 cm max +0.010 [+0.001, +0.017]
  (broad water definition +0.017 [+0.003, +0.031]). 1 of 47 additions with a CI above zero vs
  ~1.2 expected by chance: a lead, not a result. Used INSTEAD of rain it scores 0.820 vs 0.809.
- **Rain intensity adds nothing over the monthly total:** max 1/3/24/72 h, days ≥ 25 mm,
  cropland share ≥ 50 mm/24 h, 7/14/30-day antecedent: −0.003..+0.002 each, and each is worse
  than the total as a replacement.
- **By crop** (positives corn 71, soybeans 89, wheat 51): B AUC corn 0.832, soybeans 0.861,
  wheat 0.770 (rain helps wheat little, +0.026 CI spans 0). Selection-aware gains all span 0.
- **Loss SIZE is not predicted:** among loss months, out-of-sample Spearman ≤ ~0.15.
- **Flagged months:** both had 94th-percentile monthly rain after an ordinary previous month;
  B gives P(loss) 0.33 for Cumberland Sep 2023 (season alone 0.19), 0.72 for Salem May 2025 (0.44).
- **Bar for SFINCS features:** beat B (AUC ≈ 0.81) and B + NWM soil moisture with the same
  selection-aware leave-one-year-out test. With ~160 positives, gains below ~+0.03 are hard
  to resolve.

## 14. Dikes as weirs + farm-dike check valves (2026-10-05; `reports/dikes.md`)

`scripts/build_dikes.py` → `data/structures/dikes.weir`, `dike_gates_{lo,hi}.drn`,
`dikes_built.gpkg`; staged by `build.stage_structures` (user decision 2026-10-05, §10).
- **Weir:** 103 polylines, 20,466 vertices, 101.4 km of NLD alignment inside the outline,
  cd 0.6. Crest = lidar ridge (max of the pre-merged bed within ±20 m of the NLD line).
  Farm dikes (systems whose leveed area holds > 0.1 km² CDL 2023 cropland; 18 areas,
  15.1 km² cropland): 65.6 km, notches (> 0.3 m below the 200 m running median) filled,
  3.8 km filled, crest p5/p50 1.43/2.18 m. Other levees: raw ridge (real breaches stay
  open), 36.7 km, p5/p50 1.10/1.82 m.
- **Outlets:** 23 check valves (drainage type 3) for all 18 farm areas: the 6 NLD pipe gates
  at Gibbstown, otherwise the deepest notch; intake/outfall = lowest bed 120–400 m inside /
  outside (800 m once if none). C = 1.5 (lo, in the static model) or 6.0 m^2.5/s (hi, per
  run): ASSUMED sizes, no tide-gate inventory exists for these banks.
- **Plumbing traps:** (1) the engine (v2.4.2-alpha build) does NOT log reading the weir or
  drainage files; proof is behavioural (`structure_height` and `drainage_discharge` in
  `sfincs_his.nc`, and the tide below). (2) hydromt RE-WRITES `sfincs.weir` on read/write in
  `setup_event`, rounding crests to 0.1 m: `setup_event` now restores the static model's
  files. (3) inp keys re-added after every `sf.write()` (`stage_structures`).
- **6 h smoke (Sep 2023 start, v0 bed + dikes):** of the 2050 cells holding v0's persistent
  Sep 2023 cropland water, cells with a > 5 cm tidal swing fell from 84% to 16%; by pixel,
  96% stopped swinging. The rest is mostly outside any NLD leveed area (genuinely tidal);
  small leaks remain at Jones Island Road (11%) and Sayres Neck (19%).
- **`zsini` −1.0 m** (was 0) from v1: with 0 m every diked field below 0 m started full and
  could drain only through its valve.

## 15. v1 event runs: beds fix the creeks, dikes fix the cropland (2026-10-05; `reports/compare_{sep2023,may2025}.md`)

Four arms per event, all 100 m / 10 m subgrid, MRMS Pass2, 16 threads, 41–54 min each:
v0 (no burn, no dikes, zsini 0), dikes (v0 bed + §14), v1 lo (bed_v1 + dikes, valve C 1.5),
v1 hi (C 6.0). `scripts/compare_runs.py`.
- **Tidal creeks fixed by the river beds** (dikes alone barely move them):

  | Gauge (RMSE m / bias m / r) | v0 | v1 |
  |---|---|---|
  | Greenwich, Sep 2023 | 0.48 / +0.25 / 0.75 | 0.34 / +0.15 / 0.91 |
  | Hancocks Bridge, Sep 2023 | 0.58 / +0.23 / 0.23 | 0.36 / +0.10 / 0.79 |
  | Greenwich, May 2025 | 0.53 / +0.27 / 0.75 | 0.37 / +0.17 / 0.91 |
  | Hancocks Bridge, May 2025 | 0.62 / +0.25 / 0.24 | 0.38 / +0.10 / 0.80 |
  | Bivalve, Sep / May | 0.09 / 0.10 | 0.11 / 0.12 (bias +0.02–0.03) |

  Bivalve is slightly worse with the eHydro channel (r 0.99 either way). A +0.10–0.17 m low-
  tide bias remains at the side creeks.
- **The cropland artifact is gone, and the dikes did it** (beds add little on cropland):

  | Cropland > 5 cm, focus month | v0 | v1 lo |
  |---|---|---|
  | Salem Sep 2023 area-days / persistent | 152 / 3.01 km² | 44 / 0.25 km² |
  | Cumberland Sep 2023 | 34 / 0.44 | 18 / 0.14 |
  | Gloucester Sep 2023 | 19 / 0.32 | 6.5 / 0.03 |
  | Salem May 2025 | 113 / 2.22 | 17 / 0.11 |
  | Cumberland May 2025 | 18 / 0.21 | 4.8 / 0.05 |
  | Gloucester May 2025 | 16 / 0.22 | 4.3 / 0.01 |

  Peak area: Salem Sep 2023 7.6 → 4.1 km², May 2025 6.2 → 1.7 km². Salem still has the most
  wet cropland in BOTH months, including Sep 2023 when the losses were in Cumberland.
- **Valve size is second-order:** C 6.0 drains 26–34% more water than 1.5 (Sep 2023 10.1 vs
  7.5 hm³; May 2025 6.6 vs 5.3 hm³) but changes cropland area-days by < 1%. 13–19 of 23 valves
  pass > 1000 m³. (`drainage_discharge` in his is the intake's source term: negative = draining.)
- **Stream stage is still not a fair test.** Rise ratio improves where the obs cell is the
  channel (Seeley May 0.37 → 1.01; Manumuskin Sep 0.32 → 1.22; Wrights Mill 0.41 → 0.73) but
  **Maurice at Norma collapses (0.74 → 0.04 Sep; 1.92 → 0.06 May)**: its obs point sits in a
  bank cell (zmin 14.68 m) beside the burned channel (13.7 m); v0's shallow channel spilled
  onto it, v1's keeps the water. Obs points must snap to the channel cell; discharge through
  cross-sections is the real test (v1 to-do 2). Woodstown still rises 4–9× too much (dam /
  pond cell; its datum is unusable, §11).

## 16. v1 is NOT ready for multi-year runs: closed basins ratchet (2026-10-05, user asked)

Checked on the v1 lo runs before any multi-year test:
- **Wet cropland does not recede in dry spells.** Salem cropland > 5 cm (Sep 2023): 0.17 km²
  at the start → 4.1 after 32 mm on Sep 10–11 → then FLAT at 1.44–1.58 km² through the dry
  Sep 14–20 → 2.1 by month end. Same ratchet in May 2025 (0.14 → 1.0). Ponded water leaves
  only by flow or infiltration: SFINCS has no ET, so every closed depression only fills.
- **Diked interiors fill monotonically** (mean depth over farm-dike cells with bed < 1 m, 5-day
  means over the 47-day Sep 2023 window): Silver Lake 0.00 → 0.42 m, Gibbstown 0.10 → 0.44,
  Locust Island 0.11 → 0.42, Middle Neck 0.08 → 0.25.
- **Most synthetic valves cannot drain:** their outfall cells sit in creeks whose MODELLED low
  tide stays above the interior level (Silver Lake: inside p50 −0.33 m, outside p10 +0.10 m;
  inside > outside 0% of hours; Middle Neck 0%, Locust Island 1%). Only Gibbstown's real NLD
  gates drain (20–86 mm over the area). Cause: outfalls placed at the "lowest bed" in
  unburned marsh creeks / side creeks with the +0.1–0.17 m low-tide bias, and intakes in
  deep interior pockets rather than on the drainage path.
- **So `zsini = −1` HIDES the problem in short runs:** the diked areas start empty and 47 days
  is not long enough to fill them. In a year-long run they would fill toward the weir crest.
  The v0 → v1 cropland improvement (§15) is real for the tide leak but partly an artefact
  of start state and run length for the diked interiors.
- **Available remedy for ET:** SFINCS main accepts NEGATIVE precipitation and applies it only
  where a cell holds water (`sfincs_meteo.f90` ~l.1314: "hardfixing infiltration/evaporation
  ... when forcing effective rainfall"), so P − E(open water) could be forced. Its interplay
  with cnb's cumulative-rain bookkeeping is UNCHECKED.

## 17. Open-water evaporation as negative net rain (2026-10-05, agent; `reports/evaporation.md`)

Engine source = commit a9b7580 (BUILD_INFO); line numbers in SFINCS-src-main/source/src.
- **cnb ignores a negative rate:** its only rain branch is `prcp > 0` (sfincs_infiltration.f90:737);
  a negative hour is a dry hour (event closes, Se recovers, l.786-808). scs_P1 / scs_F1 change only
  in the rain branch (l.758-776), qinfmap >= 0 (l.780). Negative prcp is zeroed only where
  z_volume <= 0 (sfincs_meteo.f90:1316-1330). `cumprcp` accumulates it (l.1336): it becomes net
  rain and goes negative (to -114 mm in 48k permanently wet cells over 47 d).
- **cnb never infiltrates standing water** (l.737-822: no z_volume term): ponded water leaves
  only by flow, the other half of the §16 ratchet.
- **The engine blends -E into rain:** bilinear 1 km -> cells (sfincs_meteo.f90:1176-1236) and a
  linear ramp over each second half hour (dtwnd 1800 s; sfincs_lib.f90:495-501, sfincs_meteo.f90:1272).
  E applied only where P = 0 still removed 0.76% of Sep 2023 rain; cuminf -0.95 mm; Seff up to
  54 mm off. With no -E within 1 node / 1 h of rain (`evap.net_precip(buffer=1)`, default),
  cuminf / Seff match the no-E run to 0.008 / 0.018 mm; the buffer drops 7.5% of E.
- **The sink acts on the WHOLE cell** (sfincs_continuity.f90:469-495) once a cell holds any water.
  Without E, 89% of v1 cells hold water in the dry spell, half only in their lowest 10 m pixel
  (median wet fraction 0.01), so the sink is ~4x open-water E over all wet cells and 28-31x over
  land cells; once those puddles go, 1.4-1.7x / 4-7x. It is a bulk ponded loss, not open-water E.
- **Forcing:** gridMET ETo (THREDDS, `data/evap/gridmet_pet_2002_2025.nc`, ~1170 mm/yr, likely
  ~30% high) x Kc 1.05 (FAO-56), daylight-weighted, Sep 2023 mean 3.7 mm/d applied.
- **Sep 2023 v1 lo + E (`sep2023_evap2`):** cropland > 5 cm Sep 14 -> 21 Salem 1.04 -> 0.46 km² (base
  1.55 -> 1.44), Cumberland 0.43 -> 0.26 (0.58 -> 0.59), Gloucester 0.14 -> 0.07 (0.23 -> 0.23).
  Focus-month area-days 44.3 / 17.9 / 6.5 -> 26.3 / 11.5 / 3.4. Diked interiors Sep 14 -> 29: 9 of 18
  fall, 2 flat, 7 still rise on the Sep 22-29 rain (base: 16 of 18 rise or flat). Valves drain
  6.5 vs 7.5 hm³. Tidal gauges unchanged; stream stage -1 to -19 cm in dry spells, r down at all
  8 stream gauges (Wrights Mill 0.74 -> 0.58).
- **Not integrated into `setup_event`** (after the 2026-10-05 pivot SFINCS runs are event-scale
  only, where E matters little). Open if revived: bulk loss vs tuned Kc vs a cell-aligned
  100 m precip file.

## 18. Restart on preemption, and year-long runs (2026-10-05, agent; `agri_sfincs/restart.py`, `agri_sfincs/precip.py`)

(§17 is reserved for the evaporation agent's report.)
- **Runs write rsttype 4** (zs, q, uvmean, `scs_Se`; `sfincs_output.f90:657-700`), restored after the
  infiltration init (`sfincs_initial_conditions.F90:183-263`), so restart Se wins. No clock in the
  file: a resume rewrites `tstart`, sets `rstfile`, `tspinup = 0`.
- **NOT restored:** cnb's event/recovery state `scs_P1/F1/S1/scs_rain/rain_T1` (zeroed,
  `sfincs_infiltration.f90:382-391`), `cumprcp`/`cuminf` (the stitch offsets them), gate state for
  drainage types 4/5. So a resume ≈ a straight run, not identical:
  dry resume Seff −0.1 mm mean, zs p99 0.2 mm; mid-storm resume (Sep 11 00Z) Seff −1.24 mm on 72%
  of cells, zs p99 12 mm (max 0.9 m), cropland area-days +2–5%. `plan` therefore prefers a stamp
  with no rain in the preceding 3 h, up to 5 days back (70% of 2023's daily stamps qualify).
- **SFINCS syncs `sfincs_map.nc` after map records only** (`sfincs_ncoutput.F90:1272`): a killed
  run can lose its last zsmax block, so the resume falls back one extra day.
- **Year runs** `y2003`..`y2025` (spin-up from 1 Dec of the previous year; MRMS from 2016, Stage IV
  before; gaps filled MRMS ← Stage IV ← Stage IV 6-h): ~47 s per simulated day on 16 threads
  (~5 h/year); map ~1.5–2 GB/year, his ~40 MB. 2023 forcing 1146 mm, with dry May (35 mm) and
  October (24 mm).
- **`event_summary.py` focus mask was off by one day before 2026-10-05** (block END date): earlier
  `focus_*.tif` covered the last day of the previous month to the second-to-last day of the
  month. Fixed; CSV dates were already right. §15's persistent-area numbers shift slightly.

## 19. Sensitivities: drained soils and v2 dike outlets (Sep 2023; `reports/compare_sep2023_sens.md`)

- **Drained vs undrained dual soil groups (A/D, B/D, C/D as A/B/C):** smax p50 77 → 85 mm; wet
  cropland > 5 cm in Sep 2023 falls only 3–5% (Salem area-days 44.3 → 42.9, peak 4.14 → 3.93
  km²; Cumberland 17.9 → 17.4; Gloucester 6.5 → 6.3). Second-order for ponding on cropland.
- **v2 outlets (creek crossings, outfall chosen by modelled low tide;
  `scripts/build_dike_outlets.py`, `reports/dike_outlets.md`) do NOT fix the diked
  interiors.** 23 of 25 valves pass > 1000 m³ (v1: 19 of 23), but interior mean depth still
  climbs over the window in 7 of 9 large farm areas exactly as in v1 (Silver Lake 0 → 0.42 m,
  Locust Island 0.11 → 0.42, Gibbstown 0.11 → 0.47). Only Sunset Road (0.17 → 0.06) and
  Henby Creek (0.31 → 0.22) improve. Cropland area-days change < 5%.
- **Root cause is outside the dikes:** the modelled low tide in the creeks the valves discharge
  to is −0.46 to +0.11 m NAVD88 (Silver Lake's +0.10), against MLLW −0.7 to −0.9 m (§11):
  unburned marsh creeks on 100 m cells barely drain, so the valves rarely see a head. Against
  FIELD level (cropland p10 bed inside each area) every outfall is lower, so fields can drain
  in principle; the deep interior pockets cannot.
- Diked farm areas hold ~15 km² of cropland (~2% of the study cropland).

## 20. Wet-loss months are NOT river-flood months (2026-10-05; USGS daily discharge × loss panel)

County-month river peak (max daily Q in the month; Salem: Woodstown 01482500; Cumberland: Norma
01411500, Seeley 01412800; Gloucester: Swedesboro 01477120, Pitman 01475001) ranked against each
gauge's water-year annual maxima, WY2003–2025; wet loss = broad water indemnity > $1k, all crops.
- In loss months the median peak is beaten by the annual max of 96% of years (non-loss months:
  100%): ordinary flows. Only 11% of loss gauge-months reach a typical (median) annual peak and
  4% a top-20% annual peak (non-loss months: 5% / 2%).
- **Dollar-weighted, 14% of water indemnity fell in county-months whose most flood-like gauge
  reached a typical annual peak, 7% a top-20% annual peak.** These are UPPER bounds on river-
  flood-driven losses: a high river in the month does not mean the losses came from it.
- Of the 10 largest loss county-months only Salem Aug 2011 (Irene; the record peak) is a big
  river flood; Salem Jul 2013, Aug 2018, Jun 2018 and Cumberland Aug 2018 never beat a single
  year's annual maximum.
- Gauges see main-stem floods only: ponding in fields and small-creek overflow are invisible
  here. So the split is: river/coastal flooding ≲ 10–15% of water dollars; the rest is wetness
  (ponding + saturated soil + too wet to plant/harvest) in unknown proportions.

## 21. Bayshore cropland below the tide: a screening (2026-10-05; `reports/bayshore_exposure.md`)

First check for the saltwater-intrusion lead. Bathtub with DEM connectivity on the 30 m CDL
grid (`scripts/bayshore_exposure.py`); high water = MHHW of observed 2021-25 hourly levels
(1.02-1.27 m NAVD88; ~0.10-0.13 m above 2002-06), the median annual maximum ~0.65 m above that.
- **The exposed area is small but real.** CDL 2025 cropland in the domain is 564 km² (Salem 274,
  Cumberland 165, Gloucester 125). Below today's MHHW: 7.2 km² (1.3%, ~1,800 ac), 6.3 of it inside
  NLD leveed areas. Below MHHW + 0.3 / 0.6 / 1.0 / 1.5 m: 12 / 18 / 28 / 40 km². Below today's
  typical annual storm tide: 19 km²; + 1.0 m: 43 km². Salem holds ~2/3: between Salem City,
  Elsinboro and Hancocks Bridge (Salem River / Alloway Creek), led by the **Middle Neck** levee
  system (2.7 km² below MHHW now, 4.5 below MHHW + 1.5 m), then Locust Island, Silver Lake and
  Hancocks Bridge Poplar. Cumberland's is along the Cohansey and the necks east of it (Jones
  Island Road, Sayres Neck, Back Neck, Sheppard Davis). Gloucester's is the Gibbstown system.
- **Today it is dike-dependent; with rise it is not.** Leveed areas hold 88% of the cropland
  below MHHW but only 13 of the 40 km² below MHHW + 1.5 m: the land added by rise sits at the
  open marsh edge, not behind NLD dikes.
- **A change signal: about a third of it is real** (`reports/imagery_spotcheck.md`, NAIP 2010 vs 2023).
  Of cropland cropped in >= 3 of 2008-12, CDL 2023-25 calls 14% wetland below MHHW + 1 m vs 6% at
  1-3 m and 2% upland (> 3 m): 4.42 km². Of 36 random pixels, 12 are real conversions of
  cropped field to marsh / wet scrub (33%, CI 19-51%; ~1.5 km², ~370 ac). 13 are field-edge
  mixed pixels and 9 were not cropland in 2010 either. Low "stable cropland" controls: 12/12
  right. CDL switches cluster in 2019 and 2024 (product refreshes), so date changes from
  imagery. Clearest case: a diked field complex south of Greenwich, next to the NLD "Durham"
  levee. It was farmed in 2010-13, died back by 2017, was bare and channelled by 2019 and was
  marsh by 2023, which fits a bank breach / gate failure (cause and ownership unchecked). One
  Gloucester case (Logan Twp) is an excavated, engineered wetland, not intrusion.
- **Literature (`reports/literature_saltwater.md`, agent, ~50 refs checked against Crossref or the
  publisher):** Delmarva is well quantified (Mondal et al. 2023: 8,096 ha of farmland to marsh;
  salt patches 472 -> 905 ha), and so are the Chesapeake + Delaware Bay as a whole (Molino et al.
  2026: ~100 km² of farmland to marsh 1984-2022). NJ farmland has only historical and
  agency/NGO material: Greenwich bank failure 1989, Sandy within 1 inch of the Mill Creek dike
  crest, levee repairs $0.75-14 M (Cumberland Bayshore Recovery Plan 2013). Miller et al. 2025:
  soil salinity rises steeply below ~0.63 m above MHHW (cf. our MHHW + 0.6 m band, 18 km²). No
  study found uses SFINCS or any compound-flood model for farmland salt exposure, and no US
  hedonic study of SWI and farmland value. Middle Neck is undocumented.
- **Caveats:** surface inundation only (salt also arrives by groundwater and ditches without
  flooding); "connected" ignores gates/culverts the DEM cannot see and counts DEM notches as
  open; tide levels are IDW between bay gauges, so creek-head amplification/attenuation is
  missing (SFINCS can supply it); the DEM is one lidar epoch.

## 22. NRCS easements vs tidal exposure (2026-10-05; `reports/easement_exposure.md`)

Easements: NRCS Stewardship Lands Inventory map service (`scripts/fetch_easements.py`, 719
polygons around Delaware Bay). The service gives program, county and boundary, with **no
enrollment date and no agreement number**.
- **Study counties: 14 wetland-type easements, 6.6 km²** (WRP, ACEP-WRE, RCPP-WRE, and one
  EWPP-FPE floodplain easement, 2.5 km² in Cumberland), against **99 farmland easements, 28 km²**
  (FRPP, ACEP-ALE, RCPP-ALE). Delaware has 40 WRP + 7 ACEP-WRE + 1 RCPP-WRE (~12 km²).
- **Wetland easements sit at the tide line; farmland easements do not** (area-weighted):
  median ground −0.14 m vs +20.6 m relative to MHHW; 80% vs 8% of area below MHHW + 0.6 m.
  This is mostly by design (WRE eligibility = restorable wetland), so it is NOT evidence that
  flooding drives enrollment.
- **Most wetland-easement land was already wetland by 2008** (CDL cropland 7% in 2008-12). The
  two big Cumberland ones (WRP 2.7 km², EWPP-FPE 2.5 km², on the Downe Twp bayshore) are marsh.
- **A handful in Salem are conversions caught in the act:** CDL cropland 2008-12 → 2021-25:
  - WRP 297284: 98 → 40%;
  - RCPP-WRE 330636: 86 → 59%, all of it behind an NLD dike, at −1.7 m relative to MHHW;
  - ACEP-WRE 305704: 80 → 47%;
  - ACEP-WRE 330998: 24 → 9%.
  
  Imagery sample X04, a real conversion from §21, falls in WRP 297284. So one of the 12
  verified conversions is an easement.
- **For a participation model** (who enrolls, given exposure), NJ's handful is too few. Pool
  with Delaware and Maryland's bayshore, and compare exposed farmland that enrolled with exposed
  farmland that did not (not with upland farmland easements). Timing needs other sources
  (NCED / PAD-US dates, NRCS FOIA, or imagery).

## 23. Farm → wetland in NJDEP LU/LC 1995-2020, and its blind spot (2026-10-05; `reports/farm_wetland.md`, `reports/lulc_spotcheck.md`)

Source: NJDEP's photo-interpreted Land Use/Land Cover. Each edition layer carries the previous
code (`scripts/fetch_njlulc.py`, five periods). Farmed = 2100/2140/2200/2300/2400. Farm → wetland
= to 2150 / 6xxx / natural or tidal 5xxx (`agri_sfincs.landuse`; dug ponds, code 5300, are
excluded).
- **840 ha (8.4 km²) went from farm to wetland in the domain's three counties over 1995-2020.**
  Most of it is early: 419 / 225 / 115 / 7 / 74 ha per period. 77% is class 2150 ("former ag
  wetland, becoming shrubby"). Only 16 ha went to saline or coastal marsh. 42% lies below
  MHHW + 0.6 m and 35% more than 3 m above it. Only ~11% was behind an NLD levee.
- **NAIP check, commission:** of 24 conversions, 18 really left farming. Two were warehouse
  stormwater ponds, hence the 5300 exclusion. Most are wet marginal strips and fields going to
  old field, not tidal.
- **NAIP check, omission:** of 24 low-lying polygons (below MHHW + 1 m) that LU/LC still called
  farmed in both 2015 and 2020, **4 look marsh or abandoned by 2023**. Those are O29
  (Elsinboro), O38 and O46 (Greenwich-south / "Durham", the §21 site) and O45 (Salem, leveed).
  That is ~17% (CI 5-37%), or ~600 ha of the 3,646 ha. Class 2140 "agricultural wetlands
  (modified)" sticks after farming stops.
- **Three biased sources:** CDL over-counts (×~3, §21). LU/LC gets inland abandonment right but
  under-counts recent tidal conversion. NAIP is the arbiter. The outcome should be NAIP-dated
  field histories of the low-lying farmed / 2140 polygons (a few hundred), with LU/LC as the
  1995-2012 record.

## 24. Landsat field histories 1984-2025: low ground leaves farming several times faster (2026-10-05; `reports/field_history*.md`, `reports/exit_spotcheck.md`)

Pipeline:
- `scripts/build_field_units.py` and `build_field_cells.py` define the fields as LU/LC farm
  polygons: all farmed-in-2012 fields below MHHW + 3 m, 2,500 upland (weighted), the 1995-2012
  conversions and 200 marsh references. They are cut into 120 m cells (29,423 cells, 28,256 ha;
  interior pixels only).
- `scripts/landsat_field_stats.py` gives per-scene field means from Landsat C2 L2, 1984-2025
  (Planetary Computer; 2,522 scenes; 27 M rows).
- `scripts/field_history.py` is a ridge logistic classifier trained on interior CDL labels for
  2008-25 plus the marsh references. Out-of-fold AUC 0.91-0.95.
- An exit is "farmed in y, not farmed in any of the next 5 years" (`fieldhist.exit_events`), so
  every period is held to the same test.

Findings:
- **Spring bare-soil (BSI) does not separate farm from marsh here:** dormant marsh reads as
  bare. Summer MNDWI and peak NDVI do the work.
- **Exit rates to vegetation (cells, % of farmed area per year):**

  | Ground height above MHHW | 2006-15 | 2016-20 |
  |---|---|---|
  | Below 0 | 1.0 | 1.0 |
  | 0-0.6 m | 0.7 | 1.1 |
  | 0.6-1.5 m | 0.4 | 0.7 |
  | 1.5-3 m | 0.3 | 0.5 |
  | Above 3 m | 0.10 | 0.19 |

  That is a monotone gradient, 5-7× from lowest to upland, and it rises over time in every
  band. Unit-level runs give the same ordering.
- **Precision (NAIP, `reports/exit_spotcheck.md`):** 39-56% on low ground and ~12% on upland
  for exits to vegetation. Corrected, that is roughly 0.4 %/yr vs 0.02 %/yr, an order of
  magnitude, but the uncertainty is wide (18 samples per stratum).
- **The destinations differ:**
  - low fields → marsh and scrub;
  - upland → development (a hospital, housing, warehouses in Gloucester), and many upland
    "exits" are woods misread.
- **Not usable as is:**
  - pre-2012 rates in the cell run: survivorship, since cells were drawn from 2012 farmland
    and early small conversions are dropped;
  - CDL as a second opinion: it labels abandoned grassy fields "Other Hay";
  - summer MNDWI shows no clear wetting across exits (median +0.01; 25% of exits below MHHW
    are wetter, vs ~11% upland).
- **Next:**
  - a multi-class classifier (row crop / hay-grass / marsh / woods / developed) trained on
    NJDEP LU/LC's photo-interpreted classes (2012 / 2015 / 2020);
  - restrict the at-risk set to LU/LC-confirmed fields;
  - a larger NAIP validation (~50 per stratum).

## 25. Dike crests vs a Sandy-class storm tide (2026-10-05; `reports/dike_freeboard.md`)

- In the bay, **Sandy's peak (~1.9 m NAVD88 at Ship John Shoal) is typical of the largest storm
  tides of 2002-2025**: 2016-01-23 1.92 m, 2012-12-21 1.90 m, 2021-10-29 1.87 m. That is only
  ~0.15 m above a median annual maximum (1.75 m).
- Lidar ridge crests (`scripts/build_dikes.py`) against Sandy's peak (IDW between gauges)
  (`scripts/dike_freeboard.py`):

  | Bank length | Total | Below Sandy | Below Sandy +0.3 m | Below Sandy +0.6 m | Below Sandy +1.0 m |
  |---|---|---|---|---|---|
  | Farm levees | 65.6 km | 21.5 km (33%) | 36.4 km (56%) | 49.4 km (75%) | 57.6 km |
  | Other levees | 36.7 km | 22.8 km (62%) | | | |

  Worst farm systems at +0.3 m: Jones Island Road, Sayres Neck, Henby Creek, Hancocks Bridge
  Poplar, Durham, Locust Island.
- Lowest crest vertex per farm system (`scripts/make_dike_scenarios.py`): 0.89-0.94 m at Middle
  Neck, Lower Alloways Creek, Richard Wood and County Hwy 623, below recent MHHW. These are real
  low spots, or gate locations the notch-filling left. The intact runs will show whether they
  leak at spring tide.
- Caveats: the lidar may miss a narrow crest's top and predates post-Sandy raising (e.g.
  Sheppard Farms raised 2 ft, `reports/literature_saltwater.md`). An hourly peak overtopping
  briefly is not a breach; SFINCS gives the volumes.

## 26. Fork 1: cross-county flood × rain test is null (2026-10-05, agent; `archive/reports/fork1_flood_rain.md`)

- **Data:** NJ / DE / MD / VA / NC, 233 insured counties × 2003-2025 months. RMA water
  indemnity offset by liability; PRISM rain over cropland; FEMA NFHL 1% share of cropland (NFHL
  covers ≥ 90% of cropland in 280 of 281 counties).
- **Model:** PPML with county, month and year effects. b1 = +0.90 ± 0.25 per 100 mm;
  **b2 (rain × floodplain share) = +0.01 ± 0.35 (p = 0.97)**.
- **Variants all null:** two-part, 31+51 only, coastal plain, state × year, relief share,
  extremes. Row crops: +0.39 ± 0.35.
- **Inference:** sandwich SEs are too small (the top 1% of county-months hold 52% of dollars,
  mostly NC hurricanes), so SEs are year-jackknife. MDE80 b2 ≈ 1.0.
- **Reading:** not evidence against flood damage. A static FEMA share cannot see month-to-month
  ponding (§20). Code (archived 2026-10-15): `archive/scripts/{panel,fork1_*,fetch_prism_monthly,
  flood_prone_share}.py`; bulk data in /scratch data_bulk/{rma_states,prism,floodplain}.

## 27. Dike × sea-level-rise scenarios: today's dikes keep ordinary tides off the fields; by +0.6 m they mostly don't (2026-10-06; `reports/scenario_matrix.md`)

21 runs, v1_100m, tide only (rain zeroed): tide2024oct (an ordinary spring-neap month) ×
{intact, removed} × SLR {0, 0.3, 0.6, 1.0 m}, and sandy2012 × {intact, removed,
breach_all_farm} × SLR, plus Sandy with rain. All finished clean. The boundary offset is
exactly the SLR. "Removed" = every NLD crest dropped to ~marsh level (0.9 m); "breach_all_farm"
= one 100 m gap at each farm system's lowest crest vertex, gates kept. Flooded = > 5 cm on CDL
cropland of the event year (566 km² in 2024), the ponds CDL calls crops subtracted (0.4-0.6 km²).
Hourly animations (`scripts/animate_scenarios.py`): `reports/figs/anim_sandy2012_intact_slr000_vs_intact_slr100.gif`,
`reports/figs/anim_tide2024oct_intact_slr030_vs_removed_slr030.gif`.

- **Ordinary tide month, peak cropland flooded (km²):**

  | | today | +0.3 m | +0.6 m | +1.0 m |
  |---|---|---|---|---|
  | dikes as built | 0.03 | 2.1 | 10.4 | 22.0 |
  | dikes removed | 1.8 | 7.8 | 13.9 | 23.5 |

  With today's dikes, ordinary tides flood essentially no cropland (a good sanity check). The
  dikes matter most at +0.3 m (5.4 km² dike-dependent, per 10 m pixel). By +1.0 m they are
  overtopped and nearly irrelevant (1.6 km²). Most of the hit area is in Salem: the Salem River
  meadows SW of Salem (Elsinboro / Lower Alloways), and Hancocks Bridge. In Cumberland it is
  the Greenwich-south / Durham diked fields. Maps: `figs/scenario_first_flood_{map,zoom}.png`.
- **Sandy, peak (km²):** 7.3 as built → 43 at +1.0 m; 11.8 → 45 without dikes. **Sandy's rain
  more than doubles today's peak (18.3 vs 7.3)**, so storm-day flooding of fields is mostly
  rain-driven today.
- **breach_all_farm ≈ intact for Sandy (7.7 vs 7.3).** A 100 m gap does not fill a polder in one
  or two storm tides. Breaches matter over many tides, so the test is tide2024oct ×
  breach_all_farm (not run yet).
- Station peaks rise by up to 1.22-1.26 m for +1.0 m on the boundary. Where this happens is not
  yet checked.

## 28. Field classifier v2 fixed: OOF accuracy 83.6%; exits fall with height (2026-10-06; `reports/field_classes.md`)

- **The first run (2026-10-05) was broken:** every cell-year came out "wetwood".
  - `skill.fit_logistic` took undamped Newton steps, and the final wetwood fit diverged
    (|b| ~ 3e6). It now halves the step until the loss falls; there is a regression test.
  - ~0.2% of training scene rows had NDVI / BSI / MNDWI far outside [-1, 1] (negative
    reflectance over water; NDVI down to -107). These reached the min / max features.
    `fieldhist.yearly_features` now drops them. Both fixes raised the 5-fold OOF accuracy from
    58.5% to **83.6%**.
  - field_history.py (§24) used the same pieces, so its numbers may shift slightly if re-run.
- **Recall:** marsh 95%, water 98%, developed 89%, farm 83%, forest 76%, wetwood 75%, oldfield
  46%. Farm → "developed" is the main confusion (12% of farm square-years), so upland exits to
  development are inflated.
- **Raw exit rates to vegetation, cells farmed in 2012, %/yr:** below MHHW 2.1 (2012-16) / 0.6
  (2017-20); above 3 m 0.20 / 0.15. Tide-connected vs behind a bank or road (ground < MHHW + 1 m):
  0.96 vs 0.53. Low exits mostly go to old field, few to marsh (13 ha in 2012-20). NAIP
  precision is not yet checked for v2.

## 29. Per-field classes: 1,100 ha of farm fields are dike-dependent today, mostly in Salem (2026-10-06; `reports/field_flood_classes.md`)

`scripts/field_flood_classes.py` (rules: `agri_sfincs/fieldflood.py`, tested). Fields = 13,699
NJDEP LU/LC 2020 farm polygons (76,400 ha). Depth is computed on every 10 m pixel of each field
from the tide2024oct runs. A field "floods" when > 10% of it is > 5 cm at least once in the
month. Per-field table: `data/analysis/field_flood_classes.csv`. Maps:
`figs/field_flood_classes{,_zoom}.png`.

- **Today:**
  - 433 ha "flooded today", with 156 ha of it actually wet. 341 of the 433 ha is LU/LC 2140
    (agricultural wetland, modified), the wet farmland CDL mostly does not count as cropland.
    That is why the CDL pixel analysis (§27) finds ~0.
  - **1,117 ha dike-dependent today** (176 fields; 341 ha of it floods, median 13 wet days in
    the month, once the dikes are removed). 683 ha are in Salem, the Salem River meadows
    block SW of Salem and Hancocks Bridge.
- **With sea-level rise**, first threatened at (ha):
  - +0.3 m: 963 dike-dependent, 997 flood even with dikes;
  - +0.6 m: 378 / 1,204;
  - +1.0 m: 158 / 1,921.
  - Safe to +1.0 m: 69,200 ha (91%).
- **The banks protect more than NLD maps:** of the dike-dependent fields, 209 of 1,117 ha
  (today) and 584 of 963 ha (+0.3 m) lie OUTSIDE NLD leveed-area polygons. Their bank closes
  off a larger low area than the polygon drawn behind it.
- Caveats: one ordinary month. The 10% / 5 cm rule is a choice (the shares are in the CSV).
  Fields first farmed after 2015 are missing (the layer keeps 2015-farmed polygons).

## 30. Farm → wetland phase 1: re-opening a dike system floods its own farms; outside the bank nothing measurable changes (2026-10-06; `reports/restore_phase1.md`)

Runs: `setup_scenarios.py --restore`; structures: `make_restore_scenarios.py`; analysis:
`compare_restore.py`. Each site's outlet (its gate / old creek crossing) re-opened to local
MLLW (-0.75 m) over 100 or 300 m, with its gate removed. Compared with the as-built twin on
the tide month (today, +0.6 m) and Sandy. Sites: **Middle Neck** (Salem; 1,135 ha leveed
area; holds NRCS RCPP-WRE 330636, 7.5 ha; the most dike-dependent farmland, §29) and
**Durham** (Cumberland; §21's 2013-19 conversion).

- **SFINCS is bit-reproducible:** an identical repeat run differs by exactly 0. Every
  difference below is the scenario's.
- **Sill depth decides; width does not.**
  - Middle Neck, tide month: a marsh-level breach (the §27 kind) floods 82 → 112 ha of the
    leveed area. Re-opened to MLLW it floods 82 → 452 ha, 72 → 295 ha of it wet every day
    (ground p10 -0.77 m: subsided land becomes open water, not marsh).
  - 100 m and 300 m give the same answer: the interior creeks, not the gap, limit the flow.
- **The cost lands inside the polder:**
  - Middle Neck's 98 farm fields (701 ha): flooded fields 6 → 47 (28 → 474 ha); flooded area
    in them 8 → 137 ha; wet field-days ×16 (231 → 3,655 ha-days).
  - So re-opening the system's outlet to the tide floods ~470 ha of farm fields behind the
    same bank. The claim is the narrow one: opening a SHARED bank exposes everything behind
    it. It is not "restored marsh floods farms next door": outside the bank nothing
    measurable changes (below).
  - **Correction (same day): this is NOT how the WRE 330636 easement would be restored.** The
    parcel sits at the polder's landward edge in a low spot (ground ≈ -0.7 m), ~2.8 km from
    any bank, with upland just beyond it. As built, its water stays near -0.8 m. That is
    mostly the `zsini = -1` start held over a rain-free 38-day run, NOT gate drainage: the
    synthetic Middle Neck valve drains ~0% of hours (§16). A wetland easement there is almost
    certainly NON-tidal (stop draining a
    low spot). Re-opening the outlet is a hypothetical system-scale restoration, not the
    easement's.
  - The realistic system-scale version is a set-back (managed realignment): restore the
    non-farmed seaward 273 ha and protect the 98 fields behind a 13.6 km inner dike with its
    own gate (`make_restore_scenarios.py` setback; runs `*_restore_middle_neck_setback_*`).
  - 470 ha is close to an upper bound. Internal roads, berms and culverts that split the
    polder are only partly in the 10 m subgrid, so real compartments would flood less.
    Seepage under the banks, which SFINCS lacks, would push the other way (salt especially).
  - Literature (verified 2026-10-06, `reports/literature_restoration_neighbours.md`): every one
    of 90 European realignments has a landward dike (van den Hoven et al. 2022). Tollesbury
    built a secondary bank "to prevent any inundation of adjacent agricultural land". Long-
    diked land sits 0.3-1 m low; ~22% of breached Delaware Bay salt-hay impoundments are still
    open water / mudflat vs 0.5% of never-diked marsh. Downe Twp's claim that the PSEG / NJDEP
    dike removal caused its flooding is one unsupported sentence (2025), and PSEG's sites are
    in other townships. The "< 1 mm outside" result is for daily tides: Alkborough (440 ha)
    cut extreme levels > 15 cm, and small sites can raise surges locally (Kiesel 2021).
    Groundwater salt on adjacent farms (Kentuck Slough, OR) is outside SFINCS.
  - Sandy: 45 → 69 fields.
  - At +0.6 m it is moot: all 96 fields flood with the dikes as built. There re-opening
    LOWERS the wet field-days (11,889 → 10,927) because the water drains out at low tide
    instead of being trapped behind the bank.
- **Set-back (managed realignment) protects the farms** (2026-10-06): the non-farmed seaward
  273 ha re-opened, the 98 fields behind a 13.6 km inner dike (crest 2.0 m) with a new gate.
  - Tide month today: the restored side floods 82 → 153 ha, 72 → 129 ha of it wet daily. The
    farms behind the dike do NOT flood more: flooded fields 6 → 2, wet field-days 231 → 117.
  - That improvement comes from where I put the new gate (the lowest farm-side ground, which
    drains better than the old gate's position). It is an artifact of the design assumption,
    not a benefit of restoration. The robust result is "no worse".
  - The western strip of the restored area never gets the tide: at 100 m it is not connected
    to the outlet, so a real design would need a channel. Only ~half of the 273 ha becomes
    tidal.
  - Sandy: 45 → 38 farm fields flooded, but flooded ha 78 → 87 (mixed, small). +0.6 m: the
    farms flood anyway (96 → 92 fields) because the outer banks overtop.
  - The literature agrees this is how it is done: all 90 European realignments in van den
    Hoven et al. (2022) have a landward dike (`reports/literature_restoration_neighbours.md`).
    The inner dike here is ~2× Medmerry's 7 km new bank, so its cost matters for the econ
    comparison.
- **PSEG precedent (Ecol. Eng. 25, 2005, read in full; `reports/literature_restoration_neighbours.md`
  addendum):** the 1,780 ha of diked salt-hay farms restored on this shore in 1996-98 needed
  "upland dikes … constructed to protect adjacent properties from flooding". Those dikes are
  where the adaptive-management triggers were hit. The program also monitored local wells
  and septic systems for groundwater / salt effects.
  - Restored plains went ponded water → mudflat → low marsh. At Commercial Twp, 47-50% was
    still unvegetated in 2003. Diked plains had lost up to 1 m of elevation.
  - So the set-back design and the "open water first" result both match the local record.
- **Outside the bank, nothing measurable:**
  - Change in mean daily high water within 3 km: ≤ 0.1 cm today, ≤ 0.2 cm at +0.6 m.
  - Sandy max: a handful of cells change by up to 5 cm.
  - Farm fields in the 3 km ring: +2.3 ha flooded (393 fields).
  - Reason: the polder's tidal prism is tiny next to the Salem River / Delaware Bay.
- **Durham barely responds** (2 → 7 ha flooded, tide month). Its ground is high: median
  1.58 m NAVD88, 17% below MHHW. Caveat: lidar over dense marsh (Phragmites / Spartina) reads
  the ground 0.2-0.5 m high, and Durham went to marsh in 2013-19.
- **What SFINCS can't say here:**
  - roughness (NLCD cropland n = 0.040 vs emergent marsh 0.045: no signal);
  - marsh growth (accretion) or subsidence (ground must be imposed);
  - salinity.
  The water-side result is robust because it is driven by connection and storage, which
  SFINCS does resolve.

## 31. How farmland becomes wetland here: dikes are one route, not the main recent one (2026-10-06; synthesis of §21-§24, §30, `reports/literature_*.md`)

- **Wet-field abandonment (largest by area since 1995, no dike involved).**
  - NJDEP LU/LC: 840 ha farm → wetland 1995-2020. 77% is 2150 "former ag wetland, becoming
    shrubby"; only 16 ha went to saline / coastal marsh; ~11% was behind an NLD levee; a third
    lies > 3 m above MHHW.
  - Landsat exits from low ground go mostly to old field / scrub (§24, §28).
- **Passive bank or gate failure (the historic tidal route; now a few sites).** 71 meadow-bank
  companies by 1883, few left. Supawna, Mannington Meadows and Fortescue (1972) went back to
  the tide when banks failed. Since 2010 about 1.5 km² of cropland → marsh has been verified,
  led by Greenwich-south / Durham 2013-19 (cause unchecked).
- **Deliberate breaching:** PSEG EEP, 1990s, ~1,800 ha of diked SALT-HAY farms (not cropland).
- **Wetland easements:** mostly land already wetland by 2008. The few conversions (e.g. WRE
  330636) look non-tidal: stop farming / draining a low spot (§22, §30 correction).
- **Marsh migration onto unprotected fields with SLR (mostly future).** Of 40 km² of cropland
  below MHHW + 1.5 m, only 13 km² is behind NLD levees (§21). This is the "floods even with
  dikes" class of §29.
- **For the conversion model:** the dike × SLR runs cover the tidal routes. The largest recent
  route needs WETNESS exposure (ponding under rain, drainage class), not tides.

## 32. Per-field sample for the ag-econ colleague, and their questions (2026-10-08 to 10-12; `scripts/field_flood_sample.py`, `field_flood_classes.py --event sandy2012`)

- **Sample** (one scenario: tide2024oct, dikes intact, +0.6 m):
  `data/analysis/sample_tide2024oct_intact_slr060/` (fields.gpkg/csv, daily.csv, README.md).
  Per field: CDL 2024 crop mix + flooded %, first/last flood date, flood days, longest run,
  depth. The longest run is there because Hazus crop tables key on start day + duration, not
  depth.
- **1,273 fields flood (= §29), 2,036 ha under water (~2.7% of farm-polygon area).** Of the
  1,273:
  - 761 are LU/LC 2140;
  - 435 are ≥ 50% CDL cropland (1,159 ha flooded);
  - 236 already flood today;
  - 684 are wet on all 31 days.
- **CDL pasture (176)** is its own column, `cdl2024_pasture_pct` (2026-10-17; the colleague wants
  pasture counted). Cropland + pasture ≥ 50%: 558 fields (1,377 ha flooded); 555 / 1,369 before
  the per-class rounding. Hay (36/37) already counts as cropland.
- **Days per month** exist for October 2024 only. Other months need new runs.
- **LU/LC 2140** is farmland on mapped wetland: ~54% CDL cropland, and the class is sticky after
  abandonment (§23).
- **Salt flood, agronomy (answered in chat, not literature-checked):**
  - a spring salt flood loses or replants that season;
  - the damage lasts years only on heavy or poorly drained soil, or where water is trapped
    behind dikes;
  - RMA treated Hurricane Rita's salt as prevented planting (2006 memo).
- **Sandy, per field** (`data/analysis/field_flood_sandy2012.csv`; dikes as built, tide only):
  fields flooding today / +0.3 / +0.6 / +1.0 m = 860 / 1,317 / 1,776 / 2,255 (896 / 2,038 /
  3,603 / 5,376 ha under water). With Sandy's rain, today: 2,448 fields but only 1,915 ha.

## 33. The Sandy run passes the gauge check; FEMA's MOTF footprint floods ~4× more farm field area (2026-10-15; `reports/sandy_validation.md`, `scripts/validate_sandy.py`)

For the Sandy land-use test (does modeled flooding explain crop change beyond elevation?).
Run: `sandy2012_intact_slr000` (dikes as built, tide only).
- **No Sandy high-water marks on the NJ bayshore.** USGS STN event 24 has 4 marks inside the
  ring, all on the Delaware at Chester, PA. The STN API moved: the old
  `stn.wim.usgs.gov/STNServices` routes 301 to the web app; the new root is
  `api.waterdata.usgs.gov/stnservices/` (`events/24/sites/`, `hwms/?site=<id>`; the
  `hwms/filteredhwms/` query 502s).
- **Interior gauges, Bivalve (Maurice) and Greenwich (Cohansey):**
  - both are out Oct 29 04:00 to Oct 31 04:00 UTC, the two peak tides;
  - model high tides, Oct 20 - Nov 4: Bivalve −0.04 m mean (−0.02 on the five highest),
    Greenwich −0.11 m. Greenwich's larger hourly RMSE (0.30 m) is low tides staying too high,
    the §16 marsh-creek bias;
  - peak, estimated as Ship John's observed 1.90 m plus each gauge's offset from Ship John on
    the two highest tides before the gap: Bivalve 1.79 m (model 1.73), Greenwich 1.68 m
    (model 1.68).
- **FEMA MOTF surge extent** (read from nj_bight_sfincs `validation_v4`) is HWM-interpolated
  over lidar, with no dikes. Its flood edge sits on ground of 1.85-2.0 m almost everywhere,
  which is the bay peak carried up the creeks flat, ~0.2 m above the gauge-based peaks there.
  - Off-field ground at 0-3 m NAVD88: 83% agreement. The model is almost never wet where MOTF
    is dry (1 km²).
  - Farm fields: MOTF 23.9 km² wet against the model's 4.9.
    - Dikes removed (Sandy, today): 34% of MOTF's field area is covered.
    - Today's dikes at +0.3 m: 41%. At +0.6 m: 65%.
  - Per field (≥ 10% wet): MOTF floods 994 fields; the model floods 383, every one also wet in
    MOTF.
  - So on flat bayshore fields, ~0.2 m of peak plus overland routing over a short peak
    decides most of the difference. A bathtub at the bay peak overstates the field footprint;
    without an interior peak observation the exact split can't be settled.
- **For the land-use test:** treat the two footprints as rival exposure measures (physics vs
  bathtub vs elevation) rather than one as truth. Model extent and depth are usable. Duration
  is not (§16).

## 34. Sandy land-use first look: a hint of corn → soybeans, nothing on leaving farming (2026-10-15; `reports/sandy_panel.md`, `scripts/build_sandy_panel.py`, `scripts/plot_sandy_panel.py`)

Descriptive only (no model fits). Panel: `data/analysis/sandy_panel/`.
- **Fields:** the 12,726 LU/LC polygons farmed in 2012, before Sandy (`njlulc_2012_2015.gpkg`
  prev code). The 2015+2020 survivor set of §29 would hide 2013-19 exits.
- **Comparison groups:** fields < 1.5 m above MHHW and ≥ 50% cropland in 2008-12.
  - 428 are flooded by the model (≥ 10% of the field);
  - 169 are wet only in MOTF;
  - 324 are dry, reweighted to the flooded fields' height mix (effective n ≈ 75).
- **Leaving farming is too rare to test here:** only 27 of 839 low crop fields left farming in
  LU/LC by 2020 (13 flooded, 14 dry).
- **Change from each group's own 2008-12 mean, flooded − dry (pp of area):**
  - **Cropland:** −2.1 in 2013-16. The gap was already open in 2012 (−4.8), and CDL 2012 is the
    summer before Sandy, so it is not Sandy. Gone from 2015.
  - **Corn:** −3.1 in 2013-16 [−7.3, +1.3] and −3.0 in 2017-25 [−8.3, +1.7]. Near zero before
    (except 2011), negative in most years after.
  - **Soybeans:** +5.5 in 2013-16 [+1.0, +10.5]. This is the corn → soy direction that
    Epanchin-Niell et al. report on low Delmarva fields.
  - **Grass and vegetation:** small and inside the noise.
- **Reading:** "something in between". The direction fits salt-sensitive corn being avoided,
  but it is one storm with about 75 effective dry fields, and CDL's product jumps (pasture
  2012 → 2013, 2024) move every group.
- **Soil drainage class** is in the panel (2026-10-17, `scripts/fetch_ssurgo_drainage.py`):
  drain_dominant, drain_poor_share (poorly + very poorly), drain_spoor_share. It tracks the HSG
  stand-in (r = 0.89) but is narrower: 403 fields are ≥ 50% D / dual group yet < 50% poorly
  drained. It is NATURAL drainage; ditching and tile are not in it.
- **Cheapest power gain:** more storms rather than more area. The 2016-01-23 (1.92 m at Ship
  John) and 2021-10-29 (1.87 m) storm tides are Sandy-class (§25). Event runs of those would
  give repeated exposure per field.

## 35. The 12 storm tides flood the SAME fields again; Sandy was not a first flood (2026-10-17; `reports/storm_overlap.md`, `scripts/storm_overlap.py`)

All 22 storm runs are in (§34's "more storms"). Fields: the 1,043 low crop fields of §34 (before
its grouping); flooded = ≥ 10% of the field > 5 cm; dikes as built today.
- **One footprint, repeated.** Tide only:
  - 526 fields never flood; 114 flood in all 12 storms;
  - Sandy floods 95-100% of every other storm's fields (2021-10: 84%);
  - 79% of flooded fields are nested: a field flooded by k storms is flooded by the k biggest.
    Only 44 distinct histories.
  - With rain: 71 histories, 61% nested. Rain adds variety, but rain ponding is not salt.
- **So the storms give one exposure number per field (how big a storm floods it) plus WHEN
  storms came**, not 12 independent experiments. Height explains little of that number among
  flooded fields (r = −0.13): banks and connection do.
- **Peak height at Ship John does not order the footprints.** 2016-01 (1.92 m) floods 287
  fields; 2021-10 (1.87 m) floods 509. Duration and timing of the high water matter.
- **Sandy was not a first flood.** 393 of the 428 Sandy-flooded fields (92%) also flood in the
  April 2011 storm (1.85 m), at planting; 396 (93%) in some 2010-12 storm. §34's 2008-12
  "before" period is therefore not clean.
- **The 2011 corn dip lines up with April 2011.** Corn, flooded − dry (height-reweighted, pp):
  2008-10 +3.1 / +4.2 / +4.6, **2011 −1.6**, 2012 +4.8, 2013-15 about 0. One CDL year, so
  "consistent with" a one-season planting loss, not shown.

## 36. Public sources on the farm-dike tide gates: confirmations, no inventory (2026-10-17; `reports/tide_gates_public.md`, `data/structures/tide_gates_public.csv`)

Web search (background agent). The user has no local gate knowledge, so this is the gate record.
- **No public inventory** of meadow-bank gates in the three counties: not from NJDEP, NRCS,
  USACE or NAACC. Only Gibbstown has located gates (NLD: 3 sluices at the Repaupo mouth, 3 flap
  gates on 48 in pipes). A pump station there is named but not located; the model has no pump.
- **Confirmed but not located:**
  - Silver Lake and Locust Island: the USDA project of 1957-62 gave them "pipe sluiceways with
    tide gates"; the dike crest is "elevation 10 ft", datum not stated.
  - Middle Neck (new gates 2018, Sinnickson Landing Rd); Mill Creek / Union Bank (repaired 2014).
- **Nothing gate-specific for 11 systems**, mostly the private Lawrence / Fairfield banks.
- **Gates are failing now.** Salem County calls four of its sluice structures "critically
  failing" (Lower Alloways Creek, Pennsville). It asked for $2.7 M; $1.0 M is in the House FY27
  bill. This supports a gate-failure scenario on its own terms.
- **Unchecked lead for the crests:** if "10 ft" is NGVD29, it is ≈ 2.7 m NAVD88 (conversion not
  verified). The lidar crest medians are 2.48 m (Silver Lake) and 1.83 m (Locust Island): settled,
  eroded, or a different datum.
- **Follow-ups that need a person:**
  - the Salem County Engineer (the FY27 application should list the four sites);
  - NRCS NJ (Silver Lake–Locust Island as-builts);
  - a free NAACC login (two crossings sit on the Middle Neck and Sunset Road model sites).

## 37. All 7 spring storm tides: no consistent crop response in the flooded season (2026-10-17; `reports/storm_panel.md`, `scripts/build_storm_panel.py`, `scripts/plot_storm_panel.py`)

Descriptive. Panel: `data/analysis/storm_panel/` (field × CDL year exposure, 2008-25).
- **Design:**
  - Fields: §34's 1,043 low crop fields minus the 100 wet on ordinary spring tides = 943; 417
    are flood-prone (≥ 1 storm), 526 never flood.
  - Per spring storm: the fields it floods vs flood-prone fields it missed, height-reweighted.
  - Each field is measured against its own nearby QUIET years (no modelled storm: 2008, 2009,
    2015, 2017, 2018, 2020, 2021, 2025), not 2008-12.
- **Same season, all 7 storms (flooded − prone-dry, pp):** corn +1.2 [−2.0, +4.8], soybeans
  +1.2 [−2.0, +4.9], cropland +1.1 [−0.6, +2.7], grass 0.0 [−2.4, +2.0]. Next season also
  nothing. With rain, or against never-flooded fields: nothing in the flooded season.
- **Per storm, signs flip** (corn +10 in 2010, −7 in 2022). One of 28 storm × outcome cells
  stands out (2022 soybeans +17 [+5, +29], 38 fields), about what chance gives.
- **The 2011 corn dip (§34) is not confirmed.** Corn, April-2011-flooded − never-flooded: 2010
  +7.5, 2011 +2.6, 2012 +8.4, but the quiet years 2008 / 2009 / 2015 are +1.8 / +5.3 / +0.6.
  2011 is low only next to two FLOOD years, so a 2011 dip and corn bumps in 2010 and 2012 can't
  be told apart.
- **CDL 2024 hits flood-prone fields hardest:** cropland −22 pp for flooded and prone-dry fields
  alike, −10 for never-flooded ones. The product change, not a storm; comparisons against
  never-flooded fields carry it (their next-season cropland −4 pp is this).
- **Reading:** with these storms and CDL, a planting-season storm tide leaves no crop-mix
  signal larger than ~±4 pp pooled. §34's corn → soy hint does not recur storm by storm. The
  storms share most of their fields (§35), so the pooled interval is too narrow if anything.
- **Not modelled:** Irene (Aug 2011, 1.85 m), Oct 2018 (1.73), Isaias (Aug 2020, 1.75), Jan 2024
  (1.77), Aug 2025 (1.75); springs of 1.60-1.67 m (2016, 2017, 2019, 2025).
- **The 100 chronic fields (wet on ordinary tides TODAY) matter** (checked after a side note;
  some may be chronic because earlier storms wore their banks down):
  - 83 of them flood in all 12 storms; they sit at −0.2 to +0.3 m above MHHW (middle half),
    lower than the other flood-prone fields (+0.2 to +0.8 m). LU/LC still calls 95% of them farm in 2020.
  - Cropland vs flood-prone fields at the same height: −5 pp (2008-10) → −9 by 2015, then flat to
    2025; much of the step shows in 2012 and 2014 (spring-storm years). Against never-flooded
    fields the gap reaches −30 by 2024, with steps at the CDL 2019 / 2024 product changes.
  - Put back into the storm comparison, the pooled same-season result tilts corn → soy: corn
    −2.2 [−5.2, +0.8], soybeans +3.1 [+0.5, +5.9]. It is the same ~83 fields in every storm:
    one group's storm years vs its quiet years, not seven tests.
  - Revised reading: no signal in fields that storms flood only sometimes; a weak corn → soy tilt
    and a slow cropland decline in the fields that flood in every storm. Cause unknown (today's
    banks in every year).
  - Later the same day: they are mostly ~2 wet days in the month on the low quarter of a 0.6 ha
    marsh-edge field (median), where the 100 m model cannot see berms or ditches. Left out of the
    talk figure.
- **Yes/no per field (added 2026-10-17; outcome years ≥ 2024 left out for the CDL change):**
  - **Left cropland** (≥ half cropland the year before, < half that year and the next; usual rate
    1%/yr): flooded − prone-dry −0.6 [−1.8, +0.6] the storm season, +0.6 [−4.2, +5.8] the next.
    No exits; a few-point rise the next year can't be ruled out.
  - **Main crop changed** (usual rate 51%/yr, mostly corn / soy / small-grain rotation): +4.7
    [−5.9, +14.4] same season, +2.5 [−7.9, +13.9] next; per storm −21 to +40. Raw, flooded fields
    switch 66% in storm years vs 59% for the others (53% for both in quiet years); a few points of
    it is to CDL "wetland", likely standing water in that summer's image.
  - Against never-flooded fields "main crop changed" is +21 [+5, +35]: the few never-flooded
    fields as low as the flooded ones carry large height weights. Not trusted.

## 38. Greenness after a spring storm tide: flooded fields are not less green (2026-10-19; `reports/storm_ndvi.md`, `scripts/storm_ndvi.py`)

Preliminary, descriptive. §37's design with Landsat NDVI (`data/landsat/field_scene_stats.parquet`,
§24) as the outcome instead of CDL crop shares.
- **Fields:** 631 of §37's 943 match a Landsat field unit (98% of the area; 287 flood-prone). The
  rest are too small for a clean 30 m pixel (median 0.3 ha).
- **Outcomes:** summer peak NDVI (90th percentile of clear June-September scenes; ~0.80 on a
  flood-prone field in a quiet year, the field's own year-to-year SD ~0.05) and the July-August mean.
- **Main result: nothing.** Pooled over the 7 storms, flooded − prone-dry, peak NDVI:
  - storm season −0.005 [−0.020, +0.007];
  - next season +0.002 [−0.015, +0.017].
  - Placebo (each storm's two groups measured in nearby quiet years instead): ±0.016. Same for
    July-August, tide plus rain, and the deepest quarter (≥ 0.25 m: −0.004 [−0.046, +0.035]).
    No sign of a dose response.
- **Per storm, signs flip** (peak +0.032 in 2014, −0.037 in 2022, 25 fields), inside or at the
  edge of each storm's placebo range.
- **Month by month:** April −0.019 [−0.041, 0.000], at the placebo edge (−0.016): likely water or
  wet soil on the field at the storm, not crop. June catches up; July-September dip ~0.01-0.02
  within chance.
- **Against never-flooded fields, peak −0.022 [−0.036, −0.009], just outside the placebo
  (±0.015).** Not trusted:
  - fields the same storms missed are no browner than never-flooded ones (−0.003);
  - the never group is worth only ~16 fields per storm after height weighting (§37's problem).
- **Reading:** a spring storm tide leaves no greenness signal in the low crop fields larger than
  about ±0.02 NDVI (a few % of a summer canopy). This agrees with §37's CDL null. NDVI is
  greenness, not yield. The flood map behind it is noisy field by field (§39), which pulls a
  real difference toward zero.

## 39. Do the spring storm runs get the floods right? Place yes, extent and creek peaks no (2026-10-19; `reports/storm_gauges.md`, `reports/storm_landsat.md`, `scripts/validate_storm_{gauges,landsat}.py`)

Asked before reading §38's null. Two independent checks of the 7 spring storm-tide runs.
- **Interior gauges** (every high tide in the run windows, model max within ±3 h):

  | Gauge | High tides, all | Storm peak (where observed) | Low tides |
  |---|---|---|---|
  | Bivalve (Maurice) | −0.07 m | −0.05 (4 storms) | +0.19 |
  | Greenwich (Cohansey) | −0.14 | −0.09 (4) | +0.65 |
  | Hancocks Bridge (Alloway, Salem; 2022+) | −0.19 | −0.15 (3) | +0.45 |

  - The gauges often go out at the storm peak (Bivalve 2010-12, Greenwich 2012 / 2014), as in
    Sandy (§33); those peaks are unscored.
  - In the smaller creeks the tide is damped (lows far too high, highs short) and the Alloway
    lags: too little creek conveyance at 100 m, the §16 bias, now seen at the HIGHS too. Rain
    changes creek peaks by ≤ 1 cm.
  - On flat bayshore fields, 0.1-0.2 m of peak matters (§33): the runs likely miss some
    flooding along the Cohansey and Alloway.
- **Landsat water** (MNDWI > 0 on field interiors, new since a pre-storm scene). Only 3 storms
  have a clear scene within ~1.5 days:
  - **2011-04-17** (13 h after the peak, ~1 h after the next high tide): the only informative case.
    - Place is right. The deeper the model's water at the overpass, the more often Landsat sees
      water: 0.6% of model-dry pixels, 7% at 5-15 cm, 11% at 15-30, 18% at ≥ 30 cm. The MNDWI rise
      grows the same way. In western Salem, the observed water sits inside the model's patches.
    - 69% of the new water on low fields lies inside the run's PEAK footprint (77% with rain).
    - Extent is too big. Landsat confirms only 13% of the model's water at the overpass on low
      fields (151 ha in the model, 41 ha seen), and < 1 pixel in 5 under ≥ 30 cm of model water.
      Possible causes: real water hidden by stubble or cover, water draining faster than the model
      (§16), or banks and ground holding better than modelled. They can't be separated here.
    - Per field (≥ 10% wet), all fields: 129 seen flooded, 99 model-flooded at the overpass, only
      22 both. Many seen-only fields are upland: 36 mm of rain fell that day.
  - **2023-06-05** (1.5 days after, a dry storm, crops up): no agreement (1 ha overlap).
  - **2012-06-06:** cloud and Landsat 7 stripes; nothing scored.
- **For §37 / §38:** the exposure map is right about WHERE storms flood but noisy field by field:
  too wide at the overpass, too low in the Cohansey / Alloway creeks. Misclassified fields pull a
  flooded-vs-dry difference toward zero. So §37 and §38 show no detectable effect WITH THIS
  EXPOSURE MEASURE, not proof of no effect.

## 40. Creek tides: one Alloway bug fixed; the side creeks still carry about half the tide (2026-10-19; `reports/creek_tides.md`, `scripts/check_creek_tides.py`, `scripts/open_creek_links.py`)

Step 2 of the §39 follow-up. Nothing below is adopted into v1 yet; the test models are on
scratch (`models/e{2,3,4a,4b,5a,5b,6}_100m`, beds and roughness in `data_bulk/experiments/`).
- **Yardstick** (`check_creek_tides.py`, event `tidecal2023may`, calm tides 2023-05-24..31):
  - TUNING: highs / lows at Bivalve, Greenwich, Hancocks Bridge;
  - HELD OUT: CO-OPS published mean ranges (type R ratios to Reedy Point / Philadelphia) at 26
    stations up the creeks, × the reference's observed range those days. Checked against the
    gauges: Greenwich 1.37 m observed vs 1.40 expected; good to ~10%. Four station points fall
    in marsh / bank cells (Woodbury, Newport Landing, Abbots Meadow, Coopers Creek bridge) and
    are left out.
  - The storm peaks (§39) and Landsat stay held out for after a fix is chosen.
- **Alloway Creek was closed by its own banks (bug, fixed):** three NLD bank lines within half a
  cell of the creek land on the creek's cell links (SFINCS puts a weir on every link a segment
  crosses), so the upper 13 km (Quinton) never saw a tide. `open_creek_links.py` drops the 25
  weir segments that cut links along the 10 tidal centrelines → `dikes_open.weir`. Quinton
  0 → 0.34 of the published range. Hancocks Bridge got worse (highs −0.14 → −0.23 m): the
  reopened creek has to fill through the same channel. No other creek was affected.
- **Today (v1): the unsurveyed side creeks carry 0.36-0.45 of the published range** (Cohansey
  0.36, Oldmans 0.36, Stow 0.43, Big Timber 0.45); the surveyed Salem River 0.98-1.19. Even the
  bay-shore entrances read 0.79-0.87 and Bivalve's lows are +0.15 m: part of the deficit is
  already in the bay along the NJ shore.
- **Experiments** (all on the opened weirs except E0 / E3; median ratio per creek):

  | Run | Change | Cohansey | Stow | Oldmans | Big Timber | Greenwich lows |
  |---|---|---|---|---|---|---|
  | E0 | v1 | 0.36 | 0.43 | 0.36 | 0.45 | +0.51 |
  | E2 | chart-class beds −0.6 m (TAIL_MLLW_M 1.8, the chart's limit) | 0.42 | 0.46 | 0.46 | 0.42 | +0.44 |
  | E3 | 25 m cells along Cohansey + Alloway | 0.38 | 0.43 | 0.36 | 0.45 | +0.50 |
  | E4a / E4b | beds −1.2 / −1.8 m (beyond the chart) | 0.48 / 0.53 | 0.52 / 0.60 | 0.55 / 0.63 | 0.39 / 0.38 | +0.39 / +0.35 |
  | E5a | open-water roughness on the carved channels (NLCD calls 33% of them marsh / woods) | 0.37 | 0.44 | 0.42 | 0.61 | +0.50 |
  | E5b | E5a + E4a beds | 0.49 | 0.55 | 0.62 | 0.59 | +0.38 |
  | E6 | E5b + 420 km of NHD marsh creeks carved to −1.0 m | 0.49 | 0.55 | 0.60 | 0.57 | +0.38 |

- **Reading:** depth is the only big lever; resolution, marsh creeks and roughness add almost
  nothing (roughness helps the wooded Big Timber). It is not a face choke: the lower Cohansey's
  face conveyance matches the Salem's (median 17,000 vs 13,800 m³/s at unit slope). It is not
  storage in the wrong place: calm tides wet 138 km² of marsh and only ~5 km² of cropland.
  A Manning estimate says a 2-4 m deep, ~200 m channel cannot fill and drain the model's marsh
  on each tide without losing ~1-2 m of head over 7 km. So either the real creeks are much
  deeper than any chart we have (none has Cohansey soundings), or the model's marsh holds more
  water per tide than the real one, or the tide arriving at the mouths is already short.
  Unresolved.

## 41. The bay boundary: why the bay shore was short, and why the creek shortfall is not the boundary (2026-10-20; `reports/creek_tides.md`; scripts and inputs in `data_bulk/experiments/e7_boundary/`)

Step 3 of the §39 follow-up: the bay-shore deficit (§40) checked at the boundary, before the creeks.
- **How v1 forces the bay:** 5 NOAA gauges (Philadelphia, Marcus Hook, Reedy Point, Ship John
  Shoal, Cape May) as boundary points; SFINCS gives each of the 1,353 boundary cells a
  distance-weighted blend of its 2 nearest points (reproduced exactly from the map output).
  Boundary beds are −5 to −15 m, so the cells hold the range they are given.
- **Two losses in that blend:**
  - **phase cancellation:** neighbouring gauges are 1.2-1.5 h apart in tide phase; averaging two
    tides that far apart loses ~6-8% of range midway (boundary 1.31-1.38 m between Ship John
    and Reedy Point, which both read 1.44 m);
  - **the wrong gauge:** the Cumberland shore's tide is bigger than Cape May's (published mean
    range Fortescue 1.78, Bidwell Creek 1.73, Bivalve 1.72 m against Cape May 1.48, Ship John
    1.70), but the boundary there blends Cape May in. Boundary 1.18-1.24 m vs ~1.35 needed.
- **Yardstick fix (side agent's flag, checked):** expected ranges were ratio × the reference's
  range IN THE SCORING WEEK. That week the tide ran at a different fraction of its long-term
  mean range along the estuary (Lewes 0.74, Cape May 0.76, Ship John 0.85, Reedy 0.88,
  Marcus Hook 0.91, Philadelphia 0.95), so Reedy-referenced targets in the lower bay came out
  ~5-8% high. Dredging is not the cause: Reedy and Ship John both read 0.98 of their
  1983-2001 means over 2023. Better: station mean range (ratio × reference's published MN) ×
  that week's fraction interpolated between the 2 nearest gauges. This reconciles the
  neighbours that disagreed: Fishing Creek entrance (Reedy-referenced) 1.46 → 1.35 m,
  Dividing Creek entrance (Lewes-referenced) 1.23 → 1.35 m. It also scores the 20
  Lewes-referenced stations (Maurice, Cape May shore). Now `check_creek_tides.py`'s yardstick
  (2026-10-20); `reports/creek_tides.md` is on it, so its numbers differ by a few points from
  the §40 table.
- **Experiments** (on E1open; ranges as model / expected on the new yardstick):
  - E7a: + virtual gauges at Fortescue 8536931 and Bidwell Creek 8536581 (own harmonic
    prediction + Ship John / Cape May non-tidal residual), hourly, SFINCS blending;
  - E7b: the same 7-gauge chain, 196 boundary points (~1 per km), each a LAG-AWARE blend of its
    2 chain neighbours (both shifted to the point's phase first), 6-min.

  | | E1open | E7b |
  |---|---|---|
  | bay-shore entrances (Fishing, Dividing, Back, Cedar, Money Is., Salem Canal, Artificial Is.) | 0.79-0.89 | 0.82-1.00 |
  | Maurice: Mauricetown / Millville / East Point | 0.89 / 0.76 / 0.21 | 0.99 / 0.80 / 0.31 |
  | Bivalve gauge: highs / lows (m, model − obs) | −0.04 / +0.15 | +0.08 / +0.10 |
  | Cohansey / Stow / Oldmans / Big Timber (median, old yardstick) | 0.36 / 0.43 / 0.36 / 0.45 | 0.36 / 0.44 / 0.36 / 0.47 |
  | Greenwich / Hancocks Bridge lows (m) | +0.51 / +0.55 | +0.51 / +0.55 |

- **Reading:** the boundary explains most of the bay-shore deficit and Bivalve's range (now
  right within 0.02 m), and NOTHING in the side creeks. So the creek shortfall is inside the
  creeks (depth, or marsh storage), as §40 suspected; the "tide already short at the mouths"
  option is ruled out. E7a gets most of E7b's gain; lag-aware blending adds ~1-5 points.
- **E7 put Bivalve ~0.1 m high** at both highs and lows: the virtual gauges' datum. The
  1983-2001 MSL in NAVD88 spreads 0.13 m along the lower bay (Cape May −0.136, Ship John
  −0.068, Bivalve −0.085, Fortescue −0.008 m), and E7 used Fortescue's own tie (the outlier)
  and a Cape May / Fortescue mean for Bidwell.
- **Adopted (user, 2026-10-20) as the "chain" boundary, the default for new runs**
  (`waterlevel.CHAIN` / `chain_boundary` / `fill_virtual`, `events.chain_forcing`,
  `domain.VIRTUAL_STATIONS`; the virtual gauges are in `waterlevel_forcing_navd88.nc`, the five
  observed ones unchanged bit for bit). The virtual gauges are tied by transfer instead of
  their own ties: Fortescue from Bivalve (NAVD88 − MLLW 1.059), Bidwell from Bivalve + Cape May
  (1.073). E8chain (tidecal2023may, opened weirs): **Bivalve highs / lows +0.02 / +0.04 m**
  (E1open −0.04 / +0.15); entrances 0.84-1.02, Mauricetown 1.03, Millville 0.84; Greenwich
  lows +0.49, Hancocks Bridge +0.55, the side creeks unchanged. `--boundary gauges` restages
  the old boundary; `setup_scenarios.py` keeps it by default so the existing scenario matrix
  stays comparable with itself.

## 42. Creek depth sources: real soundings for Big Timber and Oldmans, none inside the Cohansey (2026-10-20, research agent + nj_bight_sfincs)

- **NOS digital soundings** (NCEI HYD93 XYZ, m, small files; e.g.
  `data.ngdc.noaa.gov/platforms/ocean/nos/coast/H08001-H10000/H09886/GEODAS/H09886.a93.gz`):
  - Big Timber: H09886 (1980, **MLW**), ~370 soundings from the mouth past Westville, 2.5-4.5 m,
    ~1 m at the top. nj_bight_sfincs takes MLW = −0.908 m NAVD88 (mean of Philadelphia
    8545240 and Pier 11 8545530; `build_riverbeds_tidal_v4.py`, "bigtimber").
  - Oldmans: H10027 (1982, MLLW), ~300 soundings to ~5.5 km (Pedricktown), median ~3 m.
  - Alloway: H10112 (1983, MLLW), lowest 1-2 km, ~3.4 m.
  - Cohansey: D00081 (1987) / H11070 (2001), the mouth only. Stow: nothing inside.
- So **Oldmans and Big Timber are ~1.5-2 m deeper than our convention bed** (1.2 m below MLLW,
  §11). That matches E4b (−1.8 m), where Oldmans reached ~0.6.
- **Cohansey:** a federal channel (USACE National Channel Framework `CENAP_CO_01_CRC`, 6 ft
  authorized, 100 ft wide, 2.7 mi, about Fairton to Bridgeton). eHydro has no surveys for it;
  the last maintenance dredging found was ~1985. Coast Pilot 3 ch. 6 (2026): controlling depth
  ~7 ft at the entrance, 4-6 ft shoals either side (Alloway ~3 ft to Quinton). That is only
  ~0.6-0.9 m deeper than our bed. The 1905-06 Corps survey maps with soundings along the whole
  river are scanned at Rutgers RUcore (rutgers-lib:56574 mouth, 56588 Bridgeton to Lupton's
  Landing; ft, probably MLW).
- No USGS cross-sections (Greenwich 01413038 has only water-level checks), nothing from NJDOT,
  PDE or NERRS. nj_bight_sfincs has no Cohansey data either: same 1.2 m-below-MLLW bed; its
  Greenwich range is ~0.62 of observed (§54 there).
- **Reading:** if the Cohansey's real depth is ~2 m below MLLW and the tide still wants much
  more, the depth gap is not the whole story there, and marsh storage (§40) is the suspect.

## 43. Measured depths give the measured tide: Big Timber fixed, Oldmans halfway, Cohansey short (2026-10-20; `reports/creek_tides.md`, `scripts/build_bed_e9.py`, soundings in `data/channels/nos/`)

E9 (`models/e9_100m`) = E8chain (chain boundary, opened weirs) with a bed from data instead of
the 1.2 m-below-MLLW convention (`scripts/build_bed_e9.py`, lower-only, painted on v1's tidal strip):
- Big Timber: NOS H09886 (MLW → MLLW −0.058 m), 309 soundings over 10 km, lowered a median 2.4 m;
- Oldmans: NOS H10027, 123 soundings over the lowest 5 km (to ~Pedricktown), lowered 1.7 m;
- Cohansey: 7 ft below MLLW (Coast Pilot controlling depth at the entrance) from the mouth to
  Fairton (39.381 N), 16 km, lowered 0.9 m; above Fairton unchanged;
- Alloway: H10112's soundings lie in the open-water mouth (CUDEM already), so unchanged;
- Stow: no data, unchanged (the control).

| Station (model / expected range) | E8chain | E9 |
|---|---|---|
| Big Timber, Westville | 0.47 | **0.97** |
| Oldmans, Pedricktown (sounded reach) / Auburn (above it) | 0.40 / 0.31 | 0.68 / 0.42 |
| Cohansey, Greenwich Pier / Tindalls Wharf (at Fairton, above the change) | 0.55 / 0.20 | 0.72 / 0.26 |
| Greenwich gauge lows / highs (m, model − obs) | +0.49 / −0.12 | +0.32 / −0.07 |
| Stow (3 stations), Alloway, Bivalve | — | unchanged |

- **Reading:** where the bed is measured all the way (Big Timber), the model gets the measured
  tide. So the side-creek shortfall is mostly the convention bed being too shallow, not model
  physics, and probably not marsh storage there (Big Timber has little marsh). Oldmans is fixed
  only as far as the soundings go. The Cohansey at 7 ft is still short; 7 ft is the SHALLOWEST
  point at the entrance, so the channel is probably deeper elsewhere, and the upper river
  (Fairton to Bridgeton, the federal 6 ft channel, unmaintained since ~1985) has no data at all.
- E9 is judged on the calm-tide window only (tidecal2023may); not yet on the storm peaks
  or Landsat (§39).

## 44. Delaware's record shows the NJ exit pattern: low ground leaves farming ~1.5 %/yr in both states, in the same years (2026-10-23; `reports/exit_history.md`, `scripts/exit_history.py`)

Before any DE flood model: each state's LU/LC farm polygons of 2012 (`agri_sfincs.fields`; DE =
FirstMap DE_LULC 2012, `scripts/fetch_delulc.py`, in the DE ring) that were >= 50% CDL cropland
in 2008-12; exit = the storm panel's `left_cropland`; height = median above recent MHHW
(`agri_sfincs.exposure`, DE: the 2023 statewide lidar, MHHW from Reedy Point / Ship John / Lewes).
- Crop fields: NJ 7,650 (71,172 ha), DE 3,557 (73,646 ha; of 4,443 farm polygons, 75,888 ha).
  Below 1.5 m above MHHW: NJ 1,041 fields / 4,298 ha, DE 184 / 2,363 ha (DE fields are larger).
- **Mean exit rate 2009-23 (% of area at risk per year):** below 1.5 m NJ 1.51, DE 1.50; above
  3 m NJ 0.71, DE 0.47. Low ground leaves ~2× (NJ) to ~3× (DE) faster than upland.
- **Spike years are shared by both states and every height band** (2011-13, 2019, 2021; 2024 =
  the CDL product change, NJ 8.8%, DE 3.9%). A spike common to both shores and to upland is CDL
  or regional weather, not a local flood: a flood → exit regression needs year effects and has
  to compare fields within a year. The LOW-ground excess is largest in 2010, 2013, 2019 and 2020
  in both states (see the report's table).
- LU/LC: 2012 farm area not farmed by the last edition: NJ 0.9-4.9% by county (2020), DE
  3.3-9.7% (2022; New Castle highest, development).
- Not yet: whether the DE low-ground exits follow modelled storm flooding (needs the DE runs).

## 45. v2 creek beds (NJ): measured sources in one builder; the Cohansey needs an effective 6 m (2026-10-23; `reports/creek_tides.md`, `scripts/build_riverbeds.py --tag v2`)

- **One builder:** `build_riverbeds.py` takes, per tidal reach, eHydro → NOS surveys (new, code 8)
  → crowdsourced CSB soundings (new, code 9; `fetch_channels.py csb`: NCEI tracks crossing the
  channel, tide-reduced at the nearest CO-OPS gauge, +0.5 m draft) → ENC → stated / calibrated
  depth (code 10, a floor from a point down to the mouth) → 1.2 m below MLLW. Measured points
  more than 120 m from the centreline or on open water are dropped (the Mantua's CSB points
  were Delaware River soundings at Paulsboro, ~10 m deep). `build_bed_e9.py` is gone.
- **v2 reproduces e9** where e9 had data (calm window 2023-05-24..31, model / expected range:
  Big Timber 0.97, Oldmans 0.55, Alloway 0.65, Stow 0.45, Maurice 0.84; unchanged).
- **Cohansey:** NOS D00081 + CSB (61,000 soundings, 2024-26; Sandy repo's
  `logs/cohansey_sources_2026-10-22/`) deepen the lowest ~5 km to 5-8 m below MLLW. The middle
  river has no soundings; a stated depth from Fairton down was calibrated:

  | depth below MLLW | Greenwich gauge range | lows bias | Greenwich Pier* | Tindalls Wharf* |
  |---|---|---|---|---|
  | e9 (7 ft, by latitude) | — | +0.32 | 0.72 | 0.26 |
  | 2.13 m (along channel) | 0.77 | +0.27 | 0.77 | 0.36 |
  | 3.0 m | 0.80 | +0.24 | 0.80 | 0.47 |
  | 4.5 m | 0.84 | +0.19 | 0.83 | 0.63 |
  | **6.0 m (adopted)** | 0.87 | +0.16 | 0.86 | 0.75 |

  (* held out; highs stay within −0.04..−0.02 m.) 6 m is inside the 1906 survey (30-40 ft with
  one ~7 ft bar) and the CSB, and is EFFECTIVE: it likely also stands in for channel width the
  painted strip lacks. Still short (Greenwich lows +0.16 m).
- **NJ marsh creeks need no fix:** named tidal creeks (Hope, Oranoaken, Mad Horse, Little ...)
  connect at -1.07 m, the NJ lidar's hydro-flat MLW plane; the creeks with sills above 0 m are
  gated / diked systems (Repaupo, Pargey, Fenwick, Clonmell), which the dike weirs handle. The
  Sandy repo's 55-creek problem came from CUDEM-first beds.
- Model: `v2_100m` (bed_v2, `dikes_open.weir`, `dike_gates_lo.drn`); calibration models
  `v2c{30,45,60}_100m` on scratch.

## 46. Delaware twin model, first pass: the creeks need their beds, and the DE shore gets too much tide (2026-10-23; `reports/creek_tides_de.md`)

- **Region:** 33 HUC12s (Augustine … Breakwater Harbor) + the open-bay unit 020402040000
  clipped at 39.558 N (DE's frontal units stop up to 8 km offshore; with it the DE ring meets
  NJ's along 102 km of state line) + the C&D Canal unit south of the canal
  (`scripts/split_canal_unit.py`, 67 km², DE land the plan's extent includes): 3,299 km².
- **Bed:** DE 2023 statewide lidar (3DEP 1 m, read from its COG overviews onto the NJ lidar's
  lattice, `fetch_de_lidar.py`), CUDEM below; in the ring: lidar 1,843 km², CUDEM channels
  181, open bay 1,192; no 3DEP / GMRT. Lakes are lidar water surfaces (no fake beds).
- **Open water for the boundary** is bed_source {2, 3} in DE (3 alone in NJ): DE's lidar covers
  the river beside its shore. Boundary: 866 faces on the state line, 108 on the mouth, 59 on the
  canal / river cut; forcing = the chain with Lewes first (Cape May leads Lewes by 0.1 h), so
  the state-line points get the same pairs as NJ's.
- **Dikes:** NLD has ~nothing in DE; NWI "h" (diked/impounded) perimeters as raw-ridge weirs
  (`build_dikes_nwi.py`, 63 lines, 137 km; crest medians ~1.1-1.2 m NAVD88, i.e. much of each
  perimeter is marsh, not bank). Water-control structures not modelled.
- **Creek beds (v2):** NOS for Blackbird, Leipsic, St Jones, Murderkill, Broadkill; eHydro
  Little River, Murderkill; CSB only at the Broadkill inlet (open water, unused).
- **Calm-window tide** (tidecal2023may, tide only), merged bed → v2 beds:
  Odessa (Appoquinimink) 0.09 → 0.26 of the observed range (lows +1.07 → +0.88 m: still barely
  drains); Cedar Creek 0.54 → 0.82 (lows +0.46 → +0.21); Bowers (Murderkill, gage height)
  0.86 → **1.15**; held-out Murderkill / Mispillion entrances and Woodland Beach **1.19-1.21**.
- **Open problem:** the DE shore gets ~15-20% too much tide while NJ's bay shore gets 0.84, both
  on the same state-line forcing built from NJ-shore gauges (+ Lewes at the mouth). The real
  tide differs across the bay (Lewes MN 1.24 vs Cape May 1.48); the boundary needs a DE-shore
  rail (Lewes, Brandywine Shoal, DE subordinate stations as virtual gauges) blended by
  cross-bay position, as §41 did for NJ.
