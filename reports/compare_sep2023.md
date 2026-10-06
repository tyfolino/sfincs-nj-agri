# Run comparison: sep2023 (focus month 2023-09)

Runs: `v0_100m/sep2023`, `v1dikes_100m/sep2023`, `v1_100m/sep2023`, `v1_100m/sep2023_gatehi`

## Tidal gauges (hourly water level, m)

| name | metric | v0_100m/sep2023 | v1dikes_100m/sep2023 | v1_100m/sep2023 | v1_100m/sep2023_gatehi |
|---|---|---|---|---|---|
| Maurice River at Bivalve NJ | rmse_m | 0.088 | 0.087 | 0.106 | 0.106 |
| Maurice River at Bivalve NJ | bias_m | 0.021 | 0.022 | 0.027 | 0.027 |
| Maurice River at Bivalve NJ | r_demeaned | 0.994 | 0.994 | 0.991 | 0.991 |
| Cohansey River at Greenwich NJ | rmse_m | 0.483 | 0.469 | 0.335 | 0.335 |
| Cohansey River at Greenwich NJ | bias_m | 0.247 | 0.242 | 0.148 | 0.148 |
| Cohansey River at Greenwich NJ | r_demeaned | 0.752 | 0.775 | 0.912 | 0.912 |
| Alloway Creek at Hancocks Bridge N | rmse_m | 0.575 | 0.558 | 0.360 | 0.360 |
| Alloway Creek at Hancocks Bridge N | bias_m | 0.234 | 0.217 | 0.099 | 0.099 |
| Alloway Creek at Hancocks Bridge N | r_demeaned | 0.234 | 0.309 | 0.787 | 0.787 |

## Stream gauges (stage; rise_ratio = modelled / observed rise)

| name | metric | v0_100m/sep2023 | v1dikes_100m/sep2023 | v1_100m/sep2023 | v1_100m/sep2023_gatehi |
|---|---|---|---|---|---|
| Maurice River at Norma NJ | r_demeaned | 0.650 | 0.650 | 0.730 | 0.730 |
| Maurice River at Norma NJ | rise_ratio | 0.740 | 0.740 | 0.040 | 0.040 |
| Maurice River at Norma NJ | peak_lag_h | -207.000 | -207.000 | -284.000 | -284.000 |
| Menantico Creek near Millville NJ | r_demeaned | 0.810 | 0.810 | 0.770 | 0.770 |
| Menantico Creek near Millville NJ | rise_ratio | 0.440 | 0.440 | 0.650 | 0.650 |
| Menantico Creek near Millville NJ | peak_lag_h | 26.000 | 26.000 | 31.000 | 31.000 |
| Manumuskin River at Cumberland NJ | r_demeaned | 0.730 | 0.730 | 0.820 | 0.820 |
| Manumuskin River at Cumberland NJ | rise_ratio | 0.320 | 0.320 | 1.220 | 1.220 |
| Manumuskin River at Cumberland NJ | peak_lag_h | -277.000 | -277.000 | -277.000 | -277.000 |
| Cohansey River at Seeley NJ | r_demeaned | 0.780 | 0.780 | 0.750 | 0.750 |
| Cohansey River at Seeley NJ | rise_ratio | 0.860 | 0.860 | 1.670 | 1.670 |
| Cohansey River at Seeley NJ | peak_lag_h | -46.000 | -46.000 | -46.000 | -46.000 |
| Mantua Creek at East Holly Avenue  | r_demeaned | 0.910 | 0.910 | 0.910 | 0.910 |
| Mantua Creek at East Holly Avenue  | rise_ratio | 0.990 | 0.990 | 0.990 | 0.990 |
| Mantua Creek at East Holly Avenue  | peak_lag_h | -3.000 | -3.000 | -3.000 | -3.000 |
| Raccoon Creek at Wrights Mill NJ | r_demeaned | 0.730 | 0.730 | 0.740 | 0.740 |
| Raccoon Creek at Wrights Mill NJ | rise_ratio | 0.410 | 0.410 | 0.730 | 0.730 |
| Raccoon Creek at Wrights Mill NJ | peak_lag_h | 5.000 | 5.000 | 5.000 | 5.000 |
| Raccoon Creek near Swedesboro NJ | r_demeaned | 0.640 | 0.640 | 0.600 | 0.600 |
| Raccoon Creek near Swedesboro NJ | rise_ratio | 0.230 | 0.230 | 0.490 | 0.490 |
| Raccoon Creek near Swedesboro NJ | peak_lag_h | 9.000 | 9.000 | 9.000 | 9.000 |
| Salem River at Woodstown NJ | r_demeaned | 0.770 | 0.770 | 0.760 | 0.760 |
| Salem River at Woodstown NJ | rise_ratio | 8.580 | 8.580 | 8.830 | 8.830 |
| Salem River at Woodstown NJ | peak_lag_h | -3.000 | -3.000 | -3.000 | -3.000 |

## Cropland wet > 5 cm in the focus month (km², km²·days)

| county | metric | v0_100m/sep2023 | v1dikes_100m/sep2023 | v1_100m/sep2023 | v1_100m/sep2023_gatehi |
|---|---|---|---|---|---|
| Cumberland | peak_km2 | 2.35 | 1.61 | 1.60 | 1.60 |
| Cumberland | area_days | 33.53 | 17.84 | 17.93 | 17.93 |
| Cumberland | persistent_km2 | 0.44 | 0.14 | 0.14 | 0.14 |
| Gloucester | peak_km2 | 1.19 | 0.79 | 0.79 | 0.78 |
| Gloucester | area_days | 19.45 | 6.37 | 6.45 | 6.29 |
| Gloucester | persistent_km2 | 0.32 | 0.03 | 0.03 | 0.03 |
| Salem | peak_km2 | 7.63 | 4.05 | 4.14 | 4.14 |
| Salem | area_days | 152.20 | 40.09 | 44.30 | 44.21 |
| Salem | persistent_km2 | 3.01 | 0.19 | 0.25 | 0.25 |

## Check valves

| index | v1dikes_100m/sep2023 | v1_100m/sep2023 | v1_100m/sep2023_gatehi |
|---|---|---|---|
| drained (hm³ = 10⁶ m³) | 7.312 | 7.499 | 10.072 |
| valves passing > 1000 m³ | 15.000 | 19.000 | 19.000 |
| valves | 23.000 | 23.000 | 23.000 |

