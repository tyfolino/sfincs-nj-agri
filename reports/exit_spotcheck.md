# NAIP check of Landsat-detected exits from farming (120 m cells, 2026-10-05)

Exits from `scripts/field_history.py --tag cells` (the CDL-cropland target). The check is
`scripts/exit_spotcheck.py --tag cells`, with contact sheets in
`reports/figs/exit_spotcheck_cells_{1..3}.png`. Samples are 18 per stratum, drawn at random
and area-weighted from exits in 2010-2019. The NAIP chip before is the latest at or before
the exit; the chip after is at least 3 years later. Judged by eye (Claude).

| Verdict | Low (< MHHW + 0.6 m) | Upland (> MHHW + 3 m) |
|---|---|---|
| **Real exit to marsh / scrub / old field** | **7** (L02 L06 L07 L10 L15 L16 L17) | **2** (U29 U31) |
| Real exit to development (often mistimed) | 0 | 4-5 (U24 hospital, U25, U26, U33 housing, U32 warehouse) |
| Ambiguous | 3 (L03 L05 L12) | 0 |
| Still farmed (false exit) | 3 (L00 L01 L13) | 4 (U21 U22 U23 nursery and field, U35 sports field) |
| Not farmland before either (false) | 5 (L04 L08 L09 L11 L14: marsh, grass, sand) | 6 (U18 U19 U27 U34 woods, U20 old field, U28 yard) |

- **Precision for exits to vegetation:** low ground 7-10 / 18 (39-56%); upland 2 / 16 (~12%).
  On upland the "vegetated" exits flagged by post-exit NDVI include leafy subdivisions.
- **Where farmland goes depends on height.** Low-lying fields go to marsh and scrub; upland
  fields go mostly to development (Gloucester suburbs), or the exit is a misread of woods.
- **The classifier's main confusions:**
  - hay vs abandoned grass (CDL itself labels abandoned grassy fields "Other Hay");
  - LU/LC "farm" polygons that include woods, yards and marsh.
  
  A cleaner next version would train a multi-class model (row crop / hay-grass / marsh / woods /
  developed) on NJDEP LU/LC's photo-interpreted classes rather than on CDL.
