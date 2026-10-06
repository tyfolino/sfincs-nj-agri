# Run comparison: sep2023 (focus 2023-09)

Runs: `v1_100m/sep2023`, `v1_100m/sep2023_gv2`, `v1drained_100m/sep2023`

## Tidal gauges (hourly water level, m)

| name | metric | v1_100m/sep2023 | v1_100m/sep2023_gv2 | v1drained_100m/sep2023 |
|---|---|---|---|---|
| Maurice River at Bivalve NJ | rmse_m | 0.106 | 0.106 | 0.106 |
| Maurice River at Bivalve NJ | bias_m | 0.027 | 0.027 | 0.027 |
| Maurice River at Bivalve NJ | r_demeaned | 0.991 | 0.991 | 0.991 |
| Cohansey River at Greenwich NJ | rmse_m | 0.335 | 0.335 | 0.335 |
| Cohansey River at Greenwich NJ | bias_m | 0.148 | 0.148 | 0.148 |
| Cohansey River at Greenwich NJ | r_demeaned | 0.912 | 0.912 | 0.912 |
| Alloway Creek at Hancocks Bridge N | rmse_m | 0.360 | 0.360 | 0.360 |
| Alloway Creek at Hancocks Bridge N | bias_m | 0.099 | 0.099 | 0.099 |
| Alloway Creek at Hancocks Bridge N | r_demeaned | 0.787 | 0.787 | 0.787 |

## Stream gauges (stage; rise_ratio = modelled / observed rise)

| name | metric | v1_100m/sep2023 | v1_100m/sep2023_gv2 | v1drained_100m/sep2023 |
|---|---|---|---|---|
| Maurice River at Norma NJ | r_demeaned | 0.730 | 0.730 | 0.750 |
| Maurice River at Norma NJ | rise_ratio | 0.040 | 0.040 | 0.020 |
| Maurice River at Norma NJ | peak_lag_h | -284.000 | -284.000 | -160.000 |
| Menantico Creek near Millville NJ | r_demeaned | 0.770 | 0.770 | 0.810 |
| Menantico Creek near Millville NJ | rise_ratio | 0.650 | 0.650 | 0.490 |
| Menantico Creek near Millville NJ | peak_lag_h | 31.000 | 31.000 | -270.000 |
| Manumuskin River at Cumberland NJ | r_demeaned | 0.820 | 0.820 | 0.770 |
| Manumuskin River at Cumberland NJ | rise_ratio | 1.220 | 1.220 | 1.010 |
| Manumuskin River at Cumberland NJ | peak_lag_h | -277.000 | -277.000 | -277.000 |
| Cohansey River at Seeley NJ | r_demeaned | 0.750 | 0.750 | 0.740 |
| Cohansey River at Seeley NJ | rise_ratio | 1.670 | 1.670 | 1.640 |
| Cohansey River at Seeley NJ | peak_lag_h | -46.000 | -46.000 | -46.000 |
| Mantua Creek at East Holly Avenue  | r_demeaned | 0.910 | 0.910 | 0.910 |
| Mantua Creek at East Holly Avenue  | rise_ratio | 0.990 | 0.990 | 0.970 |
| Mantua Creek at East Holly Avenue  | peak_lag_h | -3.000 | -3.000 | -3.000 |
| Raccoon Creek at Wrights Mill NJ | r_demeaned | 0.740 | 0.740 | 0.710 |
| Raccoon Creek at Wrights Mill NJ | rise_ratio | 0.730 | 0.730 | 0.630 |
| Raccoon Creek at Wrights Mill NJ | peak_lag_h | 5.000 | 5.000 | 6.000 |
| Raccoon Creek near Swedesboro NJ | r_demeaned | 0.600 | 0.600 | 0.590 |
| Raccoon Creek near Swedesboro NJ | rise_ratio | 0.490 | 0.490 | 0.480 |
| Raccoon Creek near Swedesboro NJ | peak_lag_h | 9.000 | 9.000 | 10.000 |
| Salem River at Woodstown NJ | r_demeaned | 0.760 | 0.760 | 0.740 |
| Salem River at Woodstown NJ | rise_ratio | 8.830 | 8.830 | 7.980 |
| Salem River at Woodstown NJ | peak_lag_h | -3.000 | -3.000 | 2.000 |

## Cropland wet > 5 cm in the focus period (km², km²·days)

| county | metric | v1_100m/sep2023 | v1_100m/sep2023_gv2 | v1drained_100m/sep2023 |
|---|---|---|---|---|
| Cumberland | peak_km2 | 1.60 | 1.60 | 1.53 |
| Cumberland | area_days | 17.93 | 17.80 | 17.36 |
| Cumberland | persistent_km2 | 0.15 | 0.15 | 0.15 |
| Gloucester | peak_km2 | 0.79 | 0.79 | 0.77 |
| Gloucester | area_days | 6.45 | 6.62 | 6.30 |
| Gloucester | persistent_km2 | 0.03 | 0.03 | 0.03 |
| Salem | peak_km2 | 4.14 | 4.10 | 3.93 |
| Salem | area_days | 44.30 | 42.27 | 42.93 |
| Salem | persistent_km2 | 0.26 | 0.23 | 0.26 |

## Check valves

| index | v1_100m/sep2023 | v1_100m/sep2023_gv2 | v1drained_100m/sep2023 |
|---|---|---|---|
| drained (hm³ = 10⁶ m³) | 7.499 | 2.935 | 7.426 |
| valves passing > 1000 m³ | 19.000 | 23.000 | 19.000 |
| valves | 23.000 | 25.000 | 23.000 |

