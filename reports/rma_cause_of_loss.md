# RMA Cause of Loss: can we build the loss data ourselves?

Checked 2026-10-02. Data: `data/rma/colsom_<year>_NJ.csv` from `scripts/fetch_rma_col.py`
(all 38 commodity years 1989–2026; NJ rows only, 1.8 MB). Collaborators' sample: `data/insurance/insurance.csv`
(read locally only; no sample values are quoted here, only match statistics).

**Bottom line.** The sample is RMA's public Cause of Loss file. It is aggregated to county × year-of-loss ×
month-of-loss for commodity years 2022–2025, and `indemnity_wet` is exactly cause codes **31 + 51**. We can
rebuild it ourselves, back to 1989, and add the crop, cause, insurance plan and stage (prevented planting)
detail the sample leaves out. RMA's Summary of Business supplies the liability, premium and acres that
normalize it. All of this is public and pipe-delimited, and nothing needs to be requested.

## 1. Source

| what | where |
|---|---|
| Landing page | https://www.rma.usda.gov/tools-reports/summary-of-business/cause-loss ("Cause of Loss Historical Data Files"; returned HTTP 500 to scripts on 2026-10-02, but the file server below works) |
| Files | https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/cause_of_loss/colsom_YYYY.zip, **1989–2026** (2026 is partial). One national pipe-delimited `.txt` per commodity year, no header, 40–50 MB unzipped. |
| Record layout | `COL_Summary_of_Business_with_Month_All_Years.pdf` (same directory, "as of 5/28/2026"; copied to `data/rma/`) |
| Stage codes | `Stage_Code_Listing.pdf` / `.xlsx` (same directory; copied to `data/rma/`) |
| Vintage | 1989–2020 posted 2025-04-09; 2021 posted 2025-11-24; **2022–2026 re-posted 2026-09-28**. Recent years are revised as claims settle, so re-fetch them with `--refresh`. |

The server directory has only `colsom_*` (COL **with month**) files. The older month-less summary versions are
not on it. The same month detail goes back to 1989, so nothing is lost.

**Layout (30 fields, `|`-delimited):** commodity year · state code · state abbr · county code · county name ·
commodity code · commodity name · insurance plan code · plan abbr · coverage category (A buy-up / C CAT /
E / L) · **stage code** · **cause of loss code** · cause description · **month of loss** · month name ·
**year of loss** · policies earning premium · policies indemnified · net planted quantity · net endorsed acres ·
liability · total premium · producer-paid premium · subsidy · state/private subsidy · additional subsidy ·
EFA premium discount · net determined quantity (acres etc. lost) · **indemnity** (signed) · loss ratio.

- **Month of loss** is the month the loss occurred, and **year of loss** is its calendar year. The commodity year
  is the policy (harvest) year, and the two differ for up to 18% of NJ rows in a year from 2003 on (fall-seeded wheat and barley,
  late losses). Before 2003 `year_of_loss` is blank, so only commodity year + month is known.
  Month 0 means unknown: 64 rows in the study counties, $0.31 M, almost all 1989–1990.
- **Stage** is included. Prevented planting is identifiable (stages P, P1–P4, P2, PF, PT, PP, NP). In the study
  counties, PP paid $2.24 M, and $1.44 M of that was excess-moisture PP (wheat and soybeans mostly).
- Rows exist only where a loss is recorded. The liability and premium on a COL row cover those units, not the
  county's whole book, so denominators must come from the Summary of Business (§5).
- A county code **999 "All Other Counties"** pseudo-county exists (2–9 NJ rows per year).

**Cause-of-loss codes** (national 2022–2025 files): 01 Decline in Price · 09 Asian Soybean Rust · 11 Drought ·
12 Heat · 13/14/15 irrigation failures · 21 Hail · 22 Excess Sun · **31 Excess Moisture/Precipitation/Rain** ·
41 Frost · 42 Freeze · 43 Cold Winter · **44 Cold Wet Weather** · 45 Insufficient Chilling Hours ·
**46 Tropical Storm · 47 Hurricane · 51 Flood · 52 Low Salinity Caused by Excessive Rainfall** ·
55 ARPI/SCO/ECO/STAX/MP/PACE (area plans; cause not attributed) · 58 Post Bloom Fruit Drop · 61 Wind/Excess Wind ·
62 Hot Wind · 63 Cyclone · 64 Tornado · 66 Oxygen Depletion · **67 Storm Surge** · 71 Insects · 74 Ice Flow ·
76 Salinity · 80 Disease (aquaculture) · 81 Plant Disease · 82 Mycotoxin · 85/86 ordered destruction / quarantine ·
87 Falling Numbers · 89 Smoke · 91 Fire · **92 Hurricane/Tropical Depression** · 93 Wildlife · 95 House burn ·
97 Earthquake · 98 Volcanic Eruption · 99 Other (Snow, Lightning, Etc.) · XX All Other Causes.
Descriptions are blank in some early files, and the code-55 wording changes by year.

Water-related: **31, 51** (the sample's definition). A broad set adds **44, 46, 47, 52, 67, 92**.
Of these, the NJ study counties only ever show 31, 44, 51 and 92.

## 2. Comparison with the collaborators' sample (2022–2025)

The test aggregates COL indemnity by fips × **year_of_loss** × month_of_loss over commodity years 2022–2025 and
joins the result to the sample.

| test | cells matching to < $1 |
|---|---|
| 5 NJ counties (33/11/15/01/09), all causes, keyed on **commodity year** | 188 / 240 |
| 5 NJ counties, all causes, keyed on **year of loss** | **235 / 240** |
| National, all causes (year of loss) | 148,815 / 149,232 |
| National, `indemnity_wet` vs code 31 only | 146,947 |
| National, `indemnity_wet` vs **31 + 51** | **149,133 / 149,232** |
| National, 31 + 51 + 92 / + 44 / + 46 + 47 + 92 | 148,082 / 141,144 / 147,589 |

- **The sample is derived from COL.** "year, month" are the **year and month of loss**, and the sample is limited to
  commodity years 2022–2025.
- **`indemnity_wet` = Excess Moisture/Precipitation/Rain (31) + Flood (51).** It excludes Cold Wet Weather (44),
  Hurricane/Tropical Storm/Depression (46/47/92) and Storm Surge (67). For NJ in 2022–2025 only code 31 occurs.
- Every one of the 99 national wet-mismatch cells is also an all-cause mismatch (2025: 88, 2024: 11). That pattern
  points to the 2026-09-28 re-posting (claims revised after the sample was pulled) rather than a definitional
  difference. The 5 NJ mismatches have two causes:
  - commodity-2021 area-plan (code 55) payments made in Feb 2022, which the sample excludes because it starts at
    commodity year 2022;
  - commodity-2026 wheat losses in Nov/Dec 2025 (drought, code 11), which the sample excludes because it ends at
    commodity year 2025.
- **Negatives and wet > total are in COL itself.** Indemnity is a signed field (S9(12)). 9,288 of 572,187 national
  2022–25 rows are negative (corrections or overpayment recoveries, mostly stage H/UH). COL aggregated as above
  gives exactly the sample's 89 negative-total cells, 91 negative-wet cells and 108 wet > total cells, the same 108.
  wet > total happens when other causes net negative in that cell.
- **Cape May all zeros.** COL has no Cape May (34009) rows after commodity year 2006 (7 small rows in 1995–2006),
  and the 2024 Summary of Business has no Cape May rows either. The sample is a complete county × month panel
  zero-filled where COL has nothing, so Cape May is all zeros. Any insured Cape May business may be reported
  under NJ county 999 "All Other Counties", but the public files can't show that.
  Separately, the sample has 3,109 counties against 2,906 fips in COL, and it drops the 999 pseudo-counties.

## 3. Study counties (Salem, Cumberland, Gloucester), all years 1989–2026

There are 2,649 COL rows and $52.0 M of all-cause indemnity. Water losses total $8.53 M under the broad set
(16%) and $7.73 M under 31 + 51 (15%).

| county | all-cause $ | water (broad) $ | 31+51 $ | water share |
|---|---|---|---|---|
| Salem | 21,365,516 | 3,930,091 | 3,641,416 | 0.18 |
| Gloucester | 16,682,410 | 2,129,615 | 1,855,176 | 0.13 |
| Cumberland | 13,955,570 | 2,468,439 | 2,228,764 | 0.18 |

**Water losses by cause** ($; rows > 0):

| cause | Cumberland | Gloucester | Salem | rows |
|---|---|---|---|---|
| 31 Excess Moisture/Precip/Rain | 2,228,764 | 1,853,305 | 3,641,409 | 570 |
| 44 Cold Wet Weather | 224,110 | 237,263 | 160,164 | 76 |
| 92 Hurricane/Tropical Depression | 15,565 | 37,176 | 128,512 | 17 |
| 51 Flood | 0 | 1,871 | 7 | 2 |

All causes: Drought 49%, Excess Moisture 15%, Heat 12%, Freeze 11% (peaches/apples), Hail 4%, Price 2%, Wildlife 2%.

**By crop.** A "cell" is a county × year-of-loss × month × crop with water (broad) indemnity > 0:

| crop | all-cause $ | water $ | water share | cells, all years | 2003+ | 2015+ |
|---|---|---|---|---|---|---|
| Corn | 18,222,706 | 2,083,639 | 0.11 | 105 | 97 | 55 |
| Soybeans | 18,173,984 | 2,296,899 | 0.13 | 133 | 128 | 69 |
| Peaches | 7,878,660 | 323,203 | 0.04 | 15 | 10 | 7 |
| Wheat | 2,687,782 | 1,490,285 | 0.55 | 97 | 94 | 49 |
| All Other Crops | 1,675,984 | 539,996 | 0.32 | 22 | 15 | 12 |
| Tomatoes | 1,346,957 | 1,129,714 | 0.84 | 20 | 18 | 10 |
| Apples | 1,293,545 | 297,109 | 0.23 | 20 | 19 | 11 |
| Processing Beans | 307,953 | 149,393 | 0.49 | 17 | 15 | 8 |
| Winter Squash | 306,907 | 145,705 | 0.47 | 15 | 12 | 0 |
| Barley | 109,018 | 72,203 | 0.66 | 21 | 20 | 9 |

Water cells by county: soybeans 30 / 34 / 69 (Cumberland / Gloucester / Salem), corn 16 / 35 / 54, wheat 28 / 22 / 47.
Apples are Gloucester only (20), and tomatoes Cumberland 13 / Salem 7.

**By month of loss** (water $, cells): Jan 30,762 (5) · Feb 54,822 (10) · Mar 138,723 (21) · Apr 274,544 (19) ·
May 753,351 (71) · **Jun 2,199,015 (102)** · Jul 1,611,779 (76) · Aug 1,156,481 (49) · Sep 1,251,094 (38) ·
Oct 335,760 (21) · Nov 449,422 (32) · Dec 44,029 (7) · unknown 228,362 (14).
All-cause losses instead peak in July and August (drought).

**Big water years** ($ broad, year of loss): 2013 1.39 M · 2018 1.41 M · 2011 0.73 M · 2023 0.63 M ·
2020 0.56 M · 2003 0.54 M · 2019 0.51 M · 2025 0.43 M. None in 1991 or 1993–1997.

**Sample size.**
- **465** county × month × crop cells with water losses over all years: 428 since 2003 (year of loss known) and
  **230 since 2015** (the MRMS era).
- At county × month (crops pooled): 277 cells, 251 since 2003.
- Soybeans, corn and wheat make up ~72% of the cells. Every other crop has 20 or fewer cells per crop over 37 years,
  too few for crop-specific models.
- **80% of water cells involve only 1–2 indemnified policies.** Cell values are single-claim noisy, so a
  frequency or loss-ratio framing (normalized by SOB liability) is more stable than raw dollars.

## 4. Related public sources (not downloaded in bulk)

- **RMA Summary of Business, state/county/crop**
  ([directory](https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/state_county_crop/);
  [web tool](https://public-rma.fpac.usda.gov/apps/SummaryOfBusiness)).
  - `sobcov_YYYY.zip` covers **1989–2027**, pipe-delimited, 28 fields: county × commodity × plan × coverage category
    × delivery type × **coverage level**, with policies sold/earning/indemnified, units, quantity type,
    **net reported acres**, endorsed acres, **liability**, total premium, subsidies and indemnity.
  - `sobtpu_YYYY.zip` covers **1999–2027** and adds commodity **type, practice** (e.g. irrigated) and unit structure.
  - `sobscc_1948_1988.zip` covers 1948–1988.
  - Layouts: `SOB_State_County_Crop_with_Coverage_Level_1989_Forward.pdf`, `SOBTPU_External_All_Years.pdf`.
  - This is the denominator for indemnity: liability, premium and acres by county × crop × year (annual, no month).
  - The 2024 file has 357 NJ rows. Study-county liability that year was corn $13.6 M, soybeans $12.8 M,
    peaches $5.5 M, wheat $3.3 M, tomatoes $3.1 M.
- **FSA Crop Acreage Data**
  ([page](https://www.fsa.usda.gov/tools/informational/freedom-information-act-foia/electronic-reading-room/frequently-requested/crop-acreage-data)).
  - Zipped xlsx (~20 MB per release, several releases per year, Aug–Jan), crop years **2007–2026**
    (county × crop from ~2009).
  - Sheets `plant_and_fail`, `prevent`, `county_summary`, `crop_summary`, `county_data`, `all_farm_count`.
  - Gives planted, failed and **prevented-planted acres** by state × county × crop (× type, intended use, irrigation
    practice). It is annual, not monthly, and covers all FSA-reporting farms whether or not they are insured.
- **Field-, policy- or unit-level RMA data** is not public.
  - FCIA §502(c) (7 U.S.C. 1502(c)) bars disclosure of producer-furnished information unless it is in "statistical
    or aggregate form" that cannot identify a producer, or the producer consents. 7 U.S.C. 8791 (2008 Farm Bill
    §1619) adds protection for geospatial data, with an exception for persons "working in cooperation with the
    Secretary."
  - FOIA requests ([RMA FOIA](https://www.rma.usda.gov/about-rma/website-policies-important-links/foia)) cannot
    reach unit-level records. rma.usda.gov publishes no standing researcher-access program.
  - The route researchers use is a **cooperative or research agreement with RMA (or with ERS or another USDA agency
    holding the data) plus signed non-disclosure statements.** Results can then be published only in aggregate.
  - A lighter ask is a **custom aggregate tabulation** that RMA can release under the aggregate exception, e.g.
    county × crop × month × cause × practice, or sub-county units such as HUC12 where cell sizes allow.
  - The Rutgers ag-econ collaborators are the natural requesters. Contact goes through RMA's Office of Strategic
    Data Acquisition & Analysis or the RMA regional office (Raleigh covers NJ). We could not confirm a named
    intake address on the website.

## 5. Recommendation

1. **Use COL directly instead of the sample.** It is the same numbers, it is public, it goes back to 1989
   (2003+ with a calendar year of loss), and it carries crop, cause, stage and plan. The sample adds only PRISM
   precipitation, which we compute anyway. Treat the sample as a validated subset. To reproduce `indemnity_wet`,
   use codes 31 + 51 keyed on year/month of loss.
2. **Decide the wet definition explicitly.** In these counties, Cold Wet Weather (44, $0.62 M) and
   Hurricane/Tropical Depression (92, $0.18 M, e.g. Irene/Sandy-era) are water-driven too. Run both 31+51 and the
   broad set.
3. **Normalize with Summary of Business liability** (`sobcov`, or `sobtpu` for practice) by county × crop × year.
   A natural target is a monthly loss-cost ratio = water indemnity / annual liability. A fetch script analogous to
   this one would add ~1 MB of NJ rows.
4. **Crop-level analysis only for soybeans, corn and wheat** (~100–130 cells each over all years, ~50–70 since
   2015). Pool everything else. Use stage-coded prevented planting as a separate early-season flood signal.
5. **Unit-level or sub-county data only if county × month proves too coarse.** Ask the collaborators to request a
   custom aggregate or a data agreement from RMA. Months to arrange, but it is the only route to sub-county
   attribution against SFINCS flood maps.
