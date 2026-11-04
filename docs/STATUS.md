# STATUS: what is happening now

Keep this short and forward-looking. When an item closes, move its durable fact to FINDINGS
and delete it here. History lives in git.

Last updated: **2026-11-04** (§63 DE bank fix adopted; DE panel `deo` exported stacked).

## Goal
A map of bayshore farmland: current, threatened by sea-level rise, and dike-dependent, from
SFINCS same-event scenarios (FINDINGS §27, §29-§31), now on BOTH shores: NJ + Delaware (C&D
Canal to Lewes) as twin grids forced on the same mid-bay state line. Joint ag-econ work: the
**dike pay-off** and Seowoo's **flood → farm exit** paper (AERE abstract, mid-January 2027; her
result holds on 2008-23). Plan: `~/.claude/plans/no-need-to-draft-idempotent-goblet.md`.

## Resume here (plan steps)
- **Step 1, NJ model: `e3v2a30brm65_100m` adopted** (§45, §47, §48); full rerun done with wind (§50,
  §52); storm panel on it (§53). **§29's rise explained (§55):** report flooded hectares and the
  threshold range beside any field-class number. Open: Bivalve's storm-peak scatter (§50); Stow / upper
  Oldmans still short (no data). USGS 2022 Alloway survey email: on hold (user).
- **Step 3, Delaware: `de_v2ap45o_100m` adopted** (§51, §54, §61, §63; old `de_v2ap45_100m` deleted). Banks opened:
  Frederica's tide back at half range. Open: DE creek lows ~0.35-0.4 m high (all but Bowers), Frederica's rain response
  (+0.7-0.8 m in Irene / Sandy), storm peaks +0.2-0.3 m at Bowers / Slaughter Beach (DE rail carrying Ship John's surge?).
- **Step 5, Delaware exits:** first look done without SFINCS (§44). DE storm panel code done (`build_sandy_panel.py
  --state DE`, `build_storm_panel.py --state DE`, `export_storm_panel.py --de-tag de`: stacked, `state` + `field_key`);
  built on `de_v2ap45o_100m` as tag `deo` and exported stacked (`--tag m65 --de-tag deo`, 2026-11-04);
  `claims-reviewer` pass on the stacked bundle running, then it can go to the colleague and the advisor.

## Next, in order
0. **Storm-history land-use test:** no clear crop response by area to the 7 spring storms, m65 (§53, §57). "Not
   detectable", not "no effect"; the next-season cropland gap is unexplained (every field once, also against prone-dry).
   Bundle README: see Step 5. User: storm tides only; growing season = Apr-Oct.
1. **Tide gates:** public search done (§36); the leads that need a person are the user's call.
2. **Plan checks:** mass balance; where station peaks rise by more than the SLR.
3. **Dike pay-off, per system: farmland done (§59,** `compare_restore.py --payoff`): the banks keep ~300 ha
   of water off fields today and at +0.3 m, ~90 ha at +0.6 m; Middle Neck is 43% of it. Locust Island + Silver Lake,
   opened together, is the second-largest system (59 ha today). Costs (§60): 5 of 18 systems have a figure, mostly gates;
   scale banks by length. Gibbstown cut at 1 of 6 outlets.
4. **Wetness exposure for the conversion model** (§31): rain-event ponding per field + SSURGO
   drainage → `data/analysis/farm_units.csv`. Decide first on open-water evaporation
   (`agri_sfincs/evap.py`; −40% cropland area-days wet on Sep 2023, §17).
5. **Farm → wetland options (only if the user wants them):** set-back variants, Middle Neck at
   marsh level, roughness, Sandy with rain, Durham's lidar marsh bias.
5a. **Flood-map check done (§58):** place partly right, extent too wide, field flags barely match satellites. **Next:
   salt tests:** done, NJ (§62) and pooled NJ + DE (§64): no salt signature. Open: why flooded DE fields keep MORE cropland than DE prone-dry (§64);
   rerun without the DE fields beside Bowers / Slaughter Beach only after the DE lower-bay storm peaks are fixed (user, 2026-11-04). **Exit measure:** both flags kept;
   noisy on low ground, and over half of flags return (§57). Ask Seowoo her definition; MOD-IV pilot.
6. **NAIP validation of the exits**, NJ (`exit_spotcheck.py`, default tag cells_v2) and DE.
7. **Check NLD** for levee condition / inspection fields.

## Shared / not yet shared (all private until the user shares)
- Claude Doc "Bayshore farmland and storm flooding: where the story is" (for Seowoo and James):
  https://claude.ai/code/artifact/b6020269-e82b-413f-9430-59783a9d2828; talk figures
  `reports/figs/talk_*.png` (`scripts/plot_talk_figs.py`).
- Claude Doc "Water-related crop-insurance losses": https://claude.ai/artifact/P62Vj4zoqFzRJy7BDBb7Xy
- The per-field sample (§32).
- Storm panel bundle for Seowoo: `/cache/home/tpj8/bayshore-storm-panel`
  (`scripts/export_storm_panel.py`); the user makes it a private GitHub repo.

## Operational
- **Amarel maintenance 11-10/11:** no model builds in that window. nj_bight_sfincs moves its data then and will message
  before and after; afterwards check our 7 input paths read via `config.BIGHT_DATA`.
- **Scratch quota (shared with nj_bight_sfincs):** 1 T soft; this repo 186 G on 2026-11-03 (of 581 G
  total) after deleting e9, the 23 superseded test models and the v1 runs re-done on m65. Models left:
  m65 (140 G), de_v2ap45o (DE), v1 (v1-only runs: sep2023/evap, may2025, tidecal, y2023 staged, _rep).
  Stage new sets with `--link`, and `--daily-map` where hourly maps are not read (§56);
  `scripts/link_run_inputs.py` for older runs. Never edit a run's linked inputs in place. Next lever
  if needed: thin m65 hourly maps to daily where nothing reads the hourly fields (lossy; check readers first).
- **Bulk data is symlinked into /scratch/tpj8/sfincs-nj-agri/data_bulk** (bed_*.tif, nwm grid,
  ehydro, landsat, floodplain, prism, rma_states). After a purge, rebuild with the script named
  in each one's docstring.
- **Runs: ~1 min per simulated day on 32 threads, bit-reproducible.** Always
  `sbatch hpc/sfincs_run.slurm`: the VS Code job has only 4 CPUs.
- **Tide-only runs have zeroed rain:** the engine segfaults with cnb and no rain file.
- `v1_100m/runs/tide2024oct_intact_slr000_rep` is compare_restore.py's noise floor. Keep it.
- `v1_100m/runs/y2023_zsini{0,m1}` are staged. Do not submit them unless the user asks.
