"""NJDEP Land Use/Land Cover (modified Anderson codes): farm -> wetland transitions.

NJDEP's photo-interpreted LU/LC (1995/97, 2002, 2007, 2012, 2015, 2020; ~1 ac minimum mapping
unit) comes as one polygon layer per edition that also carries the previous edition's code,
so each layer is a transition table (scripts/fetch_njlulc.py). Codes used here:

  1xxx urban (1750 = managed wetland in maintained lawn: counted urban)
  2100 cropland and pastureland       2140 agricultural wetlands (modified): farmed wet ground
  2150 former agricultural wetland (becoming shrubby, not built-up)
  2200 orchards / vineyards / nurseries   2300 confined feeding   2400 other agriculture
  4xxx forest   5xxx water   6xxx wetlands   7xxx barren
  5300 artificial lakes: dug ponds (stormwater, irrigation), NOT counted as farm -> wetland

"Farmed" = 2100, 2140, 2200, 2300, 2400 (2150 is NOT farmed: it is the abandonment class).
Wetland subclasses are told apart by the edition's LABEL (saline / coastal / tidal / other),
so a code we have not listed is not silently misfiled.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import box

#: NJDEP LU/LC 2020 (2015 -> 2020 transitions), ArcGIS Online feature layer.
LULC2020_URL = ("https://services1.arcgis.com/QWdNfRs7lkPq4g4Q/arcgis/rest/services/Land_Use_2020/"
                "FeatureServer/5")  # fmt: skip

#: Delaware's LU/LC (FirstMap DE_LULC, Delaware Modified Anderson, 3-digit codes; 2007, 2012,
#: 2017, 2022): 211 cropland, 212 pasture, 213 idle fields, 220 orchards / nurseries,
#: 230 confined feeding, 240 farmsteads, 290 other agriculture, the counterparts of NJ's
#: 2100-2400. Delaware has no "agricultural wetland" class (NJ 2140). Its codes are 3-digit and
#: NJ's 4-digit, so one FARMED set serves both states.
DE_FARMED = frozenset({211, 212, 213, 220, 230, 240, 290})
FARMED = frozenset({2100, 2140, 2200, 2300, 2400}) | DE_FARMED
FORMER_AG_WETLAND = 2150
FARMED_WETLAND = 2140
ARTIFICIAL_LAKE = 5300

# transition classes, in report order
STAYS = "stays farmed"
TO_FARMED_WET = "-> farmed wetland (2140)"
TO_FORMER = "-> former ag wetland (2150)"
TO_COASTAL = "-> coastal / saline wetland"
TO_WETLAND = "-> other wetland"
TO_WATER = "-> water"
TO_POND = "-> artificial lake / pond"
TO_FOREST = "-> forest"
TO_URBAN = "-> developed"
TO_OTHER = "-> other"
CLASSES = (STAYS, TO_FARMED_WET, TO_FORMER, TO_COASTAL, TO_WETLAND, TO_WATER, TO_POND,
           TO_FOREST, TO_URBAN, TO_OTHER)  # fmt: skip
#: the classes that count as farm -> wetland (the outcome); 2140 is still farmed, so not one
WETTING = frozenset({TO_FORMER, TO_COASTAL, TO_WETLAND, TO_WATER})
COASTAL_WORDS = ("SALINE", "COASTAL", "TIDAL")


def is_farmed(code) -> bool:
    try:
        return int(code) in FARMED
    except (TypeError, ValueError):
        return False


def transition(prev, nxt, next_label: str = "") -> str | None:
    """Class of a (previous, next) code pair; None if the previous code was not farmed."""
    if not is_farmed(prev):
        return None
    n = int(nxt)
    if n in FARMED:
        return TO_FARMED_WET if (n == FARMED_WETLAND and int(prev) != FARMED_WETLAND) else STAYS
    if n == FORMER_AG_WETLAND:
        return TO_FORMER
    major = n // 1000
    if major == 6:
        lab = (next_label or "").upper()
        return TO_COASTAL if any(w in lab for w in COASTAL_WORDS) else TO_WETLAND
    if n == ARTIFICIAL_LAKE:  # stormwater / irrigation ponds: dug, not drowned (NAIP check)
        return TO_POND
    if major == 5:
        return TO_WATER
    if major == 4:
        return TO_FOREST
    if major == 1:
        return TO_URBAN
    return TO_OTHER


def fishnet(bounds, size: float, crs) -> gpd.GeoDataFrame:
    """Square cells of ``size`` m covering ``bounds``, snapped to the 30 m CDL grid (origin
    offset 15 m)."""
    x0, y0, x1, y1 = bounds
    x0 = np.floor((x0 - 15) / size) * size + 15
    y0 = np.floor((y0 - 15) / size) * size + 15
    xs, ys = np.arange(x0, x1 + size, size), np.arange(y0, y1 + size, size)
    return gpd.GeoDataFrame(geometry=[box(x, y, x + size, y + size) for x in xs for y in ys], crs=crs)
