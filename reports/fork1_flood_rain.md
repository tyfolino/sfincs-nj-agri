# Fork 1: does flooding add crop-insurance losses beyond rain? (pilot)

*Pilot memo for the ag-econ collaborators, built by `scripts/fork1_panel.py` (2026-10-05). Public data only (RMA, PRISM, FEMA, CDL); the collaborators' loss tables in `data/insurance/` were not used.*

## The question and the design

Spec: **Damage = b1·P + b2·(P × FloodShare) + controls**. In three NJ counties b2 cannot be estimated with any precision (FINDINGS §13, §20), so this pilot pools every county of NJ, DE, MD, VA and NC and lets b2 come from counties that differ in a **fixed** flood-prone cropland share. If flooding (not just wetness) drives losses, the same extra 100 mm of rain should raise losses MORE where more cropland sits in the floodplain.

- **Outcome:** monthly water indemnity per county, all crops (RMA Cause of Loss, year/month of loss 2003–2025): broad water causes (31 excess moisture, 44 cold wet weather, 46/47 tropical storm & hurricane, 51 flood, 52, 67 storm surge, 92) and, as a check, 31 + 51 only. Exposure: the county's insured liability that season (RMA Summary of Business), entered as an offset, so the model is about the **loss ratio**.
- **Rain:** PRISM monthly precipitation (4 km), averaged over each county's cropland (2023 CDL).
- **FloodShare:** share of the county's cropland inside FEMA's 1% annual-chance flood zone (NFHL zones A*/V*), fixed over time. Where the digital FEMA maps cover < 90% of a county's cropland, a relief proxy (cropland < 2 m above the lowest ground within 1 km, 3DEP DEM) rescaled to FEMA units is used instead and flagged.
- **Model:** Poisson pseudo-maximum likelihood (PPML) with county fixed effects (absorbing each county's own level, including the share's main effect), month-of-year effects (seasonality) and year effects (region-wide bad years). b1 and b2 are semi-elasticities: b1 = change in log expected loss per +100 mm in a county with no floodplain cropland; b2 = how much that response grows per unit (0 → 100%) of FloodShare. Also a two-part version (logit for any loss > $1,000, then PPML on loss months).
- **Uncertainty:** standard errors are leave-one-year-out jackknife SEs (p-values from t with 22 df). The top 1% of county-months hold 52% of the water dollars (largest state-months: NC 2024-08 ($184 M), NC 2018-09 ($145 M), NC 2011-08 ($123 M), NC 2013-06 ($82 M), NC 2020-08 ($65 M)), losses move together across counties within a year, and the usual sandwich SEs (shown for comparison) are too small: for b2 in the main model the two-way county × year sandwich is 49% of the jackknife SE and county-only clustering 45%.

## Data coverage

| state_abbr | counties | coastal_plain | cropland_km2 | nfhl_fallback | share_sfha_median | share_flood_p90 | insured_counties | loss_months | wet_indemnity_musd | liability_musd_yr |
|---|---|---|---|---|---|---|---|---|---|---|
| DE | 3 | 3 | 1,823.32 | 0 | 0.05 | 0.06 | 3 | 403 | 31.23 | 113.76 |
| MD | 24 | 15 | 5,317.67 | 0 | 0.02 | 0.12 | 23 | 2010 | 81.08 | 303.91 |
| NC | 100 | 43 | 19,049.29 | 0 | 0.07 | 0.25 | 99 | 9802 | 2,174.21 | 1,550.88 |
| NJ | 21 | 11 | 1,658.87 | 1 | 0.06 | 0.26 | 16 | 645 | 21.69 | 84.65 |
| VA | 133 | 41 | 13,020.31 | 0 | 0.06 | 0.21 | 95 | 4949 | 230.42 | 481.29 |

County-months with insured liability: 61,644 of 77,556 (236 counties × 23 years × 12 months). Broad-water indemnity > $1,000 in 28.9% of them; total $2.54 B (31+51 only: $1.71 B); the largest 1% of county-months hold 52% of it.
FloodShare across counties: 10th pct 1.0%, median 5.5%, 90th pct 23.8%. NFHL digital maps cover ≥ 90% of the cropland in 280 of 281 counties; the relief fallback is used for Cape May County NJ (1 of them insured).

COL rows dropped (no year of loss, month unknown, out of window): no year of loss (commodity year >= start): 106 rows ($1,364,966); month 0 / unknown: 1 rows ($153); year of loss outside 2003-2025: 4,484 rows ($97,435,047).

## Estimates

| spec | model | rain | b1 (SE) | b2 (SE) | p(b2) | SE(b2) 2-way sandwich | SE(b2) county sandwich | n | counties |
|---|---|---|---|---|---|---|---|---|---|
| main: broad water, all counties | PPML | P per 100 mm | +0.895 (0.252) | +0.012 (0.350) | 0.97 | 0.172 | 0.159 | 61,296 | 233 |
| main: broad water, all counties | two-part: logit P(loss > $1,000) | P per 100 mm | +1.370 (0.095) | -0.105 (0.232) | 0.66 | 0.218 | 0.151 | 61,296 | 233 |
| main: broad water, all counties | two-part: PPML on loss months | P per 100 mm | +0.783 (0.182) | -0.185 (0.262) | 0.49 | 0.164 | 0.158 | 17,809 | 233 |
| 31+51 only | PPML | P per 100 mm | +0.871 (0.262) | +0.111 (0.374) | 0.77 | 0.119 | 0.154 | 61,296 | 233 |
| 31+51 only | two-part: logit P(loss > $1,000) | P per 100 mm | +1.376 (0.107) | -0.198 (0.241) | 0.42 | 0.215 | 0.148 | 61,296 | 233 |
| 31+51 only | two-part: PPML on loss months | P per 100 mm | +0.712 (0.213) | -0.013 (0.349) | 0.97 | 0.171 | 0.160 | 16,245 | 233 |
| coastal-plain counties | PPML | P per 100 mm | +0.870 (0.250) | -0.060 (0.318) | 0.85 | 0.175 | 0.155 | 26,316 | 96 |
| NFHL-covered, raw SFHA share | PPML | P per 100 mm | +0.895 (0.252) | +0.012 (0.350) | 0.97 | 0.172 | 0.159 | 61,296 | 233 |
| relief share (<2 m above local low) | PPML | P per 100 mm | +0.916 (0.263) | -0.143 (0.230) | 0.54 | 0.143 | 0.112 | 61,296 | 233 |
| state x year FE | PPML | P per 100 mm | +0.906 (0.250) | -0.036 (0.370) | 0.92 | 0.192 | 0.154 | 61,296 | 233 |
| without North Carolina | PPML | P per 100 mm | +0.983 (0.092) | +0.380 (1.006) | 0.71 | 0.946 | 0.749 | 35,496 | 134 |
| row crops (corn, soy, wheat) | PPML | P per 100 mm | +0.889 (0.234) | +0.386 (0.352) | 0.28 | 0.124 | 0.110 | 41,156 | 169 |
| rain extremes (P > county-month p90) | PPML | 1{P > p90} | +1.501 (0.165) | -0.160 (0.377) | 0.68 | 0.229 | 0.180 | 61,296 | 233 |
| rain extremes, 31+51 | PPML | 1{P > p90} | +1.214 (0.151) | +0.197 (0.374) | 0.60 | 0.280 | 0.244 | 61,296 | 233 |

b1 per +100 mm of monthly rain (or per month above the county's 90th percentile for that calendar month, in the "extremes" rows); b2 per unit FloodShare (0 → 1); (SE) = year-jackknife. The relief row uses the relief share in place of FloodShare, so its b2 is on that scale.

Reading the main row: +100 mm of monthly rain raises expected water losses by +145% in a county with no floodplain cropland; moving from a 10th- to a 90th-percentile FloodShare county (1.0% → 15.6% of cropland) changes that response by +0.002 log points (95% CI -0.104 to +0.108).

## Power

How large would b2 have to be for this panel to detect it (two-sided 5% test, 80% power)? Two answers:

- **Analytic**, from the jackknife SE (t test).
- **Simulated**: the main PPML re-estimated on 100 simulated panels per true b2. Each keeps the fitted rain and seasonal structure, imposes the true b2, and borrows the real model's multiplicative residuals (y / fitted) from a randomly permuted year, so the simulated losses are as lumpy, zero-heavy and cross-county-correlated as the real ones. The draws are shifted (median b2 -0.21 at a true 0), so a draw rejects when its distance from that median exceeds the 95th percentile of the b2 = 0 draws. This is conservative: in a synthetic check (heavy-tailed losses, known truth) the permuted-residual draws spread ~1.7× wider than the true sampling distribution, while the jackknife SE was within 10% of it.

| mult_se | true b2 | effect at p90 − p10 share | power, analytic | power, simulated | mean simulated b2 | 2-way sandwich |z|>1.96 |
|---|---|---|---|---|---|---|
| 0.000 | 0.000 | +0.000 | 5% | 5% | -0.245 | 19% |
| 1.000 | 0.350 | +0.051 | 16% | 11% | +0.153 | 28% |
| 2.000 | 0.700 | +0.102 | 48% | 26% | +0.485 | 43% |
| 3.000 | 1.051 | +0.153 | 82% | 47% | +0.822 | 73% |
| 4.000 | 1.401 | +0.205 | 97% | 60% | +1.068 | 78% |

- **MDE80, analytic: b2 ≈ 1.03 (+16% in the per-100-mm response between a 10th- and a 90th-percentile FloodShare county)**; simulated (conservative): b2 > 1.40 (80% not reached on the grid).
- With no true effect, the two-way sandwich z-test rejects in 19% of the simulated panels (nominal 5%) — why it is not used for inference here.
- For scale, b1 (the rain response itself) is 0.90 ± 0.25.

## Caveats

- **Cause coding is not a flood measure.** Adjusters code the dominant cause; "excess moisture" (31) covers ponding, saturated soils and late planting, "flood" (51) river overflow, and hurricanes/tropical storms (46/47) bundle wind with water. The broad set mixes all of these, and 31+51 drops hurricane-coded water damage.
- **Liability denominators** are annual and county-wide (individual plans, all crops), so monthly ratios divide one month's losses by the whole season's exposure; "all crops" includes nursery and dollar plans whose exposure is not weather-by-month (the row-crop variant checks this).
- **FEMA maps:** the NFHL is today's effective map, of mixed vintage (newest FIRM panel per county: median 2022, range 2008–2026; see `data/fork1/flood_prone_share.csv`), drawn for insurance on structures and mostly along mapped streams. It misses small-ditch and field ponding, which FINDINGS §20 suggests drives most NJ water losses. Zone A (approximate) and AE (detailed) are pooled.
- **Static share:** one CDL year (2023) and one map for 2003–2025; cropland moved and maps were redrawn over the period. The CDL "cropland" mask includes hay, which dominates upland VA. Shares are cropland shares, not insured-acre shares.
- **Cross-county identification:** b2 compares floodplain-heavy with floodplain-light counties. Anything else that differs between them and also changes the rain response (soils and drainage tile, crop mix, coastal hurricanes, insurance take-up) loads onto b2. County FE absorb levels, not slopes. The state × year and coastal-plain variants are partial checks only.
- **Dollar weighting:** PPML weights county-months by their dollars. North Carolina holds 86% of the broad water indemnity and 61% of the liability, so the pooled estimate is largely an NC estimate; the "without North Carolina" row shows the rest (and is much less precise).
- **PRISM** recent months use a newer dataset (AN91) than earlier ones (AN81); year FE absorb a common shift, not county-specific ones.
- **2003 start:** RMA Cause of Loss has no year of loss before commodity year 2003.

## Bottom line

Across 236 insured counties in five states, monthly rain strongly predicts water losses (+100 mm ≈ +145%), but the rain response is NOT detectably larger where more cropland lies in the FEMA 1% floodplain (b2 = +0.01 ± 0.35, p = 0.97; no variant reaches p < 0.05). The test is weak: only an effect of about b2 ≈ 1.03 (+16% in the per-100-mm response between a 10th- and a 90th-percentile FloodShare county) would be detected reliably, so a modest flood amplification cannot be ruled out. A sharper test needs a flood measure that varies month to month (modelled or observed inundation, e.g. SFINCS or satellite flood maps) instead of a fixed map share.
