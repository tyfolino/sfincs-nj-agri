# NAIP spot-check of NJDEP LU/LC farm → wetland (2026-10-05)

Samples: `scripts/lulc_spotcheck.py` → `data/imagery/lulc_samples.csv`; contact sheets
`reports/figs/lulc_spotcheck_{1..4}.png`. These are area-weighted random draws from
`data/landuse/farm_wetland_transitions.gpkg`. Each NAIP chip is 600 m wide with the polygon
outlined. Before | after imagery is 2010 | 2013 for 2007-12 and 2015 | 2023 for 2015-20.
Judged by eye (Claude). For big polygons only the chip's part is seen.

## C: LU/LC says farm → wetland (24 polygons, 2007-12 and 2015-20)

| Verdict | n | Samples |
|---|---|---|
| Out of farming afterwards (shrub, wet meadow, woods, marsh) | 18 | C00 C01 C03 C05 C06 C07 C08 C11 C13 C14 C15 C16 C17 C18 C20 C22 C23, C10 (weak) |
| Dug stormwater pond at a new warehouse (code 5300): development, not wetland | 2 | C02 C09 → code 5300 now its own class, out of the outcome |
| Unclear / still looks farmed or yard | 4 | C04 C12 C19 C21 |

- LU/LC's conversions are mostly real, but **most are not tidal**. They are small, wet,
  marginal strips and fields left to old-field succession (class 2150), many well inland
  (> 3 m above MHHW).
- The tidal ones sit at marsh edges or behind banks: C07, C08, C13, C15, C18.

## O: LU/LC says still farmed in 2015 AND 2020, ground below MHHW + 1 m (24 polygons)

| Verdict | n | Samples |
|---|---|---|
| Still farmed in 2023 | 16 | O24 O25 O27 O28 O30-O37 O39 O42 O43 O44 |
| **Looks converted to marsh / abandoned by 2023: missed by LU/LC** | **4** | **O29** (Elsinboro: tidal creeks in 2023), **O38** and **O46** (Greenwich-south / "Durham": the §21 site), **O45** (Salem, 78% leveed) |
| Developed (warehouse construction) | 1 | O26 |
| Never really cropland (grass strips) | 3 | O40 O41 O47 |

- **LU/LC 2020 undercounts recent low-lying conversion.** About 4/24 (17%, CI 5-37%) of the
  low "still farmed" area looks marsh or abandoned by 2023. Of the 3,646 ha LU/LC calls farmed
  below MHHW + 1 m in 2015-20, that would be ~600 ha (~180-1,350 ha). LU/LC itself finds only
  ~90 ha of farm → wetland in all of 2015-20.
- The undercount comes from class 2140 "agricultural wetlands (modified)", which stays put after
  farming stops. The Greenwich-south fields (dead by 2017, bare and channelled by 2019) are still
  2140 in LU/LC 2020. Part of the gap may also be 2020-23 change that LU/LC 2020 could not see.

## So, three sources and their biases

| Source | Bias | Evidence |
|---|---|---|
| CDL (30 m, annual) | **Over-counts** ~3× (edge pixels, early-year labels); timing jumps at product refreshes | `reports/imagery_spotcheck.md` |
| NJDEP LU/LC (photo-interpreted, 5 editions) | Mostly right when it says "converted", but those are mostly inland old fields. **Under-counts** recent low-lying, tidal conversions (sticky 2140) | this report |
| NAIP imagery (1 m, 2010-2023) | The truth for "farmed or not", not for the cause | — |

**For the outcome:** use LU/LC to find candidates and as an independent historical record
(1995-2012). Then **map low-lying 2140 / farmed polygons field by field on NAIP** (2010,
2013, 2015, 2017, 2019, 2022, 2023) to date when each stopped being farmed. There are a few
hundred polygons below MHHW + 1 m, which is feasible.
