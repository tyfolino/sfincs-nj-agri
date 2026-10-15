"""A4, first test: do cheap rain / NWM-wetness predictors explain wet-cause crop-insurance
losses (RMA Cause of Loss) per county x month, and does anything beat season + monthly
rainfall alone?  Out-of-sample by leave-one-year-out (LOYO), 2003-2022.

Runs in the shared sfincs env:  python archive/scripts/a4_first_test.py  (~2-4 min)

Inputs (all built earlier; nothing is fetched):
  data/rma/loss_panel_county_month.csv    RMA COL x SOB panel (archive/reports/loss_panel.md)
  data/precip/rain_county_month.csv       Stage IV (primary) monthly metrics, local months
  data/nwm/nwm_soil_daily_county.csv      NWM v3.0 retrospective daily, to 2023-01-31
  data/insurance/ is NEVER read.

Design
  Unit       county x month, 2003-2022 (NWM coverage), 3 counties -> 720 cells, minus
             months whose Stage IV (this or the previous month) misses > 5 % of cropland.
             Second cut: county x month x crop (corn, soybeans, wheat), one model per crop.
  Targets    wet = indemnity_wet_31_51 > $1,000 (lead); also > $0 and the broad water
             definition. "all" crop group for the county-month cut (binary, so the 2014
             "other" liability break does not matter). Secondary continuous targets among
             wet-loss months: log10 wet indemnity (all crops) and the corn+soy+wheat wet
             loss ratio.
  Predictors each for the SAME month (l0) and the PREVIOUS month (l1). In models they
             enter as within-county x calendar-month normal-score anomalies
             (agri_sfincs.skill.normal_score_anomaly; climatology 2002-2022 for NWM,
             2002-2025 for rain; no target information used).
             Rain (Stage IV, cropland mean): total (THE BASELINE), max 1/3/24/72 h,
             wet days >= 25 mm, cropland share with 24 h >= 50 mm, antecedent 7/14/30 d
             before the month (l0 only: they are already lags). max 1/3 h are set NaN
             where filled_frac > 0.05 (hours spread evenly from 6-h files).
             NWM (cropland-weighted daily, aggregated to the month): 0-10 cm and 0-100 cm
             soil moisture (mean, max), days 0-10 cm soil moisture >= the county's
             all-days 90th percentile, ponded fraction (mean, max), ponded >= 10 mm
             fraction, surface head (mean, max), saturated-from-0/10/40 cm fractions,
             water-table depth (mean), ET and underground runoff (monthly sums).
             Routing-grid variables need >= 50 % of days present (Dec 2022 gap).
  Models     ridge-penalized logistic (lam = 1, standardized on the training years):
               S   season: calendar-month + county dummies
               R0  S + log(1 + rain total) this month
               B   S + log(1 + rain total) this month + previous month   <- the baseline
                   (the strongest of the rain baselines tried: raw log totals beat their
                   anomalies, and an exposure term, log liability, made S and B worse
                   out of sample; both kept in a4_ladder.csv as sensitivities)
               B+X one predictor added (each predictor, l0 and l1 separately)
               S+X X in place of rain (X l0 and l1, compared with B)
               SEL forward selection of 1 or 3 anomaly predictors on top of B, chosen
                   INSIDE each LOYO fold by training log-likelihood (selection-aware)
  Scores     pooled LOYO out-of-fold AUC and Brier; differences with 95 % CIs from a
             2,000-draw bootstrap over years (resampling out-of-fold predictions).
             Continuous: LOYO ridge OLS on the wet-loss months; Spearman of out-of-fold
             predictions with the truth.

Writes data/analysis/:
  a4_features_county_month.csv  predictors (raw + anomaly, l0/l1) and targets per cell
  a4_ladder.csv                 season / rain baselines (S, R0, B, B_anom, S_expo, B_expo; crops)
  a4_univariate.csv             each predictor alone: AUC raw and anomaly
  a4_increments.csv             B+X and S+X vs B, every target / crop cut
  a4_selection.csv              selection-aware results and selection frequencies
  a4_continuous.csv             continuous targets
  a4_oof_predictions.csv        out-of-fold probabilities of S, R0, B, SEL1, SEL3 (lead)
The report's wording was written against the 2026-10-03 numbers; the tables are live.
  a4_flagged_months.csv         Cumberland 2023-09 and Salem 2025-05 (descriptive)
archive/reports/a4_first_test.md, archive/reports/figs/a4_delta_auc.png, archive/reports/figs/a4_season_roc.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agri_sfincs import config, domain  # noqa: E402
from agri_sfincs import skill as S  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

OUT = config.ANALYSIS_DIR
FIGS = config.ARCHIVE_REPORTS / "figs"
YEARS = (2003, 2022)
LAM = 1.0
N_BOOT = 2000
ROWCROPS = ["corn", "soybeans", "wheat"]
COUNTIES = {int(k): v for k, v in domain.COUNTIES.items()}

RAIN_VARS = {  # column -> label
    "total_mm": "rain total",
    "max1h_mm": "rain max 1 h",
    "max3h_mm": "rain max 3 h",
    "max24h_mm": "rain max 24 h",
    "max72h_mm": "rain max 72 h",
    "wetdays_25mm": "rain days >= 25 mm",
    "frac_crop_24h_ge50": "cropland share 24 h >= 50 mm",
    "ante7d_mm": "rain 7 d before month",
    "ante14d_mm": "rain 14 d before month",
    "ante30d_mm": "rain 30 d before month",
}
RAIN_NO_LAG = {"ante7d_mm", "ante14d_mm", "ante30d_mm"}
INTENSITY = ["max1h_mm", "max3h_mm"]
NWM_VARS = {
    "sm1_mean": "soil moisture 0-10 cm, mean",
    "sm1_max": "soil moisture 0-10 cm, max",
    "sm100_mean": "soil moisture 0-100 cm, mean",
    "sm100_max": "soil moisture 0-100 cm, max",
    "sm1_p90_days": "days soil 0-10 cm >= p90",
    "ponded_mean": "ponded fraction, mean",
    "ponded_max": "ponded fraction, max",
    "ponded10_mean": "ponded >= 10 mm fraction, mean",
    "sfchead_mean": "surface head, mean",
    "sfchead_max": "surface head, max",
    "sat0_mean": "saturated from surface, mean",
    "sat10_mean": "saturated from 10 cm, mean",
    "sat40_mean": "saturated from 40 cm, mean",
    "zwt_mean": "water-table depth, mean",
    "et_sum": "ET, monthly sum",
    "ugd_sum": "underground runoff, monthly sum",
}
#: a-priori direction for the single-predictor AUC (wetter -> more loss)
NEGATIVE = {"zwt_mean", "et_sum"}
LABELS = {**RAIN_VARS, **NWM_VARS}
FAMILY = {**{k: "rain" for k in RAIN_VARS}, **{k: "NWM" for k in NWM_VARS}}


# ----------------------------------------------------------------------------- data
def month_id(year, month):
    return np.asarray(year) * 12 + np.asarray(month) - 1


def load_rain() -> pd.DataFrame:
    r = pd.read_csv(config.PRECIP_DIR / "rain_county_month.csv")
    r = r[r["product"] == "stage4"].copy()
    r["rain_bad"] = r["missing_frac"] > 0.05
    for c in INTENSITY:
        r.loc[r["filled_frac"] > 0.05, c] = np.nan
    return r[["fips", "year", "month", "rain_bad", "filled_frac", *RAIN_VARS]]


def load_nwm() -> pd.DataFrame:
    d = pd.read_csv(config.NWM_DIR / "nwm_soil_daily_county.csv", parse_dates=["date"])
    d["year"], d["month"] = d.date.dt.year, d.date.dt.month
    p90 = d.groupby("fips").soil_m1.transform(lambda s: s.quantile(0.9))
    d["sm1_hi"] = (d.soil_m1 >= p90).astype(float)
    g = d.groupby(["fips", "year", "month"])
    m = pd.DataFrame({
        "sm1_mean": g.soil_m1.mean(), "sm1_max": g.soil_m1.max(),
        "sm100_mean": g.soil_m_0_100cm.mean(), "sm100_max": g.soil_m_0_100cm.max(),
        "sm1_p90_days": g.sm1_hi.sum(),
        "ponded_mean": g.ponded_frac.mean(), "ponded_max": g.ponded_frac.max(),
        "ponded10_mean": g.ponded10_frac.mean(),
        "sfchead_mean": g.sfchead_mean_mm.mean(), "sfchead_max": g.sfchead_max_mm.max(),
        "sat0_mean": g.sat_0cm_frac.mean(), "sat10_mean": g.sat_10cm_frac.mean(),
        "sat40_mean": g.sat_40cm_frac.mean(), "zwt_mean": g.zwt_mean_m.mean(),
        "et_sum": g.accet_mm.sum(min_count=1), "ugd_sum": g.ugdrnoff_mm.sum(min_count=1),
    })  # fmt: skip
    rt_ok = g.n_rt.apply(lambda s: (s.fillna(0) > 0).mean() >= 0.5)
    rt_cols = ["ponded_mean", "ponded_max", "ponded10_mean", "sfchead_mean",
               "sfchead_max", "sat0_mean", "sat10_mean", "sat40_mean", "zwt_mean"]  # fmt: skip
    m.loc[~rt_ok, rt_cols] = np.nan
    m = m.reset_index()
    # Only whole months (the record ends 2023-01-31, starts 2002-01-01).
    return m[m.year <= 2022]


def load_losses() -> pd.DataFrame:
    p = pd.read_csv(config.RMA_DIR / "loss_panel_county_month.csv")
    keep = ["fips", "year", "month", "crop_group", "indemnity_wet_31_51",
            "indemnity_wet_broad", "liability"]  # fmt: skip
    p = p[keep]
    rc = (p[p.crop_group.isin(ROWCROPS)].groupby(["fips", "year", "month"], as_index=False)
          [["indemnity_wet_31_51", "indemnity_wet_broad", "liability"]].sum())  # fmt: skip
    rc["crop_group"] = "rowcrop"
    return pd.concat([p, rc], ignore_index=True)


def add_lags_and_anoms(df: pd.DataFrame, cols, clim_years) -> pd.DataFrame:
    """Per county on a complete monthly index: l1 = previous calendar month; a_ =
    normal-score anomaly within county x calendar month over ``clim_years``."""
    df = df.sort_values(["fips", "year", "month"]).copy()
    df["mid"] = month_id(df.year, df.month)
    inclim = df.year.between(*clim_years)
    for c in cols:
        a = pd.Series(np.nan, index=df.index)
        a[inclim] = S.normal_score_anomaly(df.loc[inclim, c], [df.loc[inclim, "fips"], df.loc[inclim, "month"]])
        # outside the climatology years: rank against the climatology (for flagged months)
        for i in df.index[~inclim & df[c].notna()]:
            ref = df.loc[inclim & (df.fips == df.at[i, "fips"]) & (df.month == df.at[i, "month"]), c].dropna()
            q = ((ref < df.at[i, c]).sum() + 0.5 * (ref == df.at[i, c]).sum() + 0.5) / (len(ref) + 1)
            from statistics import NormalDist

            a[i] = NormalDist().inv_cdf(q)
        df["a_" + c] = a
    prev = df[["fips", "mid", *cols, *("a_" + c for c in cols)]].copy()
    prev["mid"] += 1
    prev = prev.rename(columns={c: c + "_l1" for c in prev.columns if c not in ("fips", "mid")})
    return df.merge(prev, on=["fips", "mid"], how="left")


def build_features() -> pd.DataFrame:
    rain = add_lags_and_anoms(load_rain(), list(RAIN_VARS), (2002, 2025))
    rb = rain[["fips", "mid", "rain_bad"]].copy()
    rb["mid"] += 1
    rain = rain.merge(rb.rename(columns={"rain_bad": "rain_bad_l1"}), on=["fips", "mid"], how="left")
    nwm = add_lags_and_anoms(load_nwm(), list(NWM_VARS), (2002, 2022))
    return rain.merge(nwm.drop(columns=["year", "month"]), on=["fips", "mid"], how="left")


# --------------------------------------------------------------------------- models
def design(df: pd.DataFrame, extra: list[str], expo: str | None = None) -> np.ndarray:
    """Season (month + county dummies) [+ log exposure column ``expo``] + ``extra``."""
    mon = pd.get_dummies(df.month.astype(int)).reindex(columns=range(2, 13), fill_value=0)
    cty = pd.get_dummies(df.fips.astype(int)).reindex(columns=[34015, 34033], fill_value=0)
    cols = [mon.to_numpy(float), cty.to_numpy(float)]
    if expo:
        cols.append(np.log(df[[expo]].to_numpy(float).clip(1e3)))
    if extra:
        cols.append(df[extra].to_numpy(float))
    return np.column_stack(cols)


N_DUMMY = 13  # 11 month + 2 county


def _fit_logit(Xtr, ytr):
    cont = list(range(N_DUMMY, Xtr.shape[1]))
    mu, sd = Xtr[:, cont].mean(0), Xtr[:, cont].std(0)
    sd[sd == 0] = 1
    Z = Xtr.copy()
    Z[:, cont] = (Z[:, cont] - mu) / sd
    return S.fit_logistic(Z, ytr, lam=LAM), cont, mu, sd


def _pred_logit(model, Xte):
    b, cont, mu, sd = model
    Z = Xte.copy()
    Z[:, cont] = (Z[:, cont] - mu) / sd
    return S.predict_logistic(b, Z)


def _fit_lin(Xtr, ytr):
    cont = list(range(N_DUMMY, Xtr.shape[1]))
    mu, sd = Xtr[:, cont].mean(0), Xtr[:, cont].std(0)
    sd[sd == 0] = 1
    Z = Xtr.copy()
    Z[:, cont] = (Z[:, cont] - mu) / sd
    return S.fit_ridge(Z, ytr, lam=LAM), cont, mu, sd


def _pred_lin(model, Xte):
    b, cont, mu, sd = model
    Z = Xte.copy()
    Z[:, cont] = (Z[:, cont] - mu) / sd
    return S.predict_linear(b, Z)


def oof(df, y, extra, expo=None, kind="logit"):
    X = design(df, extra, expo)
    f, p = (_fit_logit, _pred_logit) if kind == "logit" else (_fit_lin, _pred_lin)
    return S.logo_predict(X, y, df.year.to_numpy(), f, p)


def boot_diff(y, years, pa, pb, metric="auc", seed=0):
    """Point difference (b - a) and 95 % year-bootstrap CI for AUC, Brier or Spearman."""
    fn = {"auc": S.auc, "brier": S.brier, "spearman": S.spearman}[metric]
    d0 = fn(y, pb) - fn(y, pa)
    bs = S.group_bootstrap(years, lambda i: fn(y[i], pb[i]) - fn(y[i], pa[i]), N_BOOT, seed)
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return d0, lo, hi, float(np.mean(bs <= 0) if metric != "brier" else np.mean(bs >= 0))


BASE = ["log_total", "log_total_l1"]  # log(1 + monthly rain), this and last month


def candidates() -> list[tuple[str, str, int]]:
    """(column, variable, lag) for every anomaly predictor except the rain total."""
    out = []
    for v in [*RAIN_VARS, *NWM_VARS]:
        if v == "total_mm":
            continue
        out.append((f"a_{v}", v, 0))
        if v not in RAIN_NO_LAG:
            out.append((f"a_{v}_l1", v, 1))
    return out


def increments(df, ycol, expo, tag) -> pd.DataFrame:
    """B+X vs B and S+X(l0,l1) vs B, each on the rows where X is present."""
    rows = []
    cands = candidates()
    for col, var, lag in cands:
        sub = df[df[col].notna()]
        y = sub[ycol].to_numpy(float)
        yrs = sub.year.to_numpy()
        pB = oof(sub, y, BASE, expo)
        pBX = oof(sub, y, BASE + [col], expo)
        d, lo, hi, pnull = boot_diff(y, yrs, pB, pBX, "auc", seed=len(rows))
        db = S.brier(y, pBX) - S.brier(y, pB)
        rec = dict(target=tag, var=var, label=LABELS[var], family=FAMILY[var], lag=lag,
                   n=len(sub), n_pos=int(y.sum()), auc_B=S.auc(y, pB), auc_BX=S.auc(y, pBX),
                   dauc=d, dauc_lo=lo, dauc_hi=hi, p_boot=pnull, dbrier=db)  # fmt: skip
        if lag == 0:  # replacement test: S + X(l0, l1) vs B
            both = [col] + ([col + "_l1"] if var not in RAIN_NO_LAG else [])
            sub2 = df[df[both].notna().all(axis=1)]
            y2 = sub2[ycol].to_numpy(float)
            pB2 = oof(sub2, y2, BASE, expo)
            pSX = oof(sub2, y2, both, expo)
            d2, lo2, hi2, _ = boot_diff(y2, sub2.year.to_numpy(), pB2, pSX, "auc", seed=999 + len(rows))
            rec.update(auc_SX=S.auc(y2, pSX), dauc_SX_vs_B=d2, dauc_SX_lo=lo2, dauc_SX_hi=hi2)
        rows.append(rec)
    return pd.DataFrame(rows)


def forward_select(df_tr, y_tr, pool, k, expo):
    """Greedy: add the pool column with the largest training log-likelihood gain."""
    chosen = []
    for _ in range(k):
        best, best_ll = None, -np.inf
        for c in pool:
            if c in chosen:
                continue
            X = design(df_tr, BASE + chosen + [c], expo)
            m = _fit_logit(X, y_tr)
            p = np.clip(_pred_logit(m, X), 1e-9, 1 - 1e-9)
            ll = np.sum(y_tr * np.log(p) + (1 - y_tr) * np.log(1 - p))
            if ll > best_ll:
                best, best_ll = c, ll
        chosen.append(best)
    return chosen


def selection_aware(df, ycol, expo, ks=(1, 3)):
    """Outer LOYO; inside each training set pick k predictors by forward selection.
    All rows; a missing anomaly (max 1/3 h where filled_frac > 0.05, routing-grid
    variables in Dec 2022) is set to 0, the climatological median."""
    pool = [c for c, _, _ in candidates()]
    sub = df.copy().reset_index(drop=True)
    sub[pool] = sub[pool].fillna(0.0)
    y = sub[ycol].to_numpy(float)
    yrs = sub.year.to_numpy()
    pB = oof(sub, y, BASE, expo)
    res, picks = {}, []
    for k in ks:
        p = np.full(len(y), np.nan)
        for yr in np.unique(yrs):
            te = yrs == yr
            ch = forward_select(sub[~te], y[~te], pool, k, expo)
            picks += [dict(k=k, year=yr, rank=i + 1, col=c) for i, c in enumerate(ch)]
            m = _fit_logit(design(sub[~te], BASE + ch, expo), y[~te])
            p[te] = _pred_logit(m, design(sub[te], BASE + ch, expo))
        res[k] = p
    return sub, y, pB, res, pd.DataFrame(picks)


# ------------------------------------------------------------------------------ main
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    feat = build_features()
    loss = load_losses()
    expo_rc = loss[loss.crop_group == "rowcrop"][["fips", "year", "month", "liability"]]
    expo_rc = expo_rc.rename(columns={"liability": "liab_rowcrop"})

    def cell_table(group):
        L = loss[loss.crop_group == group].drop(columns="crop_group")
        df = feat.merge(L, on=["fips", "year", "month"], how="inner").merge(
            expo_rc, on=["fips", "year", "month"], how="left")
        df = df[df.year.between(*YEARS)]
        df = df[~df.rain_bad & ~df.rain_bad_l1.fillna(False).astype(bool)].reset_index(drop=True)
        df["log_total"], df["log_total_l1"] = np.log1p(df.total_mm), np.log1p(df.total_mm_l1)
        for thr, nm in [(1000, "1k"), (0, "0")]:
            df[f"y_3151_{nm}"] = (df.indemnity_wet_31_51 > thr).astype(float)
            df[f"y_broad_{nm}"] = (df.indemnity_wet_broad > thr).astype(float)
        return df

    allc = cell_table("all")
    n_drop = 720 - len(allc)
    allc.assign(county=allc.fips.map(COUNTIES)).to_csv(OUT / "a4_features_county_month.csv", index=False)
    print(f"county-months: {len(allc)} (dropped {n_drop} for Stage IV missing > 5%)")

    # --- univariate: each predictor alone (no fitting -> already out-of-sample)
    lead = "y_3151_1k"
    uni = []
    for v in [*RAIN_VARS, *NWM_VARS]:
        sgn = -1 if v in NEGATIVE else 1
        for lag, suf in [(0, ""), (1, "_l1")]:
            if lag and v in RAIN_NO_LAG:
                continue
            for ycol in ["y_3151_1k", "y_broad_1k"]:
                y = allc[ycol]
                uni.append(dict(target=ycol, var=v, label=LABELS[v], family=FAMILY[v], lag=lag,
                                auc_raw=S.auc(y, sgn * allc[v + suf]),
                                auc_anom=S.auc(y, sgn * allc["a_" + v + suf])))  # fmt: skip
    uni = pd.DataFrame(uni)
    uni.to_csv(OUT / "a4_univariate.csv", index=False)

    # --- base ladder + increments, county x month, four target definitions
    ladder, incs = [], []
    oofs = {}
    for ycol in ["y_3151_1k", "y_3151_0", "y_broad_1k", "y_broad_0"]:
        y = allc[ycol].to_numpy(float)
        yrs = allc.year.to_numpy()
        p = {"S": oof(allc, y, []),
             "R0": oof(allc, y, ["log_total"]),
             "B": oof(allc, y, BASE),
             # sensitivities: rain as anomalies; with exposure (log row-crop liability)
             "B_anom": oof(allc, y, ["a_total_mm", "a_total_mm_l1"]),
             "S_expo": oof(allc, y, [], "liab_rowcrop"),
             "B_expo": oof(allc, y, BASE, "liab_rowcrop")}  # fmt: skip
        for name, pp in p.items():
            rec = dict(target=ycol, model=name, n=len(y), n_pos=int(y.sum()), auc=S.auc(y, pp), brier=S.brier(y, pp))
            if name != "S":
                d, lo, hi, _ = boot_diff(y, yrs, p["S"], pp, "auc")
                rec.update(dauc_vs_S=d, lo=lo, hi=hi)
            ladder.append(rec)
        if ycol == lead:
            oofs.update(p)
        print(ycol, "increments ...", flush=True)
        incs.append(increments(allc, ycol, None, ycol).assign(cut="county-month"))
    ladder = pd.DataFrame(ladder)

    # --- crop cut
    crop_ladder = []
    for crop in ROWCROPS:
        cdf = cell_table(crop)
        y = cdf[lead].to_numpy(float)
        yrs = cdf.year.to_numpy()
        pS = oof(cdf, y, [])
        pB = oof(cdf, y, BASE)
        d, lo, hi, _ = boot_diff(y, yrs, pS, pB, "auc")
        crop_ladder.append(dict(crop=crop, n=len(y), n_pos=int(y.sum()), auc_S=S.auc(y, pS),
                                auc_B=S.auc(y, pB), dauc_B_vs_S=d, lo=lo, hi=hi,
                                auc_S_expo=S.auc(y, oof(cdf, y, [], "liability")),
                                auc_B_expo=S.auc(y, oof(cdf, y, BASE, "liability"))))  # fmt: skip
        print(crop, "increments ...", flush=True)
        incs.append(increments(cdf, lead, None, lead).assign(cut=crop))
    crop_ladder = pd.DataFrame(crop_ladder)
    pd.concat([ladder.assign(cut="county-month"), crop_ladder.assign(cut=crop_ladder.crop)],
              ignore_index=True).to_csv(OUT / "a4_ladder.csv", index=False)  # fmt: skip
    inc = pd.concat(incs, ignore_index=True)
    inc.to_csv(OUT / "a4_increments.csv", index=False)

    # --- selection-aware (lead target, county-month; and each crop with k=1)
    print("selection-aware ...", flush=True)
    sel_rows, pick_rows = [], []
    sub, y, pB, res, picks = selection_aware(allc, lead, None)
    for k, p in res.items():
        d, lo, hi, pn = boot_diff(y, sub.year.to_numpy(), pB, p, "auc")
        sel_rows.append(dict(cut="county-month", k=k, n=len(y), n_pos=int(y.sum()), auc_B=S.auc(y, pB),
                             auc_SEL=S.auc(y, p), dauc=d, lo=lo, hi=hi, p_boot=pn,
                             dbrier=S.brier(y, p) - S.brier(y, pB)))  # fmt: skip
    oofs["SEL1_rows"], oofs["SEL_y"], oofs["SEL_B"] = res[1], y, pB
    oofs["SEL3_rows"] = res[3]
    pick_rows.append(picks.assign(cut="county-month"))
    for crop in ROWCROPS:
        cdf = cell_table(crop)
        s2, y2, pB2, r2, pk2 = selection_aware(cdf, lead, None, ks=(1,))
        d, lo, hi, pn = boot_diff(y2, s2.year.to_numpy(), pB2, r2[1], "auc")
        sel_rows.append(dict(cut=crop, k=1, n=len(y2), n_pos=int(y2.sum()), auc_B=S.auc(y2, pB2),
                             auc_SEL=S.auc(y2, r2[1]), dauc=d, lo=lo, hi=hi, p_boot=pn,
                             dbrier=S.brier(y2, r2[1]) - S.brier(y2, pB2)))  # fmt: skip
        pick_rows.append(pk2.assign(cut=crop))
    sel = pd.DataFrame(sel_rows)
    picks = pd.concat(pick_rows, ignore_index=True)
    picks["var"] = picks.col.str.replace("a_", "", n=1).str.replace("_l1", "", regex=False)
    picks["lag"] = picks.col.str.endswith("_l1").astype(int)
    freq = (picks.groupby(["cut", "k", "col"]).size().rename("n_folds").reset_index()
            .sort_values(["cut", "k", "n_folds"], ascending=[True, True, False]))  # fmt: skip
    pd.concat([sel.assign(kind="score"), freq.assign(kind="selected")], ignore_index=True).to_csv(
        OUT / "a4_selection.csv", index=False)

    # --- continuous (wet-loss months only)
    print("continuous ...", flush=True)
    cont_rows = []
    rc = cell_table("rowcrop")
    targets = {
        "log10 wet indemnity (all crops)": (allc[allc.indemnity_wet_31_51 > 0].reset_index(drop=True),
                                            lambda d: np.log10(d.indemnity_wet_31_51), None),
        "row-crop wet loss ratio": (rc[rc.indemnity_wet_31_51 > 0].reset_index(drop=True),
                                    lambda d: d.indemnity_wet_31_51 / d.liability, None),
    }  # fmt: skip
    for tname, (d, fy, expo) in targets.items():
        yv = fy(d).to_numpy(float)
        yrs = d.year.to_numpy()
        pS = oof(d, yv, [], expo, "lin")
        pB = oof(d, yv, BASE, expo, "lin")
        cont_rows.append(dict(target=tname, model="S", var="", lag=np.nan, n=len(yv), rho=S.spearman(yv, pS)))
        dd, lo, hi, _ = boot_diff(yv, yrs, pS, pB, "spearman")
        cont_rows.append(dict(target=tname, model="B", var="", lag=np.nan, n=len(yv), rho=S.spearman(yv, pB),
                              drho=dd, lo=lo, hi=hi))  # fmt: skip
        for col, var, lag in candidates():
            dsub = d[d[col].notna()]
            ys = fy(dsub).to_numpy(float)
            pb = oof(dsub, ys, BASE, expo, "lin")
            px = oof(dsub, ys, BASE + [col], expo, "lin")
            dd, lo, hi, _ = boot_diff(ys, dsub.year.to_numpy(), pb, px, "spearman")
            cont_rows.append(dict(target=tname, model="B+X", var=var, lag=lag, n=len(ys),
                                  rho=S.spearman(ys, px), drho=dd, lo=lo, hi=hi,
                                  rho_raw_anom=S.spearman(ys, dsub[col])))  # fmt: skip
    cont = pd.DataFrame(cont_rows)
    cont.to_csv(OUT / "a4_continuous.csv", index=False)

    # --- out-of-fold predictions (lead)
    oof_df = allc[["fips", "year", "month", lead]].copy()
    for k in ["S", "R0", "B"]:
        oof_df["p_" + k] = oofs[k]
    oof_df["p_SEL1"], oof_df["p_SEL3"] = oofs["SEL1_rows"], oofs["SEL3_rows"]
    oof_df.to_csv(OUT / "a4_oof_predictions.csv", index=False)

    # --- flagged months (rain only; NWM ends 2023-01)
    flagged = flagged_months(feat, loss, allc)
    flagged.to_csv(OUT / "a4_flagged_months.csv", index=False)

    figures(allc, inc, oofs, lead)
    write_report(allc, n_drop, uni, ladder, crop_ladder, inc, sel, freq, cont, flagged)


def flagged_months(feat, loss, allc) -> pd.DataFrame:
    lead = "y_3151_1k"
    y = allc[lead].to_numpy(float)
    m = _fit_logit(design(allc, BASE), y)
    ms = _fit_logit(design(allc, []), y)
    rows = []
    for fips, yr, mo in [(34011, 2023, 9), (34033, 2025, 5)]:
        c = feat[(feat.fips == fips) & (feat.year == yr) & (feat.month == mo)].copy()
        c["log_total"], c["log_total_l1"] = np.log1p(c.total_mm), np.log1p(c.total_mm_l1)
        L = loss[(loss.fips == fips) & (loss.year == yr) & (loss.month == mo) & (loss.crop_group == "all")]
        rate = allc[(allc.fips == fips) & (allc.month == mo)][lead].mean()
        rec = dict(county=COUNTIES[fips], year=yr, month=mo,
                   wet_31_51_usd=float(L.indemnity_wet_31_51.iloc[0]),
                   hist_rate_2003_2022=rate,
                   p_season=float(_pred_logit(ms, design(c, []))[0]),
                   p_B=float(_pred_logit(m, design(c, BASE))[0]))  # fmt: skip
        for v in RAIN_VARS:
            rec[v] = float(c[v].iloc[0])
            rec["pctl_" + v] = float(100 * _phi(c["a_" + v].iloc[0]))
        rec["total_mm_l1"] = float(c["total_mm_l1"].iloc[0])
        rec["pctl_total_mm_l1"] = float(100 * _phi(c["a_total_mm_l1"].iloc[0]))
        rows.append(rec)
    return pd.DataFrame(rows)


def _phi(z):
    from statistics import NormalDist

    return NormalDist().cdf(float(z)) if np.isfinite(z) else np.nan


# --------------------------------------------------------------------------- figures
BLUE, ORANGE, GREY, INK, INK2 = "#2a78d6", "#eb6834", "#8a8984", "#0b0b0b", "#52514e"


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9c8c2")
    ax.tick_params(colors=INK2, labelsize=8.5)
    ax.xaxis.label.set_color(INK2)
    ax.yaxis.label.set_color(INK2)


def figures(allc, inc, oofs, lead):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # 1. Delta AUC forest, lead target, county-month
    d = inc[(inc.cut == "county-month") & (inc.target == lead)].copy()
    order = (d.groupby("var").dauc.max().sort_values()).index
    fig, ax = plt.subplots(figsize=(7.2, 0.27 * len(order) + 1.4))
    ypos = {v: i for i, v in enumerate(order)}
    for _, r in d.iterrows():
        yy = ypos[r["var"]] + (0.17 if r.lag == 0 else -0.17)
        col = BLUE if r.family == "rain" else ORANGE
        ax.plot([r.dauc_lo, r.dauc_hi], [yy, yy], color=col, lw=1.4, alpha=0.8, solid_capstyle="round")
        ax.plot(r.dauc, yy, "o" if r.lag == 0 else "s", ms=5.5, mfc=col if r.lag == 0 else "white",
                mec=col, mew=1.4)  # fmt: skip
    ax.axvline(0, color=GREY, lw=1)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([LABELS[v] for v in order], fontsize=8.5, color=INK)
    ax.set_xlabel("change in out-of-sample AUC over season + monthly rain\n(95% CI, bootstrap over years)")
    _style(ax)
    from matplotlib.lines import Line2D

    h = [Line2D([], [], color=BLUE, marker="o", lw=1.4, label="rain, same month"),
         Line2D([], [], color=BLUE, marker="s", mfc="white", lw=1.4, label="rain, previous month"),
         Line2D([], [], color=ORANGE, marker="o", lw=1.4, label="NWM, same month"),
         Line2D([], [], color=ORANGE, marker="s", mfc="white", lw=1.4, label="NWM, previous month")]  # fmt: skip
    ax.legend(handles=h, fontsize=8, frameon=False, loc="lower right")
    fig.suptitle("Nothing clearly adds to season + monthly rain\n"
                 "Any wet loss (causes 31+51 > $1k), 3 counties, 2003–2022, leave-one-year-out",
                 fontsize=10, color=INK, x=0.02, ha="left")  # fmt: skip
    fig.tight_layout()
    fig.savefig(FIGS / "a4_delta_auc.png", dpi=150)
    plt.close(fig)

    # 2. Seasonality + ROC
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.5, 3.8))
    rate = allc.groupby("month")[lead].mean()
    a1.bar(rate.index, rate.values, color=BLUE, width=0.75)
    a1.set_xticks(range(1, 13))
    a1.set_xticklabels(list("JFMAMJJASOND"))
    a1.set_ylabel("share of county-months with a wet loss")
    a1.set_title("Wet losses are seasonal", fontsize=10, color=INK, loc="left")
    _style(a1)
    y = allc[lead].to_numpy(float)

    def roc(yv, p):
        o = np.argsort(-p)
        ys = yv[o]
        tpr = np.concatenate([[0], np.cumsum(ys) / ys.sum()])
        fpr = np.concatenate([[0], np.cumsum(1 - ys) / (1 - ys).sum()])
        return fpr, tpr

    curves = [("S", "season", GREY, "--"), ("B", "season + monthly rain", BLUE, "-")]
    for k, lab, col, ls in curves:
        f, t = roc(y, oofs[k])
        a2.plot(f, t, color=col, ls=ls, lw=2, label=f"{lab} (AUC {S.auc(y, oofs[k]):.2f})")
    ys = oofs["SEL_y"]
    f, t = roc(ys, oofs["SEL1_rows"])
    a2.plot(f, t, color=ORANGE, lw=2, label=f"+ 1 predictor chosen per fold (AUC {S.auc(ys, oofs['SEL1_rows']):.2f})")
    a2.plot([0, 1], [0, 1], color="#c9c8c2", lw=1)
    a2.set_xlabel("false-positive rate")
    a2.set_ylabel("true-positive rate")
    a2.set_title("Out-of-sample ROC (leave-one-year-out)", fontsize=10, color=INK, loc="left")
    a2.legend(fontsize=8, frameon=False, loc="lower right")
    a2.set_aspect("equal")
    _style(a2)
    fig.tight_layout()
    fig.savefig(FIGS / "a4_season_roc.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------- report
def _ordinal(x) -> str:
    n = int(round(x))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf} pctl"


def _ci(d, lo, hi, nd=3):
    return f"{d:+.{nd}f} [{lo:+.{nd}f}, {hi:+.{nd}f}]"


def _lab(col: str) -> str:
    v = col.removeprefix("a_")
    lag = v.endswith("_l1")
    v = v.removesuffix("_l1")
    return f"{LABELS[v]} ({'previous' if lag else 'same'} month)"


def write_report(allc, n_drop, uni, ladder, crop_ladder, inc, sel, freq, cont, flagged):
    lead = "y_3151_1k"
    L = ladder[ladder.target == lead].set_index("model")
    li = inc[(inc.cut == "county-month") & (inc.target == lead)].copy()
    li["rank"] = li.dauc.rank(ascending=False)
    best = li.sort_values("dauc", ascending=False).iloc[0]
    pre = li[(li["var"] == "sm1_mean") & (li.lag == 0)].iloc[0]  # pre-specified (FINDINGS §8)
    n_tests = len(li)
    n_sig = int((li.dauc_lo > 0).sum())
    sc = sel[sel.cut == "county-month"].set_index("k")
    rain_int = li[(li.family == "rain")]
    sx = li[li.lag == 0].dropna(subset=["dauc_SX_vs_B"]).sort_values("dauc_SX_vs_B", ascending=False)
    top_sx = sx.iloc[0]
    n_pos = int(allc[lead].sum())

    def pick(cut, k=1):
        f = freq[(freq.cut == cut) & (freq.k == k)]
        return ", ".join(f"{_lab(r.col)} {int(r.n_folds)}/20" for r in f.head(3).itertuples())

    lines = [
        "# A4 first test: do cheap wetness predictors beat season + monthly rain?",
        "",
        "Made by `archive/scripts/a4_first_test.py` from the RMA loss panel (`data/rma/`), Stage IV "
        "rain (`data/precip/`) and the NWM v3.0 retrospective (`data/nwm/`). Tables: "
        "`data/analysis/a4_*.csv`. The collaborators' file in `data/insurance/` is not read.",
        "",
        "**Bottom line.**",
        "",
        f"- **Season does most of the work; monthly rain adds a clear second step.** Any wet "
        f"loss (causes 31 + 51 > $1k, all crops), {len(allc)} county-months 2003–2022 "
        f"({n_pos} with a loss), leave-one-year-out AUC: season alone (calendar month + "
        f"county) {L.at['S', 'auc']:.3f}; + this month's rain {L.at['R0', 'auc']:.3f}; "
        f"**+ this and last month's rain {L.at['B', 'auc']:.3f}** (the baseline B, "
        f"{_ci(L.at['B', 'dauc_vs_S'], L.at['B', 'lo'], L.at['B', 'hi'])} over season; 95% "
        "CIs from a bootstrap over years).",
        f"- **Nothing beats season + monthly rain by a margin distinguishable from zero.** "
        f"Choosing the extra predictor inside each training fold (the honest number), one "
        f"added predictor gains {_ci(sc.at[1, 'dauc'], sc.at[1, 'lo'], sc.at[1, 'hi'])} AUC "
        f"and three gain {_ci(sc.at[3, 'dauc'], sc.at[3, 'lo'], sc.at[3, 'hi'])}: more "
        f"predictors overfit at ~{n_pos} positives. The one test fixed in advance (NWM "
        f"0–10 cm soil-moisture anomaly, same month; FINDINGS §8) gives "
        f"{_ci(pre.dauc, pre.dauc_lo, pre.dauc_hi)}.",
        f"- **The only consistent extra signal is NWM soil moisture,** worth about +0.01 to "
        f"+0.02 AUC, roughly a fifth of what rain adds over season. The fold-wise selection "
        f"picks {pick('county-month')}. The best single additions are "
        f"{_lab('a_' + best['var'] + ('_l1' if best.lag else ''))} "
        f"{_ci(best.dauc, best.dauc_lo, best.dauc_hi)} and the same-month 0–100 cm maximum "
        f"{_ci(*li[(li['var'] == 'sm100_max') & (li.lag == 0)][['dauc', 'dauc_lo', 'dauc_hi']].iloc[0])}. "
        f"Only {n_sig} of {n_tests} additions has a CI above zero (~{0.025 * n_tests:.1f} "
        "expected by chance), so this is a lead, not a result. Under the broad water "
        "definition the 0–100 cm maximum gives "
        f"{_ci(*inc[(inc.cut == 'county-month') & (inc.target == 'y_broad_1k') & (inc['var'] == 'sm100_max') & (inc.lag == 0)][['dauc', 'dauc_lo', 'dauc_hi']].iloc[0])}. "
        f"Used *instead of* rain, the best NWM state ({LABELS[top_sx['var']]}, both lags) "
        f"scores {top_sx.auc_SX:.3f} against {top_sx.auc_B:.3f} for B "
        f"({_ci(top_sx.dauc_SX_vs_B, top_sx.dauc_SX_lo, top_sx.dauc_SX_hi)}). Soil "
        "moisture can stand in for monthly rain, and is no worse.",
        f"- **Rain intensity adds nothing over the monthly total.** Max 1/3/24/72 h, days ≥ "
        f"25 mm, cropland share ≥ 50 mm in 24 h and the 7/14/30-day antecedent totals each "
        f"change AUC by {rain_int.dauc.min():+.3f} to {rain_int.dauc.max():+.3f}. Every one "
        "is worse than the monthly total when used in its place. At county × month, these "
        "losses do not respond to sub-daily intensity.",
        f"- **Lag:** for rain, the same month matters most (adding last month's rain moves "
        f"AUC {L.at['R0', 'auc']:.3f} → {L.at['B', 'auc']:.3f}). For soil moisture, the "
        "previous month is the most consistent pick. That fits a slow storage signal, and "
        "losses recorded at harvest after the damage. By crop, corn's pick is the previous "
        "month; soybeans' and wheat's are the same month.",
        "- **By crop** (tables 4–5): no crop shows a gain distinguishable from zero after "
        "selection: soybeans "
        f"{_ci(*sel[sel.cut == 'soybeans'][['dauc', 'lo', 'hi']].iloc[0])}, wheat "
        f"{_ci(*sel[sel.cut == 'wheat'][['dauc', 'lo', 'hi']].iloc[0])}, corn "
        f"{_ci(*sel[sel.cut == 'corn'][['dauc', 'lo', 'hi']].iloc[0])}. Even so, each crop "
        "picks one soil-moisture variable in 19 of 20 folds. Rain helps corn and soybeans "
        f"(B over S ≈ +0.06) much more than wheat "
        f"({_ci(*crop_ladder[crop_ladder.crop == 'wheat'][['dauc_B_vs_S', 'lo', 'hi']].iloc[0])}).",
        "- **Loss size, given a loss occurred, is not predicted** by anything here "
        "(out-of-sample Spearman ≤ ~0.15; table 6). In single-policy cells the dollar size "
        "is mostly farm-specific.",
        f"- **For SFINCS (Track B):** the bar is AUC ≈ {L.at['B', 'auc']:.2f} (season + "
        "monthly rain). The predictor that comes closest to clearing it is a soil-storage "
        "state, not rain intensity. SFINCS features should be scored the same way: against "
        "B, and against B + NWM soil moisture.",
        "",
        "![Change in AUC per predictor](figs/a4_delta_auc.png)",
        "",
        "![Seasonality and ROC](figs/a4_season_roc.png)",
        "",
        "## 1. Design",
        "",
        f"- **Cells:** 3 counties × 2003–2022 × 12 months = 720; {n_drop} dropped because "
        "Stage IV misses > 5% of a county's cropland in that month or the one before "
        "(2004-02, 2005-02, 2005-07, 2005-12, 2007-07 and their following months).",
        "- **Targets:** any wet indemnity > $1k (lead) or > $0, under causes 31 + 51 (lead) "
        "or the broad water set (`archive/reports/loss_panel.md`); crop group \"all\" for county × "
        "month (binary, so the 2014 \"other\" liability break does not matter), and corn, "
        "soybeans, wheat separately. Continuous: log10 wet indemnity and the corn + soy + "
        "wheat wet loss ratio, among loss months.",
        "- **Predictors:** Stage IV cropland-mean rain metrics and NWM daily cropland-weighted "
        "states aggregated to the month (list in the script docstring), for the same and the "
        "previous month. In models they enter as normal-score anomalies within county × "
        "calendar month, so the season is handled only by the dummies. Max 1/3 h are blanked "
        "where > 5% of the month's cropland hours were spread from 6-h files (Jun–Jul 2003, "
        "Jan–Apr 2005, Oct 2015–Feb 2016, Feb 2004).",
        "- **Models:** ridge logistic (λ = 1, standardized on training years). S = month + "
        "county dummies. B = S + log(1 + Stage IV monthly total) this month and last month: "
        "the strongest of the simple rain baselines tried (table 2; an exposure term, log "
        "liability, made both S and B worse out of sample). B + X adds one predictor; "
        "S + X puts X (both lags) in place of rain. Selection-aware: forward selection of 1 "
        "or 3 predictors from all 47 by training log-likelihood, redone inside each of the "
        "20 leave-one-year-out folds (missing anomalies set to 0, the median).",
        f"- **Scores:** pooled out-of-fold AUC and Brier; CIs from {N_BOOT} bootstrap draws "
        "of whole years over the out-of-fold predictions (the models are not refitted per "
        "draw, so CIs are somewhat narrow). `p_boot` = share of draws with no gain.",
        "",
        "## 2. Baselines (county × month)",
        "",
    ]
    lad = ladder.copy()
    lad["model"] = lad.model.map({
        "S": "S = season (month + county)", "R0": "S + log rain this month",
        "B": "B = S + log rain this + last month", "B_anom": "S + rain anomaly this + last month",
        "S_expo": "S + log liability (exposure)", "B_expo": "B + log liability (exposure)"}).fillna(lad.model)  # fmt: skip
    lad["vs S"] = [("" if pd.isna(r.dauc_vs_S) else _ci(r.dauc_vs_S, r.lo, r.hi)) for r in lad.itertuples()]
    lines += [md_table(lad[["target", "model", "n_pos", "auc", "brier", "vs S"]].set_index("target")), ""]
    u = uni[uni.target == lead].copy()
    u["predictor"] = [_lab("a_" + r["var"] + ("_l1" if r.lag else "")) for _, r in u.iterrows()]
    u = pd.concat([u.sort_values("auc_anom", ascending=False).head(8),
                   u[(u["var"] == "total_mm")]]).drop_duplicates("predictor")  # fmt: skip
    lines += [
        "## 2b. Each predictor alone (no fitting; lead target)",
        "",
        "`auc_raw` keeps the seasonal cycle; `auc_anom` is the anomaly within county × "
        "calendar month (season removed). The 8 best anomalies, and the rain total. ET is "
        "scored with low ET = wet; its AUC < 0.5 means the opposite holds.",
        "",
        md_table(u[["predictor", "family", "auc_raw", "auc_anom"]].set_index("predictor")),
        "",
    ]
    lines += [
        "## 3. One predictor added to B (county × month)",
        "",
        "Lead target (31 + 51 > $1k), the 12 largest gains and every rain-intensity row. "
        "`auc S+X` = X in place of rain (lag 0 rows only).",
        "",
    ]
    t = li.sort_values("dauc", ascending=False)
    t = pd.concat([t.head(12), t[(t.family == "rain") & ~t.index.isin(t.head(12).index)]])
    t = t.assign(predictor=[_lab("a_" + r["var"] + ("_l1" if r.lag else "")) for _, r in t.iterrows()],
                 **{"ΔAUC [95% CI]": [_ci(r.dauc, r.dauc_lo, r.dauc_hi) for r in t.itertuples()]})  # fmt: skip
    lines += [md_table(t[["predictor", "n", "n_pos", "auc_BX", "ΔAUC [95% CI]", "p_boot", "dbrier", "auc_SX"]]
                       .set_index("predictor"), floatfmt="{:.3f}"), ""]  # fmt: skip
    lines += ["Best addition under each target definition:", ""]
    bt = (inc[inc.cut == "county-month"].sort_values("dauc", ascending=False).groupby("target").head(2))
    bt = bt.assign(predictor=[_lab("a_" + r["var"] + ("_l1" if r.lag else "")) for _, r in bt.iterrows()],
                   **{"ΔAUC [95% CI]": [_ci(r.dauc, r.dauc_lo, r.dauc_hi) for r in bt.itertuples()]},
                   n_ci_above_0=bt.target.map(inc[inc.cut == "county-month"].groupby("target")
                                              .apply(lambda g: int((g.dauc_lo > 0).sum()))))  # fmt: skip
    lines += [md_table(bt.sort_values(["target", "dauc"], ascending=[True, False])
                       [["target", "n_pos", "auc_B", "predictor", "ΔAUC [95% CI]", "n_ci_above_0"]]
                       .set_index("target"), floatfmt="{:.3f}"), ""]  # fmt: skip
    lines += ["## 4. By crop (31 + 51 > $1k)", ""]
    cl = crop_ladder.assign(**{"B vs S": [_ci(r.dauc_B_vs_S, r.lo, r.hi) for r in crop_ladder.itertuples()]})
    lines += [md_table(cl[["crop", "n", "n_pos", "auc_S", "auc_B", "B vs S", "auc_S_expo", "auc_B_expo"]]
                       .set_index("crop")), "",
              "(`_expo`: with the crop's log liability as an exposure term; sensitivity only.)", ""]  # fmt: skip
    ct = inc[inc.cut != "county-month"].sort_values("dauc", ascending=False).groupby("cut").head(3)
    ct = ct.assign(predictor=[_lab("a_" + r["var"] + ("_l1" if r.lag else "")) for _, r in ct.iterrows()],
                   **{"ΔAUC [95% CI]": [_ci(r.dauc, r.dauc_lo, r.dauc_hi) for r in ct.itertuples()]})  # fmt: skip
    lines += ["Top three single additions to B per crop:", "",
              md_table(ct[["cut", "predictor", "auc_BX", "ΔAUC [95% CI]", "p_boot"]].set_index("cut"),
                       floatfmt="{:.3f}"), ""]  # fmt: skip
    lines += ["## 5. Selection-aware (predictors chosen inside each fold)", ""]
    st = sel.assign(**{"ΔAUC [95% CI]": [_ci(r.dauc, r.lo, r.hi) for r in sel.itertuples()]})
    st["chosen (folds of 20)"] = [pick(r.cut, r.k) for r in st.itertuples()]
    lines += [md_table(st[["cut", "k", "n_pos", "auc_B", "auc_SEL", "ΔAUC [95% CI]", "p_boot", "dbrier",
                           "chosen (folds of 20)"]].set_index("cut"), floatfmt="{:.3f}"), ""]  # fmt: skip
    lines += ["## 6. Loss size among loss months (out-of-sample Spearman)", ""]
    cb = cont[cont.model != "B+X"].copy()
    cx = cont[cont.model == "B+X"].sort_values("drho", ascending=False).groupby("target").head(2).copy()
    cx["model"] = [f"B + {_lab('a_' + r['var'] + ('_l1' if r.lag else ''))}" for _, r in cx.iterrows()]
    cc = pd.concat([cb, cx]).sort_values("target", kind="stable")
    cc["Δρ vs previous [95% CI]"] = [("" if pd.isna(r.drho) else _ci(r.drho, r.lo, r.hi, 2)) for r in cc.itertuples()]
    lines += [md_table(cc[["target", "model", "n", "rho", "Δρ vs previous [95% CI]"]].set_index("target"),
                       floatfmt="{:.3f}"), "",
              "(Δρ: B vs S, and B + X vs B. The best X of 47 is shown, so its Δρ is optimistic.)", ""]  # fmt: skip
    lines += [
        "## 7. The two flagged months (descriptive; NWM ends 2023-01)",
        "",
        "Percentiles: rank among the same county and calendar month, 2002–2025. "
        "`p_season`, `p_B`: probability of a wet loss > $1k from S and B fitted on all of "
        "2003–2022.",
        "",
    ]
    fl = flagged.copy()
    fl["cell"] = fl.county + " " + fl.year.astype(str) + "-" + fl.month.map("{:02d}".format)
    show = {"wet_31_51_usd": "wet 31+51 $", "hist_rate_2003_2022": "share of years with a loss",
            "p_season": "p_season", "p_B": "p_B"}  # fmt: skip
    for v in ["total_mm", "total_mm_l1", "max1h_mm", "max24h_mm", "max72h_mm", "frac_crop_24h_ge50", "ante14d_mm"]:
        fl[v] = [f"{a:.2f}" if v == "frac_crop_24h_ge50" else f"{a:.1f}" for a in fl[v]]
        fl[v] = [f"{a} ({_ordinal(b)})" for a, b in zip(fl[v], fl["pctl_" + v])]
        show[v] = v
    lines += [md_table(fl.set_index("cell")[list(show)].rename(columns=show).T, floatfmt="{:,.2f}"), ""]
    lines += [
        "Both months were in the top ~6% for their county-month rain total, with an ordinary "
        "previous month; B raises the loss probability over season alone in both. "
        "Neither is extreme in 24 h rain.",
        "",
        "## 8. Caveats",
        "",
        f"- **Multiple comparisons.** {n_tests} predictor × lag additions per target, 7 "
        "target/crop cuts and 4 water/threshold definitions. Single-test CIs above zero "
        "should be read against that; the selection-aware rows in §5 are the honest numbers.",
        "- **Correlated tests.** The soil-moisture variables are strongly inter-correlated, "
        "so their consistent ranking is one signal seen several times, not several signals.",
        "- **Anomaly climatologies** use every year, including the held-out one (predictor "
        "values only, never the target), so they are not strictly out-of-sample.",
        "- **ET** carries the opposite sign to the a-priori one (higher ET anomaly with "
        "losses: wet soil evaporates more in this energy-limited climate).",
        "- **Loss timing.** Month of loss is when the loss is recorded (often at harvest), "
        "not when water stood. This blurs the lag structure and favours slow storage "
        "variables over event intensity.",
        "- **Binary targets** dodge the single-policy dollar noise and the 2014 \"other\" "
        "liability break; 31 + 51 is almost all cause 31 (excess moisture).",
        "- **2003–2022 only** (NWM). Rain-only models could use 2003–2025.",
        "",
    ]
    (config.ARCHIVE_REPORTS / "a4_first_test.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
