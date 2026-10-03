"""Paths. Nothing geographic lives here (that is ``domain.py``)."""

from __future__ import annotations

import os
from pathlib import Path

#: The repo root. ``AGRI_ROOT`` may point at an out-of-tree checkout, but it must be
#: the parent of THIS package: nj_bight_sfincs once built a whole model against another
#: repo's inputs because a root variable pointed at the wrong directory, silently.
ROOT = Path(__file__).resolve().parents[1]
_env_root = os.environ.get("AGRI_ROOT")
if _env_root and Path(_env_root).resolve() != ROOT:
    raise RuntimeError(
        f"AGRI_ROOT={_env_root!r} is not the parent of the imported agri_sfincs "
        f"package ({ROOT}). Unset it or point it at this checkout."
    )

DATA = ROOT / "data"
REGION_DIR = DATA / "region"  # HUC12s, counties, the ring (small; source)
CDL_DIR = DATA / "cdl"  # Cropland Data Layer, NJ statewide GeoTIFF per year (bulk)
GAUGE_DIR = DATA / "gauges"  # inventories and downloaded series
INSURANCE_DIR = DATA / "insurance"  # ag-econ loss tables (never published)
RMA_DIR = DATA / "rma"  # USDA RMA public Cause of Loss files, NJ rows (bulk)
NWM_DIR = DATA / "nwm"  # National Water Model v3.0 retrospective extracts (bulk)
REPORTS = ROOT / "reports"
CATALOG = DATA / "data_catalog.yml"

#: Built models and runs: regenerable, so on scratch (1 TB tier, purged when idle),
#: never in the repo.
MODELS = Path("/scratch/tpj8/sfincs-nj-agri/models")
#: SFINCS: the native CPU build of the main branch (it restores cnb soil state from
#: restart files, rsttype 4). Built by nj_bight_sfincs hpc/build_sfincs_native.sh.
SFINCS_BIN = (
    Path.home() / "nj_sandy_sfincs/sfincs-native/main-winddir-fix-1-gf11/bin/sfincs"
)

#: Read-only rasters the bight project already holds that cover these counties.
#: Pointed at, never copied or modified.
BIGHT_DATA = Path.home() / "nj_bight_sfincs" / "data"
