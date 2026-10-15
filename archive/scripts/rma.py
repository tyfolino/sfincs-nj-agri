"""USDA RMA public data: the Cause of Loss (colsom) and Summary of Business (sobcov)
files, per state, and the county x month x crop-group loss panel built from them.

Fetching: archive/scripts/fetch_rma_col.py and fetch_rma_sob.py (``fetch_states``). Panel:
archive/scripts/build_loss_panel.py (NJ) and archive/scripts/fork1_panel.py (the Fork 1 states).
data/insurance/ is never read.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd

from agri_sfincs import config, domain
from agri_sfincs.net import download

GROUPS = ["soybeans", "corn", "wheat", "other", "all"]
#: RMA commodity code -> crop group; everything else is "other".
GROUP_OF = {"0081": "soybeans", "0041": "corn", "0011": "wheat"}
#: Fall-seeded small grains: Sep-Dec losses belong to the next commodity year.
FALL_SEEDED = {"0011", "0091"}
FALL_MONTHS = {9, 10, 11, 12}

WET_31_51 = {"31", "51"}
WET_BROAD = {"31", "44", "46", "47", "51", "52", "67", "92"}
#: Prevented-planting stage codes (Stage_Code_Listing.pdf).
PP_STAGES = {"P", "P1", "P2", "P3", "P4", "PF", "PT", "PP", "NP"}
#: Area/index/endorsement plan abbreviations (exact, or as a "XXX-" prefix).
_AREA_PLAN = re.compile(r"^(GRP|GRIP|ARP|ARH|AYP|RI|VI|SCO|ECO|STAX|HIP|MP|PACE)(-|$)")


def norm_code(s: pd.Series, width: int) -> pd.Series:
    """Zero-padded string codes ('31', '0041'), whatever the CSV parser made of them."""
    return s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(width)


def crop_group(commodity_code: str) -> str:
    return GROUP_OF.get(str(commodity_code).zfill(4), "other")


def is_area_plan(abbr: str) -> bool:
    return bool(_AREA_PLAN.match(str(abbr).strip().upper()))


def exposure_year(commodity_code: str, year: int, month: int) -> int:
    """The commodity year whose liability is exposed to a loss in ``year``/``month``."""
    if str(commodity_code).zfill(4) in FALL_SEEDED and int(month) in FALL_MONTHS:
        return int(year) + 1
    return int(year)


def load_col(paths) -> pd.DataFrame:
    df = pd.concat([pd.read_csv(p, dtype=str) for p in paths], ignore_index=True)
    df["commodity_code"] = norm_code(df.commodity_code, 4)
    df["col_code"] = norm_code(df.col_code, 2)
    df["county_code"] = norm_code(df.county_code, 3)
    df["stage_code"] = df.stage_code.fillna("").str.strip().str.upper()
    for c in ("commodity_year", "month_of_loss", "year_of_loss"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("indemnity", "policies_indemnified"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


def load_sob(paths) -> pd.DataFrame:
    df = pd.concat([pd.read_csv(p, dtype=str) for p in paths], ignore_index=True)
    df["commodity_code"] = norm_code(df.commodity_code, 4)
    df["commodity_year"] = pd.to_numeric(df.commodity_year).astype(int)
    for c in ("liability", "total_premium", "net_reported_qty", "policies_earning_premium",
              "indemnity"):  # fmt: skip
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["area_plan"] = df.insurance_plan_abbr.map(is_area_plan)
    return df


def select_col(col: pd.DataFrame, fips, start: int, end: int) -> tuple[pd.DataFrame, dict]:
    """Study-county COL rows usable in the panel, and counts/$ of what was dropped."""
    d = col[col.fips.isin(fips)]
    drop = {}
    recent = d.commodity_year >= start  # pre-2003 rows have no year of loss by design
    m = recent & d.year_of_loss.isna()
    drop["no year of loss (commodity year >= start)"] = (int(m.sum()), d.indemnity[m].sum())
    d = d[~d.year_of_loss.isna()]
    m = d.month_of_loss.fillna(0) == 0
    drop["month 0 / unknown"] = (int(m.sum()), d.indemnity[m].sum())
    d = d[~m]
    m = (d.year_of_loss < start) | (d.year_of_loss > end)
    drop[f"year of loss outside {start}-{end}"] = (int(m.sum()), d.indemnity[m].sum())
    d = d[~m].copy()
    d["year"] = d.year_of_loss.astype(int)
    d["month"] = d.month_of_loss.astype(int)
    d["crop_group"] = d.commodity_code.map(crop_group)
    d["exp_cy"] = [exposure_year(c, y, mo) for c, y, mo in zip(d.commodity_code, d.year, d.month)]
    return d, drop


def aggregate_losses(d: pd.DataFrame) -> pd.DataFrame:
    """COL rows -> fips x year x month x crop_group sums (crop groups plus "all")."""
    wet = d.col_code.isin(WET_31_51)
    wetb = d.col_code.isin(WET_BROAD)
    v = pd.DataFrame({
        "fips": d.fips, "year": d.year, "month": d.month, "crop_group": d.crop_group,
        "indemnity_total": d.indemnity,
        "indemnity_wet_31_51": d.indemnity.where(wet, 0.0),
        "indemnity_wet_broad": d.indemnity.where(wetb, 0.0),
        "indemnity_wet_broad_pp": d.indemnity.where(wetb & d.stage_code.isin(PP_STAGES), 0.0),
        "n_policies_wet_31_51": d.policies_indemnified.where(wet, 0.0),
        "n_policies_wet_broad": d.policies_indemnified.where(wetb, 0.0),
        "indemnity_other_cy": d.indemnity.where(d.commodity_year != d.exp_cy, 0.0),
    })  # fmt: skip
    keys = ["fips", "year", "month", "crop_group"]
    g = v.groupby(keys, as_index=False).sum()
    a = v.assign(crop_group="all").groupby(keys, as_index=False).sum()
    return pd.concat([g, a], ignore_index=True)


def complete_index(fips, years, months=range(1, 13), groups=GROUPS) -> pd.DataFrame:
    """The full fips x year x month x crop_group grid."""
    idx = pd.MultiIndex.from_product(
        [list(fips), list(years), list(months), list(groups)],
        names=["fips", "year", "month", "crop_group"],
    )
    return idx.to_frame(index=False)


def liability_by_commodity(sob: pd.DataFrame, fips) -> pd.DataFrame:
    """fips x commodity_code x commodity_year liability (individual plans and all plans),
    premium, net reported acres and policies earning premium."""
    s = sob[sob.fips.isin(fips)].copy()
    ind = ~s.area_plan
    s["liability_ind"] = s.liability.where(ind, 0.0)
    s["acres"] = s.net_reported_qty.where(ind & (s.quantity_type.str.strip() == "Acres"), 0.0)
    s["policies"] = s.policies_earning_premium.where(ind, 0.0)
    return s.groupby(["fips", "commodity_code", "commodity_year"], as_index=False).agg(
        liability=("liability_ind", "sum"),
        liability_all_plans=("liability", "sum"),
        total_premium=("total_premium", "sum"),
        net_acres=("acres", "sum"),
        policies_earning_premium=("policies", "sum"),
    )


EXPOSURE_COLS = ["liability", "liability_all_plans", "total_premium", "net_acres",
                 "policies_earning_premium"]  # fmt: skip


def panel_exposure(liab: pd.DataFrame, fips, years) -> pd.DataFrame:
    """fips x year x month x crop_group exposure, each commodity at its exposure year."""
    rows = []
    for (f, code), g in liab.groupby(["fips", "commodity_code"]):
        by_cy = g.set_index("commodity_year")[EXPOSURE_COLS]
        grp = crop_group(code)
        for y in years:
            for m in range(1, 13):
                cy = exposure_year(code, y, m)
                if cy in by_cy.index:
                    rows.append((f, y, m, grp, *by_cy.loc[cy].to_numpy()))
    e = pd.DataFrame(rows, columns=["fips", "year", "month", "crop_group", *EXPOSURE_COLS])
    keys = ["fips", "year", "month", "crop_group"]
    g = e.groupby(keys, as_index=False).sum()
    a = e.assign(crop_group="all").groupby(keys, as_index=False).sum()
    return pd.concat([g, a], ignore_index=True)


def build_panel(col_sel: pd.DataFrame, liab: pd.DataFrame, fips, years) -> pd.DataFrame:
    keys = ["fips", "year", "month", "crop_group"]
    p = complete_index(fips, years)
    loss = aggregate_losses(col_sel)
    p = p.merge(loss, on=keys, how="left")
    lcols = [c for c in loss.columns if c not in keys]
    p[lcols] = p[lcols].fillna(0.0)
    exp = panel_exposure(liab, fips, years)
    p = p.merge(exp, on=keys, how="left")
    p[EXPOSURE_COLS] = p[EXPOSURE_COLS].fillna(0.0)
    p.insert(1, "county", p.fips.map(domain.COUNTIES))
    lead_fall = (p.crop_group == "wheat") & p.month.isin(FALL_MONTHS)
    p.insert(5, "liability_commodity_year", p.year + lead_fall.astype(int))

    def ratio(num, den):
        return (num / den.where(den > 0)).astype(float)

    p["lr_total"] = ratio(p.indemnity_total, p.liability_all_plans)
    p["lr_wet_31_51"] = ratio(p.indemnity_wet_31_51, p.liability)
    p["lr_wet_broad"] = ratio(p.indemnity_wet_broad, p.liability)
    order = {g: i for i, g in enumerate(GROUPS)}
    p = p.sort_values(["fips", "year", "month", "crop_group"],
                      key=lambda s: s.map(order) if s.name == "crop_group" else s)  # fmt: skip
    return p.reset_index(drop=True)


def parse_states(s: str | None) -> dict[str, str]:
    """``"NJ,DE"`` -> {"NJ": "34", "DE": "10"}; None -> every state in ``FORK1_STATES``."""
    if not s:
        return dict(domain.FORK1_STATES)
    out = {}
    for ab in (x.strip().upper() for x in s.split(",") if x.strip()):
        if ab not in domain.FORK1_STATES:
            raise SystemExit(f"unknown state {ab!r}; known: {', '.join(domain.FORK1_STATES)}")
        out[ab] = domain.FORK1_STATES[ab]
    return out


def state_csv(prefix: str, year: int, abbr: str) -> Path:
    """Where one state's rows for one year go: NJ in data/rma/ (unchanged), others in
    data/rma_states/."""
    d = config.RMA_DIR if abbr == "NJ" else config.RMA_STATES_DIR
    return d / f"{prefix}_{year}_{abbr}.csv"


def split_states(lines: Iterable[str], codes: Iterable[str], ncols: int,
                 where: str = "") -> tuple[dict[str, list[list[str]]], int]:  # fmt: skip
    """Pipe-delimited RMA records -> {state code: [[fips, *fields], ...]} for the
    requested 2-digit state ``codes`` (field 2 of both layouts), and the number of
    records read. Blank lines are skipped; a record with the wrong field count raises
    (the layout changed)."""
    keep = {c: [] for c in codes}
    n = 0
    for line in lines:
        if not line.strip():
            continue
        n += 1
        f = [v.strip() for v in line.rstrip("\r\n").split("|")]
        if len(f) != ncols:
            raise RuntimeError(
                f"{where} record {n}: {len(f)} fields, layout has {ncols} — the record "
                "layout changed; update COLUMNS"
            )
        rows = keep.get(f[1])
        if rows is not None:
            rows.append([f[1] + f[3], *f])
    return keep, n


def write_csv(dest: Path, columns: list[str], rows: list[list[str]]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".csv.part")
    with open(part, "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(["fips", *columns])
        w.writerows(rows)
    part.rename(dest)


def fetch_states(prefix: str, base: str, columns: list[str], year: int,
                 states: dict[str, str], refresh: bool) -> str:  # fmt: skip
    """Shared by this script and fetch_rma_sob.py: one national ``<prefix>_<year>.zip``
    -> one CSV per requested state that is missing (or all of them with ``refresh``)."""
    todo = {ab: c for ab, c in states.items()
            if refresh or not state_csv(prefix, year, ab).exists()}  # fmt: skip
    if not todo:
        return f"{year}: have {', '.join(states)}"
    zdir = config.DATA_BULK / "rma_zips"
    zpath = zdir / f"{prefix}_{year}.zip"
    download(f"{base}{prefix}_{year}.zip", zpath)
    try:
        with zipfile.ZipFile(zpath) as z:
            (name,) = [n for n in z.namelist() if n.lower().endswith(".txt")]
            with z.open(name) as fb:
                keep, n_all = split_states(io.TextIOWrapper(fb, encoding="latin-1"),
                                           todo.values(), len(columns), name)  # fmt: skip
    finally:
        zpath.unlink(missing_ok=True)  # the national file is not kept
    msg = []
    for ab, code in todo.items():
        write_csv(state_csv(prefix, year, ab), columns, keep[code])
        msg.append(f"{ab} {len(keep[code]):,}")
    return f"{year}: wrote {'; '.join(msg)} of {n_all:,} rows"
