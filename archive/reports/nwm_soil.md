# NWM v3.0 retrospective: soil-wetness predictors per county

Checked 2026-10-02. Script: `archive/scripts/fetch_nwm_soil.py` (log: `logs/fetch_nwm_soil.log`). Outputs are in `data/nwm/`.

**Bottom line.** Anonymous windowed reads of the NWM v3.0 retrospective zarr on AWS work well. All of
2002-01-01 → 2023-01-31 took about 30 minutes (~1 min per year at 1 km, 20 s per year at 250 m). The record
ends on **2023-01-31**, so it does not reach the two flagged events (Sep 2023, May 2025). The retrospective
has no `SOILSAT_TOP` or `SFCRNOFF`. Ponding is available on the 250 m routing grid as `sfcheadsubrt`.

## 1. What exists

**Bucket:** `s3://noaa-nwm-retrospective-3-0-pds/CONUS/`, anonymous. It holds `zarr/` (chunked, the practical
route) and `netcdf/` (one CONUS file per 3 h: LDASOUT 140–210 MB, RTOUT 43 MB, so a window costs a whole file).

| store | grid | variables |
|---|---|---|
| `ldasout.zarr` | 1 km LCC (3840 × 4608) | ACCET, ACSNOM, ALBEDO, ALBSND, ALBSNI, COSZ, EDIR, FIRA, FSA, FSNO, HFX, LH, QRAIN, QSNOW, SNEQV, SNOWH, **SOIL_M** and **SOIL_W** (4 layers: 0–10, 10–40, 40–100, 100–200 cm), TRAD, **UGDRNOFF** |
| `rtout.zarr` | 250 m LCC (15360 × 18432) | **sfcheadsubrt** (surface head, i.e. ponded water, mm), **zwattablrt** (depth to saturation, m) |
| `gwout.zarr`, `chrtout.zarr`, `lakeout.zarr`, `forcing/` | reaches, lakes, 1 km forcing | not used here |

- **No** SOILSAT_TOP, SFCRNOFF, SOIL_T or soil ice. The netCDF LDASOUT files carry the same 20 variables.
- `zwattablrt` takes only the layer tops 0, 0.1, 0.4 and 1.0 m, or 2.0 m when nothing is saturated.
- **Time:** 3-hourly, 1979-02-01T03Z → 2023-02-01T00Z. LDAS is complete. RTOUT is **missing 2022-12-08T03Z →
  2023-01-04T00Z** (27 days).
- **Format:** int32 packed (scale 0.01 for soil/ET/runoff, 1 mm for head, 0.1 m for depth), zstd, zarr v2. Chunks
  are 224 steps (28 days) × 350 × 350.
- **Cost:** the study window is 2 spatial chunks at 1 km and 4 at 250 m, about 190 MB per 28 days for everything
  pulled, ~5 s per chunk.
- **Accumulators** (ACCET, UGDRNOFF) restart at 0 at 00Z on the first day of every calendar quarter. This was checked
  for 2002–2022: no negative UGDRNOFF increments remain after handling the restarts.
- **After 2023-01:** only the operational NWM archive covers later dates (`gs://national-water-model/nwm.YYYYMMDD/analysis_assim/`,
  from 2018-09). Its hourly land files are ~120 MB each, whole-file only, and do include SOILSAT_TOP and SOIL_T.
  It is a different configuration (data assimilation, MRMS/HRRR forcing), so it is not homogeneous with the
  retrospective. Covering Feb 2023 – 2025 at one file per day would mean downloading ~120 GB.

## 2. What was pulled

- **Window:** the bounding box of the ring plus the three whole counties, padded by 2 km. That is 94 × 75 cells at
  1 km and 372 × 294 cells at 250 m.
- **Days:** day D is the mean of the 8 instants D 03Z … D+1 00Z (UTC).
- **Gridded data**, one netCDF per year, **1.3 GB** in total:
  - `grid/nwm_ldas_daily_<year>.nc`: soil_m1–4, sneqv, qrain, accet_eod and ugdrnoff_eod;
  - `grid/nwm_rt_daily_<year>.nc`: sfchead_mean/max and zwt_mean/min.
- **Cropland weights** (`nwm_cropland_weights.nc`):
  - Every 30 m CDL cropland pixel inside a study county is counted in the NWM cell that contains its centre, on both
    grids.
  - Each year uses the CDL of that year. 2002–2007 use CDL 2008.
  - **CDL 2010 is skipped** (Gloucester artifact, FINDINGS §1), so 2010 uses 2009.
  - The whole county is used, not only the part inside the ring, because the losses are whole-county.
  - NWM water cells (NaN) drop out of the weights.
- **County series:** `nwm_soil_daily_county.csv` has 23,103 rows (3 counties × 7,701 days) and 25 columns:
  - date, fips, county, cdl_year, crop_km2;
  - soil_m1–4 and soil_m_0_100cm (depth-weighted);
  - sneqv_mm, qrain_mm, accet_mm, ugdrnoff_mm (daily increments);
  - sfchead_mean_mm and sfchead_max_mm;
  - ponded_frac and ponded10_frac (share of cropland whose daily-max head is > 0 or ≥ 10 mm);
  - zwt_mean_m and zwt_min_m;
  - sat_0cm/10cm/40cm_frac (share of cropland saturated from that depth up at any instant of the day);
  - n_ldas and n_rt (number of samples).
- **Gaps:** the only NaNs are the 27 RTOUT-gap days (81 rows).

Sanity check: across county-years, the annual means are qrain ≈ 1,140 mm, ET ≈ 790 mm and underground runoff
≈ 220 mm.

## 3. First look against the loss panel

This is a first look only: in-sample and uncontrolled. It uses `data/rma/loss_panel_county_month.csv` with the "all"
crop group, 2003–2022, which gives 720 county-months, 217 of them with broad-wet indemnity > 0. AUC measures how well
the monthly predictor separates months with and without a wet loss. The anomaly column standardizes each predictor
within county × calendar month, which removes the seasonal cycle.

| monthly predictor | AUC raw | AUC anomaly |
|---|---|---|
| soil_m1 mean (0–10 cm) | 0.54 | **0.72** |
| soil_m_0_100cm mean | 0.57 | **0.72** |
| sat_0cm_frac mean | 0.58 | 0.68 |
| ponded_frac mean | 0.65 | 0.70 |
| sfchead_mean_mm | 0.59 | 0.69 |
| ugdrnoff_mm sum | 0.54 | 0.69 |
| qrain_mm sum (NWM's own rain) | **0.73** | 0.67 |

- Raw rain wins mostly through seasonality: wet losses cluster in May–Aug.
- Once the seasonal cycle is removed, NWM soil moisture separates wet-loss months better than NWM rain does.
- Treat this as a reason to carry soil moisture into the real model, not as a result.

## 4. Caveats

- **Ends 2023-01-31.** The retrospective cannot score the Sep 2023 or May 2025 events. Panel years 2023–2025 need
  another source (operational NWM, SMAP L4, or our own MRMS-driven water balance).
- **NWM soils and drainage are generic.** It uses Noah-MP with STATSGO-derived soil classes at 1 km, no tile drainage
  and no SSURGO dual hydrologic groups. Absolute values are not field truth; use anomalies and percentiles.
- **sfcheadsubrt** is ponded head after the routing grid's retention depth. Most cropland cell-days are 0, and ≥ 10 mm
  is rare (0.2–0.7% of all window cell-days, by year). `ponded_frac` is therefore a small-number share.
- **qrain** is the instantaneous rain rate sampled every 3 h, times 86,400. It is indicative only; use AORC, Stage IV
  or MRMS for rain.
- **Days are UTC.** D 03Z … D+1 00Z is about 22:00 the previous evening to 19:00 EST, which is immaterial at monthly
  scale.
- **Weights before 2008** use CDL 2008, so crop location there is held fixed.
