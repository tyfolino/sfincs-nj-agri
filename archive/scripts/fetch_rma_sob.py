"""Download USDA RMA's Summary of Business by state/county/crop/coverage level, per state.

Source: RMA's public file server, "Summary of Business — State/County/Crop with
Coverage Level", https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/state_county_crop/
as ``sobcov_<commodity year>.zip`` (1989 onward; the current and next commodity years are
partial). Each zip holds one pipe-delimited, header-less text file of 28 fields, one row
per state x county x commodity x insurance plan x coverage category x delivery type x
coverage level, with policies sold / earning premium / indemnified, units, quantity
type, net reported quantity (acres when the quantity type is Acres), endorsed acres,
**liability**, total premium, subsidies, indemnity and loss ratio. The record layout is
``SOB_State_County_Crop_with_Coverage_Level_1989_Forward.pdf`` (saved alongside, "as of
5/28/2026"). This is the denominator (liability, premium, acres) for the Cause of Loss
indemnities fetched by archive/scripts/fetch_rma_col.py. RMA re-issues recent years as business
settles (2022-2027 were re-posted 2026-09-28), so re-fetch recent years with ``--refresh``.

The national files are ~25-30 MB unzipped each; only the rows of the requested states
are kept (default NJ, DE, MD, VA, NC). Writes sobcov_<year>_<ST>.csv per state (named
columns, whitespace stripped, plus a 5-digit ``fips``): NJ to data/rma/ exactly as
before, the others to data/rma_states/ (see archive/scripts/fetch_rma_col.py, whose download and
state split this shares), and the layout PDF. Existing state files are skipped.

Usage:  python archive/scripts/fetch_rma_sob.py [--years 1989-2027] [--states NJ,DE,MD,VA,NC] [--refresh]
"""

from __future__ import annotations

import argparse
import re
import zipfile

from agri_sfincs import config
from agri_sfincs.cli import parse_years
from agri_sfincs.net import download, get
from rma import fetch_states, parse_states

BASE = "https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/state_county_crop/"
DOCS = ["SOB_State_County_Crop_with_Coverage_Level_1989_Forward.pdf"]

#: The 28 elements of the record layout (layout doc "as of 5/28/2026"), in order.
COLUMNS = [
    "commodity_year", "state_code", "state_abbr", "county_code", "county_name",
    "commodity_code", "commodity_name", "insurance_plan_code", "insurance_plan_abbr",
    "coverage_category", "delivery_type", "coverage_level",
    "policies_sold", "policies_earning_premium", "policies_indemnified",
    "units_earning_premium", "units_indemnified", "quantity_type",
    "net_reported_qty", "endorsed_companion_acres", "liability", "total_premium",
    "subsidy", "state_private_subsidy", "additional_subsidy", "efa_premium_discount",
    "indemnity", "loss_ratio",
]  # fmt: skip


def available_years() -> list[int]:
    """Commodity years the server lists, from its directory page."""
    return sorted(int(y) for y in set(re.findall(r"sobcov_(\d{4})\.zip", get(BASE).text)))


def parse_line(line: str, where: str = "") -> list[str]:
    """One record split on ``|`` with whitespace stripped; raises if the field count is
    not the layout's (the layout changed, or the file is not a sobcov file)."""
    f = [v.strip() for v in line.rstrip("\r\n").split("|")]
    if len(f) != len(COLUMNS):
        raise RuntimeError(
            f"{where}: {len(f)} fields, layout has {len(COLUMNS)} — the record layout "
            "changed; update COLUMNS"
        )
    return f


def fetch_year(year: int, refresh: bool, states: dict[str, str] | None = None) -> str:
    return fetch_states("sobcov", BASE, COLUMNS, year, states or {"NJ": "34"}, refresh)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", help="e.g. 2000-2025 or 2022,2024 (default: all listed)")
    ap.add_argument("--states", help="comma list of abbreviations (default: NJ,DE,MD,VA,NC)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch years already present")
    a = ap.parse_args()
    states = parse_states(a.states)
    config.RMA_DIR.mkdir(parents=True, exist_ok=True)
    for doc in DOCS:
        if not (config.RMA_DIR / doc).exists():
            download(BASE + doc, config.RMA_DIR / doc)
    listed = available_years()
    years = parse_years(a.years) if a.years else listed
    failed = []
    for y in years:
        if y not in listed:
            print(f"{y}: not on the server (it lists {listed[0]}-{listed[-1]})", flush=True)
            continue
        try:
            print(fetch_year(y, a.refresh, states), flush=True)
        except (OSError, RuntimeError, zipfile.BadZipFile) as e:
            # requests' exceptions are OSErrors; keep going so one bad year
            # does not cost the rest, and say so at the end.
            print(f"{y}: FAILED {type(e).__name__}: {e}", flush=True)
            failed.append(y)
    if failed:
        raise SystemExit(f"failed years: {failed} — rerun; finished years are skipped")


if __name__ == "__main__":
    main()
