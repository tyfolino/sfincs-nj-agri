# RMA loss panel: county × month × crop group

Built by `scripts/build_loss_panel.py` from `data/rma/colsom_*_NJ.csv` (Cause of Loss) and `data/rma/sobcov_*_NJ.csv` (Summary of Business). Output `data/rma/loss_panel_county_month.csv`. The collaborators' file in `data/insurance/` is not read.

## Method

- **Grid:** 3 study counties × 23 calendar years of loss (2003–2025) × 12 months × 5 crop groups (soybeans 0081, corn 0041, wheat 0011, other = every other commodity, all) = **4,140 rows**. Every cell is present; cells without COL rows are zeros.
- **Year/month** are COL's year and month **of loss** (as in the collaborators' sample). COL has no year of loss before commodity year 2003, so the panel starts in 2003. 2026 is left out because that calendar year is still being reported.
- **Wet:** `indemnity_wet_31_51` = causes 31 + 51 (the collaborators' definition); `indemnity_wet_broad` adds 44, 46, 47, 52, 67, 92. `indemnity_wet_broad_pp` is the prevented-planting part (stages P, P1–P4, PF, PT, PP, NP). Indemnity is **signed** (negative COL rows are corrections and are kept), so a cell can be negative.
- **Policies:** `n_policies_wet_*` sums COL `policies_indemnified` over the wet rows, an upper bound on distinct policies (one policy paid under two causes, stages or plans counts twice).
- **Liability (denominator)** comes from the Summary of Business for one commodity year per commodity: the year of loss, except wheat (0011) and barley (0091) losses in **Sep–Dec**, which are charged to commodity year **+1** (the crop seeded that fall). The same rule is used for zero cells, so the denominator does not depend on whether a loss occurred. `liability_commodity_year` gives the lead crop's year (wheat: +1 in Sep–Dec). `indemnity_other_cy` holds any indemnity in the cell whose COL commodity year differs from the rule.
- **Plans:** `liability` excludes area/index/endorsement plans (GRP, GRIP, RI, SCO, ECO, STAX, HIP-WI, …). Their indemnity is always cause 55 in NJ COL, never wet, and their liability double-counts acres already insured by the underlying policy. `liability_all_plans` keeps them and is the denominator of `lr_total`.
- Loss ratios = indemnity / liability; NaN where liability is 0.

## Rows dropped

| reason | COL rows | indemnity $ |
|---|---|---|
| no year of loss (commodity year >= start) | 4 | 6,760 |
| month 0 / unknown | 0 | 0 |
| year of loss outside 2003-2025 | 40 | 4,957,523 |

County 999 "All Other Counties" and non-study counties are outside the panel by construction.

## Coverage

Cells per group: 828.

| crop_group | cells ≠0 total | cells ≠0 wet 31+51 | cells ≠0 wet broad | total $ | wet broad $ | cells with liability |
|---|---|---|---|---|---|---|
| soybeans | 312 | 121 | 126 | 16,276,886 | 2,235,766 | 828 |
| corn | 275 | 91 | 95 | 16,225,424 | 2,035,101 | 828 |
| wheat | 165 | 71 | 92 | 2,516,002 | 1,448,846 | 828 |
| other | 202 | 74 | 94 | 6,709,236 | 2,182,285 | 828 |
| all | 503 | 213 | 246 | 41,727,548 | 7,901,996 | 828 |

- Wet (broad) cells with **no liability**: 0 ($0); none.
- Indemnity whose COL commodity year differs from the rule: $855,987 of $41,727,548 all-cause (2.1% of absolute $). Most of it is late claims (loss months Feb–Jun charged to the previous commodity year) and a few fall row-crop losses filed against the next year.
- Consistency: SOB indemnity for the study counties, commodity years 2003–2025, is $41,746,432; COL panel rows sum to $41,727,548. These need not match exactly: COL is keyed by year of loss, and the two files are revised separately.

**Liability by year (June exposure, $M, three counties summed):**

| year | soybeans | corn | wheat | other |
|---|---|---|---|---|
| 2003 | 1.86 | 1.91 | 0.25 | 28.57 |
| 2004 | 3.32 | 2.63 | 0.28 | 33.61 |
| 2005 | 2.57 | 2.69 | 0.23 | 39.93 |
| 2006 | 2.50 | 2.36 | 0.33 | 37.45 |
| 2007 | 2.92 | 4.84 | 0.42 | 37.45 |
| 2008 | 5.54 | 5.94 | 0.99 | 41.02 |
| 2009 | 5.34 | 4.98 | 2.44 | 38.78 |
| 2010 | 6.11 | 6.17 | 1.28 | 26.91 |
| 2011 | 8.11 | 11.76 | 2.68 | 29.89 |
| 2012 | 8.30 | 11.13 | 2.79 | 27.20 |
| 2013 | 9.56 | 11.83 | 3.20 | 19.57 |
| 2014 | 9.85 | 8.48 | 2.27 | 6.48 |
| 2015 | 8.79 | 6.94 | 1.82 | 5.78 |
| 2016 | 7.76 | 7.36 | 1.52 | 6.68 |
| 2017 | 9.01 | 7.47 | 1.20 | 7.49 |
| 2018 | 9.79 | 7.38 | 1.15 | 8.04 |
| 2019 | 8.51 | 8.53 | 1.39 | 7.13 |
| 2020 | 7.66 | 9.16 | 1.64 | 6.80 |
| 2021 | 11.32 | 10.49 | 1.77 | 7.31 |
| 2022 | 14.76 | 14.81 | 2.68 | 8.24 |
| 2023 | 13.85 | 16.15 | 4.19 | 9.78 |
| 2024 | 11.98 | 12.47 | 3.26 | 9.88 |
| 2025 | 9.86 | 13.84 | 2.75 | 9.28 |

## Caveats

- **Single-policy cells.** Of 407 county × month × crop-group cells with broad-wet indemnity, 78% involve ≤ 2 indemnified policies (row sums) and 54% only 1. They hold 47% and 31% of the absolute wet $. Dollar amounts and loss ratios in those cells reflect one farm's claim; prefer frequency (any wet loss), pooled crops or multi-month windows, and weight or robustify cell-level regressions.
- Largest wet loss ratios (cells):

| cell | indemnity_wet_broad | liability | lr_wet_broad | n_policies_wet_broad |
|---|---|---|---|---|
| Cumberland 2003-06 corn | 87,436.000 | 511,602.000 | 0.171 | 2.000 |
| Cumberland 2020-10 wheat | 63,133.000 | 448,784.000 | 0.141 | 1.000 |
| Salem 2018-10 wheat | 122,122.500 | 886,884.000 | 0.138 | 6.000 |
| Cumberland 2009-11 wheat | 41,787.000 | 314,410.000 | 0.133 | 4.000 |
| Cumberland 2003-06 wheat | 8,894.000 | 69,686.000 | 0.128 | 1.000 |

- **Liability is annual and county-wide;** a monthly loss ratio is monthly indemnity over the whole season's exposure. Sum months for seasonal ratios.
- **"other"** is dominated by nursery and "All Other Crops" liability (dollar plans, whole-farm products), whose losses are rarely weather-by-month. Its liability also has a **structural break**: SOB "All Other Crops" in the study counties is ~$20-24 M a year through 2013 and under $1.1 M from 2014, so "other" (and "all") liability drops ~70% in 2014, most likely a change in how a product is reported rather than in acreage (unverified). Its loss ratios are not comparable to the row crops or across that break.
- **Commodity-year edges:** Sep–Dec wheat/barley use next-year liability; for the last panel year that is commodity year 2026, which RMA is still reporting.
- **Revisions:** RMA re-posts recent COL and SOB years as claims settle; re-fetch both with `--refresh` and rebuild.
- **Signed rows:** 38 COL rows in the panel are negative ($-73,184); they are kept and net within cells.
- **Signed values:** 0 panel cells have negative total indemnity, 0 negative broad-wet indemnity, and 0 have wet > total (other causes net negative).
- **"all" includes "other"**, so its liability is mostly nursery/dollar-plan exposure; for a row-crop wet ratio, sum soybeans + corn + wheat instead.
