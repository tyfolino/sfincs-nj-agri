"""County x month x crop-group crop-insurance loss panel, with liability and loss ratios.

Inputs (local only): data/rma/colsom_<year>_NJ.csv (scripts/fetch_rma_col.py) and
data/rma/sobcov_<year>_NJ.csv (scripts/fetch_rma_sob.py). The collaborators' sample in
data/insurance/ is NOT read.

One row per study county (domain.COUNTIES) x calendar year of loss (2003, the first year
COL carries a year of loss, to --end-year) x month of loss (1-12) x crop group
(soybeans, corn, wheat, other, all). The panel is COMPLETE: cells with no COL rows are
zero-filled, so months without losses are explicit zeros.

Losses (Cause of Loss, signed: negative rows are RMA corrections and are kept):
  indemnity_total          all causes, all plans
  indemnity_wet_31_51      causes 31 Excess Moisture/Precip/Rain + 51 Flood (the
                           collaborators' ``indemnity_wet``)
  indemnity_wet_broad      31, 44, 46, 47, 51, 52, 67, 92 (adds cold wet weather,
                           tropical storm, hurricane, low salinity, storm surge)
  indemnity_wet_broad_pp   the prevented-planting part of the broad wet indemnity
  n_policies_wet_31_51 / n_policies_wet_broad
                           SUM of ``policies_indemnified`` over the wet COL rows. A policy
                           paid for two causes, stages or plans in the same cell is counted
                           twice, so this is an upper bound on distinct policies.
  indemnity_other_cy       the part of indemnity_total whose COL commodity year differs
                           from ``liability_commodity_year`` (diagnostic for the rule below)

Liability (Summary of Business, annual, by commodity year):
  The denominator for a cell is the county's SOB liability for the crops in the group in
  ONE commodity year per commodity: the "exposure" commodity year is the calendar year of
  loss, except for fall-seeded small grains (wheat 0011, barley 0091), whose losses in
  September-December belong to the crop planted that fall, i.e. commodity year + 1. COL
  agrees: in the study counties every 2003+ wheat row from October-December has commodity
  year = year of loss + 1, and 4 of 6 September rows do. The rule is applied to every
  cell, zero or not, so a cell's denominator never depends on whether a loss happened.
  ``liability_commodity_year`` is the exposure year of the group's lead crop (wheat for
  "wheat", otherwise the year of loss); in "other" and "all", barley/wheat use year + 1 in
  Sep-Dec inside the sum. Liability in "all" is the sum of the four groups.
  ``liability`` excludes area/index/endorsement plans (GRP, GRIP, ARP/ARH, RI, VI, SCO,
  ECO, STAX, HIP, MP, PACE): they layer extra liability on the same acres and their
  indemnity is coded cause 55, never a wet cause (checked: every NJ COL row of these plans
  is cause 55). ``liability_all_plans`` keeps them and is the denominator of lr_total.

Ratios: lr_wet_31_51 = indemnity_wet_31_51 / liability, lr_wet_broad likewise,
lr_total = indemnity_total / liability_all_plans; NaN where the denominator is 0/missing.

Rows dropped from the panel (counted in the report): COL rows with no year of loss,
month 0 (unknown), county 999 "All Other Counties" (not a study county), and years
outside the panel.

Writes:
  data/rma/loss_panel_county_month.csv
  reports/loss_panel.md      method summary, row counts, coverage and caveats

Usage:  python scripts/build_loss_panel.py [--start-year 2003] [--end-year 2025]
"""

from __future__ import annotations

import argparse
import re

import numpy as np
import pandas as pd

from agri_sfincs import config, domain
from agri_sfincs.report import md_table

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

PANEL_FILE = config.RMA_DIR / "loss_panel_county_month.csv"
REPORT_FILE = config.REPORTS / "loss_panel.md"


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


def write_report(p: pd.DataFrame, col_sel: pd.DataFrame, drop: dict, liab: pd.DataFrame,
                 sob: pd.DataFrame, start: int, end: int) -> str:  # fmt: skip
    L = []
    w = L.append
    nf, ny = p.fips.nunique(), p.year.nunique()
    w("# RMA loss panel: county × month × crop group\n")
    w(f"Built by `scripts/build_loss_panel.py` from `data/rma/colsom_*_NJ.csv` (Cause of Loss) and "
      f"`data/rma/sobcov_*_NJ.csv` (Summary of Business). Output `data/rma/loss_panel_county_month.csv`. "
      f"The collaborators' file in `data/insurance/` is not read.\n")
    w("## Method\n")
    w(f"- **Grid:** {nf} study counties × {ny} calendar years of loss ({start}–{end}) × 12 months × "
      f"5 crop groups (soybeans 0081, corn 0041, wheat 0011, other = every other commodity, all) "
      f"= **{len(p):,} rows**. Every cell is present; cells without COL rows are zeros.")
    w("- **Year/month** are COL's year and month **of loss** (as in the collaborators' sample). "
      "COL has no year of loss before commodity year 2003, so the panel starts in 2003. "
      f"{end + 1} is left out because that calendar year is still being reported.")
    w("- **Wet:** `indemnity_wet_31_51` = causes 31 + 51 (the collaborators' definition); "
      "`indemnity_wet_broad` adds 44, 46, 47, 52, 67, 92. `indemnity_wet_broad_pp` is the "
      "prevented-planting part (stages P, P1–P4, PF, PT, PP, NP). Indemnity is **signed** "
      "(negative COL rows are corrections and are kept), so a cell can be negative.")
    w("- **Policies:** `n_policies_wet_*` sums COL `policies_indemnified` over the wet rows, an "
      "upper bound on distinct policies (one policy paid under two causes, stages or plans counts twice).")
    w("- **Liability (denominator)** comes from the Summary of Business for one commodity year per "
      "commodity: the year of loss, except wheat (0011) and barley (0091) losses in **Sep–Dec**, "
      "which are charged to commodity year **+1** (the crop seeded that fall). The same rule is "
      "used for zero cells, so the denominator does not depend on whether a loss occurred. "
      "`liability_commodity_year` gives the lead crop's year (wheat: +1 in Sep–Dec). "
      "`indemnity_other_cy` holds any indemnity in the cell whose COL commodity year differs "
      "from the rule.")
    w("- **Plans:** `liability` excludes area/index/endorsement plans (GRP, GRIP, RI, SCO, ECO, "
      "STAX, HIP-WI, …). Their indemnity is always cause 55 in NJ COL, never wet, and their "
      "liability double-counts acres already insured by the underlying policy. "
      "`liability_all_plans` keeps them and is the denominator of `lr_total`.")
    w("- Loss ratios = indemnity / liability; NaN where liability is 0.\n")

    w("## Rows dropped\n")
    dd = pd.DataFrame([(k, n, v) for k, (n, v) in drop.items()],
                      columns=["reason", "COL rows", "indemnity $"]).set_index("reason")  # fmt: skip
    w(md_table(dd, "{:,.0f}"))
    w("\nCounty 999 \"All Other Counties\" and non-study counties are outside the panel by "
      "construction.\n")

    w("## Coverage\n")
    a = p[p.crop_group == "all"]
    nz = lambda s: int((s != 0).sum())  # noqa: E731
    by = []
    for g in GROUPS:
        q = p[p.crop_group == g]
        by.append((g, nz(q.indemnity_total), nz(q.indemnity_wet_31_51), nz(q.indemnity_wet_broad),
                   q.indemnity_total.sum(), q.indemnity_wet_broad.sum(),
                   int((q.liability > 0).sum())))  # fmt: skip
    t = pd.DataFrame(by, columns=["crop_group", "cells ≠0 total", "cells ≠0 wet 31+51",
                                  "cells ≠0 wet broad", "total $", "wet broad $",
                                  "cells with liability"]).set_index("crop_group")  # fmt: skip
    w(f"Cells per group: {len(a):,}.\n")
    w(md_table(t, "{:,.0f}"))
    # Loss rows whose cell has no liability.
    orphan = p[(p.indemnity_wet_broad != 0) & ~(p.liability > 0)]
    w(f"\n- Wet (broad) cells with **no liability**: {len(orphan)} "
      f"(${orphan.indemnity_wet_broad.sum():,.0f}); "
      + (", ".join(f"{r.county} {r.year}-{r.month:02d} {r.crop_group}" for r in orphan.itertuples())
         or "none") + ".")
    oc = p[p.crop_group == "all"].indemnity_other_cy
    w(f"- Indemnity whose COL commodity year differs from the rule: ${oc.sum():,.0f} of "
      f"${a.indemnity_total.sum():,.0f} all-cause ({oc.abs().sum() / a.indemnity_total.abs().sum():.1%} "
      f"of absolute $). Most of it is late claims (loss months Feb–Jun charged to the previous "
      f"commodity year) and a few fall row-crop losses filed against the next year.")
    # SOB vs COL indemnity consistency (study counties, panel commodity years).
    s = sob[sob.fips.isin(p.fips.unique()) & sob.commodity_year.between(start, end)]
    c = col_sel
    w(f"- Consistency: SOB indemnity for the study counties, commodity years {start}–{end}, is "
      f"${s.indemnity.sum():,.0f}; COL panel rows sum to ${c.indemnity.sum():,.0f}. "
      "These need not match exactly: COL is keyed by year of loss, and the two files are revised separately.")
    ly = p[(p.crop_group != "all") & (p.month == 6)].pivot_table(
        index="year", columns="crop_group", values="liability", aggfunc="sum") / 1e6
    w("\n**Liability by year (June exposure, $M, three counties summed):**\n")
    w(md_table(ly[[g for g in GROUPS if g in ly.columns]], "{:,.2f}"))
    w("")

    w("## Caveats\n")
    wet = p[(p.crop_group != "all") & (p.indemnity_wet_broad != 0)]
    few = wet.n_policies_wet_broad <= 2
    one = wet.n_policies_wet_broad <= 1
    tot = wet.indemnity_wet_broad.abs().sum()
    w(f"- **Single-policy cells.** Of {len(wet)} county × month × crop-group cells with broad-wet "
      f"indemnity, {few.mean():.0%} involve ≤ 2 indemnified policies (row sums) and "
      f"{one.mean():.0%} only 1. They hold {wet.indemnity_wet_broad[few].abs().sum() / tot:.0%} and "
      f"{wet.indemnity_wet_broad[one].abs().sum() / tot:.0%} of the absolute wet $. Dollar amounts "
      "and loss ratios in those cells reflect one farm's claim; prefer frequency (any wet loss), "
      "pooled crops or multi-month windows, and weight or robustify cell-level regressions.")
    big = (wet.assign(cell=wet.county + " " + wet.year.astype(str) + "-" + wet.month.astype(str).str.zfill(2)
                      + " " + wet.crop_group)
           .nlargest(5, "lr_wet_broad")[["cell", "indemnity_wet_broad", "liability",
                                         "lr_wet_broad", "n_policies_wet_broad"]].set_index("cell"))  # fmt: skip
    w("- Largest wet loss ratios (cells):\n")
    w(md_table(big, "{:,.3f}"))
    w("")
    w("- **Liability is annual and county-wide;** a monthly loss ratio is monthly indemnity over the "
      "whole season's exposure. Sum months for seasonal ratios.")
    w("- **\"other\"** is dominated by nursery and \"All Other Crops\" liability (dollar plans, whole-farm "
      "products), whose losses are rarely weather-by-month. Its liability also has a **structural break**: SOB \"All "
      "Other Crops\" in the study counties is ~$20-24 M a year through 2013 and under $1.1 M from 2014, "
      "so \"other\" (and \"all\") liability drops ~70% in 2014, most likely a change in how a product is reported rather than in "
      "acreage (unverified). Its loss ratios are not comparable to the row crops or across that break.")
    w("- **Commodity-year edges:** Sep–Dec wheat/barley use next-year liability; for the last panel year "
      f"that is commodity year {end + 1}, which RMA is still reporting.")
    w("- **Revisions:** RMA re-posts recent COL and SOB years as claims settle; re-fetch both with "
      "`--refresh` and rebuild.")
    w(f"- **Signed rows:** {int((col_sel.indemnity < 0).sum())} COL rows in the panel are negative "
      f"(${col_sel.indemnity[col_sel.indemnity < 0].sum():,.0f}); they are kept and net within cells.")
    n_neg_t = int((p.indemnity_total < 0).sum())
    n_neg_w = int((p.indemnity_wet_broad < 0).sum())
    n_gt = int((p.indemnity_wet_broad > p.indemnity_total + 0.5).sum())
    w(f"- **Signed values:** {n_neg_t} panel cells have negative total indemnity, {n_neg_w} negative "
      f"broad-wet indemnity, and {n_gt} have wet > total (other causes net negative).")
    w("- **\"all\" includes \"other\"**, so its liability is mostly nursery/dollar-plan exposure; for "
      "a row-crop wet ratio, sum soybeans + corn + wheat instead.")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start-year", type=int, default=2003)
    ap.add_argument("--end-year", type=int, default=2025)
    a = ap.parse_args()
    col_paths = sorted(config.RMA_DIR.glob("colsom_*_NJ.csv"))
    sob_paths = sorted(config.RMA_DIR.glob("sobcov_*_NJ.csv"))
    if not col_paths or not sob_paths:
        raise SystemExit("missing inputs — run scripts/fetch_rma_col.py and scripts/fetch_rma_sob.py")
    fips = list(domain.COUNTIES)
    years = range(a.start_year, a.end_year + 1)
    col = load_col(col_paths)
    sob = load_sob(sob_paths)
    need = {exposure_year("0011", y, 12) for y in years} | set(years)
    have = set(sob.commodity_year.unique())
    if need - have:
        raise SystemExit(f"Summary of Business missing commodity years {sorted(need - have)}")
    col_sel, drop = select_col(col, fips, a.start_year, a.end_year)
    liab = liability_by_commodity(sob, fips)
    p = build_panel(col_sel, liab, fips, years)
    expected = len(fips) * len(years) * 12 * len(GROUPS)
    if len(p) != expected or p.duplicated(["fips", "year", "month", "crop_group"]).any():
        raise RuntimeError(f"panel has {len(p)} rows, expected {expected} unique")
    # The "all" rows must equal the sum of the four groups.
    num = p.select_dtypes("number").columns.difference(
        ["year", "month", "liability_commodity_year", "lr_total", "lr_wet_31_51", "lr_wet_broad"])
    k = ["fips", "year", "month"]
    s4 = p[p.crop_group != "all"].groupby(k)[list(num)].sum()
    sa = p[p.crop_group == "all"].set_index(k)[list(num)]
    if not np.allclose(s4.sort_index().to_numpy(), sa.sort_index().to_numpy(), atol=0.01):
        raise RuntimeError("'all' rows do not equal the sum of the crop groups")
    part = PANEL_FILE.with_suffix(".csv.part")
    p.to_csv(part, index=False, float_format="%.12g")
    part.rename(PANEL_FILE)
    print(f"wrote {PANEL_FILE} ({len(p):,} rows, {p.shape[1]} columns)")
    config.REPORTS.mkdir(exist_ok=True)
    REPORT_FILE.write_text(write_report(p, col_sel, drop, liab, sob, a.start_year, a.end_year))
    print(f"wrote {REPORT_FILE}")


if __name__ == "__main__":
    main()
