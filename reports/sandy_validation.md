# Sandy (2012) run vs observations

Run: `v1_100m/runs/sandy2012_intact_slr000` (dikes as built, today's sea level, tide only). Written by `scripts/validate_sandy.py`.

## High tides at the interior gauges

Each observed high tide (Oct 20 - Nov 4) vs the model's highest level within 3 h. **Both gauges are out from Oct 29 04:00 to Oct 31 04:00 UTC**, so Sandy's two peak tides are not observed: the highest recorded tide is the one before the gap.

| gauge | highs | mean_diff_m | rmse_m | top5_mean_diff_m |
|---|---|---|---|---|
| Cohansey River at Greenwich | 27 | -0.111 | 0.117 | -0.093 |
| Maurice River at Bivalve | 27 | -0.039 | 0.059 | -0.017 |

Sandy's peak itself, estimated from Ship John Shoal (observed peak 1.90 m NAVD88, Oct 30 04:00 UTC) plus each gauge's offset from Ship John on the two highest tides before the gap:

| index | offset from Ship John, m | estimated peak, m | highest observed (before the gap), m | model peak, m |
|---|---|---|---|---|
| Maurice River at Bivalve | -0.110 | 1.790 | 1.390 | 1.730 |
| Cohansey River at Greenwich | -0.220 | 1.680 | 1.290 | 1.680 |

## Flood footprint vs FEMA MOTF

MOTF interpolates a water surface from high-water marks over lidar, with no dikes: it is a check where nothing blocks the water; behind levees it is what a bathtub map would show. Model wet = peak depth > 0.05 m on 10 m pixels; MOTF's NJ-valid area only.

| index | km² scored | wet in both | MOTF only | model only | agree (of either wet) |
|---|---|---|---|---|---|
| ground 0-3 m NAVD88, not a field | 335.58 | 235.61 | 48.36 | 1.01 | 0.83 |
| farm fields, open to the tide | 637.54 | 4.17 | 14.69 | 0.01 | 0.22 |
| farm fields, behind an NLD levee | 6.18 | 0.74 | 4.32 | 0.00 | 0.15 |

Per field (flooded = at least 10% of the field wet):

| index | model dry | model flooded |
|---|---|---|
| open, MOTF dry | 10031 | 0 |
| open, MOTF flooded | 474 | 341 |
| behind levee, MOTF dry | 15 | 0 |
| behind levee, MOTF flooded | 137 | 42 |

The water level MOTF implies: ground height under its flood edge (m NAVD88), by 10 km band of UTM northing (4,340 = Bivalve, 4,370 = Greenwich, 4,400 = Gloucester's river front). A flat surface near the bay peak, carried up the creeks:

| northing, km | count | 25% | 50% | 75% |
|---|---|---|---|---|
| 4320 | 6,225.00 | 1.83 | 2.01 | 2.22 |
| 4330 | 2,057.00 | 1.66 | 1.82 | 1.94 |
| 4340 | 24,671.00 | 1.73 | 1.90 | 2.02 |
| 4350 | 16,508.00 | 1.59 | 1.96 | 2.24 |
| 4360 | 12,673.00 | 1.88 | 2.54 | 3.32 |
| 4370 | 7,240.00 | 1.47 | 1.86 | 2.15 |
| 4380 | 12,005.00 | 1.68 | 1.98 | 2.14 |
| 4390 | 13,916.00 | 1.55 | 1.95 | 2.14 |
| 4400 | 26,362.00 | 1.43 | 1.85 | 2.06 |
| 4410 | 8,633.00 | 1.44 | 1.87 | 2.16 |
