# Run comparison: may2025 (focus month 2025-05)

Runs: `v0_100m/may2025`, `v1dikes_100m/may2025`, `v1_100m/may2025`, `v1_100m/may2025_gatehi`

## Tidal gauges (hourly water level, m)

| name | metric | v0_100m/may2025 | v1dikes_100m/may2025 | v1_100m/may2025 | v1_100m/may2025_gatehi |
|---|---|---|---|---|---|
| Maurice River at Bivalve NJ | rmse_m | 0.098 | 0.097 | 0.119 | 0.119 |
| Maurice River at Bivalve NJ | bias_m | 0.015 | 0.016 | 0.023 | 0.023 |
| Maurice River at Bivalve NJ | r_demeaned | 0.993 | 0.994 | 0.990 | 0.990 |
| Cohansey River at Greenwich NJ | rmse_m | 0.526 | 0.514 | 0.371 | 0.371 |
| Cohansey River at Greenwich NJ | bias_m | 0.272 | 0.268 | 0.166 | 0.166 |
| Cohansey River at Greenwich NJ | r_demeaned | 0.747 | 0.764 | 0.905 | 0.905 |
| Alloway Creek at Hancocks Bridge N | rmse_m | 0.616 | 0.601 | 0.378 | 0.378 |
| Alloway Creek at Hancocks Bridge N | bias_m | 0.247 | 0.235 | 0.102 | 0.103 |
| Alloway Creek at Hancocks Bridge N | r_demeaned | 0.237 | 0.307 | 0.796 | 0.796 |

## Stream gauges (stage; rise_ratio = modelled / observed rise)

| name | metric | v0_100m/may2025 | v1dikes_100m/may2025 | v1_100m/may2025 | v1_100m/may2025_gatehi |
|---|---|---|---|---|---|
| Maurice River at Norma NJ | r_demeaned | 0.650 | 0.650 | 0.850 | 0.850 |
| Maurice River at Norma NJ | rise_ratio | 1.920 | 1.920 | 0.060 | 0.060 |
| Maurice River at Norma NJ | peak_lag_h | 93.000 | 93.000 | -29.000 | -29.000 |
| Manumuskin River at Cumberland NJ | r_demeaned | 0.750 | 0.750 | 0.750 | 0.750 |
| Manumuskin River at Cumberland NJ | rise_ratio | 0.530 | 0.530 | 2.960 | 2.960 |
| Manumuskin River at Cumberland NJ | peak_lag_h | 9.000 | 9.000 | -2.000 | -2.000 |
| Cohansey River at Seeley NJ | r_demeaned | 0.520 | 0.520 | 0.580 | 0.580 |
| Cohansey River at Seeley NJ | rise_ratio | 0.370 | 0.370 | 1.010 | 1.010 |
| Cohansey River at Seeley NJ | peak_lag_h | 335.000 | 335.000 | 341.000 | 341.000 |
| Mantua Creek at East Holly Avenue  | r_demeaned | 0.860 | 0.860 | 0.870 | 0.870 |
| Mantua Creek at East Holly Avenue  | rise_ratio | 0.620 | 0.620 | 0.660 | 0.660 |
| Mantua Creek at East Holly Avenue  | peak_lag_h | -1.000 | -1.000 | -3.000 | -3.000 |
| Raccoon Creek at Wrights Mill NJ | r_demeaned | 0.720 | 0.720 | 0.720 | 0.720 |
| Raccoon Creek at Wrights Mill NJ | rise_ratio | 0.230 | 0.230 | 0.410 | 0.410 |
| Raccoon Creek at Wrights Mill NJ | peak_lag_h | 11.000 | 11.000 | 11.000 | 11.000 |
| Raccoon Creek near Swedesboro NJ | r_demeaned | 0.560 | 0.560 | 0.530 | 0.530 |
| Raccoon Creek near Swedesboro NJ | rise_ratio | 0.190 | 0.190 | 0.590 | 0.590 |
| Raccoon Creek near Swedesboro NJ | peak_lag_h | -333.000 | -333.000 | -330.000 | -330.000 |
| Salem River at Woodstown NJ | r_demeaned | 0.310 | 0.310 | 0.290 | 0.290 |
| Salem River at Woodstown NJ | rise_ratio | 3.920 | 3.920 | 3.840 | 3.840 |
| Salem River at Woodstown NJ | peak_lag_h | -330.000 | -330.000 | -330.000 | -330.000 |

## Cropland wet > 5 cm in the focus month (km², km²·days)

| county | metric | v0_100m/may2025 | v1dikes_100m/may2025 | v1_100m/may2025 | v1_100m/may2025_gatehi |
|---|---|---|---|---|---|
| Cumberland | peak_km2 | 1.19 | 0.44 | 0.45 | 0.45 |
| Cumberland | area_days | 17.75 | 4.68 | 4.75 | 4.75 |
| Cumberland | persistent_km2 | 0.21 | 0.05 | 0.05 | 0.05 |
| Gloucester | peak_km2 | 0.91 | 0.35 | 0.36 | 0.36 |
| Gloucester | area_days | 15.95 | 4.05 | 4.26 | 4.21 |
| Gloucester | persistent_km2 | 0.22 | 0.01 | 0.01 | 0.01 |
| Salem | peak_km2 | 6.18 | 1.54 | 1.73 | 1.72 |
| Salem | area_days | 113.06 | 14.21 | 16.74 | 16.65 |
| Salem | persistent_km2 | 2.22 | 0.09 | 0.11 | 0.11 |

## Check valves

| index | v1dikes_100m/may2025 | v1_100m/may2025 | v1_100m/may2025_gatehi |
|---|---|---|---|
| drained (hm³ = 10⁶ m³) | 5.250 | 5.293 | 6.611 |
| valves passing > 1000 m³ | 11.000 | 13.000 | 13.000 |
| valves | 23.000 | 23.000 | 23.000 |

