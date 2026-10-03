"""Download USDA RMA's public Cause of Loss files (with month of loss), New Jersey only.

Source: RMA's public file server, the "Cause of Loss Historical Data Files"
(rma.usda.gov > Tools & Reports > Summary of Business > Cause of Loss), served from
https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/cause_of_loss/
as ``colsom_<commodity year>.zip`` (1989 onward; the current year is partial). Each zip
holds one pipe-delimited, header-less text file of 30 fields, one row per
state x county x commodity x insurance plan x coverage category x stage x cause of loss
x month/year of loss; the record layout is
``COL_Summary_of_Business_with_Month_All_Years.pdf`` (saved alongside, with the
stage-code listing). RMA re-issues recent years as claims settle (2022-2026 were
re-posted 2026-09-28), so re-fetch recent years with ``--refresh``.

The national files are 40-50 MB unzipped each; only New Jersey rows (state 34) are
kept. Writes data/rma/colsom_<year>_NJ.csv (named columns, whitespace stripped, plus a
5-digit ``fips``) and the two layout PDFs. Existing files are skipped.

Usage:  python scripts/fetch_rma_col.py [--years 1989-2026] [--refresh]
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import zipfile

from agri_sfincs import config, domain
from agri_sfincs.net import download, get

BASE = "https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/cause_of_loss/"
DOCS = ["COL_Summary_of_Business_with_Month_All_Years.pdf", "Stage_Code_Listing.pdf"]

#: The 30 elements of the record layout (layout doc "as of 5/28/2026"), in order.
COLUMNS = [
    "commodity_year", "state_code", "state_abbr", "county_code", "county_name",
    "commodity_code", "commodity_name", "insurance_plan_code", "insurance_plan_abbr",
    "coverage_category", "stage_code", "col_code", "col_desc",
    "month_of_loss", "month_of_loss_name", "year_of_loss",
    "policies_earning_premium", "policies_indemnified", "net_planted_qty",
    "net_endorsed_acres", "liability", "total_premium", "producer_paid_premium",
    "subsidy", "state_private_subsidy", "additional_subsidy", "efa_premium_discount",
    "net_determined_qty", "indemnity", "loss_ratio",
]  # fmt: skip


def available_years() -> list[int]:
    """Commodity years the server lists, from its directory page."""
    return sorted(int(y) for y in set(re.findall(r"colsom_(\d{4})\.zip", get(BASE).text)))


def parse_years(s: str) -> list[int]:
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(y) for y in s.split(",")]


def fetch_year(year: int, refresh: bool) -> str:
    dest = config.RMA_DIR / f"colsom_{year}_NJ.csv"
    if dest.exists() and not refresh:
        return f"{year}: have {dest.name}"
    zpath = config.RMA_DIR / f"colsom_{year}.zip"
    download(f"{BASE}colsom_{year}.zip", zpath)
    n_all = n_nj = 0
    rows = []
    try:
        with zipfile.ZipFile(zpath) as z:
            (name,) = [n for n in z.namelist() if n.lower().endswith(".txt")]
            with z.open(name) as fb:
                for line in io.TextIOWrapper(fb, encoding="latin-1"):
                    n_all += 1
                    f = [v.strip() for v in line.rstrip("\r\n").split("|")]
                    if len(f) != len(COLUMNS):
                        raise RuntimeError(
                            f"{name} line {n_all}: {len(f)} fields, layout has "
                            f"{len(COLUMNS)} — the record layout changed; update COLUMNS"
                        )
                    if f[1] == domain.STATE_FIPS:
                        n_nj += 1
                        rows.append([f[1] + f[3], *f])
    finally:
        zpath.unlink(missing_ok=True)  # the national file is not kept
    part = dest.with_suffix(".csv.part")
    with open(part, "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(["fips", *COLUMNS])
        w.writerows(rows)
    part.rename(dest)
    return f"{year}: wrote {dest.name} ({n_nj:,} NJ of {n_all:,} rows)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", help="e.g. 2000-2025 or 2022,2024 (default: all listed)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch years already present")
    a = ap.parse_args()
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
            print(fetch_year(y, a.refresh), flush=True)
        except (OSError, RuntimeError, zipfile.BadZipFile) as e:
            # requests' exceptions are OSErrors; keep going so one bad year
            # does not cost the rest, and say so at the end.
            print(f"{y}: FAILED {type(e).__name__}: {e}", flush=True)
            failed.append(y)
    if failed:
        raise SystemExit(f"failed years: {failed} — rerun; finished years are skipped")


if __name__ == "__main__":
    main()
