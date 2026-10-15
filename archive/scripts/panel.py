"""Fork 1 helpers (pure; numpy + pandas): cropland-weighted county means, flood-prone
shares, and Poisson pseudo-maximum likelihood (PPML) / logit with high-dimensional
fixed effects and (multiway) cluster-robust sandwich standard errors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def weighted_county_mean(fips, weight, value) -> pd.Series:
    """Weighted mean of ``value`` per ``fips`` (rows with NaN value are left out and the
    rest renormalized); NaN for a county with no valid row."""
    d = pd.DataFrame({"f": np.asarray(fips), "w": np.asarray(weight, float),
                      "v": np.asarray(value, float)})  # fmt: skip
    ok = np.isfinite(d.v) & (d.w > 0)
    d["wv"] = (d.w * d.v).where(ok, 0.0)
    d["w"] = d.w.where(ok, 0.0)
    g = d.groupby("f")[["wv", "w"]].sum()
    return (g.wv / g.w.where(g.w > 0)).rename("mean")


# --------------------------------------------------------------------------- shares


def cropland_shares(land, in_county, zones: dict, crop_codes) -> dict:
    """Cropland pixel count in a county and, per zone mask, the share of that cropland
    inside the zone: ``{"n_crop": n, "share_<zone>": float}`` (NaN shares when the
    county has no cropland). ``land`` holds CDL class codes; ``in_county`` and each zone
    are boolean arrays of the same shape."""
    crop = np.isin(np.asarray(land), np.fromiter(crop_codes, int)) & np.asarray(in_county, bool)
    n = int(crop.sum())
    out = {"n_crop": n}
    for k, z in zones.items():
        out[f"share_{k}"] = float((crop & np.asarray(z, bool)).sum() / n) if n else float("nan")
    return out


def relative_elevation(dem, radius_px: float) -> np.ndarray:
    """Height above the lowest cell within ``radius_px`` (a disk): a cheap stand-in for
    height above nearest drainage. NaN cells are ignored as minima and stay NaN."""
    from scipy.ndimage import minimum_filter

    z = np.asarray(dem, float)
    r = int(np.floor(radius_px))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disk = (yy**2 + xx**2) <= radius_px**2
    filled = np.where(np.isfinite(z), z, np.inf)
    low = minimum_filter(filled, footprint=disk, mode="nearest")
    return np.where(np.isfinite(z), z - low, np.nan)


# ------------------------------------------------------- fixed-effect GLMs (IRLS)


def codes(*keys) -> np.ndarray:
    """Integer group codes 0..G-1 for one key array or the combination of several."""
    if len(keys) == 1:
        return pd.factorize(np.asarray(keys[0]))[0]
    return pd.MultiIndex.from_arrays([np.asarray(k) for k in keys]).factorize()[0]


def demean(A, fe: list, w, tol: float = 1e-10, max_iter: int = 10_000) -> np.ndarray:
    """Weighted within-transformation of the columns of ``A`` with respect to several
    sets of fixed effects (``fe``: list of integer code arrays), by alternating
    projections: the residual of a weighted least-squares regression of each column on
    all the FE dummies (Frisch-Waugh-Lovell)."""
    A = np.array(A, float, copy=True)
    one_d = A.ndim == 1
    if one_d:
        A = A[:, None]
    w = np.asarray(w, float)
    sw = [np.bincount(g, w) for g in fe]
    scale = np.maximum(np.abs(A).max(axis=0), 1e-300)
    for _ in range(max_iter):
        delta = 0.0
        for g, s in zip(fe, sw):
            for j in range(A.shape[1]):
                m = np.bincount(g, w * A[:, j], minlength=len(s)) / np.where(s > 0, s, 1.0)
                A[:, j] -= m[g]
                delta = max(delta, float(np.abs(m).max() / scale[j]))
        if delta < tol or len(fe) == 1:
            break
    return A[:, 0] if one_d else A


def drop_degenerate(y, fe: list, binary: bool = False) -> np.ndarray:
    """Mask of observations to keep: repeatedly drops every FE group whose outcome is
    all zero (PPML and logit: its FE goes to minus infinity) or, for ``binary``, all one.
    Those observations carry no information about the slopes."""
    y = np.asarray(y, float)
    keep = np.ones(len(y), bool)
    changed = True
    while changed:
        changed = False
        for g in fe:
            gg = np.where(keep, g, -1)
            n = np.bincount(gg[keep], minlength=g.max() + 1)
            s = np.bincount(gg[keep], y[keep], minlength=g.max() + 1)
            bad = (s <= 0) | ((s >= n) if binary else False)
            bad &= n > 0
            drop = keep & bad[g]
            if drop.any():
                keep &= ~drop
                changed = True
    return keep


def _irls(y, X, fe, offset, family: str, tol: float, max_iter: int) -> dict:
    n = len(y)
    off = np.zeros(n) if offset is None else np.asarray(offset, float)
    if family == "poisson":
        mu = (y + y.mean()) / 2.0
        eta = np.log(mu)
    else:
        mu = (y + 0.5) / 2.0
        eta = np.log(mu / (1 - mu))
    dev_old = np.inf
    for it in range(1, max_iter + 1):
        if family == "poisson":
            w = mu
            z = eta - off + (y - mu) / mu
        else:
            w = mu * (1 - mu)
            z = eta - off + (y - mu) / w
        Zt = demean(np.column_stack([z, X]), fe, w)
        zt, Xt = Zt[:, 0], Zt[:, 1:]
        sw = np.sqrt(w)
        beta = np.linalg.lstsq(Xt * sw[:, None], zt * sw, rcond=None)[0]
        resid = zt - Xt @ beta
        eta = off + z - resid
        if family == "poisson":
            mu = np.exp(eta)
            pos = y > 0
            dev = 2 * (np.sum(y[pos] * np.log(y[pos] / mu[pos])) - np.sum(y - mu))
        else:
            mu = np.clip(1 / (1 + np.exp(-eta)), 1e-12, 1 - 1e-12)
            dev = -2 * np.sum(y * np.log(mu) + (1 - y) * np.log(1 - mu))
        if abs(dev - dev_old) / (abs(dev) + 0.1) < tol:
            break
        dev_old = dev
    w = mu if family == "poisson" else mu * (1 - mu)
    Xt = demean(X, fe, w)
    return {"beta": beta, "mu": mu, "eta": eta, "Xt": Xt, "w": w, "iterations": it,
            "converged": it < max_iter, "deviance": dev}  # fmt: skip


def _meat(Xt, u, g) -> np.ndarray:
    G = g.max() + 1
    S = np.zeros((G, Xt.shape[1]))
    np.add.at(S, g, Xt * u[:, None])
    return G / (G - 1) * (S.T @ S)


def cluster_vcov(Xt, w, u, cluster) -> np.ndarray:
    """Cluster-robust sandwich for a GLM with canonical link: bread (Xt' W Xt)^-1, meat
    = sum over clusters of (sum_i Xt_i u_i)(...)' with the small-sample factor G/(G-1).
    ``Xt`` are the regressors with the fixed effects partialled out (weights ``w``),
    ``u`` = y - mu. ``cluster`` is one array, or a list of arrays for multiway
    clustering (Cameron, Gelbach & Miller 2011: inclusion-exclusion over the
    intersections; negative eigenvalues of the result clipped to 0)."""
    from itertools import combinations

    Xt = np.asarray(Xt, float)
    u = np.asarray(u, float)
    bread = np.linalg.inv(Xt.T @ (Xt * np.asarray(w, float)[:, None]))
    ways = list(cluster) if isinstance(cluster, (list, tuple)) else [cluster]
    meat = np.zeros((Xt.shape[1], Xt.shape[1]))
    for r in range(1, len(ways) + 1):
        for sub in combinations(ways, r):
            meat += (-1) ** (r + 1) * _meat(Xt, u, codes(*sub))
    V = bread @ meat @ bread
    if len(ways) > 1:
        ev, vec = np.linalg.eigh((V + V.T) / 2)
        if ev.min() < 0:
            V = vec @ np.diag(np.clip(ev, 0, None)) @ vec.T
    return V


def fit_fe_glm(y, X, fe_keys: list, cluster, offset=None, family: str = "poisson",
               tol: float = 1e-10, max_iter: int = 200) -> dict:  # fmt: skip
    """Poisson pseudo-ML (``family="poisson"``, PPML: y >= 0, any scale) or logit
    (``"logit"``, y in {0, 1}) with several sets of fixed effects absorbed, by IRLS with
    a weighted within-transformation each step, and cluster-robust sandwich standard
    errors (``cluster``: one array, e.g. county, or a list for multiway clustering, e.g.
    [county, year]; ``n_clusters`` counts the first).

    ``X``: n x k slopes (no constant: the FE absorb it). ``fe_keys``: list of arrays
    (e.g. county, month-of-year, year). ``offset``: e.g. log(liability), so PPML models
    the loss RATIO weighted by exposure. Observations in FE groups with no variation in
    y are dropped first (they do not inform the slopes). Returns beta, se, vcov,
    the keep mask, mu (on kept rows), n, n_clusters, iterations.
    """
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    if X.ndim == 1:
        X = X[:, None]
    fe_all = [codes(k) for k in fe_keys]
    keep = drop_degenerate(y, fe_all, binary=family == "logit")
    fe = [codes(np.asarray(k)[keep]) for k in fe_keys]
    off = None if offset is None else np.asarray(offset, float)[keep]
    r = _irls(y[keep], X[keep], fe, off, family, tol, max_iter)
    ways = list(cluster) if isinstance(cluster, (list, tuple)) else [cluster]
    cl = [np.asarray(c)[keep] for c in ways]
    V = cluster_vcov(r["Xt"], r["w"], y[keep] - r["mu"], cl if len(cl) > 1 else cl[0])
    return {**r, "vcov": V, "se": np.sqrt(np.diag(V)), "keep": keep, "n": int(keep.sum()),
            "n_clusters": int(codes(cl[0]).max() + 1)}  # fmt: skip
