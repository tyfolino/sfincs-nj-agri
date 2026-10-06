# Dikes as weirs, farm-dike outlets (scripts/build_dikes.py)

Weir file `data/structures/dikes.weir`: 103 polylines, 20,466 vertices, 101.4 km of NLD alignment inside the model outline. Crest = lidar ridge (max of the pre-merged bed within ±20 m), cd 0.6.

| banks | km | crest p5 / p50 / p95 (m NAVD88) | km filled | km crest < 1.2 m |
|---|---|---|---|---|
| farm dikes (notches filled) | 65.6 | 1.43 / 2.18 / 6.50 | 3.8 | 1.1 |
| other levees (raw ridge) | 36.7 | 1.10 / 1.82 / 9.77 | 0.0 | 2.7 |

Farm leveed areas (> 0.1 km² CDL 2023 cropland): 18, 15.1 km² cropland. Check valves (drainage type 3, `dike_gates_lo.drn` C = 1.5, `dike_gates_hi.drn` C = 6.0 m^2.5/s): 23.

| system | crop_km2 | area_km2 | site | notch_ridge | z_in | z_out |
|---|---|---|---|---|---|---|
| Middle Neck | 5.10 | 11.50 | deepest_notch | 1.27 | -2.17 | -10.98 |
| Gibbstown | 1.74 | 22.43 | nld_pipe_gate | nan | -0.68 | -1.29 |
| Gibbstown | 1.74 | 22.43 | nld_pipe_gate | nan | -0.68 | -1.29 |
| Gibbstown | 1.74 | 22.43 | nld_pipe_gate | nan | -0.61 | -1.29 |
| Gibbstown | 1.74 | 22.43 | nld_pipe_gate | nan | -0.59 | -1.29 |
| Gibbstown | 1.74 | 22.43 | nld_pipe_gate | nan | -0.60 | -1.29 |
| Gibbstown | 1.74 | 22.43 | nld_pipe_gate | nan | -0.68 | -1.29 |
| Jones Island Road | 1.60 | 2.32 | deepest_notch | 1.07 | 0.86 | -1.09 |
| Locust Island | 1.08 | 3.83 | deepest_notch | 1.17 | -0.98 | -1.34 |
| Silver Lake | 1.05 | 7.93 | deepest_notch | 2.17 | -0.88 | -1.07 |
| Sayres Neck | 0.99 | 1.25 | deepest_notch | 1.21 | 0.18 | -0.91 |
| Hancocks Bridge Poplar | 0.59 | 1.08 | deepest_notch | 1.11 | 0.06 | -1.07 |
| Sheppard Davis | 0.50 | 0.75 | deepest_notch | 1.43 | 1.27 | 0.05 |
| Back Neck | 0.34 | 0.46 | deepest_notch | 1.18 | -0.41 | -0.90 |
| Sunset Road | 0.34 | 1.56 | lowest_ridge | 1.57 | -0.50 | -0.27 |
| Henby Creek | 0.32 | 6.21 | deepest_notch | 1.49 | -0.04 | -1.07 |
| Lower Alloways Creek | 0.32 | 0.64 | deepest_notch | 0.87 | -0.22 | -1.34 |
| Lighthouse | 0.24 | 1.93 | deepest_notch | 1.35 | -0.69 | -1.07 |
| Richard Wood | 0.23 | 0.69 | deepest_notch | 0.52 | -0.48 | -1.33 |
| Mill Creek (Union Bank) | 0.22 | 1.98 | deepest_notch | 1.32 | -0.92 | -1.48 |
| Durham | 0.19 | 1.49 | deepest_notch | 1.14 | 0.51 | -0.93 |
| Sea Breeze Road | 0.14 | 0.40 | deepest_notch | 1.80 | -0.54 | -0.80 |
| County Hwy 623 | 0.13 | 0.42 | deepest_notch | 0.27 | -0.70 | -1.33 |

⚠️ Gate sizes and sites are ASSUMPTIONS: no tide-gate inventory exists for these banks (NLD has 13 pipe gates, all at Chester PA and Gibbstown).
