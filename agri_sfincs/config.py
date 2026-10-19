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
PRECIP_DIR = DATA / "precip"  # Stage IV / MRMS hourly clips + county rain metrics (bulk)
ELEV_DIR = DATA / "elevation"  # the pre-merged bed and the river-bed burn
CHANNELS_DIR = DATA / "channels"  # ENC soundings, NHDPlus HR, USGS sections, tidal datums (bulk)
EVAP_DIR = DATA / "evap"  # gridMET daily reference ET (pet) clipped to the BBOX (bulk)
LANDUSE_DIR = DATA / "landuse"  # NJDEP Land Use/Land Cover editions + farm-to-wetland transitions
LANDSAT_DIR = DATA / "landsat"  # Landsat C2 L2 per-field per-scene stats (bulk; symlink to /scratch)
STRUCT_DIR = DATA / "structures"  # NID, NLD levees, head of tide, lakes; dike weirs and gates
STRUCTURES = STRUCT_DIR / "structures.gpkg"
SOILS_DIR = DATA / "soils"  # SSURGO hydrologic soil groups and ksat
LANDCOVER_DIR = DATA / "landcover"  # NLCD
EASEMENT_DIR = DATA / "easements"  # NRCS conservation easements
IMAGERY_DIR = DATA / "imagery"  # NAIP spot-check samples and chips
ANALYSIS_DIR = DATA / "analysis"  # derived per-field / per-test tables
RELEASE_DIR = ROOT.parent / "bayshore-storm-panel"  # data bundle for the econ colleague (its own git repo)
REPORTS = ROOT / "reports"
ARCHIVE_REPORTS = ROOT / "archive" / "reports"  # reports of the archived side lines (archive/README.md)
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

#: Fork 1 (cross-county flood x rain test). Bulk downloads live on scratch under
#: DATA_BULK/<name>/ and are symlinked into data/; only small derived CSVs stay on /home.
DATA_BULK = Path("/scratch/tpj8/sfincs-nj-agri/data_bulk")
RMA_STATES_DIR = DATA / "rma_states"  # RMA COL/SOB rows for the non-NJ states (bulk)
PRISM_DIR = DATA / "prism"  # PRISM AN 4 km monthly precipitation zips (bulk)
FLOODPLAIN_DIR = DATA / "floodplain"  # NFHL 1% zones, multi-state CDL, coarse DEM (bulk)
FORK1_DIR = DATA / "fork1"  # small derived tables: counties, county P, shares, panel
