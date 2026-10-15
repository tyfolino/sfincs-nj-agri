"""Field histories v2: a multi-class Landsat classifier trained on NJDEP LU/LC, applied to
the 120 m farm cells, 1984-2025, with exit destinations and the tidal-vs-wet comparisons.

Why v2 (FINDINGS §24): CDL labels abandoned grassy fields "Other Hay", so a CDL-trained
farmed / not-farmed classifier confuses hay with old field. NJDEP's photo-interpreters do not.

1. Training: data/landuse/lulc_training_squares.gpkg (scripts/fetch_lulc_training.py: squares
   in LU/LC polygons unchanged 2015 -> 2020, 7 classes: farm, oldfield, marsh, wetwood,
   forest, developed, water), Landsat features for 2015-2020 (agri_sfincs.fieldhist.
   yearly_features; stats from landsat_field_stats.py --tag train).
2. One-vs-rest ridge logistic per class (agri_sfincs.skill.fit_logistic) on class-balanced
   resamples; probabilities normalised. Out-of-fold confusion matrix, 5 folds by square.
3. Cells (scripts/build_field_cells.py; stats --tag cells): class probabilities per year,
   3-year running mean, argmax. Farm series -> exits (agri_sfincs.fieldhist.exit_events:
   farmed in y, not farmed in any of the next 5 years); destination = the most common class
   in y+1..y+5.
4. At risk: cells LU/LC called farmed in 2012 (kind farmed2012), years 2012-2020, upland
   cells weighted by their parent's inverse sampling fraction. Rates by ground height above
   recent MHHW and destination, and two comparisons at the same height:
     tide-connected vs not  (DEM connectivity to tidal water at MHHW + 1 m: §21's
                             bayshore_exposure.connected_low; "not" = behind a bank or road)
     bayshore vs inland     (distance to tidal water <= or > NEAR_KM)

Writes data/landuse/field_classes_cells.parquet (cell, year, class probabilities, cls),
data/landuse/field_exit_events_cells_v2.parquet, reports/field_classes.md.
Usage:  python scripts/field_classes.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy import ndimage

from agri_sfincs import cdl, config, exposure, fieldhist, skill
from agri_sfincs.report import md_table

CLASSES = ["farm", "oldfield", "marsh", "wetwood", "forest", "developed", "water"]
TRAIN_YEARS = (2015, 2020)
N_PER_CLASS, LAM, SEED, WINDOW, NEAR_KM = 4000, 1.0, 20261011, 5, 2.0
BANDS = [-np.inf, 0.0, 0.6, 1.5, 3.0, np.inf]
BAND_LABELS = ["< 0", "0-0.6", "0.6-1.5", "1.5-3", "> 3"]
PERIODS = [(2012, 2016), (2017, 2020)]


def features(tag: str) -> pd.DataFrame:
    return fieldhist.yearly_features(pd.read_parquet(config.LANDSAT_DIR / f"field_scene_stats_{tag}.parquet"))


class OVR:
    """One-vs-rest ridge logistic over standardised features, NaN -> training median."""

    def fit(self, X: pd.DataFrame, y: np.ndarray):
        self.cols = [c for c in X.columns if not c.endswith("_nobs")]
        x = X[self.cols]
        self.med = x.median()
        x = x.fillna(self.med)
        self.mu, self.sd = x.mean(), x.std().replace(0, 1)
        z = ((x - self.mu) / self.sd).values
        self.b = {c: skill.fit_logistic(z, (y == c).astype(float), lam=LAM) for c in CLASSES}
        return self

    def proba(self, X: pd.DataFrame) -> pd.DataFrame:
        z = ((X[self.cols].fillna(self.med) - self.mu) / self.sd).values
        p = np.column_stack([skill.predict_logistic(self.b[c], z) for c in CLASSES])
        p = p / p.sum(axis=1, keepdims=True)
        return pd.DataFrame(p, index=X.index, columns=CLASSES)


def balanced(T: pd.DataFrame, rng) -> pd.DataFrame:
    return pd.concat([T[T.cls == c].sample(N_PER_CLASS, replace=True, random_state=int(rng.integers(1 << 31)))
                      for c in CLASSES if (T.cls == c).any()])  # fmt: skip


def train(rng):
    sq = gpd.read_file(config.LANDUSE_DIR / "lulc_training_squares.gpkg").set_index("sq")
    F = features("train")
    yr = F.index.get_level_values(1)
    F = F[(yr >= TRAIN_YEARS[0]) & (yr <= TRAIN_YEARS[1]) & F.su_ndvi.notna()]
    T = F.copy()
    T["sq"] = T.index.get_level_values(0)
    T["cls"] = sq.cls.reindex(T.sq).values
    T = T[T.cls.notna()]
    # out-of-fold confusion, folds by square
    sqs = T.sq.unique()
    fold = pd.Series(rng.integers(0, 5, sqs.size), index=sqs)
    T["fold"] = T.sq.map(fold)
    pred = pd.Series(index=T.index, dtype=object)
    for k in range(5):
        tr = balanced(T[T.fold != k], rng)
        m = OVR().fit(tr.drop(columns=["cls", "sq", "fold"]), tr.cls.values)
        te = T[T.fold == k]
        pred[te.index] = m.proba(te.drop(columns=["cls", "sq", "fold"])).idxmax(axis=1)
    cm = pd.crosstab(T.cls, pred, rownames=["LU/LC"], colnames=["predicted"]).reindex(
        index=CLASSES, columns=CLASSES, fill_value=0)  # fmt: skip
    tr = balanced(T, rng)
    model = OVR().fit(tr.drop(columns=["cls", "sq", "fold"]), tr.cls.values)
    return model, cm, T


def cell_context(cells: gpd.GeoDataFrame) -> pd.DataFrame:
    """Per cell: tide-connected at MHHW + 1 m (centroid cell of the §21 grid) and km to tidal water."""
    G = exposure.load_grid()
    cdl25 = cdl.read(2025, G.win)
    valid = np.isfinite(G.z_mean)
    seed = np.isin(cdl25, [0, 83, 111]) & (G.z_mean < 0.0)
    zmax = np.where(valid, G.z_max, np.inf)
    zmean = np.where(valid, G.z_mean, np.inf)
    low, con = exposure.connected_low(zmean, zmax, G.hw["mhhw"] + 1.0, seed)
    dist = ndimage.distance_transform_edt(~seed) * abs(G.tr.a) / 1000.0
    pts = cells.geometry.representative_point()
    x, y = Transformer.from_crs(cells.crs, G.crs, always_xy=True).transform(pts.x.values, pts.y.values)
    r = np.clip(((y - G.tr.f) / G.tr.e).astype(int), 0, G.shape[0] - 1)
    c = np.clip(((x - G.tr.c) / G.tr.a).astype(int), 0, G.shape[1] - 1)
    return pd.DataFrame({"tide_connected": con[r, c], "low_1m": low[r, c], "km_to_tide": dist[r, c]},
                        index=cells.index)  # fmt: skip


def main() -> None:
    rng = np.random.default_rng(SEED)
    model, cm, T = train(rng)
    acc = np.trace(cm.values) / cm.values.sum()
    recall = (np.diag(cm.values) / cm.sum(axis=1).values)

    cells = gpd.read_file(config.LANDUSE_DIR / "field_cells.gpkg").rename(columns={"unit": "parent"})
    cells = cells.rename(columns={"cell": "unit"}).set_index("unit")
    parents = gpd.read_file(config.LANDUSE_DIR / "field_units.gpkg")
    t = gpd.read_file(config.LANDUSE_DIR / "farm_wetland_transitions.gpkg")
    n_up = int(((t.y0 == 2012) & ~(t.m_above_mhhw < 3.0)).sum())
    up_parent = set(parents.loc[(parents.kind == "farmed2012") & ~(parents.m_above_mhhw < 3.0), "unit"])
    cells["w"] = np.where(cells.parent.isin(list(up_parent)), n_up / max(len(up_parent), 1), 1.0)
    cells["band"] = pd.cut(cells.m_above_mhhw, BANDS, labels=BAND_LABELS)
    cells = cells.join(cell_context(cells))
    cells["setting"] = np.where(cells.km_to_tide <= NEAR_KM, "bayshore", "inland")

    F = features("cells")
    F = F[F.su_ndvi.notna() & (F.index.get_level_values(1) <= 2025)]
    P = model.proba(F)
    Ps = P.groupby(level=0).transform(lambda s: s.rolling(3, center=True, min_periods=1).mean())
    cls = Ps.idxmax(axis=1).rename("cls")
    top = cls.value_counts(normalize=True)
    if top.iloc[0] > 0.9:  # 2026-10-06: a diverged fit once put every cell-year in one class
        raise RuntimeError(f"{top.index[0]} takes {100 * top.iloc[0]:.0f}% of cell-years: check the fit")
    out = Ps.join(cls).reset_index()
    out.to_parquet(config.LANDUSE_DIR / "field_classes_cells.parquet", index=False)

    rows = []
    for u, g in out.groupby("unit"):
        yrs = g.year.values
        full = np.arange(yrs.min(), yrs.max() + 1)
        c = g.set_index("year").cls.reindex(full)
        f = np.where(c.isna(), np.nan, (c == "farm").astype(float))
        risk, ex = fieldhist.exit_events(full, f, window=WINDOW)
        for i in np.flatnonzero(risk):
            dest = None
            if ex[i]:
                nxt = c.iloc[i + 1 : i + 1 + WINDOW].dropna()
                dest = nxt.mode().iloc[0] if len(nxt) else None
            rows.append((u, int(full[i]), bool(ex[i]), dest))
    E = pd.DataFrame(rows, columns=["unit", "year", "exit", "dest"])
    E = E.join(cells[["kind", "ha", "w", "band", "m_above_mhhw", "tide_connected", "km_to_tide",
                      "setting", "county", "parent"]], on="unit")  # fmt: skip
    E = E[(E.kind == "farmed2012") & (E.year >= 2012)]
    E.to_parquet(config.LANDUSE_DIR / "field_exit_events_cells_v2.parquet", index=False)

    def rate(x, dests=None):
        a = (x.ha * x.w).sum()
        hit = x.exit if dests is None else x.exit & x.dest.isin(dests)
        return 100 * (x.ha * x.w * hit).sum() / a if a else np.nan

    natural = ["oldfield", "marsh", "wetwood", "forest", "water"]
    tab = {}
    for (y0, y1) in PERIODS:
        x = E[E.year.between(y0, y1)]
        for b in BAND_LABELS:
            xb = x[x.band == b]
            tab[(f"{y0}-{y1}", b)] = {"to vegetation/water": rate(xb, natural),
                                      "to marsh/wet": rate(xb, ["marsh", "wetwood", "water"]),
                                      "to development": rate(xb, ["developed"]),
                                      "exits": int((xb.exit & xb.dest.isin(natural)).sum())}  # fmt: skip
    hz = pd.DataFrame(tab).T
    hz.index.names = ["period", "m above MHHW"]

    x = E[E.year.between(2012, 2020) & (E.m_above_mhhw < 1.0)]
    cmp1 = x.groupby("tide_connected").apply(lambda d: pd.Series({
        "farmed ha-yr": (d.ha * d.w).sum(), "%/yr to vegetation": rate(d, natural),
        "%/yr to marsh/wet": rate(d, ["marsh", "wetwood", "water"])}), include_groups=False)  # fmt: skip
    cmp1.index = ["behind a bank / road" if not v else "tide-connected" for v in cmp1.index]
    x2 = E[E.year.between(2012, 2020) & (E.m_above_mhhw < 3.0)]
    cmp2 = x2.groupby("setting").apply(lambda d: pd.Series({
        "farmed ha-yr": (d.ha * d.w).sum(), "%/yr to vegetation": rate(d, natural),
        "%/yr to marsh/wet": rate(d, ["marsh", "wetwood", "water"])}), include_groups=False)  # fmt: skip
    dest = (E[E.exit & E.year.between(2012, 2020)].assign(lowup=lambda d: np.where(d.m_above_mhhw < 0.6, "low < 0.6 m", np.where(d.m_above_mhhw > 3, "upland > 3 m", "middle")))
            .pivot_table(index="dest", columns="lowup", values="ha", aggfunc="sum", fill_value=0))  # fmt: skip

    cmo = cm.copy()
    cmo["recall"] = (100 * recall).round(0)
    lines = ["# Field histories v2: multi-class Landsat classifier trained on NJDEP LU/LC (2026-10-05)", "",
             "Generated by `scripts/field_classes.py` (method in its docstring).", "",
             f"**Classifier:** {len(T):,} square-years, 2015-2020; out-of-fold accuracy **{100 * acc:.1f}%** "
             "(5 folds by square; rows = LU/LC class, columns = predicted).", "",
             md_table(cmo), "",
             "## Exit rates, cells LU/LC-farmed in 2012 (% of farmed area per year; out for all of the next 5 years)", "",
             md_table(hz.round(3), floatfmt="{:.3f}"), "",
             "## Same height, different tidal access (ground < MHHW + 1 m, 2012-2020)", "",
             md_table(cmp1.round(3), floatfmt="{:.3f}"), "",
             f"## Bayshore (≤ {NEAR_KM:g} km from tidal water) vs inland (ground < MHHW + 3 m, 2012-2020)", "",
             md_table(cmp2.round(3), floatfmt="{:.3f}"), "",
             "## Where exits went (ha, 2012-2020)", "", md_table(dest.round(1), floatfmt="{:.1f}"), ""]  # fmt: skip
    text = "\n".join(lines)
    (config.REPORTS / "field_classes.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
