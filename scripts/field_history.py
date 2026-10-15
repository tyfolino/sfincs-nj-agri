"""When did each field stop being farmed? Landsat 1984-2025, trained on CDL, checked on NAIP.

1. Features per unit-year from data/landsat/field_scene_stats.parquet
   (agri_sfincs.fieldhist.yearly_features: spring / summer / fall medians of NDVI, MNDWI,
   BSI, SWIR1, NIR, the summer NDVI max and the spring NDVI min).
2. Labels for 2008-2025 from CDL inside each unit (inset 15 m, so no edge pixels):
   farmed = CDL cropland share >= 0.7, not farmed = <= 0.1, in between left out; plus the
   marsh_ref units as not farmed in every year. Units checked on NAIP (FINDINGS §21, §23)
   are HELD OUT of training.
3. Ridge logistic (agri_sfincs.skill.fit_logistic) on standardised features, missing
   spring/fall filled by the training median. Out-of-fold AUC by 5 unit-grouped folds.
4. Per unit: P(farmed) per year, 3-year running median, farmed = > 0.5;
   exit year = agri_sfincs.fieldhist.exit_year (>= 3 later years not farmed, to the end;
   the "last farmed" date for maps); exit RATES use agri_sfincs.fieldhist.exit_events
   (farmed in y, not farmed in any of the next 5 years), so every period meets one test.
5. Checks: NAIP-verified units; LU/LC (a unit LU/LC says left farming between y0 and y1
   should be farmed near y0 and not farmed after y1).
6. Result: exit rate (% of farmed area per year) by ground height above recent MHHW and
   period, upland farmed2012 units weighted by their inverse sampling fraction
   (scripts/build_field_units.py); and the summer MNDWI change across the exit (wetter?).

With --tag cells it runs on the 120 m cells (scripts/build_field_cells.py; stats from
landsat_field_stats.py --tag cells); sampling weights then come from each cell's parent unit.
With --target row, "farmed" = ROW crops (CDL row-crop share >= 0.7; not farmed = neither row
crops nor hay-like / grass), and every output gets a _row suffix.
Superseded for exits by the multi-class scripts/field_classes.py (FINDINGS §28); kept for §24.

Writes, with <sfx> = [_<tag>][_row]: data/landuse/field_history<sfx>.parquet (unit, year, p,
p_smooth, farmed), data/landuse/field_exit<sfx>.csv, data/landuse/field_exit_events<sfx>.parquet
(per unit-year at risk: exit or not; read by scripts/exit_spotcheck.py),
reports/field_history<sfx>.md and reports/figs/field_history<sfx>.png.
Usage:  python scripts/field_history.py [--tag cells] [--target crop | row]
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds

from agri_sfincs import cdl, config, fieldhist, skill
from agri_sfincs.report import md_table

STATS = config.LANDSAT_DIR / "field_scene_stats.parquet"
UNITS = config.LANDUSE_DIR / "field_units.gpkg"
TRANS = config.LANDUSE_DIR / "farm_wetland_transitions.gpkg"
NAIP_FARMED = {"lulc": ["O24", "O25", "O27", "O28", "O30", "O31", "O32", "O34", "O35", "O36",
                        "O37", "O39", "O42", "O43", "O44"],
               "cdl": [f"K{i}" for i in range(36, 48)]}  # fmt: skip
NAIP_CONV = {"lulc": ["O29", "O38", "O45", "O46"],
             "cdl": ["X00", "X02", "X03", "X04", "X07", "X19", "X20", "X22", "X30"]}  # fmt: skip
BANDS = [-np.inf, 0.0, 0.6, 1.5, 3.0, np.inf]
BAND_LABELS = ["< 0", "0-0.6", "0.6-1.5", "1.5-3", "> 3"]
PERIODS = [(1986, 1995), (1996, 2005), (2006, 2015), (2016, 2020)]  # exits need 5 years after
WINDOW = 5
PERIODS_C = [(2009, 2014), (2015, 2020)]  # Landsat + CDL-confirmed exits
LAM, SEED = 1.0, 20261008


#: CDL "cropland" that is NOT annual cropping: alfalfa, other hay, clover, sod, switchgrass,
#: fallow. CDL labels abandoned grassy fields "Other Hay" (NAIP check, FINDINGS §24), so these
#: are ambiguous and are left out of the row-crop labels.
HAYLIKE = frozenset({36, 37, 58, 59, 60, 61})
ROWCROP = frozenset(cdl.CROPLAND - HAYLIKE)


def cdl_shares(units: gpd.GeoDataFrame, inset_m: float = 15.0) -> pd.DataFrame:
    """CDL cropland share and annual row-crop / hay-like shares inside each unit (inset
    ``inset_m``), 2008-2025."""
    with rasterio.open(cdl.path(2025)) as c:
        u = units.to_crs(c.crs)
        win = from_bounds(*u.total_bounds, transform=c.transform).round_offsets().round_lengths()
        tr, shape = c.window_transform(win), (int(win.height), int(win.width))
    ins = u.geometry.buffer(-inset_m) if inset_m else u.geometry
    lab = rasterize([(g, int(i)) for g, i in zip(ins, u.unit) if not g.is_empty], out_shape=shape,
                    transform=tr, fill=0, dtype="int32")  # fmt: skip
    m = lab > 0
    n = np.bincount(lab[m], minlength=int(u.unit.max()) + 1)
    rows = []
    for y in range(2008, 2026):
        a = cdl.read(y, win)
        sh = {}
        for k, codes in (("cdl_crop", cdl.CROPLAND), ("cdl_row", ROWCROP), ("cdl_hay", HAYLIKE | {176})):
            c = np.bincount(lab[m], weights=np.isin(a[m], list(codes)), minlength=n.size)
            with np.errstate(invalid="ignore", divide="ignore"):
                sh[k] = c / n
        ok = np.flatnonzero(n >= 2)
        rows.append(pd.DataFrame({"unit": ok, "year": y, **{k: v[ok] for k, v in sh.items()}}))
    return pd.concat(rows).set_index(["unit", "year"])


def ref_units(units: gpd.GeoDataFrame, which: dict) -> dict:
    out = {}
    for src, ids in which.items():
        f = config.IMAGERY_DIR / ("lulc_samples.csv" if src == "lulc" else "spotcheck_samples.csv")
        s = pd.read_csv(f)
        s = s[s.id.isin(ids)]
        p = gpd.GeoDataFrame(s, geometry=gpd.points_from_xy(s.lon, s.lat), crs=4326).to_crs(units.crs)
        j = gpd.sjoin(p, units[["unit", "geometry"]], predicate="within", how="left")
        out.update({r.id: int(r.unit) for r in j.itertuples() if pd.notna(r.unit)})
    return out


def fit_predict(F: pd.DataFrame, lab: pd.Series, units_train, folds: int = 5):
    cols = [c for c in F.columns if not c.endswith("_nobs")]
    tr = F.loc[lab.index][cols]
    med = tr.median()
    mu, sd = tr.fillna(med).mean(), tr.fillna(med).std().replace(0, 1)

    def X(df):
        return ((df[cols].fillna(med) - mu) / sd).values

    # out-of-fold AUC, folds by unit
    rng = np.random.default_rng(SEED)
    uu = np.array(sorted(set(units_train)))
    fold = dict(zip(uu, rng.integers(0, folds, uu.size)))
    fi = np.array([fold[u] for u in lab.index.get_level_values(0)])
    oof = np.full(len(lab), np.nan)
    for k in range(folds):
        b = skill.fit_logistic(X(tr[fi != k]), lab.values[fi != k], lam=LAM)
        oof[fi == k] = skill.predict_logistic(b, X(tr[fi == k]))
    b = skill.fit_logistic(X(tr), lab.values, lam=LAM)
    p = pd.Series(skill.predict_logistic(b, X(F)), index=F.index, name="p")
    p[F.su_ndvi.isna()] = np.nan  # no clear summer scene: unknown
    return p, oof, dict(zip(["intercept"] + cols, b))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", default="", help="'cells' for the 120 m cells")
    ap.add_argument("--target", default="crop", choices=["crop", "row"],
                    help="farmed = any CDL cropland (crop) or annual row crops only (row)")
    a = ap.parse_args()
    sfx = (f"_{a.tag}" if a.tag else "") + ("_row" if a.target == "row" else "")
    parents = gpd.read_file(UNITS)
    if a.tag == "cells":
        units = gpd.read_file(config.LANDUSE_DIR / "field_cells.gpkg").rename(columns={"unit": "parent"})
        units = units.rename(columns={"cell": "unit"})
    else:
        units = parents.assign(parent=parents.unit)
    F = fieldhist.yearly_features(pd.read_parquet(
        config.LANDSAT_DIR / f"field_scene_stats{'_' + a.tag if a.tag else ''}.parquet"))  # fmt: skip
    F = F[F.index.get_level_values(1) <= 2025]
    sh = cdl_shares(units, inset_m=0.0 if a.tag == "cells" else 15.0)
    vf, vc = ref_units(units, NAIP_FARMED), ref_units(units, NAIP_CONV)
    held = set(vf.values()) | set(vc.values())
    marsh = set(units.loc[units.kind == "marsh_ref", "unit"])

    J = F.join(sh, how="left")
    if a.target == "row":  # farmed = row crops; not = neither row crops nor hay-like/grass
        lab = pd.Series(np.where(J.cdl_row >= 0.7, 1.0,
                                 np.where((J.cdl_row <= 0.1) & (J.cdl_hay <= 0.1), 0.0, np.nan)),
                        index=J.index)  # fmt: skip
    else:
        lab = pd.Series(np.where(J.cdl_crop >= 0.7, 1.0, np.where(J.cdl_crop <= 0.1, 0.0, np.nan)),
                        index=J.index)  # fmt: skip
    um = J.index.get_level_values(0)
    lab[um.isin(list(marsh))] = 0.0
    lab[um.isin(list(held))] = np.nan
    lab = lab[lab.notna() & J.su_ndvi.notna()]
    p, oof, coef = fit_predict(F, lab, lab.index.get_level_values(0))
    auc = skill.auc(lab.values, oof)
    acc = float(((oof > 0.5) == (lab.values > 0.5)).mean())

    H = p.to_frame()
    H["p_smooth"] = H.groupby(level=0).p.transform(lambda s: s.rolling(3, center=True, min_periods=1).median())
    H["farmed"] = (H.p_smooth > 0.5).astype(float).where(H.p_smooth.notna())
    H.reset_index().to_parquet(config.LANDUSE_DIR / f"field_history{sfx}.parquet", index=False)

    ex = {u: fieldhist.exit_year(g.index.get_level_values(1), g.farmed.values)
          for u, g in H.groupby(level=0)}  # fmt: skip
    ever = H.groupby(level=0).farmed.max()
    U = units.drop(columns="geometry").set_index("unit")
    U["ever_farmed"] = ever.reindex(U.index)
    U["exit_year"] = pd.Series(ex).reindex(U.index)
    t = gpd.read_file(TRANS)
    n_up = int(((t.y0 == 2012) & ~(t.m_above_mhhw < 3.0)).sum())
    up_parent = set(parents.loc[(parents.kind == "farmed2012") & ~(parents.m_above_mhhw < 3.0), "unit"])
    n_up_s = len(up_parent)
    U["w"] = np.where(U.parent.isin(list(up_parent)), n_up / max(n_up_s, 1), 1.0)
    U["band"] = pd.cut(U.m_above_mhhw, BANDS, labels=BAND_LABELS)

    # wetness across the exit: summer MNDWI, 3 years after minus 3 years before
    mn = F.su_mndwi
    dm = {}
    for u, y in U.exit_year.dropna().items():
        s = mn.loc[u] if u in mn.index.get_level_values(0) else None
        if s is None:
            continue
        before, after = s[(s.index > y - 3) & (s.index <= y)], s[(s.index > y) & (s.index <= y + 3)]
        if len(before) and len(after):
            dm[u] = after.mean() - before.mean()
    U["d_mndwi"] = pd.Series(dm).reindex(U.index)
    U.reset_index().to_csv(config.LANDUSE_DIR / f"field_exit{sfx}.csv", index=False)

    # exit hazard by band x period, area-weighted, fixed 5-year look-ahead (exit_events)
    ev_rows = []
    for u, g in H.groupby(level=0):
        yrs = g.index.get_level_values(1).values
        full = np.arange(yrs.min(), yrs.max() + 1)
        f = g.farmed.droplevel(0).reindex(full).values
        risk, ex = fieldhist.exit_events(full, f, window=WINDOW)
        if risk.any():
            ev_rows.append(pd.DataFrame({"unit": u, "year": full[risk], "exit": ex[risk]}))
    E = pd.concat(ev_rows).merge(U[["ha", "w", "band", "kind"]], left_on="unit", right_index=True)
    E = E[E.kind != "marsh_ref"]
    # CDL second opinion, 2008-2021 (interior pixels only, so CDL's edge problem is absent):
    # at risk only if CDL crop share >= 0.5 in y or y-1; exit only if <= 0.2 in each of y+1..y+3
    cc = sh.cdl_row if a.target == "row" else sh.cdl_crop
    def cdl(u, y):
        return cc.get((u, y), np.nan)
    E["cdl_now"] = [np.nanmax([cdl(u, y), cdl(u, y - 1)]) if (u, y) in cc.index or (u, y - 1) in cc.index
                    else np.nan for u, y in zip(E.unit, E.year)]  # fmt: skip
    E["cdl_after"] = [np.nanmax([cdl(u, y + k) for k in (1, 2, 3)])
                      if any((u, y + k) in cc.index for k in (1, 2, 3)) else np.nan
                      for u, y in zip(E.unit, E.year)]  # fmt: skip
    E["risk_c"] = E.year.between(2009, 2021) & (E.cdl_now >= 0.5)
    E["exit_c"] = E.risk_c & E.exit & (E.cdl_after <= 0.2)
    E.to_parquet(config.LANDUSE_DIR / f"field_exit_events{sfx}.parquet", index=False)
    rows = []
    for (y0, y1) in PERIODS:
        for b in BAND_LABELS:
            x = E[(E.band == b) & E.year.between(y0, y1)]
            ar, ev = (x.ha * x.w).sum(), (x.ha * x.w * x.exit).sum()
            rows.append({"period": f"{y0}-{y1}", "m above MHHW": b, "farmed ha-yr": ar,
                         "exits ha": ev, "units exiting": int(x.exit.sum()),
                         "%/yr": 100 * ev / ar if ar else np.nan})  # fmt: skip
    hz = pd.DataFrame(rows)
    hzp = hz.pivot(index="m above MHHW", columns="period", values="%/yr").reindex(BAND_LABELS)
    hzn = hz.pivot(index="m above MHHW", columns="period", values="units exiting").reindex(BAND_LABELS)
    crow = []
    for (y0, y1) in PERIODS_C:
        for b in BAND_LABELS:
            x = E[(E.band == b) & E.year.between(y0, y1) & E.risk_c]
            ar, ev = (x.ha * x.w).sum(), (x.ha * x.w * x.exit_c).sum()
            crow.append({"period": f"{y0}-{y1}", "m above MHHW": b, "%/yr": 100 * ev / ar if ar else np.nan,
                         "exits": int(x.exit_c.sum()), "farmed ha-yr": ar})  # fmt: skip
    hc = pd.DataFrame(crow)
    hcp = hc.pivot(index="m above MHHW", columns="period", values="%/yr").reindex(BAND_LABELS)
    hcn = hc.pivot(index="m above MHHW", columns="period", values="exits").reindex(BAND_LABELS)

    # checks
    def frac_farmed(us, y0, y1):
        x = H.loc[H.index.get_level_values(0).isin(us)]
        x = x[(x.index.get_level_values(1) >= y0) & (x.index.get_level_values(1) <= y1)]
        return float(x.farmed.mean())

    chk = [{"set": "NAIP farmed (held out)", "units": len(vf),
            "result": f"{100 * frac_farmed(list(vf.values()), 2010, 2023):.0f}% of 2010-23 unit-years farmed"}]  # fmt: skip
    vce = U.loc[list(set(vc.values())), ["exit_year"]]
    chk.append({"set": "NAIP converted (held out)", "units": len(vce),
                "result": "exit years " + ", ".join(str(int(v)) if pd.notna(v) else "none"
                                                    for v in vce.exit_year)})  # fmt: skip
    mr = H.loc[H.index.get_level_values(0).isin(list(marsh))]
    chk.append({"set": "marsh refs (trained on)", "units": len(marsh),
                "result": f"{100 * mr.farmed.mean():.1f}% of unit-years farmed"})
    # LU/LC early conversions: farmed at y0 (+-1) and not farmed by y1 + 2
    ce = U[(U.kind == "conv_pre2012") & U.y0.notna()]
    ok0 = ok1 = n = 0
    for u, r in ce.iterrows():
        if u not in H.index.get_level_values(0):
            continue
        s = H.loc[u].farmed
        a = s[(s.index >= r.y0 - 1) & (s.index <= r.y0 + 1)]
        bb = s[(s.index > r.y1) & (s.index <= r.y1 + 3)]
        if a.notna().any() and bb.notna().any():
            n += 1
            ok0 += int(a.max() == 1)
            ok1 += int(bb.max() == 0)
    chk.append({"set": "LU/LC conversions 1995-2012", "units": n,
                "result": f"farmed near y0: {100 * ok0 / max(n, 1):.0f}%; not farmed after y1: "
                          f"{100 * ok1 / max(n, 1):.0f}%"})  # fmt: skip

    wet = U[U.exit_year.notna() & U.d_mndwi.notna()].copy()
    wet_t = wet.groupby("band", observed=True).agg(exits=("d_mndwi", "size"),
                                                   d_mndwi_median=("d_mndwi", "median"),
                                                   wetter_share=("d_mndwi", lambda s: (s > 0.05).mean()))  # fmt: skip

    lines = ["# Field farming histories from Landsat, 1984-2025 (2026-10-05)", "",
             f"Figure: `figs/field_history{sfx}.png`.", "",
             "Generated by `scripts/field_history.py` (method in its docstring). Units = NJDEP LU/LC "
             "farm polygons (`scripts/build_field_units.py`): all farmed-in-2012 fields below MHHW + 3 m, "
             f"{n_up_s} of {n_up} higher ones (weighted ×{n_up / max(n_up_s, 1):.1f}), every 1995-2012 "
             "conversion, and 200 stable-marsh references.", "",
             f"**Classifier:** CDL-labelled unit-years 2008-25 + marsh refs, n = {len(lab):,}; "
             f"out-of-fold AUC **{auc:.3f}**, accuracy {100 * acc:.1f}% (5 folds by unit).", "",
             "## Checks", "", md_table(pd.DataFrame(chk).set_index("set")), "",
             f"## Exit rate: % of farmed area leaving farming per year (out for all of the next {WINDOW} years)", "",
             md_table(hzp.round(2), floatfmt="{:.2f}"), "",
             "Units exiting (count):", "", md_table(hzn, floatfmt="{:.0f}"), "",
             "## Confirmed exits, 2009-2020: Landsat AND CDL agree (farmed: CDL crop >= 0.5 in y or "
             "y-1; out: Landsat for 5 years and CDL crop <= 0.2 in each of the next 3)", "",
             md_table(hcp.round(3), floatfmt="{:.3f}"), "", "Confirmed exits (count):", "",
             md_table(hcn, floatfmt="{:.0f}"), "",
             "## Wetter after the exit? Summer MNDWI, 3 years after minus 3 years before", "",
             md_table(wet_t.round(3), floatfmt="{:.3f}"), "",
             "## Classifier coefficients (standardised features)", "",
             md_table(pd.Series(coef, name="beta").round(2).to_frame(), floatfmt="{:.2f}"), ""]  # fmt: skip
    text = "\n".join(lines)
    (config.REPORTS / f"field_history{sfx}.md").write_text(text + "\n")
    print(text)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for b in BAND_LABELS:
        ax.plot(range(len(PERIODS)), hzp.loc[b].values, marker="o", label=f"{b} m above MHHW")
    ax.set_xticks(range(len(PERIODS)), [f"{a}-{b}" for a, b in PERIODS])
    ax.set_ylabel("% of farmed area leaving farming per year")
    ax.legend(fontsize=8)
    ax.set_title("Field exits from farming by ground height (Landsat, NJ bayshore counties)")
    fig.tight_layout()
    fig.savefig(config.REPORTS / "figs" / f"field_history{sfx}.png", dpi=150)


if __name__ == "__main__":
    main()
