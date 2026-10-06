# Farm-dike outlets v2 (scripts/build_dike_outlets.py)

Reference low tide: `v1_100m/sep2023` (p10 of hourly zs, last 30 days). 25 check valves for 18 of 18 farm areas (`dike_gates_v2_lo.drn` C = 1.5, `_hi` C = 6.0).

drain margin = intake bed + 0.1 − outfall low tide (m); > 0: the valve can draw the interior down to ~10 cm above its lowest point at an ordinary low tide.

| system | crop_km2 | valves | site | best_margin | out_lowtide | out_km |
|---|---|---|---|---|---|---|
| Middle Neck | 5.10 | 2 | creek_crossing | -0.56 | -0.46 | 0.07 |
| Gibbstown | 1.74 | 6 | nld_pipe_gate | -0.10 | -0.44 | 0.12 |
| Jones Island Road | 1.60 | 1 | deepest_notch | 1.04 | -0.08 | 0.48 |
| Locust Island | 1.08 | 1 | creek_crossing | -0.75 | -0.12 | 0.86 |
| Silver Lake | 1.05 | 1 | creek_crossing | -0.88 | 0.10 | 0.14 |
| Sayres Neck | 0.99 | 1 | deepest_notch | 0.29 | -0.00 | 0.21 |
| Hancocks Bridge Poplar | 0.59 | 1 | deepest_notch | -0.25 | -0.22 | 0.41 |
| Sheppard Davis | 0.50 | 1 | deepest_notch | -0.24 | -0.41 | 0.64 |
| Back Neck | 0.34 | 1 | deepest_notch | -0.38 | 0.07 | 0.24 |
| Sunset Road | 0.34 | 1 | creek_crossing | -0.05 | -0.35 | 0.63 |
| Henby Creek | 0.32 | 2 | creek_crossing | 0.47 | -0.42 | 0.09 |
| Lower Alloways Creek | 0.32 | 1 | deepest_notch | -0.46 | -0.13 | 0.30 |
| Lighthouse | 0.24 | 1 | deepest_notch | 0.07 | -0.67 | 0.16 |
| Richard Wood | 0.23 | 1 | deepest_notch | 0.62 | -1.00 | 0.12 |
| Mill Creek (Union Bank) | 0.22 | 1 | creek_crossing | -0.93 | 0.11 | 0.06 |
| Durham | 0.19 | 1 | deepest_notch | 0.16 | 0.18 | 0.12 |
| Sea Breeze Road | 0.14 | 1 | deepest_notch | 0.05 | -0.49 | 0.39 |
| County Hwy 623 | 0.13 | 1 | deepest_notch | 0.40 | -1.00 | 0.12 |
