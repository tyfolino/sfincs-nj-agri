# Imagery spot-check of the CDL "cropland → wetland" signal (2026-10-05)

Samples and chips: `scripts/imagery_spotcheck.py` → `data/imagery/spotcheck_samples.csv`,
contact sheets `reports/figs/imagery_spotcheck_{1..4}.png`, site time series
`reports/figs/imagery_sites.png`. Imagery: NAIP (USDA, public domain), summer 2010 vs 2023.
Judged by eye (Claude), one 30 m pixel per sample in a 240 m chip.

**Population:** pixels below recent MHHW + 1 m that CDL calls cropland in ≥ 3 of 2008-12 and
wetland in ≥ 2 of 2023-25: **4.42 km²**. 36 drawn at random (area-weighted); 12 controls drawn
from the 17.85 km² of low pixels CDL calls cropland throughout.

## Verdicts

| Verdict | n / 36 | Samples |
|---|---|---|
| **Real: cropped field in 2010, marsh / wet scrub / abandoned in 2023** | **12** | X00 X02 X03 X04 X05 X07 X08 X15 X19 X20 X22 X30 |
| Edge pixel: straddles a field edge and existing marsh / woods; field still there | 13 | X01 X06 X12 X16 X17 X18 X21 X24 X27 X29 X32 X33 X35 |
| Not cropland in 2010 either (yard, old field, nursery woods, marsh): CDL's early label wrong | 9 | X09 X10 X11 X13 X23 X25 X26 X28 X34 |
| Still farmed in 2023 / can't tell | 2 | X14 X31 |
| Controls that are cropland in both years | 12 / 12 | K36-K47 |

- **About a third of the signal is real:** 12/36 = 33% (95% binomial CI 19-51%), i.e. ~1.5 km²
  (0.8-2.2 km², ~370 ac) of 2008-12 cropland below MHHW + 1 m left production for marsh or
  scrub by 2023. The rest is CDL noise: mixed pixels at field/marsh edges, and early-year
  labels. The low-lying "cropland" CDL keeps throughout is reliable (12/12).
- **CDL's timing can't be trusted.** Many switches fall exactly in 2019 or 2024, the years
  the CDL's non-crop classes were refreshed (and 2024 cropland drops in every height band, upland
  too: `reports/bayshore_exposure.md`). Date changes from imagery, not CDL.
- **Imagery can't give the cause.** It cannot tell salt from waterlogging, abandonment,
  purchase for conservation or deliberate restoration.
  - X05/X08 (Logan Twp, Raccoon Creek, Gloucester) were excavated in 2013-19 and are now
    channelled marsh: almost certainly an engineered wetland (mitigation or restoration), not
    passive intrusion.
  - The real samples cluster. X00, X02, X07 and X20, plus X15 nearby, are one site.

## The Greenwich-south site (Cumberland, ~39.352 N 75.293 W)

This is the clearest case: a diked field complex next to the NLD "Durham" levee system, near the Dix
Wildlife Management Area (`reports/figs/imagery_sites.png`, top row).

| Year | What the imagery shows |
|---|---|
| 2010, 2013 | Rectangular fields farmed inside the bank, ringed by marsh |
| 2017 | Grey-brown die-off across the northern and eastern fields |
| 2019 | A large bare / dead patch in the north-west cell with a channel network cutting into it. That is the look of tidal water let in through a breach or failed gate |
| 2023 | Almost all of it is uniform marsh; only the fields by the farmstead remain |

The sequence (dieback 2013-17, bare ground and channels by 2019, marsh by 2023) fits a
meadow-bank breach or gate failure, possibly after Sandy (October 2012). It is also consistent
with a planned restoration. **Ownership and management history is the next thing to check
before calling it saltwater intrusion.**

## Implication

There is a real, if small, loss of low-lying bayshore cropland to marsh: ~1.5 km² in ~15 years,
some of it in the form of whole diked fields going over. That is the kind of event SFINCS can
represent: a failed bank or gate letting the tide in. CDL alone overstates the loss about
threefold and mistimes it. Any land-change outcome for the econ side should be built from
imagery-checked, field-level transitions rather than raw CDL pixels.
