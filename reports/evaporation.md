# Open-water evaporation as negative net rain (2026-10-05)

`agri_sfincs/evap.py`, `scripts/fetch_pet.py`, `scripts/evap_check.py`. Demo runs
`v1_100m/runs/sep2023_evap` and `sep2023_evap2`: both are `v1_100m/runs/sep2023` (v1 lo)
plus P − E (§4).

## 1. Source audit: what negative precipitation does with `cnb`

Engine: `config.SFINCS_BIN`, built from `~/nj_sandy_sfincs/SFINCS-src-main` commit
a9b7580 (BUILD_INFO). The checkout's HEAD (eaf1283) differs from it only in SnapWave;
`git diff a9b7580 HEAD` is empty for meteo, infiltration, continuity, input, ncinput,
ncoutput and lib. Line numbers below are in `source/src/`.

| Step | What happens | Source |
|---|---|---|
| read | `Precipitation` (mm/h) from `netamprfile`, used as a block from each `time` (ampr_block default on) and interpolated bilinearly to cell centres; cells outside the raster get 0 | sfincs_ncinput.F90:834; sfincs_input.f90:549-552; sfincs_meteo.f90:1155-1159, 1176-1236, 1199-1213 |
| clamp | `prcp < 0` is set to 0 if the cell has no water: subgrid `z_volume <= 0` (regular: `zs <= zb`) | sfincs_meteo.f90:1316-1330 |
| net | `netprcp = prcp`; `cumprcp += prcp*dt` INCLUDING the negative part | sfincs_meteo.f90:1332, 1336 |
| order | meteo forcing, then infiltration, then continuity, every step | sfincs_lib.f90:530, 538, 618 |
| time blend | fields are sampled every `dtwnd` (1800 s), and the block value is that hour's. Between samples `prcp = prcp0 (1−f) + prcp1 f`, so the second half of every hour ramps linearly to the next hour's value | sfincs_lib.f90:495-501; sfincs_input.f90:69; sfincs_meteo.f90:1272, 1312 |
| cnb | `if (prcp > 0)` is the only rain branch. A negative (or zero) rate takes the DRY branch: the event closes (`scs_rain = 0`, `qinfmap = 0`, `rain_T1 = 0`), recovery time accumulates, and `Se` recovers once `rain_T1 > 0.06/kr` h. `scs_P1` and `scs_F1` (cnb's cumulative rain and infiltration) change only in the rain branch, and `qinfmap` is clamped at 0 or above | sfincs_infiltration.f90:737, 758-776, 779-780, 786-808 |
| net after cnb | `netprcp -= qinfmap` (0 in a dry hour, so the negative rate passes unchanged); `cuminf += qinfmap*dt` (unchanged) | sfincs_infiltration.f90:815, 821 |
| continuity | `dvol += netprcp * a * dt` with `a` = the FULL cell area; `z_volume += dvol` with no lower clamp; `z_volume <= 1e-6` gives `zs = zmin` | sfincs_continuity.f90:469, 481, 495, 535, 555 |
| output | `cumprcp` map and his output is the running sum above; never reset | sfincs_ncoutput.F90:515, 1496; sfincs_output.f90:215 (commented reset) |
| spin-up | the clamp is repeated on `netprcp` only if `spinup_meteo` is set (it is off by default; it is off here) | sfincs_meteo.f90:1349-1392; sfincs_input.f90:112, 608-611 |

The answers:
- **CN cumulative rain is never decremented.** cnb keeps its own per-event rain total
  `scs_P1`; `cumprcp` is used only by the OLD method `cna` (infiltration.f90:691-703).
- **Se recovery is not broken.** A negative hour is a dry hour, so it recovers as it
  would at zero rain.
- **Infiltration cannot go negative**, because `qinfmap` is clamped at 0 or above (l.780) and is 0 when dry.
- **`cumprcp` CAN go negative.** It becomes rain minus the E that was actually removed,
  in any cell that held water. Treat it as net rain, not rain. `storecumprcp` only
  switches that bookkeeping and its output on (input.f90:524-527).
- **E is applied after the clamp and before infiltration.** In the hour it falls, it
  replaces the rain.
- **With `P − E` in every hour, light rain is lost.** In an hour with 0 < P < E the net
  rate is negative, so cnb sees no rain. The rain is lost and the cnb event is split. The
  next rain restarts with `S1 = Se` (l.745-752).
- **Even E applied only where P = 0 eats rain.** The engine blends neighbouring values:
  bilinearly in space (1 km nodes to cell centres) and linearly in time over each second
  half hour. A −E node beside a raining node therefore lowers the rain cells receive.
  Emulated over Sep 2023, this removes 0.76% of the rain, and 93% of cells lose more
  than 1 mm. The demo run shows it: cuminf is 0.67% lower (−0.95 mm) and differs by
  more than 0.1 mm in 84% of cells. Hence the default `mode="dry_hours", buffer=1`: no
  −E within one 1 km node or one hour of any rain, so no −E is ever blended with rain
  (emulated loss 0). That buffer drops 7.5% of the E.
- **cnb never infiltrates STANDING water.** `qinfmap` is non-zero only while it rains,
  and then it is the CN share of that rain (l.737-822; there is no `z_volume` term).
  Until now ponded water could leave a closed depression only by flow. That is the
  second half of the FINDINGS §16 ratchet.
- **Partially wet subgrid cells lose E over the whole cell.** The clamp asks only
  whether `z_volume > 0`, and the sink is `E × a` (the full 1 ha), not `E × wet area`.
  §3 below gives the size of this. The overshoot to negative `z_volume` in the step a
  cell dries is ≤ E·a·dt (~0.002 m³ per cell at this run's mean dt of 3.6 s); the next rain repays it.

**Verdict: safe with conditions.**
1. Use `mode="dry_hours", buffer=1` so cnb's rain series is untouched.
2. Read `cumprcp` as net rain.
3. Accept that the sink acts on the whole area of any cell holding water. It is then a
   bulk "ponded-water loss" (E plus the seepage cnb lacks), not physical open-water E.
   §3 sizes the overcount.

## 2. Evaporation forcing

- **Source:** gridMET daily `pet` (ASCE Penman–Monteith grass ETo, ~4 km), fetched over
  THREDDS OPeNDAP (it works: ~0.2 s per year) for 2002–2025 over `fetch_mrms.BBOX`. The
  result is `data/evap/gridmet_pet_2002_2025.nc` (20 × 23 cells, no NaN).
- **gridMET days:** a gridMET day runs from 07Z to 07Z (dataset note5).
- **Size:** the domain mean is 2.9–3.6 mm/d by year, or ~1170 mm/yr. That is probably
  HIGH next to NWS TR-33 free-water evaporation for southern NJ (~800–900 mm/yr,
  approximate; not checked here). The whole-cell overcount in §3 is far larger.
- **Factor:** Kc = 1.05, the FAO-56 Table 12 value for open water less than 2 m deep.
- **Hourly shape:** each gridMET day's E is spread over the hours in proportion to
  sin(solar elevation) at mid-hour, at (−75.2 E, 39.45 N). E is radiation-driven, so
  night E is ~0. This also keeps E out of the night-time rain hours. Uniform spreading is
  available too (`shape="uniform"`).
- **Regridding:** E is interpolated bilinearly from gridMET to the run's ~1 km netampr
  grid. The engine then interpolates to cells exactly as it does for rain.
- **Rain hours:** E is dropped wherever P > 0. For Sep 2023 that drops 3.4% of the E
  (applied: 3.85 mm/d); with the ±1 node / ±1 h buffer it drops 7.5% (3.69 mm/d).
- **netampr convention (checked):** hydromt divides the hour-ending totals by the
  interval and shifts them left one step (meteo.py:382-388). The file therefore holds
  mm/h for the hour STARTING at `time`, which is how the engine applies it. Its
  `units: mm` / "ending at time" attrs are stale.

## 3. Partially wet subgrid cells: how large is the overcount?

`scripts/evap_check.py`, part 1. A cell counts as engine-wet when the map has `zs`: SFINCS
writes `zs` only where `zs − zmin > huthresh`, and huthresh is forced to 0 with subgrid
(sfincs_ncoutput_helpers.F90:186-230; sfincs_subgrid.F90:40). For each engine-wet cell,
f = the share of its 100 10 m pixels lying below `zs`. Because the sink is applied over
the whole cell, it is 1/f times what open water over the wet area would lose.

| v1 lo Sep 2023, 18Z | engine-wet share of 346,156 cells | f p10 / p50 / p90 | overcount, all wet cells | overcount, land cells (zmin > 0.5 m) |
|---|---|---|---|---|
| base, Sep 14 / 17 / 20 | 0.89 / 0.89 / 0.89 | 0.01 / 0.01 / 1.0 | 4.3 / 3.8 / 4.2 | 31 / 28 / 30 |
| evap (buffer 1), same days | 0.33 / 0.30 / 0.29 | 0.02–0.08 / 0.78–1.0 / 1.0 | 1.7 / 1.4 / 1.4 | 7.3 / 4.5 / 3.9 |

Without E, 89% of cells hold water during the dry spell. For half of them it is only
the lowest 10 m pixel (f ≤ 0.01): leftovers below the cell's outflow faces that can
never drain. Once E is on, those puddles go within hours, because the whole-cell sink
is ~30× the physical rate. After that the cells still wet are mostly fully wet
(median f 0.78–1.0), and the remaining overcount is 1.4–1.7× over all wet cells and
4–7× over land cells.

So on cropland the sink works as a bulk ponded-water loss. Its size is roughly
4–30 × E, i.e. 15–100 mm/d, which is in the range of real ponded seepage on
coastal-plain soils. cnb models no seepage at all (§1), but nothing here is calibrated.

## 4. Demonstration: Sep 2023, v1 lo with and without E

Runs: `sep2023` (base); `sep2023_evap` (dry_hours, no buffer); `sep2023_evap2`
(dry_hours, buffer 1 = the default). All are 16 threads, 42 / 48 min. Full tables:
`reports/compare_sep2023_evap.md` and `<run>/summary/evap_check_*.csv`.

**cnb is untouched with the buffer.** End-of-run cuminf: mean 141.661 mm in both runs,
max |difference| 0.008 mm. Seff: max |difference| 0.018 mm. Without the buffer, cuminf
is 0.95 mm lower and Seff differs by up to 54 mm (§1). `cumprcp` falls from 180.0 to
130.6 mm (domain mean) and is negative in 48,348 cells, down to −114 mm: the
permanently wet cells (channels, lakes, the bay).

**Wet cropland now recedes in the dry spell.** Cropland > 5 cm in km², daily maximum,
buffer-1 run:

| | Sep 13 | Sep 14 | Sep 17 | Sep 21 | Sep 30 |
|---|---|---|---|---|---|
| Salem base / evap | 2.13 / 1.62 | 1.55 / 1.04 | 1.58 / 0.77 | 1.44 / 0.46 | 2.01 / 0.90 |
| Cumberland base / evap | 1.60 / 1.32 | 0.58 / 0.43 | 0.56 / 0.30 | 0.59 / 0.26 | 0.85 / 0.47 |
| Gloucester base / evap | 0.25 / 0.17 | 0.23 / 0.14 | 0.23 / 0.09 | 0.23 / 0.07 | 0.32 / 0.12 |

Between Sep 14 and Sep 21 the base run stays flat or falls by 7%. With E the area falls
by 56% (Salem), 40% (Cumberland) and 50% (Gloucester). September totals:

- Area-days: Salem 44.3 → 26.3, Cumberland 17.9 → 11.5, Gloucester 6.5 → 3.4.
- Peak area: Salem 4.14 → 3.83, Cumberland 1.60 → 1.32.
- Persistent area: Salem 0.26 → 0.18 km².

Salem is still the wettest county.

**Diked interiors.** Mean depth over farm-dike cells with bed < 1 m, 5-day means
(buffer-1 run):

| | Sep 14 | Sep 19 | Sep 24 | Sep 29 |
|---|---|---|---|---|
| Silver Lake | 0.32 / 0.23 | 0.33 / 0.22 | 0.38 / 0.25 | 0.42 / 0.30 |
| Gibbstown | 0.35 / 0.29 | 0.32 / 0.25 | 0.40 / 0.33 | 0.44 / 0.36 |
| Locust Island | 0.33 / 0.27 | 0.34 / 0.25 | 0.40 / 0.32 | 0.42 / 0.33 |
| Middle Neck | 0.21 / 0.13 | 0.21 / 0.11 | 0.23 / 0.12 | 0.25 / 0.13 |
| Jones Island Road | 0.26 / 0.13 | 0.30 / 0.10 | 0.30 / 0.08 | 0.30 / 0.06 |
| Sayres Neck | 0.32 / 0.15 | 0.37 / 0.13 | 0.39 / 0.11 | 0.40 / 0.10 |

(Each cell: base / evap, m.) In the base run 16 of the 18 areas rise or stay flat from
Sep 14 to Sep 29 (Sunset Road and Lighthouse fall). With E:

- 9 FALL (Back Neck, County Hwy 623, Durham, Hancocks Bridge Poplar, Jones Island Road,
  Mill Creek, Sayres Neck, Sheppard Davis, Sunset Road).
- 2 stay flat (Lighthouse, Middle Neck).
- 7 still rise.
- The 7 that rise are Gibbstown, Henby Creek, Locust Island, Lower Alloways Creek,
  Richard Wood, Sea Breeze Road and Silver Lake. They rise less, and only from
  Ophelia's rain (Sep 22–23) and the Sep 27–29 rain. One wet month cannot show whether
  they would ratchet over a year.

The valves drain less with E (6.5 vs 7.5 hm³; 12 vs 19 valves pass more than 1000 m³),
because there is less water inside.

**Gauges.**
- Tidal gauges: unchanged (Bivalve identical; Greenwich / Hancocks Bridge bias falls by
  0.003 m).
- Stream stage drops in dry spells: by about 1 cm at Wrights Mill and Norma, 8 cm at
  Menantico and 11–19 cm at Swedesboro, because channel cells are partly wet and lose
  E over the whole cell.
- Correlation falls at all 8 stream gauges. The largest falls are Wrights Mill
  0.74 → 0.58 and Swedesboro 0.60 → 0.48. Rise ratios move both ways.
- The modelled peak at Menantico and Swedesboro moves to the Sep 11–13 storm because
  late-September stage is lower.
- Per §15 these obs points are not yet a fair test. Still, the channel E is also
  overcounted, and SFINCS has no baseflow to offset it.

## 5. Decision for the user

The mechanism is safe for cnb, provided the default `dry_hours` mode with buffer 1 is
used. It removes the ratchet in dry spells. Its strength on partially wet cells is not
physical: about 1.4–30 × open-water E, depending on how wet the cell is. Options:

- (a) Accept it as a bulk ponded-water loss (E plus the seepage cnb lacks). This is
  the simplest option.
- (b) Lower Kc to tune it, e.g. against observed ponding duration or NWM
  `sfcheadsubrt`. A constant cannot fix the 1/f dependence.
- (c) Restrict E to chosen cells. This needs a cell-aligned 100 m netampr, whose nodes
  sit on cell centres so bilinear interpolation returns them exactly: about 2.6 GB per
  47-day event.

The gridMET ETo level (~1170 mm/yr) may be ~30% high, but that is second order next to
the 1/f effect.
