# archive: frozen side lines

Archived 2026-10-15. The code here ran and its results are in docs/FINDINGS.md. It is kept
so those results can be traced and rerun, not developed further. Nothing in agri_sfincs/,
scripts/ or tests/ imports from here.

## What is here

The crop-insurance track (FINDINGS §4-§5, §8, §12-§13, §20, §26). After the 2026-10-05 pivot
it is no longer the main line, and Fork 1 tested null.

| Part | Scripts | Reports |
|---|---|---|
| RMA Cause of Loss and the county x month loss panel | fetch_rma_col, fetch_rma_sob, build_loss_panel; module `rma.py` | loss_panel.md, rma_cause_of_loss.md |
| Cheap predictors vs losses (track A) | fetch_nwm_soil, rain_metrics, rain_compare, a4_first_test; module `cropweights.py` | nwm_soil.md, rain_metrics.md, a4_first_test.md |
| Fork 1: cross-county flood x rain | fork1_counties, fetch_prism_monthly, flood_prone_share, fork1_panel; module `panel.py` | fork1_flood_rain.md |

`rma.py`, `cropweights.py` and `panel.py` are library modules (no `main`). They sit next to
the scripts, so the scripts find them with no path setup.

Still live, not here: the MRMS / Stage IV fetchers (scripts/fetch_mrms.py,
fetch_precip_hourly.py), which feed the SFINCS rain forcing (agri_sfincs/precip.py); the
6-h gap fill and axis check rain_metrics shares with that forcing (agri_sfincs.precip); and
open-water evaporation (agri_sfincs/evap.py), which may matter for ponding runs (§17).

## Rerunning

From the repo root, in the shared env (CLAUDE.md):

```bash
export PATH=$HOME/nj_sandy_sfincs/micromamba/envs/sfincs/bin:$PATH PYTHONPATH=$PWD
python archive/scripts/build_loss_panel.py
python -m unittest discover -s archive/tests     # synthetic, no network
```

Reports go to archive/reports/ (`config.ARCHIVE_REPORTS`); data still goes to data/ (bulk on
scratch, see docs/STATUS.md). data/insurance/ is never read.
