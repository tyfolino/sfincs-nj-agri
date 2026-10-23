"""agri_sfincs — watershed-bounded SFINCS models of the Delaware Bay shore (NJ: Salem /
Cumberland / Gloucester; DE: the C&D Canal to Lewes), for bayshore farmland under storm
tides, dikes and sea-level rise, and the farm-exit and dike pay-off work with the Rutgers
ag-econ colleagues (the crop-insurance line is archived).

Every geographic fact lives in ``domain.py``; every path in ``config.py``.
"""

# Prime PROJ before anything pulls in hydromt_sfincs, and pin PROJ_DATA to the env's
# own proj directory. Both are lessons from nj_bight_sfincs (its nj_sfincs/__init__.py):
#   * importing hydromt_sfincs.utils before PROJ is initialised can hit a native
#     "double free or corruption" in downscale_floodmap;
#   * on this account ~/.local/share/proj shadows the env's proj.db, which in-process
#     only prints "proj_create_from_database: Open of ... failed" but makes the gdal
#     CLI die with "Invalid SRS".
# setdefault, so an explicit PROJ_DATA in the environment still wins.
import os as _os
from pathlib import Path as _Path

import pyproj  # noqa: F401  (PROJ primer — keep ahead of any hydromt_sfincs import)

_proj_data = _Path(pyproj.datadir.get_data_dir())
if (_proj_data / "proj.db").exists():
    _os.environ.setdefault("PROJ_DATA", str(_proj_data))
    _os.environ.setdefault("PROJ_LIB", str(_proj_data))  # PROJ < 9.1 spelling
