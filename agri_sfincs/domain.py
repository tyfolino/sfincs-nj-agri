"""Every geographic fact about the model, in one place.

The domain is a set of USGS WBD HUC12s: every Delaware-draining watershed from Big
Timber Creek (the Camden/Gloucester line) south to West Creek (the Cumberland/Cape May
line). Decided with the user 2026-10-02:

* whole watersheds, so no river is cut — area outside the three counties stays in the
  model and is clipped out at analysis time;
* Delaware side only — Gloucester's Great Egg Harbor headwaters (~150 km2 of ~870) are
  left out; ``GREAT_EGG_GLOUCESTER`` names them so the cropland they hold can be
  measured (scripts/cropland_coverage.py) and the call revisited;
* the downstream boundary is observed Delaware River/Bay tide gauges.

HUC12 codes and names are WBD as served by hydro.nationalmap.gov (queried 2026-10-02).
WBD spells Mantua Creek "Manuta Creek"; the name is kept as WBD serves it.
"""

from __future__ import annotations

EPSG = 32618  # UTM 18N, as nj_bight_sfincs
STATE_FIPS = "34"

# fmt: off
#: HUC12 -> WBD name. Order: north (Big Timber) to south-east (West Creek).
HUC12 = {
    # HUC8 02040202 Lower Delaware — the Gloucester river front
    "020402020501": "North Branch Big Timber Creek",   # all Camden; needed for closure
    "020402020502": "South Branch Big Timber Creek",
    "020402020503": "Big Timber Creek",
    "020402020506": "Manuta Creek",
    "020402020507": "Woodbury Creek-Delaware River",
    "020402020606": "Raccoon Creek",
    "020402020607": "Repaupo Creek-Delaware River",
    "020402020608": "Oldmans Creek-Delaware River",
    # HUC8 02040206 Cohansey-Maurice
    "020402060101": "Game Creek",
    "020402060102": "Headwaters Salem River",
    "020402060103": "Whooping John Creek-Frontal Delaware River",
    "020402060104": "Mannington Creek",
    "020402060105": "Mill Creek-Frontal Delaware River",
    "020402060106": "Salem River-Frontal Delaware River",
    "020402060201": "Cedar Brook-Alloway Creek",
    "020402060202": "Town of Quinton-Alloway Creek",
    "020402060203": "Alloway Creek-Frontal Delaware River",
    "020402060301": "Upper Cohansey River",
    "020402060302": "Middle Cohansey River",
    "020402060303": "Lower Cohansey River",
    "020402060401": "Scotland Run",
    "020402060402": "Reed Branch-Still Run",
    "020402060403": "Upper Muddy Run",
    "020402060404": "Lower Muddy Run",
    "020402060405": "Burnt Mill Branch-Maurice River",
    "020402060501": "Mill Creek",
    "020402060502": "Union Lake-Maurice River",
    "020402060503": "Manantico Creek",
    "020402060504": "Buckshutem Creek",
    "020402060505": "White Marsh Run-Maurice River",
    "020402060506": "Manumuskin River",
    "020402060507": "Muskee Creek-Maurice River-Frontal Maurice River Cove",
    "020402060601": "Sarah Run-Stow Creek",
    "020402060602": "Mad Horse Creek-Frontal Delaware Bay",
    "020402060603": "Stow Creek-Frontal Delaware Bay",
    "020402060604": "Back Creek-Frontal Delaware Bay",
    "020402060605": "Oranoaken Creek-Frontal Delaware Bay",
    "020402060703": "West Creek-Frontal Delaware Bay",
    # NOT 020402060701 Fishing Creek / 020402060702 Dennis Creek: east of West Creek,
    # all Cape May.
}

#: Gloucester's Great Egg Harbor headwaters — OUTSIDE the domain (see module docstring).
GREAT_EGG_GLOUCESTER = {
    "020403020101": "Fourmile Branch-Great Egg Harbor River",
    "020403020102": "Upper Hospitality Branch",
    "020403020103": "Marsh Lake Branch",
    "020403020104": "Lower Hospitality Branch",
    "020403020106": "Squankum Branch-Great Egg Harbor River",
}

#: Counties the analysis is about (the loss data are county x month).
COUNTIES = {"34033": "Salem", "34011": "Cumberland", "34015": "Gloucester"}
#: Counties the domain also touches; modelled, never analysed.
COUNTIES_FRINGE = {"34007": "Camden", "34001": "Atlantic", "34009": "Cape May"}

#: NOAA CO-OPS water-level stations along the Delaware River/Bay, upstream to mouth.
#: Coordinates and MLLW-only datum handling as nj_bight_sfincs
#: scripts/download_noaa_sandy_wl.py STATIONS_V4 (navd_from = NAVD88-tied neighbours
#: whose NAVD88-MSL separation is transferred).
NOAA_STATIONS = [
    {"id": "8545240", "name": "Philadelphia, PA",       "lon": -75.1420, "lat": 39.9331},
    {"id": "8540433", "name": "Marcus Hook, PA",        "lon": -75.4095, "lat": 39.8118},
    {"id": "8551910", "name": "Reedy Point, DE",        "lon": -75.5719, "lat": 39.5583},
    {"id": "8537121", "name": "Ship John Shoal, NJ",    "lon": -75.3767, "lat": 39.3054,
     "datum": "MLLW", "navd_from": ["8557380", "8551910"]},
    {"id": "8555889", "name": "Brandywine Shoal Light", "lon": -75.1133, "lat": 38.9867,
     "datum": "MLLW", "navd_from": ["8557380", "8536110"]},
    {"id": "8536110", "name": "Cape May, NJ",           "lon": -74.9600, "lat": 38.9683},
    {"id": "8557380", "name": "Lewes, DE",              "lon": -75.1193, "lat": 38.7828},
]

#: USGS sites known to matter (the nj_bight_sfincs v4 lists). Labels are short
#: reminders; the inventory script reports the official names from the USGS API and
#: also discovers every other site inside the ring.
USGS_SITES = {
    "01411500": "Maurice R. at Norma",
    "01412800": "Cohansey R. at Seeley",
    "01482500": "Salem R. at Woodstown",
    "01477120": "Raccoon Ck",
    "01475001": "Mantua Ck",
    "01412150": "Maurice R. at Bivalve (tidal)",
    "01413038": "Cohansey R. at Greenwich (tidal)",
}
# fmt: on


def huc12_codes() -> list[str]:
    return list(HUC12)
