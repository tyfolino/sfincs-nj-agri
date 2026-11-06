"""Plain counts for the ag-econ write-up: of the low NJ crop fields, how many flooded fields left
farming or changed crops, beside the fields the storms never flooded. Descriptive only, no
height weighting or storm timing (that is scripts/build_storm_panel.py's job, FINDINGS §53, §57).

Fields: panel.low_crop_fields (< 1.5 m above MHHW, >= half CDL cropland 2008-12; the §34 set).
Flooded = >= 10% of the field > 5 cm in at least one of the 18 storm tides (tide only, dikes as
they stand; field_event.csv of ``--panel``). Outcomes:
  LU/LC exit            not farmed in NJDEP LU/LC 2020 (landuse.is_farmed)
  out of farming 2023   CDL cropland + pasture (panel.farmland) below half in 2023 (the last
                        year before CDL's 2024 product change, FINDINGS §37)
  ever flagged          panel.left_cropland on cropland + pasture, any year 2009-22 (about half
                        of flags come back, FINDINGS §57)
  corn / soy            area-weighted CDL share, 2008-12 vs 2019-23
Also: out of farming 2023 by height band x behind an NLD levee; storm footprint overlap (each storm's
flooded fields inside Sandy's); and §34's Sandy comparison redone on this panel (FINDINGS §71:
flooded - same-height dry fields, 2013-16 change from each group's own 2008-12 mean, 500 field
resamples; method of the deleted plot_sandy_panel.py, git 53001c1^).
Writes reports/exit_counts_<tag>.md.

Usage:  python scripts/exit_counts.py [--panel data/analysis/sandy_panel_m65] [--tag m65]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from agri_sfincs import config, fieldflood, landuse, panel
from agri_sfincs.report import md_table

BANDS = [(-np.inf, 0.5, "below 0.5 m"), (0.5, 1.0, "0.5-1.0 m"), (1.0, 1.5, "1.0-1.5 m")]
N_BOOT = 500


def sandy_change(f: pd.DataFrame, fy: pd.DataFrame, col: str, rng) -> tuple[float, float, float]:
    """Sandy-flooded - same-height dry fields (dry in the model and in FEMA's MOTF), 2013-16 mean of the
    change from each group's own 2008-12 mean; pp and 95% interval from resampling fields."""
    fl = f.sandy_share >= fieldflood.SHARE
    dry = (f.sandy_share == 0) & (f.motf_share.fillna(0) < fieldflood.SHARE)
    w = panel.height_weights(f.m_above_mhhw, f.ha, fl, dry)
    v = fy.pivot(index="field_id", columns="year", values=col).reindex(f.index)

    def chg(ids):
        m = v.loc[ids].mul(w.loc[ids], axis=0).sum() / w.loc[ids].sum()
        return m[list(range(2013, 2017))].mean() - m[list(panel.PRE)].mean()

    a, b = f.index[fl], f.index[dry]
    boot = [chg(rng.choice(a, len(a))) - chg(rng.choice(b, len(b))) for _ in range(N_BOOT)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return 100 * (chg(a) - chg(b)), 100 * lo, 100 * hi


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--panel", default="data/analysis/sandy_panel_m65")
    ap.add_argument("--tag", default="m65")
    a = ap.parse_args()
    d = config.ROOT / a.panel
    f = pd.read_csv(d / "fields.csv").set_index("field_id")
    fy = pd.read_csv(d / "field_year.csv")
    fe = pd.read_csv(d / "field_event.csv")
    f = f[panel.low_crop_fields(f, fy)].copy()
    n = fe[fe.tide_share >= 0.1].groupby("field_id").size()
    f["n_storms"] = n.reindex(f.index).fillna(0).astype(int)
    f["lulc_exit"] = [pd.notna(c) and not landuse.is_farmed(c) for c in f.lulc2020.astype(object)]
    farm = fy.assign(fm=panel.farmland(fy)).pivot(index="field_id", columns="year", values="fm").reindex(f.index)
    f["out_2023"] = farm[2023] < 0.5
    f["flagged"] = panel.left_cropland(farm)[list(range(2009, 2023))].max(axis=1) == 1
    share = {k: fy.pivot(index="field_id", columns="year", values=f"share_{k}").reindex(f.index) for k in ("corn", "soybeans")}

    def row(g: pd.DataFrame, name: str) -> dict:
        r = {"group": name, "fields": len(g), "ha": round(g.ha.sum()), "median m above MHHW": round(g.m_above_mhhw.median(), 2)}
        for k, lab in (("lulc_exit", "LU/LC exit by 2020"), ("out_2023", "out of farming 2023 (CDL)"),
                       ("flagged", "ever flagged 2009-22 (CDL)")):  # fmt: skip
            r[lab] = f"{int(g[k].sum())} ({100 * g[k].mean():.1f}%)"
        for k, s in share.items():
            pre = np.average(s.loc[g.index, range(2008, 2013)].mean(axis=1).fillna(0), weights=g.ha)
            post = np.average(s.loc[g.index, range(2019, 2024)].mean(axis=1).fillna(0), weights=g.ha)
            r[f"{k} % 2008-12 → 2019-23"] = f"{100 * pre:.0f} → {100 * post:.0f}"
        return r

    fl, nv = f[f.n_storms > 0], f[f.n_storms == 0]
    rows = [row(fl, "flooded by ≥ 1 storm tide"), row(nv, "never flooded"), row(f[f.n_storms >= 10], "flooded by ≥ 10")]
    bands = []
    for lo, hi, lab in BANDS:
        b = f[(f.m_above_mhhw >= lo) & (f.m_above_mhhw < hi)]
        for g, name in ((b[b.n_storms > 0], "flooded"), (b[b.n_storms == 0], "never flooded")):
            bands.append({"height above MHHW": lab, "group": name, "fields": len(g),
                          "LU/LC exit by 2020": f"{100 * g.lulc_exit.mean():.1f}%",
                          "out of farming 2023 (CDL)": f"{int(g.out_2023.sum())} ({100 * g.out_2023.mean():.1f}%)"})  # fmt: skip
    lev = []
    for lo, hi, lab in BANDS:
        b = f[(f.m_above_mhhw >= lo) & (f.m_above_mhhw < hi)]
        for on, name in ((False, "no levee"), (True, "behind a levee")):
            g = b[b.behind_levee.astype(bool) == on]
            lev.append({"height above MHHW": lab, "group": name, "fields": len(g),
                        "out of farming 2023 (CDL)": f"{int(g.out_2023.sum())} ({100 * g.out_2023.mean():.1f}%)"})  # fmt: skip
    hit = fe[fe.field_id.isin(f.index) & (fe.tide_share >= fieldflood.SHARE)]
    hit = hit.assign(key=hit.event + " " + hit.peak.astype(str).str[:10])
    sandy_ids = set(hit[hit.event == "sandy2012"].field_id)
    inside = hit.groupby("key").field_id.apply(lambda s: 100 * len(set(s) & sandy_ids) / len(set(s)))
    n_all = (hit.groupby("field_id").key.nunique() == hit.key.nunique()).sum()
    rng = np.random.default_rng(0)
    sandy = []
    for k in ("cropland", "corn", "soybeans"):
        pp, lo, hi = sandy_change(f, fy, k if k == "cropland" else f"share_{k}", rng)
        sandy.append({"outcome": k, "flooded - dry, 2013-16 (pp)": f"{pp:+.1f} [{lo:+.1f}, {hi:+.1f}]"})
    out = config.REPORTS / f"exit_counts_{a.tag}.md"
    out.write_text("\n".join([
        f"# Exits and crop change on low NJ crop fields, flooded vs never flooded ({a.tag})", "",
        f"Generated by `scripts/exit_counts.py --panel {a.panel} --tag {a.tag}`. Descriptive counts, no height weighting",
        "and no storm timing: flooded fields sit lower, and lower ground leaves farming faster anyway (FINDINGS §44).",
        "The timed tests (a storm season against the same fields' quiet years) are FINDINGS §53 / §57.",
        "", md_table(pd.DataFrame(rows)), "", "## By height", "", md_table(pd.DataFrame(bands)), "",
        "## By height and levee (behind_levee: >= 50% of the field inside an NLD leveed area)", "",
        md_table(pd.DataFrame(lev)), "",
        "## The same footprint", "",
        f"{len(hit.field_id.unique())} low crop fields flood in at least one of {hit.key.nunique()} storm tides; {n_all} in all of them. "
        f"Each other storm's flooded fields lying inside Sandy's: {inside.drop(index=[i for i in inside.index if i.startswith('sandy')]).min():.0f}-"
        f"{inside.drop(index=[i for i in inside.index if i.startswith('sandy')]).max():.0f}%.", "",
        "## Sandy, flooded vs same-height dry fields (FINDINGS §34 method, §71)", "",
        md_table(pd.DataFrame(sandy)), ""]))  # fmt: skip
    print(out.read_text())


if __name__ == "__main__":
    main()
