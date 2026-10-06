# Run comparison: sep2023 (focus 2023-09)

Runs: `v1_100m/sep2023`, `v1_100m/sep2023_evap`, `v1_100m/sep2023_evap2`

## Tidal gauges (hourly water level, m)

| name | metric | v1_100m/sep2023 | v1_100m/sep2023_evap | v1_100m/sep2023_evap2 |
|---|---|---|---|---|
| Maurice River at Bivalve NJ | rmse_m | 0.106 | 0.106 | 0.106 |
| Maurice River at Bivalve NJ | bias_m | 0.027 | 0.027 | 0.027 |
| Maurice River at Bivalve NJ | r_demeaned | 0.991 | 0.991 | 0.991 |
| Cohansey River at Greenwich NJ | rmse_m | 0.335 | 0.333 | 0.333 |
| Cohansey River at Greenwich NJ | bias_m | 0.148 | 0.145 | 0.145 |
| Cohansey River at Greenwich NJ | r_demeaned | 0.912 | 0.912 | 0.912 |
| Alloway Creek at Hancocks Bridge N | rmse_m | 0.360 | 0.359 | 0.359 |
| Alloway Creek at Hancocks Bridge N | bias_m | 0.099 | 0.097 | 0.097 |
| Alloway Creek at Hancocks Bridge N | r_demeaned | 0.787 | 0.787 | 0.787 |

## Stream gauges (stage; rise_ratio = modelled / observed rise)

| name | metric | v1_100m/sep2023 | v1_100m/sep2023_evap | v1_100m/sep2023_evap2 |
|---|---|---|---|---|
| Maurice River at Norma NJ | r_demeaned | 0.730 | 0.610 | 0.670 |
| Maurice River at Norma NJ | rise_ratio | 0.040 | 0.130 | 0.130 |
| Maurice River at Norma NJ | peak_lag_h | -284.000 | -284.000 | -284.000 |
| Menantico Creek near Millville NJ | r_demeaned | 0.770 | 0.700 | 0.720 |
| Menantico Creek near Millville NJ | rise_ratio | 0.650 | 0.460 | 0.460 |
| Menantico Creek near Millville NJ | peak_lag_h | 31.000 | -270.000 | -270.000 |
| Manumuskin River at Cumberland NJ | r_demeaned | 0.820 | 0.780 | 0.770 |
| Manumuskin River at Cumberland NJ | rise_ratio | 1.220 | 1.520 | 1.530 |
| Manumuskin River at Cumberland NJ | peak_lag_h | -277.000 | -277.000 | -277.000 |
| Cohansey River at Seeley NJ | r_demeaned | 0.750 | 0.720 | 0.730 |
| Cohansey River at Seeley NJ | rise_ratio | 1.670 | 1.880 | 1.900 |
| Cohansey River at Seeley NJ | peak_lag_h | -46.000 | -45.000 | -46.000 |
| Mantua Creek at East Holly Avenue  | r_demeaned | 0.910 | 0.900 | 0.900 |
| Mantua Creek at East Holly Avenue  | rise_ratio | 0.990 | 0.940 | 0.950 |
| Mantua Creek at East Holly Avenue  | peak_lag_h | -3.000 | -3.000 | -3.000 |
| Raccoon Creek at Wrights Mill NJ | r_demeaned | 0.740 | 0.570 | 0.580 |
| Raccoon Creek at Wrights Mill NJ | rise_ratio | 0.730 | 0.770 | 0.770 |
| Raccoon Creek at Wrights Mill NJ | peak_lag_h | 5.000 | 5.000 | 5.000 |
| Raccoon Creek near Swedesboro NJ | r_demeaned | 0.600 | 0.470 | 0.480 |
| Raccoon Creek near Swedesboro NJ | rise_ratio | 0.490 | 0.610 | 0.610 |
| Raccoon Creek near Swedesboro NJ | peak_lag_h | 9.000 | -440.000 | -439.000 |
| Salem River at Woodstown NJ | r_demeaned | 0.760 | 0.720 | 0.720 |
| Salem River at Woodstown NJ | rise_ratio | 8.830 | 8.050 | 8.170 |
| Salem River at Woodstown NJ | peak_lag_h | -3.000 | -2.000 | -2.000 |

## Cropland wet > 5 cm in the focus period (km², km²·days)

| county | metric | v1_100m/sep2023 | v1_100m/sep2023_evap | v1_100m/sep2023_evap2 |
|---|---|---|---|---|
| Cumberland | peak_km2 | 1.60 | 1.31 | 1.32 |
| Cumberland | area_days | 17.93 | 11.34 | 11.52 |
| Cumberland | persistent_km2 | 0.15 | 0.10 | 0.10 |
| Gloucester | peak_km2 | 0.79 | 0.73 | 0.75 |
| Gloucester | area_days | 6.45 | 3.28 | 3.40 |
| Gloucester | persistent_km2 | 0.03 | 0.02 | 0.02 |
| Salem | peak_km2 | 4.14 | 3.79 | 3.83 |
| Salem | area_days | 44.30 | 25.69 | 26.25 |
| Salem | persistent_km2 | 0.26 | 0.18 | 0.18 |

## Check valves

| index | v1_100m/sep2023 | v1_100m/sep2023_evap | v1_100m/sep2023_evap2 |
|---|---|---|---|
| drained (hm³ = 10⁶ m³) | 7.499 | 6.427 | 6.481 |
| valves passing > 1000 m³ | 19.000 | 12.000 | 12.000 |
| valves | 23.000 | 23.000 | 23.000 |

