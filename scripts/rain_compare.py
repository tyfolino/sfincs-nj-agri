"""Stage IV vs MRMS (vs NWM rain) comparison and the rain-metrics report.

Shared sfincs env, after scripts/rain_metrics.py:  python scripts/rain_compare.py

Reads data/precip/: rain_county_month.csv, stage4_hourly_vs_6h.csv, the year files'
``status`` (archive coverage), and data/nwm/nwm_soil_daily_county.csv (``qrain_mm``).
Writes reports/rain_metrics.md and reports/rain_metrics_compare.png.

Comparison rules: county x local-month totals, only months with missing_frac < 2 % in
BOTH products. Periods: MRMS GaugeCorr (to 2020-09) and Pass2 (2020-11 on); 2020-10, the
switch month, is left out of both. NWM ``qrain_mm`` is the daily mean of 3-hourly rates
(indicative only) on UTC days D 03Z .. D+1 00Z, summed by calendar month of D: a few
hours' shift against the local months here.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

from agri_sfincs import config  # noqa: E402
from agri_sfincs.report import md_table  # noqa: E402

P = config.PRECIP_DIR
REPORT = config.REPORTS / "rain_metrics.md"
FIG = config.REPORTS / "rain_metrics_compare.png"
MAX_MISSING = 0.02
SWITCH = (2020, 10)
#: Palette: validated default categorical slots 1-2 (dataviz skill), text in ink.
BLUE, ORANGE, INK, MUTED = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e"


def tab(df: pd.DataFrame, fmt: str = "{:.3f}") -> str:
    """md_table with NaN as an en dash and integer-valued count columns as integers."""
    d = df.copy().astype(object)
    for c in d.columns:
        d[c] = [("–" if pd.isna(v) else str(int(v)) if c in ("n", "files") or
                 str(c).endswith("absent") else fmt.format(v) if isinstance(v, float) else str(v))
                for v in df[c]]  # fmt: skip
    return md_table(d)


def period(year, month) -> np.ndarray:
    ym = np.asarray(year) * 12 + np.asarray(month)
    sw = SWITCH[0] * 12 + SWITCH[1]
    return np.where(ym < sw, "GaugeCorr", np.where(ym > sw, "Pass2", "switch"))


def stats(a: pd.Series, b: pd.Series) -> dict:
    """Agreement of ``b`` (test) with ``a`` (reference)."""
    d = b - a
    return {"n": len(a), "r": a.corr(b), "mean_ref_mm": a.mean(), "mean_test_mm": b.mean(),
            "bias_mm": d.mean(), "bias_se_mm": d.std() / np.sqrt(max(len(d), 1)),
            "ratio_of_sums": b.sum() / a.sum(), "median_ratio": (b / a)[a > 10].median()}  # fmt: skip


def coverage() -> pd.DataFrame:
    rows = []
    for prod in ("stage4", "stage4_6h", "mrms"):
        for f in sorted((P / prod).glob(f"{prod}_[0-9]*.nc")):
            with xr.open_dataset(f) as ds:
                st = ds.status.values
                row = {"product": prod, "year": int(f.stem.split("_")[-1]),
                       "files_ok": int((st == 0).sum()), "absent": int((st == 1).sum()),
                       "unreadable": int((st == 3).sum())}  # fmt: skip
                if "source" in ds:
                    src = ds.source.values[st == 0]
                    row["pass2_iastate"] = int((src == 2).sum())
                rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    m = pd.read_csv(P / "rain_county_month.csv", dtype={"fips": str})
    out = ["# Radar rainfall metrics per county × month (Stage IV, MRMS)", ""]
    out += [f"Made by `scripts/rain_compare.py` on {pd.Timestamp.now():%Y-%m-%d} from "
            "`data/precip/rain_county_month.csv` (`scripts/rain_metrics.py`) and the hourly "
            "clips from `scripts/fetch_precip_hourly.py`.", ""]  # fmt: skip

    out += ["## 1. Sources", "",
            "| product | source | worked? |", "|---|---|---|",
            "| Stage IV hourly + 6-h, 2002 → | Iowa Environmental Mesonet `mesonet.agron.iastate.edu/archive/data/YYYY/MM/DD/stage4/ST4.YYYYMMDDHH.01h.grib` (`.06h.grib`) | yes, every year; GRIB1 to ~2019, GRIB2 after, same 1121 × 881 HRAP grid |",
            "| Stage IV | Iowa State `mtarchive.geol.iastate.edu/YYYY/MM/DD/stage4/` | **no** (404; mtarchive has no stage4) |",
            "| Stage IV | NCAR EOL ds21.093 / RDA ds507.5 | not tried (IEM was enough) |",
            "| MRMS GaugeCorr_QPE_01H | Iowa State mtarchive | 2015-05-06T20 → 2020-10-14T12 |",
            "| MRMS MultiSensor_QPE_01H_Pass2 | AWS `noaa-mrms-pds` | from **2020-10-14T20** (not 00Z) |",
            "| MRMS MultiSensor_QPE_01H_Pass2 | Iowa State mtarchive | from 2020-10-13T19: fills the 8 h between the two |",
            "",
            "- Both: the file time is the END of the hour (checked against the GRIB validity time "
            "for Stage IV and the reference time for MRMS, which MRMS stamps at the hour's end). "
            "Units mm (kg m⁻²). Missing → NaN (Stage IV bitmap; MRMS −3 = no coverage).",
            "- Clip: `fetch_mrms.BBOX` (−75.64…−74.80 E, 38.98…39.94 N), which holds all three "
            "WHOLE counties incl. Gloucester's Great Egg Harbor part. MRMS 96 × 84 cells of "
            "0.01°; Stage IV 34 × 31 HRAP cells (~4.76 km). The MRMS clip reproduces "
            "`data/precip/mrms_2023-09.nc` exactly.",
            "- Weighting as `fetch_nwm_soil.py`: 30 m CDL cropland pixels binned to the cell "
            "holding their centre; CDL of the year (2008 for 2002–07, 2009 for 2010). "
            "Months and days are **America/New_York local**; an hour belongs to the local "
            "day holding its start.", ""]  # fmt: skip

    cov = coverage()
    if len(cov):
        out += ["## 2. Coverage", ""]
        out += ["Files per year (`absent` = 404; `unreadable` = bad GRIB or wrong time/grid):", ""]
        piv = cov.pivot_table(index="year", columns="product", values="absent", aggfunc="sum")
        piv.columns = [f"{c} absent" for c in piv.columns]
        out += [tab(piv), ""]
        if cov["unreadable"].sum():
            out += [f"Unreadable files: {int(cov['unreadable'].sum())}.", ""]
        g = m.groupby(["product", "year"]).agg(
            missing_frac=("missing_frac", "mean"), filled_frac=("filled_frac", "mean"),
            worst_month_missing=("missing_frac", "max")).reset_index()  # fmt: skip
        g = g.pivot(index="year", columns="product")
        g.columns = [f"{b} {a}" for a, b in g.columns]
        out += ["Cropland-weighted share of cell-hours missing after the 6-h fill, and the share "
                "filled from Stage IV 6-h files (mean over county-months; worst county-month):", "",
                tab(g * 100, "{:.1f}"), "",
                "(Percent.) The Stage IV HOURLY mosaic has whole hours with no data over NJ although "
                "the file exists (MARFC's hourly field absent), mostly in the early years; the 6-h "
                "files are complete there. Each missing hour gets an even share of the 6-h total "
                "minus the hours present, so totals are right and peak intensities in those hours "
                "are smoothed: use `filled_frac` to screen intensity metrics.", ""]  # fmt: skip
        bad = m[(m["product"] == "stage4") & (m.missing_frac > 0.05)]
        bad = bad.groupby(["year", "month"]).missing_frac.max()
        out += ["Stage IV months still missing > 5 % on some county's cropland (where the 6-h "
                "files are blank or absent too; IEM has no 6-h files for 2006 or 2009-01..09): "
                + ", ".join(f"{y}-{mo:02d} ({v:.0%})" for (y, mo), v in bad.items()) + ".", ""]  # fmt: skip
    chk = P / "stage4_hourly_vs_6h.csv"
    if chk.exists():
        c = pd.read_csv(chk)
        out += ["### Stage IV hourly vs 6-h over complete 6-h windows", "",
                tab(c.set_index("year"), "{:.4g}"), "",
                f"Hourly sums are {c.hourly_mm.sum() / c.six_hour_mm.sum():.3f} × the 6-h totals "
                "over 6-h windows where all six hours exist (all years, cropland-weighted).", ""]  # fmt: skip

    # ---- Stage IV vs MRMS
    key = ["fips", "county", "year", "month"]
    s4 = m[m["product"] == "stage4"].set_index(key)
    mr = m[m["product"] == "mrms"].set_index(key)
    j = s4.join(mr, lsuffix="_s4", rsuffix="_mr", how="inner")
    j = j[(j.missing_frac_s4 < MAX_MISSING) & (j.missing_frac_mr < MAX_MISSING)].reset_index()
    j["period"] = period(j.year, j.month)
    if len(j):
        out += ["## 3. Stage IV vs MRMS", "",
                f"County × month pairs with < {MAX_MISSING:.0%} missing in both; MRMS is the test, "
                "Stage IV the reference. bias = mean(MRMS − Stage IV); se its standard error.", ""]  # fmt: skip
        rows = {}
        for var in ("total_mm", "max1h_mm", "max24h_mm", "peakcell_max1h_mm",
                    "wetdays_1mm", "ante30d_mm"):  # fmt: skip
            for per in ("GaugeCorr", "Pass2"):
                q = j[j.period == per]
                if len(q) > 2:
                    rows[(var, per)] = stats(q[f"{var}_s4"], q[f"{var}_mr"])
        t = pd.DataFrame(rows).T
        t.index.names = ["metric", "MRMS period"]
        out += [tab(t), ""]
        bc = j[j.period != "switch"].groupby(["period", "county"]).apply(
            lambda q: pd.Series(stats(q.total_mm_s4, q.total_mm_mr)), include_groups=False)
        out += ["Monthly totals by county:", "", tab(bc[["n", "r", "bias_mm", "ratio_of_sums"]]), ""]
        yr = j.groupby("year").apply(lambda q: q.total_mm_mr.sum() / q.total_mm_s4.sum(),
                                     include_groups=False).rename("MRMS / Stage IV")  # fmt: skip
        out += ["Annual ratio of summed monthly totals (all three counties):", "",
                tab(yr.to_frame()), ""]
        d = pd.read_csv(P / "rain_county_daily.csv", dtype={"fips": str})
        dd = d.pivot_table(index=["county", "date"], columns="product", values="mm").dropna()
        dd["MRMS − Stage IV"] = dd["mrms"] - dd["stage4"]
        big = dd[dd["MRMS − Stage IV"].abs() > 30].sort_values("MRMS − Stage IV")
        out += [f"Daily county cropland means agree at r = {dd.mrms.corr(dd.stage4):.3f} "
                f"({len(dd):,} county-days). Days differing by more than 30 mm (all are MRMS "
                "too high; MRMS Pass1 and RadarOnly carry the same values, so these are radar "
                "artifacts the gauge correction left in, which Stage IV's RFC QC removed — "
                "2020-12-25 01–03Z: 44 and 35 mm/h over the whole clip against Stage IV 6–8; "
                "2024-08-30 04–05Z: 14 mm/h against 1.5). Prefer Stage IV in those months:", "",
                tab(big, "{:.1f}"), ""]  # fmt: skip
        fig_compare(j, yr)
        out += [f"![Stage IV vs MRMS]({FIG.name})", ""]

    # ---- NWM
    nwmf = config.NWM_DIR / "nwm_soil_daily_county.csv"
    if nwmf.exists():
        n = pd.read_csv(nwmf, usecols=["date", "fips", "qrain_mm"], dtype={"fips": str},
                        parse_dates=["date"])  # fmt: skip
        n = n.groupby([n.fips, n.date.dt.year.rename("year"), n.date.dt.month.rename("month")])
        n = n.qrain_mm.agg(["sum", "size"]).reset_index()
        n = n[n["size"] >= 28].rename(columns={"sum": "nwm_qrain_mm"})
        rows = {}
        for prod in ("stage4", "mrms"):
            q = m[(m["product"] == prod) & (m.missing_frac < MAX_MISSING)].merge(n, on=["fips", "year", "month"])
            for season, months in (("all months", range(1, 13)), ("Apr-Oct", range(4, 11))):
                qs = q[q.month.isin(months)]
                if len(qs) > 2:
                    rows[(prod, season)] = stats(qs.nwm_qrain_mm, qs.total_mm) | {
                        "years": f"{qs.year.min()}-{qs.year.max()}"}
        if rows:
            t = pd.DataFrame(rows).T
            t.index.names = ["product", "months"]
            t["n"] = t["n"].astype(int)
            out += ["## 4. Against NWM `qrain_mm` (indicative)", "",
                    "NWM v3.0 retrospective rain (AORC-forced; daily mean of 3-hourly rates, so "
                    "only indicative), summed by calendar month and compared with the monthly "
                    "totals here (radar = test, NWM = reference), to 2023-01. **`qrain` is "
                    "LIQUID rain only** (snow is `QSNOW`), so winter radar totals (liquid "
                    "equivalent of all precipitation) run 30-90 % above it; Apr-Oct is the fair "
                    "comparison.", "", tab(t), ""]  # fmt: skip

    # ---- headlines
    s = m[m["product"] == "stage4"]
    if len(s):
        out += ["## 5. Headline numbers (Stage IV, cropland means unless 'peak cell')", ""]
        cols = ["county", "year", "month", "total_mm", "max24h_mm", "max1h_mm",
                "peakcell_max1h_mm", "filled_frac"]  # fmt: skip
        out += ["Wettest county-months:", "", tab(s.nlargest(8, "total_mm")[cols].set_index("county"), "{:.1f}"), ""]
        out += ["Largest cropland-mean 1 h rates:", "", tab(s.nlargest(6, "max1h_mm")[cols].set_index("county"), "{:.1f}"), ""]
        out += ["Largest cropland-mean 24 h totals:", "", tab(s.nlargest(6, "max24h_mm")[cols].set_index("county"), "{:.1f}"), ""]
        mx = m.loc[m.groupby("product").peakcell_max1h_mm.idxmax(), ["product", *cols]]
        out += ["Largest single-cell hour on cropland, per product:", "", tab(mx.set_index("product"), "{:.1f}"), ""]
        fl = m[(m["product"] == "stage4") & (m.year.isin([2023, 2025]))]
        ev = fl[((fl.county == "Cumberland") & (fl.year == 2023) & (fl.month == 9))
                | ((fl.county == "Salem") & (fl.year == 2025) & (fl.month == 5))]  # fmt: skip
        both = m[m.set_index(["county", "year", "month"]).index.isin(
            ev.set_index(["county", "year", "month"]).index)]  # fmt: skip
        if len(both):
            out += ["The two flagged months:", "",
                    tab(both[["product", *cols, "ante30d_mm", "frac_crop_24h_ge50"]]
                        .set_index("product"), "{:.2f}"), ""]  # fmt: skip
    out[4:4] = bottom_line(m, j if "j" in locals() else None)
    REPORT.write_text("\n".join(out))
    print(f"wrote {REPORT}")


def bottom_line(m: pd.DataFrame, j) -> list[str]:
    s4 = m[m["product"] == "stage4"]
    lines = ["**Bottom line.**", "",
             f"- Stage IV hourly is complete for 2002–2025 from IEM; cropland-weighted, "
             f"{(s4.missing_frac > 0.02).sum()} of {len(s4)} county-months miss more than 2 % "
             f"after filling absent hourly fields from the 6-h files "
             f"({s4.filled_frac.mean():.1%} of cell-hours filled overall, most in 2003–2005)."]  # fmt: skip
    if j is not None and len(j):
        r = {p: (j[j.period == p].total_mm_mr.sum() / j[j.period == p].total_mm_s4.sum(),
                 j[j.period == p].total_mm_s4.corr(j[j.period == p].total_mm_mr))
             for p in ("GaugeCorr", "Pass2")}  # fmt: skip
        lines += [f"- MRMS monthly totals are {1 - r['GaugeCorr'][0]:.1%} below Stage IV in the "
                  f"GaugeCorr era (r {r['GaugeCorr'][1]:.3f}) and {1 - r['Pass2'][0]:.1%} below "
                  f"in the Pass2 era (r {r['Pass2'][1]:.3f}): **no step at the 2020-10 switch** "
                  "in totals. Hourly maxima agree less well under Pass2, and two MRMS radar "
                  "artifacts (Dec 2020, Aug 2024) inflate those months (§3).",
                  "- Peak-cell 1 h maxima are ~15–20 % higher in MRMS: 1 km cells against "
                  "Stage IV's ~4.8 km, so the products' peak-cell metrics are not "
                  "interchangeable; cropland-mean metrics are."]  # fmt: skip
    lines += ["- Recommendation for A4: Stage IV for 2003–2022 (one homogeneous product); "
              "MRMS as a check and for 1 km peak intensity.", ""]
    return lines


def fig_compare(j: pd.DataFrame, yr: pd.Series) -> None:
    fig, (a, b) = plt.subplots(1, 2, figsize=(10.5, 4.6))
    for per, col, mk in (("GaugeCorr", BLUE, "o"), ("Pass2", ORANGE, "^")):
        q = j[j.period == per]
        a.scatter(q.total_mm_s4, q.total_mm_mr, s=14, color=col, marker=mk, alpha=0.75,
                  linewidths=0, label=f"MRMS {per} ({len(q)})")  # fmt: skip
    hi = float(np.nanmax(j[["total_mm_s4", "total_mm_mr"]].to_numpy())) * 1.05
    a.plot([0, hi], [0, hi], color=MUTED, lw=1, ls="--")
    a.set(xlim=(0, hi), ylim=(0, hi), xlabel="Stage IV monthly total (mm)",
          ylabel="MRMS monthly total (mm)", title="County × month cropland-mean totals")  # fmt: skip
    a.legend(frameon=False, loc="upper left")
    x = yr.index.to_numpy()
    b.plot(x, yr.to_numpy(), color=BLUE, lw=2, marker="o", ms=6)
    b.axhline(1, color=MUTED, lw=1, ls="--")
    b.axvline(SWITCH[0] + (SWITCH[1] - 0.5) / 12, color=MUTED, lw=1)
    b.text(SWITCH[0] + 0.95, 1.095, "Pass2 from\n2020-10-14", va="top", color=INK, fontsize=9)
    b.set(xlabel="year", ylabel="MRMS / Stage IV", title="Annual ratio of summed monthly totals",
          ylim=(0.85, 1.10))  # fmt: skip
    for ax in (a, b):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(color="#e6e5e1", lw=0.6)
        ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(FIG, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
