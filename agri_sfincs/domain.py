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

from dataclasses import dataclass

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
GLOUCESTER = "34015"  # the county whose Great Egg headwaters are left out
#: Counties the domain also touches; modelled, never analysed.
COUNTIES_FRINGE = {"34007": "Camden", "34001": "Atlantic", "34009": "Cape May"}

#: Fork 1 (cross-county flood x rain test): state abbreviation -> 2-digit FIPS of the
#: states it pools, NJ first.
FORK1_STATES = {"NJ": "34", "DE": "10", "MD": "24", "VA": "51", "NC": "37"}

#: The MRMS / Stage IV / gridMET clip, lon/lat (w, s, e, n). scripts/fetch_mrms.py keeps
#: a literal copy (it runs in the grib env, which cannot import this package);
#: tests/test_region.py checks the two agree.
RAIN_BBOX = (-75.64, 38.98, -74.80, 39.94)

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
SHIP_JOHN = "8537121"  # Ship John Shoal: the bay gauge nearest the Cumberland bayshore
CAPE_MAY = "8536110"  # the one forcing gauge on the ocean side

#: VIRTUAL forcing gauges on the Cumberland / Cape May shore (FINDINGS §41): NOAA harmonic
#: stations with no observations here, whose tide is bigger than Cape May's. Their own
#: NAVD88 ties are set aside (Fortescue's sits ~0.08 m off Bivalve's, Ship John's and Cape
#: May's); navd_from = the NAVD88-tied neighbours used instead. Bivalve 8535055 is a
#: CO-OPS datum station with a NAVD88 tie.
VIRTUAL_STATIONS = [
    {"id": "8536931", "name": "Fortescue Creek, NJ",       "lon": -75.1750, "lat": 39.2383,
     "navd_from": ["8535055"]},
    {"id": "8536581", "name": "Bidwell Creek entrance, NJ", "lon": -74.8920, "lat": 39.1280,
     "navd_from": ["8535055", "8536110"]},
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


# fmt: off
#: Tidal river reaches whose bed is burned from the NOAA chart (ENC) — user, 2026-10-02:
#: "navigable tidal reaches" (Maurice -> Millville, Cohansey -> Bridgeton, Salem River,
#: Alloway Creek) plus the other charted tributary mouths in the ring. ``head`` is the
#: NJDEP head-of-tide point (data/structures/structures.gpkg, njdep_head_of_tide; the
#: coordinates are copied from it) where the tidal reach starts; the reach runs down the
#: NHDPlus HR main path to the first "Delaware River/Bay" flowline, and is cut where it
#: runs out into open water (bed_source 3, lidar NoData) — see build_riverbeds.py.
#: Above ``head`` the stream is non-tidal and gets the surface-minus-depth rule.
#: ``ehydro`` = the USACE eHydro channel name whose surveys REPLACE the chart soundings
#: where they reach (user, 2026-10-05).
#: v2 beds (2026-10-23, FINDINGS §42-43): ``nos`` = NOS hydrographic surveys (NCEI HYD93,
#: data/channels/nos/<id>.a93.gz) as (survey id, MLW - MLLW in m: 0 for an MLLW survey), which
#: come after eHydro and before the chart; ``stated`` = (lon, lat, depth below MLLW): from the
#: centreline point nearest (lon, lat) down to the mouth, the bed is at least that deep (a
#: charted controlling depth, or a calibrated effective depth where nothing was measured).
TIDAL_REACHES = {
    "maurice":    {"river": "Maurice River",   "head": (-75.053997, 39.401027),
                   "note": "head = Union Lake dam, Millville", "ehydro": "Maurice River",
                   "ehydro_prefix": "MA_"},
    "cohansey":   {"river": "Cohansey River",  "head": (-75.235098, 39.446669),
                   "note": "head = Bridgeton",
                   # D00081 (1987) / H11070 (2001): the mouth to 39.349 N, MLLW
                   "nos": [("D00081", 0.0), ("H11070", 0.0)],
                   # From Fairton landing down: an EFFECTIVE depth, calibrated 2026-10-23 on the
                   # calm-window tide (FINDINGS §45): 2.13 (7 ft, the Coast Pilot entrance
                   # depth, e9) / 3.0 / 4.5 / 6.0 m took Greenwich 0.77 / 0.80 / 0.84 / 0.87
                   # and the held-out Tindalls Wharf 0.36 / 0.47 / 0.63 / 0.75; 6 m is inside
                   # the 1906 survey (30-40 ft, one ~7 ft bar) and the CSB (4.5-8.4 m), and
                   # likely also stands in for channel width the painted strip lacks
                   "stated": (-75.2301, 39.3811, 6.0)},
    "salem":      {"river": "Salem River",     "head": (-75.477245, 39.670411),
                   "note": "head = NJDEP point north of Salem", "ehydro": "Salem River",
                   "ehydro_prefix": "SA_"},
    "alloway":    {"river": "Alloway Creek",   "head": (-75.360844, 39.564649),
                   "note": "head = Alloway Lake dam, Alloway", "nos": [("H10112", 0.0)]},
    "stow":       {"river": "Stow Creek",      "head": (-75.361918, 39.465272),
                   "note": "head = NJDEP point"},
    "oldmans":    {"river": "Oldmans Creek",   "head": (-75.341584, 39.704183),
                   "note": "head = NJDEP point above Auburn", "nos": [("H10027", 0.0)]},
    "raccoon":    {"river": "Raccoon Creek",   "head": (-75.276262, 39.742546),
                   "note": "head = Swedesboro"},
    "mantua":     {"river": "Mantua Creek",    "head": (-75.155693, 39.786579),
                   "note": "head = Mantua"},
    "woodbury":   {"river": "Woodbury Creek",  "head": (-75.150567, 39.842022),
                   "note": "head = Woodbury"},
    "big_timber": {"river": "Big Timber Creek", "head": (-75.081778, 39.809432),
                   "note": "head = NJDEP point on the South Branch (the North "
                           "Branch is all Camden County)",
                   # H09886 (1980) is on MLW: MLW - MLLW = 0.058 m (Philadelphia, Pier 11)
                   "nos": [("H09886", 0.058)]},
}
# fmt: on

#: Marsh branch networks beside a tidal reach (scripts/paint_branches.py, test 2026-10-25):
#: ``bbox`` (lon0, lat0, lon1, lat1) holds the lidar flat-water channels joined to the reach's
#: painted channel. Lower Alloway: Hancocks Bridge to the river, with the Abbotts Meadow
#: branches and Hope Creek down to its mouth (~39.45 N), which reach the river by their own mouths.
BRANCH_NETWORKS = {
    "alloway": {"reach": "alloway", "bbox": (-75.565, 39.435, -75.455, 39.53)},
}


# fmt: off
#: Map labels, lon/lat: towns (for orientation) and waters.
PLACES = {
    "Salem": (-75.467, 39.572), "Pennsville": (-75.517, 39.654),
    "Penns Grove": (-75.468, 39.730), "Paulsboro": (-75.240, 39.830),
    "Woodstown": (-75.328, 39.652), "Hancocks Bridge": (-75.461, 39.507),
    "Greenwich": (-75.337, 39.390), "Bridgeton": (-75.234, 39.427),
    "Millville": (-75.039, 39.402), "Fortescue": (-75.170, 39.237),
    "Port Norris": (-75.035, 39.246), "Mauricetown": (-74.993, 39.286),
}
WATERS = {
    "Delaware River": (-75.36, 39.80), "Delaware Bay": (-75.30, 39.24),
    "Mannington\nMeadow": (-75.43, 39.615), "Salem R.": (-75.50, 39.585),
    "Alloway Cr.": (-75.50, 39.50), "Stow Cr.": (-75.41, 39.43),
    "Cohansey R.": (-75.33, 39.355), "Maurice R.": (-74.98, 39.33),
}
#: The two bayshore zoom windows of the scenario maps: lon0, lat0, lon1, lat1.
ZOOMS = {
    "Salem River / Mannington Meadow / Hancocks Bridge": (-75.57, 39.47, -75.38, 39.63),
    "Cumberland bayshore: Greenwich to the Maurice River": (-75.40, 39.21, -74.93, 39.42),
}
# fmt: on


# ── the two sides (2026-10-23) ────────────────────────────────────────────────
# Delaware state joins as a TWIN grid (user, 2026-10-23): the bay-draining watersheds from
# the C&D Canal south to Lewes, its own SFINCS model, forced on the same mid-bay state line as
# NJ with the same gauge chain. One region, one analysis. The NJ constants above stay as they
# were (every NJ script reads them); ``SIDES`` holds both sides for code that takes --side.

# fmt: off
#: Delaware: HUC12 -> WBD name, north (the canal) to south (Lewes). WBD spellings kept
#: ("Smryna", "Lepsic", "Issac", "Missipillion"). NOT 020402050705 "Chesapeake and Delaware
#: Canal-Frontal Delaware River": the canal is the north edge (user, 2026-10-23), nor the
#: Christina / Brandywine units north of it.
DE_HUC12 = {
    # HUC8 02040205 Brandywine-Christina, south of the canal
    "020402050801": "Augustine Creek-Frontal Delaware River",
    "020402050802": "Appoquinimink River-Frontal Delaware River",
    "020402050803": "Blackbird Creek-Frontal Delaware River",
    # HUC8 02040207 Broadkill-Smyrna
    "020402070101": "Duck Creek",
    "020402070102": "Smryna River",
    "020402070103": "Cedar Swamp-Frontal Delaware Bay",
    "020402070201": "Upper Leipsic River",
    "020402070202": "Lower Lepsic River",
    "020402070203": "Duck Creek-Frontal Delaware Bay",
    "020402070204": "Simons River-Frontal Delaware Bay",
    "020402070205": "Little River-Frontal Delaware Bay",
    "020402070301": "Upper Saint Jones River",
    "020402070302": "Issac Branch",
    "020402070303": "Tidbury Creek",
    "020402070304": "Lower Saint Jones River",
    "020402070401": "Spring Branch-Murderkill River",
    "020402070402": "Browns Branch",
    "020402070403": "Spring Creek",
    "020402070404": "Ash Gut-Murderkill River",
    "020402070405": "Murderkill River",
    "020402070406": "Brockonbridge Gut-Frontal Delaware Bay",
    "020402070501": "Upper Mispillion River",
    "020402070502": "Upper Cedar Creek",
    "020402070503": "Middle Mispillion River",
    "020402070504": "Slaughter Creek-Frontal Delaware Bay",
    "020402070505": "Lower Cedar Creek",
    "020402070506": "Lower Missipillion River",
    "020402070507": "Grecos Canal-Delaware Bay",
    "020402070601": "Round Pole Branch-Broadkill River",
    "020402070602": "Primehook Creek",
    "020402070603": "Beaverdam Creek-Broadkill River",
    "020402070604": "Canary Creek-Broadkill River",
    "020402070605": "Breakwater Harbor-Delaware Bay",
}
DE_COUNTIES = {"10003": "New Castle", "10001": "Kent", "10005": "Sussex"}
#: Delaware's tidal reaches, as TIDAL_REACHES. ``head`` = the lowest dam (USACE NID,
#: data/structures/structures_de.gpkg), else nj_bight_sfincs' head of tide (its
#: scripts/build_riverbeds_hierarchy_v4.py, whose survey lists these copy). MLW surveys:
#: MLW - MLLW = 0.05 m (Lewes 0.048, Reedy Point 0.055, CO-OPS 1983-2001).
DE_TIDAL_REACHES = {
    "appoquinimink": {"river": "Appoquinimink River", "head": (-75.6831, 39.4344),
                      "note": "head = Noxontown Pond dam", "nos": [("H10200", 0.0)]},
    "blackbird":     {"river": "Blackbird Creek",     "head": (-75.6510, 39.3765),
                      "note": "head = bight's head of tide (no dam)", "nos": [("H10200", 0.0)]},
    "smyrna":        {"river": "Smyrna River",        "head": (-75.6004, 39.2968),
                      "note": "head = Lake Como dam, Smyrna", "nos": [("D00081", 0.0)]},
    "duck":          {"river": "Duck Creek",          "head": (-75.6227, 39.3082),
                      "note": "head = Duck Creek Pond dam"},
    "leipsic":       {"river": "Leipsic River",       "head": (-75.5884, 39.2440),
                      "note": "head = Garrisons Lake dam", "nos": [("H10255", 0.0)]},
    "little_river":  {"river": "Little River",        "head": (-75.4632, 39.1615),
                      "note": "head = Cartanza dam", "ehydro": "Little River", "ehydro_prefix": "LI_"},
    "st_jones":      {"river": "St Jones River",      "head": (-75.5216, 39.1683),
                      "note": "head = Silver Lake dam, Dover", "nos": [("H10079", 0.0)]},
    "murderkill":    {"river": "Murderkill River",    "head": (-75.5105, 38.9889),
                      "note": "head = Coursey Pond dam", "ehydro": "Murderkill River",
                      "ehydro_prefix": "MU_", "nos": [("H10079", 0.0), ("H06254", 0.05)]},
    "mispillion":    {"river": "Mispillion River",    "head": (-75.4330, 38.9113),
                      "note": "head = Silver Lake dam, Milford"},
    "cedar_de":      {"river": "Cedar Creek",         "head": (-75.3774, 38.8691),
                      "note": "head = Swiggetts Pond dam"},
    "broadkill":     {"river": "Broadkill River",     "head": (-75.3129, 38.7773),
                      "note": "head = Wagamons Pond dam, Milton",
                      "nos": [("H09202", 0.05), ("H09203", 0.05), ("H07034", 0.05)]},
}
#: Delaware gauges known to matter (nj_bight_sfincs v4's DE list)
DE_USGS_SITES = {
    "01484085": "Murderkill R. at Bowers (tidal)",
    "01484080": "Murderkill R. at Frederica (tidal)",
    "01483700": "St Jones R. at Dover",
    "01484100": "Beaverdam Br. at Houston (Mispillion)",
}
#: The open-bay HUC12 between the DE frontal units and NJ's ring. NJ's frontal units run out to
#: the state line but Delaware's stop up to ~8 km offshore, so the bay unit (both states) fills
#: the gap: with it the DE ring meets NJ's along the state line (133 km), the line both grids
#: are forced on. Clipped at ``DE_BAY_MAX_LAT`` (Reedy Point, the canal's mouth): north of it
#: the unit is the river beside the Christina basin, outside the DE side.
DE_BAY_HUC12 = "020402040000"
DE_BAY_MAX_LAT = 39.558
#: The C&D Canal unit: NOT in DE_HUC12, but its part SOUTH of the canal (DE land between the
#: canal and Augustine Creek, and its river frontage to Port Penn) is in the DE ring, from
#: data/region/de_canal_south.geojson (scripts/split_canal_unit.py).
DE_CANAL_HUC12 = "020402050705"
# fmt: on


@dataclass(frozen=True)
class Side:
    """Everything that differs between the NJ and DE models. ``files`` = the suffix of the
    side's region files and model names ("" for NJ, which keeps its original names)."""

    key: str
    state: str  # postal abbreviation, also agri_sfincs.fields' state key
    state_fips: str
    huc12: dict
    counties: dict
    counties_fringe: dict
    foreign_fips: dict  # states whose LAND is cut out of the model outline
    tidal_reaches: dict
    usgs_sites: dict
    ref_gauge: str  # the bay gauge that times a storm's peak (FINDINGS §37)
    files: str
    bay_huc12: str = ""  # an open-water HUC12 added to the ring, clipped north at bay_max_lat
    bay_max_lat: float = 90.0


SIDES = {
    "nj": Side("nj", "NJ", STATE_FIPS, HUC12, COUNTIES, COUNTIES_FRINGE, {"42": "PA", "10": "DE"},
               TIDAL_REACHES, USGS_SITES, SHIP_JOHN, ""),
    "de": Side("de", "DE", "10", DE_HUC12, DE_COUNTIES, {}, {"34": "NJ", "42": "PA", "24": "MD"},
               DE_TIDAL_REACHES, DE_USGS_SITES, SHIP_JOHN, "_de", DE_BAY_HUC12, DE_BAY_MAX_LAT),
}  # fmt: skip


def side(key: str = "nj") -> Side:
    if key not in SIDES:
        raise ValueError(f"no side {key!r} (have {sorted(SIDES)})")
    return SIDES[key]
