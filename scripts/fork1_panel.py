"""Fork 1: does flooding add crop-insurance damage beyond what rain alone predicts?

A deliberately basic cross-county test of the ag-econ spec
    Damage = b1 * P + b2 * (P x FloodShare) + controls
where identification of b2 comes from counties that differ in a FIXED flood-prone
cropland share, interacted with monthly rain. No SFINCS.

Inputs (all public; data/insurance/ is NOT read):
  data/rma/colsom_*_NJ.csv + data/rma_states/colsom_*_<ST>.csv   Cause of Loss
  data/rma/sobcov_*_NJ.csv + data/rma_states/sobcov_*_<ST>.csv   Summary of Business
      (scripts/fetch_rma_col.py, scripts/fetch_rma_sob.py)
  data/fork1/counties.gpkg            scripts/fork1_counties.py
  data/fork1/prism_county_monthly.csv scripts/fetch_prism_monthly.py
  data/fork1/flood_prone_share.csv    scripts/flood_prone_share.py

Panel: county x calendar month of loss, 2003 (COL's first year of loss) to 2025.
  ind_wet_broad / ind_wet_31_51  water indemnity, all crops, cause sets of
      scripts/build_loss_panel.py (WET_BROAD: 31, 44, 46, 47, 51, 52, 67, 92; WET_31_51:
      31 Excess Moisture + 51 Flood); cell sums of signed COL rows, clipped at 0.
  liability  SOB liability of individual (non-area) plans, all crops, each commodity at
      its exposure commodity year (wheat/barley Sep-Dec -> +1), as build_loss_panel.py.
  *_row      the same for corn + soybeans + wheat only.
  ppt_mm     PRISM monthly precipitation, cropland-weighted county mean.
  share_*    fixed flood-prone cropland shares; ``share_flood`` is NFHL 1% SFHA where the
      NFHL covers >= 90% of the county's cropland, else the scaled relief fallback.
Cells with no liability are dropped from the models.

Models (``agri_sfincs.panel.fit_fe_glm``): FE for county (absorbs the share's main
effect), month of year and year.
  PPML     E[indemnity] = liability * exp(b1 P + b2 P x share + FE)  (P per 100 mm)
  two-part logit Pr(indemnity > $1,000) with the same FE, and PPML on the loss cells
  variants: 31+51 outcome, coastal-plain counties only, NFHL-only counties with the raw
      SFHA share, the relief share, state x year FE, without NC (most of the dollars),
      row crops, and rain EXTREMES (P above the county's 90th percentile for that
      calendar month).
Inference: leave-one-year-out jackknife SEs, t with (years - 1) df. The two-way
(county, year) and county-only sandwich SEs are reported too; both are too small here
(a few hurricane months dominate the dollars).
Power: analytic from the jackknife SE, and simulated: the main PPML re-estimated on
``--sims`` panels per true b2 with y* = mu(b2_true) x (y / mu_hat) of the same county and
month in a randomly permuted year (keeps the overdispersion, zeros and within-year
cross-county correlation, breaks any link to rain), rejecting when |b2_hat| exceeds the
95th percentile of the b2 = 0 draws (both centred on the null draws' median). MDE80 = the
true b2 with 80% power.

Writes:
  data/fork1/panel_county_month.csv.gz
  data/fork1/estimates.csv, data/fork1/power.csv
  reports/fork1_flood_rain.md

Usage:  python scripts/fork1_panel.py [--start-year 2003] [--end-year 2025] [--sims 100]
"""

from __future__ import annotations

import argparse

import build_loss_panel as blp
import geopandas as gpd
import numpy as np
import pandas as pd
from fetch_rma_col import STATES

from agri_sfincs import config
from agri_sfincs.panel import cluster_vcov, fit_fe_glm
from agri_sfincs.report import md_table

PANEL = config.FORK1_DIR / "panel_county_month.csv.gz"
EST = config.FORK1_DIR / "estimates.csv"
POWER = config.FORK1_DIR / "power.csv"
REPORT = config.REPORTS / "fork1_flood_rain.md"
ROW_GROUPS = {"corn", "soybeans", "wheat"}
ANY_LOSS = 1000.0  # $: the two-part model's "any loss" threshold (as FINDINGS §13)


def rma_paths(prefix: str, years) -> list:
    """NJ from data/rma/, the other Fork 1 states from data/rma_states/."""
    out = []
    for ab in STATES:
        d = config.RMA_DIR if ab == "NJ" else config.RMA_STATES_DIR
        for y in years:
            p = d / f"{prefix}_{y}_{ab}.csv"
            if not p.exists():
                raise SystemExit(f"missing {p} — run scripts/fetch_rma_{'col' if prefix == 'colsom' else 'sob'}.py")
            out.append(p)
    return out


def exposure(liab: pd.DataFrame) -> pd.DataFrame:
    """fips x year x month liability (all crops and row crops), each commodity at its
    exposure commodity year — a vectorized ``build_loss_panel.panel_exposure``."""
    lb = liab[["fips", "commodity_code", "commodity_year", "liability"]].copy()
    lb["row"] = lb.commodity_code.map(blp.crop_group).isin(ROW_GROUPS)
    lb["fall"] = lb.commodity_code.isin(blp.FALL_SEEDED)
    e = lb.merge(pd.DataFrame({"month": range(1, 13)}), how="cross")
    e["year"] = e.commodity_year - (e.fall & e.month.isin(blp.FALL_MONTHS)).astype(int)
    e["liability_row"] = e.liability.where(e.row, 0.0)
    return e.groupby(["fips", "year", "month"], as_index=False)[["liability", "liability_row"]].sum()


def losses(col_sel: pd.DataFrame) -> pd.DataFrame:
    a = blp.aggregate_losses(col_sel)
    keys = ["fips", "year", "month"]
    cols = {"indemnity_wet_broad": "ind_wet_broad", "indemnity_wet_31_51": "ind_wet_31_51",
            "indemnity_total": "ind_total"}  # fmt: skip
    al = a[a.crop_group == "all"].set_index(keys)[list(cols)].rename(columns=cols)
    rw = a[a.crop_group.isin(ROW_GROUPS)].groupby(keys)[list(cols)].sum()
    rw.columns = [cols[c] + "_row" for c in rw.columns]
    return al.join(rw, how="outer").fillna(0.0).reset_index()


def build(start: int, end: int) -> tuple[pd.DataFrame, dict]:
    counties = gpd.read_file(config.FORK1_DIR / "counties.gpkg", ignore_geometry=True)
    fips = counties.fips.tolist()
    col = blp.load_col(rma_paths("colsom", range(start, end + 2)))
    sob = blp.load_sob(rma_paths("sobcov", range(start, end + 2)))
    col_sel, drop = blp.select_col(col, fips, start, end)
    p = pd.MultiIndex.from_product([fips, range(start, end + 1), range(1, 13)],
                                   names=["fips", "year", "month"]).to_frame(index=False)  # fmt: skip
    p = p.merge(losses(col_sel), on=["fips", "year", "month"], how="left")
    p = p.merge(exposure(blp.liability_by_commodity(sob, fips)), on=["fips", "year", "month"],
                how="left").fillna(0.0)  # fmt: skip
    for c in [c for c in p.columns if c.startswith("ind_")]:
        p[c] = p[c].clip(lower=0.0)  # net-negative cells are corrections
    pr = pd.read_csv(config.FORK1_DIR / "prism_county_monthly.csv", dtype={"fips": str})
    p = p.merge(pr[["fips", "year", "month", "ppt_mm"]], on=["fips", "year", "month"], how="left")
    sh = pd.read_csv(config.FORK1_DIR / "flood_prone_share.csv", dtype={"fips": str})
    p = p.merge(sh[["fips", "share_flood", "share_sfha", "share_low2m", "share_source",
                    "nfhl_coverage", "crop_km2"]], on="fips", how="left")  # fmt: skip
    p = p.merge(counties[["fips", "state_abbr", "name", "coastal_plain"]], on="fips")
    q90 = p.groupby(["fips", "month"]).ppt_mm.transform(lambda s: s.quantile(0.9))
    p["ppt_extreme"] = (p.ppt_mm > q90).astype(float)
    return p, drop


def design(d: pd.DataFrame, share: str, rain: str = "P") -> np.ndarray:
    if rain == "P":
        x = d.ppt_mm.to_numpy() / 100.0
    else:
        x = d.ppt_extreme.to_numpy()
    return np.column_stack([x, x * d[share].to_numpy()])


def fe_keys(d: pd.DataFrame, state_year: bool = False) -> list:
    yr = d.state_abbr + d.year.astype(str) if state_year else d.year
    return [d.fips.to_numpy(), d.month.to_numpy(), np.asarray(yr)]


SPECS = [
    # name, sample, outcome, liability column, share, rain ("P" or "X" extremes), state x year FE
    ("main: broad water, all counties", "all", "ind_wet_broad", "liability", "share_flood", "P", False),
    ("31+51 only", "all", "ind_wet_31_51", "liability", "share_flood", "P", False),
    ("coastal-plain counties", "coastal", "ind_wet_broad", "liability", "share_flood", "P", False),
    ("NFHL-covered, raw SFHA share", "nfhl", "ind_wet_broad", "liability", "share_sfha", "P", False),
    ("relief share (<2 m above local low)", "all", "ind_wet_broad", "liability", "share_low2m", "P", False),
    ("state x year FE", "all", "ind_wet_broad", "liability", "share_flood", "P", True),
    ("without North Carolina", "noNC", "ind_wet_broad", "liability", "share_flood", "P", False),
    ("row crops (corn, soy, wheat)", "row", "ind_wet_broad_row", "liability_row", "share_flood", "P", False),
    ("rain extremes (P > county-month p90)", "all", "ind_wet_broad", "liability", "share_flood", "X", False),
    ("rain extremes, 31+51", "all", "ind_wet_31_51", "liability", "share_flood", "X", False),
]  # fmt: skip
TWO_PART = {"main: broad water, all counties", "31+51 only"}


def sample(p: pd.DataFrame, which: str) -> pd.DataFrame:
    ok = p.ppt_mm.notna() & p.share_flood.notna()
    if which == "row":
        return p[ok & (p.liability_row > 0)]
    d = p[ok & (p.liability > 0)]
    return {"all": d, "coastal": d[d.coastal_plain], "nfhl": d[d.share_source == "nfhl"],
            "noNC": d[d.state_abbr != "NC"]}[which]  # fmt: skip


def clusters(d: pd.DataFrame) -> list:
    """Two-way clustering, county and year (losses and rain move together across counties
    within a year)."""
    return [d.fips.to_numpy(), d.year.to_numpy()]


def fit_part(d, y, L, sh, rain, sy, part: str) -> dict:
    """One model: ``part`` = "ppml" (all cells), "logit" (loss > ANY_LOSS) or "positive"
    (PPML on loss cells only)."""
    if part == "positive":
        d = d[d[y] > ANY_LOSS]
    X = design(d, sh, rain)
    if part == "logit":
        return fit_fe_glm((d[y].to_numpy() > ANY_LOSS).astype(float), X, fe_keys(d, sy),
                          clusters(d), family="logit")  # fmt: skip
    return fit_fe_glm(d[y].to_numpy(), X, fe_keys(d, sy), clusters(d), offset=np.log(d[L].to_numpy()))


def jackknife_year(d, *args) -> np.ndarray:
    """Leave-one-year-out jackknife SEs of (b1, b2): no sandwich involved, and robust to
    the within-year correlation and the few catastrophic months that dominate the
    dollar-weighted fit. In a synthetic check (heavy-tailed compound-Poisson dollars with
    year x month shocks, 23 years) it gave 0.28 against a true sampling SD of 0.26, where
    the two-way sandwich gave 0.23 and rejected a true null 13% of the time."""
    bs = np.array([fit_part(d[d.year != yr], *args)["beta"] for yr in sorted(d.year.unique())])
    G = len(bs)
    return np.sqrt((G - 1) / G * ((bs - bs.mean(axis=0)) ** 2).sum(axis=0))


def run_models(p: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    from scipy.stats import t as student_t

    rows, fits = [], {}
    for name, which, y, L, sh, rain, sy in SPECS:
        d = sample(p, which)
        parts = ["ppml", "logit", "positive"] if name in TWO_PART else ["ppml"]
        for part in parts:
            args = (y, L, sh, rain, sy, part)
            r = fit_part(d, *args)
            dk = (d[d[y] > ANY_LOSS] if part == "positive" else d)[r["keep"]]
            u = (dk[y].to_numpy() > ANY_LOSS).astype(float) if part == "logit" else dk[y].to_numpy()
            se_c = np.sqrt(np.diag(cluster_vcov(r["Xt"], r["w"], u - r["mu"], dk.fips.to_numpy())))
            jk = jackknife_year(d, *args)
            G = d.year.nunique()
            b = r["beta"]
            s = dk[sh].to_numpy()
            rows.append({
                "spec": name, "model": {"ppml": "PPML", "logit": f"two-part: logit P(loss > ${ANY_LOSS:,.0f})",
                                        "positive": "two-part: PPML on loss months"}[part],
                "rain": "P per 100 mm" if rain == "P" else "1{P > p90}",
                "b1": b[0], "se_b1": jk[0], "b2": b[1], "se_b2": jk[1], "t_b2": b[1] / jk[1],
                "p_b2": 2 * student_t.sf(abs(b[1] / jk[1]), G - 1),
                "se_b2_twoway": r["se"][1], "se_b2_county": se_c[1],
                "n": r["n"], "counties": r["n_clusters"], "years": G,
                "share_p10": np.quantile(s, 0.1), "share_p90": np.quantile(s, 0.9),
                "converged": r["converged"]})  # fmt: skip
            if part == "ppml":
                fits[name] = (r, d, y, L, sh, rain, sy)
            print(f"  {name} / {part}: b2 = {b[1]:+.3f} (jk {jk[1]:.3f})", flush=True)
    return pd.DataFrame(rows), fits


def simulate(fit, b2_true: float, sims: int, rng) -> pd.DataFrame:
    """Re-estimate a PPML spec on ``sims`` simulated panels with true b2 = ``b2_true``:
    y* = mu(b2_true) x (y / mu_hat) taken from the same county and month in a randomly
    permuted year (one permutation per draw, shared by all counties and months), so the
    real overdispersion, zeros and within-year cross-county correlation are kept and any
    link to this year's rain is broken. Returns b2_hat and its two-way z per draw."""
    r, d, y, L, sh, rain, sy = fit
    dk = d[r["keep"]].reset_index(drop=True)
    X = design(dk, sh, rain)
    mu = r["mu"]
    ratio = dk[y].to_numpy() / mu
    yrs = np.sort(dk.year.unique())
    yi = np.searchsorted(yrs, dk.year.to_numpy())
    lookup = pd.Series(ratio, index=pd.MultiIndex.from_arrays([dk.fips, dk.month, yi]))
    off = np.log(dk[L].to_numpy())
    fk, cl = fe_keys(dk, sy), clusters(dk)
    mu_true = mu * np.exp((b2_true - r["beta"][1]) * X[:, 1])
    out = []
    for _ in range(sims):
        perm = rng.permutation(len(yrs))
        rr = lookup.reindex(pd.MultiIndex.from_arrays([dk.fips, dk.month, perm[yi]])).to_numpy()
        rr = np.where(np.isfinite(rr), rr, ratio)  # hole in the permuted year: own ratio
        f = fit_fe_glm(mu_true * rr, X, fk, cl, offset=off)
        out.append((f["beta"][1], f["beta"][1] / f["se"][1]))
    return pd.DataFrame(out, columns=["b2_hat", "z"])


def power(fit, se_jk: float, sims: int, mults=(1.0, 2.0, 3.0, 4.0), seed: int = 1) -> pd.DataFrame:
    """Power to reject b2 = 0 at true b2 = mult x the jackknife SE:
    ``power_jk``  analytic, a two-sided 5% t-test (G-1 df) with the jackknife SE;
    ``power_sim`` simulated (``simulate``), rejecting when |b2_hat - c| exceeds the 95th
                  percentile of |b2_hat - c| in the b2 = 0 draws, c = their median (the
                  permuted-residual draws are shifted by a roughly constant amount; exact
                  size, no SE);
    ``size_twoway`` the rejection rate of |z| > 1.96 with the two-way sandwich SE."""
    from scipy.stats import nct, t as student_t

    rng = np.random.default_rng(seed)
    G = fit[1].year.nunique()
    tc = student_t.ppf(0.975, G - 1)
    null = simulate(fit, 0.0, sims, rng)
    c0 = float(null.b2_hat.median())
    crit_b = float(np.quantile((null.b2_hat - c0).abs(), 0.95))
    rows = []
    for m in (0.0, *mults):
        dr = null if m == 0 else simulate(fit, m * se_jk, sims, rng)
        pj = float(nct.sf(tc, G - 1, m) + nct.cdf(-tc, G - 1, m))
        rows.append({"mult_se": m, "b2_true": m * se_jk, "power_jk": pj,
                     "power_sim": float(((dr.b2_hat - c0).abs() > crit_b).mean()),
                     "size_twoway": float((dr.z.abs() > 1.96).mean()),
                     "mean_b2_hat": float(dr.b2_hat.mean()), "sd_b2_hat": float(dr.b2_hat.std()),
                     "null_median_b2": c0, "crit_b2": crit_b, "sims": sims})  # fmt: skip
        print(f"  b2 = {m:.0f} x jk SE: analytic {pj:.2f}, simulated {rows[-1]['power_sim']:.2f}",
              flush=True)  # fmt: skip
    return pd.DataFrame(rows)


def mde80(pw: pd.DataFrame, col: str) -> float:
    """Smallest b2 with 80% power, by linear interpolation of the power curve."""
    pw = pw.sort_values("b2_true").reset_index(drop=True)
    above = pw.index[pw[col] >= 0.8]
    if not len(above):
        return float("nan")
    i = above[0]
    if i == 0:
        return float(pw.b2_true[0])
    p0, p1, b0, b1 = pw[col][i - 1], pw[col][i], pw.b2_true[i - 1], pw.b2_true[i]
    return float(b0 + (0.8 - p0) * (b1 - b0) / (p1 - p0))


def write_report(p, est, pw, drop, start, end) -> str:
    L = []
    w = L.append
    base = p[p.liability > 0]
    sh = p.drop_duplicates("fips")
    m = est.iloc[0]
    sp = m.share_p90 - m.share_p10
    mde_jk, mde_sim = mde80(pw, "power_jk"), mde80(pw, "power_sim")
    w("# Fork 1: does flooding add crop-insurance losses beyond rain? (pilot)\n")
    w("*Pilot memo for the ag-econ collaborators, built by `scripts/fork1_panel.py` "
      f"({pd.Timestamp.today():%Y-%m-%d}). Public data only (RMA, PRISM, FEMA, CDL); the "
      "collaborators' loss tables in `data/insurance/` were not used.*\n")
    w("## The question and the design\n")
    w("Spec: **Damage = b1·P + b2·(P × FloodShare) + controls**. In three NJ counties b2 cannot "
      "be estimated with any precision (FINDINGS §13, §20), so this pilot pools every county of "
      "NJ, DE, MD, VA and NC and lets b2 come from counties that differ in a **fixed** "
      "flood-prone cropland share. If flooding (not just wetness) drives losses, the same "
      "extra 100 mm of rain should raise losses MORE where more cropland sits in the floodplain.\n")
    w("- **Outcome:** monthly water indemnity per county, all crops (RMA Cause of Loss, year/month "
      f"of loss {start}–{end}): broad water causes (31 excess moisture, 44 cold wet weather, "
      "46/47 tropical storm & hurricane, 51 flood, 52, 67 storm surge, 92) and, as a check, "
      "31 + 51 only. Exposure: the county's insured liability that season (RMA Summary of "
      "Business), entered as an offset, so the model is about the **loss ratio**.")
    w("- **Rain:** PRISM monthly precipitation (4 km), averaged over each county's cropland "
      "(2023 CDL).")
    w("- **FloodShare:** share of the county's cropland inside FEMA's 1% annual-chance flood zone "
      "(NFHL zones A*/V*), fixed over time. Where the digital FEMA maps cover < 90% of a "
      "county's cropland, a relief proxy (cropland < 2 m above the lowest ground within 1 km, "
      "3DEP DEM) rescaled to FEMA units is used instead and flagged.")
    w("- **Model:** Poisson pseudo-maximum likelihood (PPML) with county fixed effects (absorbing "
      "each county's own level, including the share's main effect), month-of-year effects "
      "(seasonality) and year effects (region-wide bad years). b1 and b2 are semi-elasticities: "
      "b1 = change in log expected loss per +100 mm in a county with no floodplain cropland; "
      "b2 = how much that response grows per unit (0 → 100%) of FloodShare. Also a two-part "
      "version (logit for any loss > $1,000, then PPML on loss months).")
    top1 = base.ind_wet_broad.nlargest(int(len(base) * 0.01)).sum() / base.ind_wet_broad.sum()
    ev = (base.groupby(["state_abbr", "year", "month"]).ind_wet_broad.sum().nlargest(5) / 1e6)
    evs = ", ".join(f"{st} {y}-{mo:02d} (${v:,.0f} M)" for (st, y, mo), v in ev.items())
    w(f"- **Uncertainty:** standard errors are leave-one-year-out jackknife SEs (p-values from "
      f"t with {int(m.years) - 1} df). The top 1% of county-months hold {top1:.0%} of the water "
      f"dollars (largest state-months: {evs}), losses move together across counties within a "
      "year, and the usual sandwich SEs (shown for comparison) are too small: for b2 in the main "
      f"model the two-way county × year sandwich is {m.se_b2_twoway / m.se_b2:.0%} of the "
      f"jackknife SE and county-only clustering {m.se_b2_county / m.se_b2:.0%}.\n")
    w("## Data coverage\n")
    by = sh.groupby("state_abbr").agg(counties=("fips", "size"),
                                       coastal_plain=("coastal_plain", "sum"),
                                       cropland_km2=("crop_km2", "sum"),
                                       nfhl_fallback=("share_source", lambda s: int((s != "nfhl").sum())),
                                       share_sfha_median=("share_sfha", "median"),
                                       share_flood_p90=("share_flood", lambda s: s.quantile(0.9)))  # fmt: skip
    insured = base.groupby("state_abbr").agg(
        insured_counties=("fips", "nunique"),
        loss_months=("ind_wet_broad", lambda s: int((s > ANY_LOSS).sum())),
        wet_indemnity_musd=("ind_wet_broad", lambda s: s.sum() / 1e6),
        liability_musd_yr=("liability", lambda s: s.sum() / 12 / (end - start + 1) / 1e6))
    w(md_table(by.join(insured), "{:,.2f}"))
    top = base.ind_wet_broad.nlargest(int(len(base) * 0.01)).sum() / base.ind_wet_broad.sum()
    w(f"\nCounty-months with insured liability: {len(base):,} of {len(p):,} "
      f"({base.fips.nunique()} counties × {end - start + 1} years × 12 months). Broad-water "
      f"indemnity > $1,000 in {(base.ind_wet_broad > ANY_LOSS).mean():.1%} of them; total "
      f"${base.ind_wet_broad.sum() / 1e9:,.2f} B (31+51 only: ${base.ind_wet_31_51.sum() / 1e9:,.2f} B); "
      f"the largest 1% of county-months hold {top:.0%} of it.")
    q = sh.share_flood.quantile([0.1, 0.5, 0.9])
    shf = pd.read_csv(config.FORK1_DIR / "flood_prone_share.csv", dtype={"fips": str})
    vint = pd.to_datetime(shf[shf.fips.isin(base.fips)].eff_date_max)
    w(f"FloodShare across counties: 10th pct {q[0.1]:.1%}, median {q[0.5]:.1%}, 90th pct "
      f"{q[0.9]:.1%}. NFHL digital maps cover ≥ 90% of the cropland in "
      f"{int((sh.share_source == 'nfhl').sum())} of {len(sh)} counties; "
      + (f"the relief fallback is used for {', '.join(fb.name + ' ' + fb.state_abbr for fb in sh[sh.share_source != 'nfhl'].itertuples())}"
         f" ({int(sh[sh.share_source != 'nfhl'].fips.isin(base.fips).sum())} of them insured).\n"
         if (sh.share_source != "nfhl").any() else "no county needs the relief fallback.\n"))
    if drop:
        w("COL rows dropped (no year of loss, month unknown, out of window): " + "; ".join(
            f"{k}: {n:,} rows (${v:,.0f})" for k, (n, v) in drop.items()) + ".\n")

    w("## Estimates\n")
    e = est.copy()
    e["b1 (SE)"] = [f"{b:+.3f} ({s:.3f})" for b, s in zip(e.b1, e.se_b1)]
    e["b2 (SE)"] = [f"{b:+.3f} ({s:.3f})" for b, s in zip(e.b2, e.se_b2)]
    e["p(b2)"] = e.p_b2.map("{:.2f}".format)
    e["SE(b2) 2-way sandwich"] = e.se_b2_twoway.map("{:.3f}".format)
    e["SE(b2) county sandwich"] = e.se_b2_county.map("{:.3f}".format)
    e["n"] = e.n.map("{:,}".format)
    w(md_table(e.set_index(["spec", "model"])[["rain", "b1 (SE)", "b2 (SE)", "p(b2)",
                                               "SE(b2) 2-way sandwich", "SE(b2) county sandwich",
                                               "n", "counties"]]))  # fmt: skip
    w("\nb1 per +100 mm of monthly rain (or per month above the county's 90th percentile for "
      "that calendar month, in the \"extremes\" rows); b2 per unit FloodShare (0 → 1); (SE) = "
      "year-jackknife. The relief row uses the relief share in place of FloodShare, so its b2 "
      "is on that scale.")
    w(f"\nReading the main row: +100 mm of monthly rain raises expected water losses by "
      f"{np.expm1(m.b1):+.0%} in a county with no floodplain cropland; moving from a 10th- to a "
      f"90th-percentile FloodShare county ({m.share_p10:.1%} → {m.share_p90:.1%} of cropland) "
      f"changes that response by {m.b2 * sp:+.3f} log points (95% CI "
      f"{(m.b2 - 2.07 * m.se_b2) * sp:+.3f} to {(m.b2 + 2.07 * m.se_b2) * sp:+.3f}).\n")

    w("## Power\n")
    n0 = pw.iloc[0]
    w("How large would b2 have to be for this panel to detect it (two-sided 5% test, 80% power)? "
      "Two answers:\n")
    w("- **Analytic**, from the jackknife SE (t test).")
    w(f"- **Simulated**: the main PPML re-estimated on {int(n0.sims)} simulated panels per true "
      "b2. Each keeps the fitted rain and seasonal structure, imposes the true b2, and borrows the "
      "real model's multiplicative residuals (y / fitted) from a randomly permuted year, so the "
      "simulated losses are as lumpy, zero-heavy and cross-county-correlated as the real ones. "
      f"The draws are shifted (median b2 {n0.null_median_b2:+.2f} at a true 0), so a draw rejects "
      "when its distance from that median exceeds the 95th percentile of the b2 = 0 draws. This "
      "is conservative: in a synthetic check (heavy-tailed losses, known truth) the "
      "permuted-residual draws spread ~1.7× wider than the true sampling distribution, while the "
      "jackknife SE was within 10% of it.\n")
    t = pw.assign(**{"true b2": pw.b2_true.map("{:.3f}".format),
                     "effect at p90 − p10 share": (pw.b2_true * sp).map("{:+.3f}".format),
                     "power, analytic": pw.power_jk.map("{:.0%}".format),
                     "power, simulated": pw.power_sim.map("{:.0%}".format),
                     "mean simulated b2": pw.mean_b2_hat.map("{:+.3f}".format),
                     "2-way sandwich |z|>1.96": pw.size_twoway.map("{:.0%}".format),
                     }).set_index("mult_se")  # fmt: skip
    w(md_table(t[["true b2", "effect at p90 − p10 share", "power, analytic", "power, simulated",
                  "mean simulated b2", "2-way sandwich |z|>1.96"]]))  # fmt: skip

    def fmt(v):
        return (f"b2 ≈ {v:.2f} ({np.expm1(v * sp):+.0%} in the per-100-mm response between a "
                "10th- and a 90th-percentile FloodShare county)") if np.isfinite(v) else \
            f"b2 > {pw.b2_true.max():.2f} (80% not reached on the grid)"

    w(f"\n- **MDE80, analytic: {fmt(mde_jk)}**; simulated (conservative): {fmt(mde_sim)}.")
    w(f"- With no true effect, the two-way sandwich z-test rejects in {n0.size_twoway:.0%} of the "
      "simulated panels (nominal 5%) — why it is not used for inference here.")
    w(f"- For scale, b1 (the rain response itself) is {m.b1:.2f} ± {m.se_b1:.2f}.\n")

    w("## Caveats\n")
    w("- **Cause coding is not a flood measure.** Adjusters code the dominant cause; \"excess "
      "moisture\" (31) covers ponding, saturated soils and late planting, \"flood\" (51) river "
      "overflow, and hurricanes/tropical storms (46/47) bundle wind with water. The broad set "
      "mixes all of these, and 31+51 drops hurricane-coded water damage.")
    w("- **Liability denominators** are annual and county-wide (individual plans, all crops), "
      "so monthly ratios divide one month's losses by the whole season's exposure; \"all crops\" "
      "includes nursery and dollar plans whose exposure is not weather-by-month (the row-crop "
      "variant checks this).")
    w("- **FEMA maps:** the NFHL is today's effective map, of mixed vintage (newest FIRM panel per "
      f"county: median {vint.dt.year.median():.0f}, range {vint.dt.year.min():.0f}–{vint.dt.year.max():.0f}; "
      "see `data/fork1/flood_prone_share.csv`), drawn for insurance on structures and mostly along "
      "mapped streams. It misses small-ditch and field ponding, which FINDINGS §20 suggests drives "
      "most NJ water losses. Zone A (approximate) and AE (detailed) are pooled.")
    w("- **Static share:** one CDL year (2023) and one map for 2003–2025; cropland moved and maps "
      "were redrawn over the period. The CDL \"cropland\" mask includes hay, which dominates "
      "upland VA. Shares are cropland shares, not insured-acre shares.")
    w("- **Cross-county identification:** b2 compares floodplain-heavy with floodplain-light "
      "counties. Anything else that differs between them and also changes the rain response "
      "(soils and drainage tile, crop mix, coastal hurricanes, insurance take-up) loads onto b2. "
      "County FE absorb levels, not slopes. The state × year and coastal-plain variants are "
      "partial checks only.")
    nc = base.state_abbr == "NC"
    w(f"- **Dollar weighting:** PPML weights county-months by their dollars. North Carolina "
      f"holds {base.ind_wet_broad[nc].sum() / base.ind_wet_broad.sum():.0%} of the broad water "
      f"indemnity and {base.liability[nc].sum() / base.liability.sum():.0%} of the liability, so "
      "the pooled estimate is largely an NC estimate; the \"without North Carolina\" row shows "
      "the rest (and is much less precise).")
    w("- **PRISM** recent months use a newer dataset (AN91) than earlier ones (AN81); year FE "
      "absorb a common shift, not county-specific ones.")
    w("- **2003 start:** RMA Cause of Loss has no year of loss before commodity year 2003.\n")

    w("## Bottom line\n")
    rc = est[(est.spec == "row crops (corn, soy, wheat)") & (est.model == "PPML")].iloc[0]
    sig = est[(est.p_b2 < 0.05) & (est.index > 0)]
    others = [f"{r.spec} / {r.model}: b2 = {r.b2:+.2f}, p = {r.p_b2:.2f}" for r in sig.itertuples()]
    verdict = ("is NOT detectably larger" if m.p_b2 >= 0.05 else
               ("IS larger" if m.b2 > 0 else "is SMALLER"))
    w(f"Across {base.fips.nunique()} insured counties in five states, monthly rain strongly "
      f"predicts water losses (+100 mm ≈ {np.expm1(m.b1):+.0%}), but the rain response "
      f"{verdict} where more cropland lies in the FEMA 1% floodplain (b2 = {m.b2:+.2f} ± "
      f"{m.se_b2:.2f}, p = {m.p_b2:.2f}; "
      + ("variants with p < 0.05: " + "; ".join(others) if others else
         "no variant reaches p < 0.05") + "). "
      f"The test is weak: only an effect of about {fmt(mde_jk)} would be detected reliably, "
      "so a modest flood amplification cannot be ruled out. A sharper test needs a flood "
      "measure that varies month to month (modelled or observed inundation, e.g. SFINCS or "
      "satellite flood maps) instead of a fixed map share.")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start-year", type=int, default=2003)
    ap.add_argument("--end-year", type=int, default=2025)
    ap.add_argument("--sims", type=int, default=100)
    a = ap.parse_args()
    p, drop = build(a.start_year, a.end_year)
    p.to_csv(PANEL, index=False, float_format="%.6g")
    print(f"wrote {PANEL} ({len(p):,} rows)")
    est, fits = run_models(p)
    est.to_csv(EST, index=False, float_format="%.6g")
    print(est[["spec", "model", "b1", "se_b1", "b2", "se_b2", "p_b2", "se_b2_twoway"]].to_string())
    pw = power(fits[est.spec.iloc[0]], est.se_b2.iloc[0], sims=a.sims)
    pw.to_csv(POWER, index=False, float_format="%.6g")
    REPORT.write_text(write_report(p, est, pw, drop, a.start_year, a.end_year))
    print(f"wrote {EST}, {POWER}, {REPORT}")


if __name__ == "__main__":
    main()
