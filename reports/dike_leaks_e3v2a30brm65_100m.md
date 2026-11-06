# Dike leak routes against the lidar: `e3v2a30brm65_100m`

Written by `scripts/check_dike_leaks.py` (method in its docstring). Levels: m relative to local MHHW. `wall`: check_dike_seal.py's spill (every weir face closed, a face opens at its subgrid uv_zmin). `wall+lidar`: the same with every other face near the systems raised to the lowest lidar ground a crossing of it must get over. `model route on lidar`: the level at which the model's own route into the bulk of the system opens on the lidar. Lidar cannot see culverts, pipes or gates.

## Spill level and route

| system | interior ha | model leak kind | wall spill median | model leak face lidar crest | model route on lidar | wall+lidar spill median | lidar entry uv_zmin rel MHHW | lidar entry crest rel MHHW | lidar entry to model leak face m | lidar entry to weir m | lidar entry to gate m |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Gibbstown | 2,090.00 | no bank | -0.75 | -0.41 | -0.41 | -0.41 | -0.75 | -0.41 | 0.00 | 966.17 | 1,550.29 |
| Middle Neck | 992.00 | no bank | -0.18 | -0.47 | 0.12 | -0.18 | -0.18 | -0.47 | 0.00 | 1,490.21 | 2,120.66 |
| Silver Lake | 685.00 | end gap | -0.44 | -0.54 | -0.21 | -0.44 | -0.44 | -0.54 | 0.00 | 44.28 | 798.35 |
| Henby Creek | 495.00 | end gap | -0.15 | -0.18 | -0.13 | -0.15 | -0.15 | -0.18 | 0.00 | 53.38 | 3,197.49 |
| Locust Island | 246.69 | end gap | -0.43 | -0.52 | -0.34 | -0.43 | -0.43 | -0.52 | 0.00 | 44.28 | 798.35 |
| Jones Island Road | 142.00 | end gap | 0.73 | 0.74 | 0.74 | 0.74 | 0.73 | 0.74 | 0.00 | 75.17 | 2,784.23 |
| Lighthouse | 117.00 | end gap | 0.10 | 0.03 | 0.12 | 0.12 | -0.98 | 0.12 | 540.83 | 121.87 | 373.21 |
| Mill Creek (Union Bank) | 116.06 | no bank | 0.22 | 0.23 | 0.23 | 0.22 | 0.22 | 0.22 | 50.00 | 343.64 | 1,183.93 |
| Sunset Road | 92.00 | no bank | 0.16 | 0.16 | 0.16 | 0.16 | 0.16 | 0.16 | 0.00 | 1,466.94 | 1,516.64 |
| Sayres Neck | 85.00 | no bank | 0.37 | 0.31 | 0.40 | 0.40 | 0.35 | 0.40 | 304.14 | 70.99 | 1,264.27 |
| Durham | 83.00 | no bank | 0.34 | 0.26 | 0.34 | 0.34 | 0.34 | 0.26 | 0.00 | 429.64 | 994.64 |
| Hancocks Bridge Poplar | 76.75 | end gap | 0.13 | 0.31 | 0.31 | 0.18 | 0.17 | 0.18 | 1,509.60 | 232.04 | 1,003.51 |
| Sheppard Davis | 49.00 | no bank | 0.92 | 0.87 | 0.92 | 0.92 | 0.92 | 0.87 | 0.00 | 72.06 | 479.46 |
| Lower Alloways Creek | 31.00 | no bank | -0.41 | -0.42 | -0.33 | -0.41 | -0.41 | -0.42 | 0.00 | 197.90 | 897.97 |
| Back Neck | 29.00 | no bank | 0.25 | 0.11 | 0.34 | 0.30 | 0.26 | 0.30 | 460.98 | 682.46 | 1,050.87 |
| Sea Breeze Road | 26.00 | end gap | 0.14 | 0.10 | 0.14 | 0.14 | 0.14 | 0.10 | 0.00 | 28.22 | 577.47 |
| Richard Wood | 24.50 | end gap | -1.36 | -1.32 | -0.34 | -1.35 | -1.36 | -1.35 | 12.50 | 77.76 | 107.38 |
| County Hwy 623 | 21.06 | end gap | 0.11 | 0.08 | 0.60 | 0.11 | 0.11 | 0.08 | 0.00 | 72.38 | 684.88 |

## Interior hectares reached at MHHW + d

| system | wall ha @+0.0 | wall+lidar ha @+0.0 | wall ha @+0.3 | wall+lidar ha @+0.3 | wall ha @+0.6 | wall+lidar ha @+0.6 | wall ha @+1.0 | wall+lidar ha @+1.0 |
|---|---|---|---|---|---|---|---|---|
| Gibbstown | 1,789 | 1,734 | 1,883 | 1,878 | 1,948 | 1,941 | 1,989 | 1,989 |
| Middle Neck | 909 | 906 | 937 | 930 | 958 | 957 | 973 | 973 |
| Silver Lake | 680 | 680 | 685 | 685 | 685 | 685 | 685 | 685 |
| Henby Creek | 430 | 421 | 475 | 472 | 492 | 492 | 495 | 495 |
| Locust Island | 237 | 236 | 246 | 246 | 247 | 247 | 247 | 247 |
| Jones Island Road | 0 | 0 | 10 | 0 | 45 | 21 | 142 | 142 |
| Lighthouse | 0 | 0 | 117 | 117 | 117 | 117 | 117 | 117 |
| Mill Creek (Union Bank) | 0 | 0 | 116 | 116 | 116 | 116 | 116 | 116 |
| Sunset Road | 0 | 0 | 92 | 92 | 92 | 92 | 92 | 92 |
| Sayres Neck | 0 | 0 | 1 | 1 | 80 | 80 | 85 | 85 |
| Durham | 0 | 0 | 40 | 40 | 78 | 77 | 83 | 83 |
| Hancocks Bridge Poplar | 0 | 0 | 77 | 77 | 77 | 77 | 77 | 77 |
| Sheppard Davis | 0 | 0 | 0 | 0 | 0 | 0 | 41 | 41 |
| Lower Alloways Creek | 30 | 30 | 30 | 30 | 31 | 31 | 31 | 31 |
| Back Neck | 0 | 0 | 29 | 0 | 29 | 29 | 29 | 29 |
| Sea Breeze Road | 0 | 0 | 26 | 26 | 26 | 26 | 26 | 26 |
| Richard Wood | 24 | 24 | 24 | 24 | 24 | 24 | 24 | 24 |
| County Hwy 623 | 0 | 0 | 21 | 21 | 21 | 21 | 21 | 21 |

## NLD bank pieces the model dropped (open_creek_links.py): lidar crest, m rel MHHW

| system | dropped m | dropped crest min | dropped crest p50 |
|---|---|---|---|
| Locust Island | 35.97 | 0.44 | 0.75 |
| Richard Wood | 58.07 | 0.14 | 0.48 |
| County Hwy 623 | 34.08 | 0.44 | 0.71 |
