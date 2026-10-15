"""Small, dependency-light skill-score helpers for the A4 loss-predictor tests
(``archive/scripts/a4_first_test.py``): AUC, Brier, a ridge-penalized logistic regression
fitted by Newton steps, leave-one-group-out prediction, a group (year) bootstrap and
a within-group normal-score anomaly. numpy + pandas only, so the stdlib tests run fast.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd


def _avg_ranks(x: np.ndarray) -> np.ndarray:
    """1-based ranks with ties given their average rank."""
    x = np.asarray(x, float)
    _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    start = np.concatenate([[0], np.cumsum(counts)[:-1]])  # 0-based first position
    return (start + (counts + 1) / 2.0)[inv]


def auc(y, score) -> float:
    """Area under the ROC curve (Mann-Whitney; ties count one half). NaN pairs dropped.
    NaN if either class is empty."""
    y = np.asarray(y, float)
    s = np.asarray(score, float)
    ok = np.isfinite(y) & np.isfinite(s)
    y, s = y[ok] > 0.5, s[ok]
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = _avg_ranks(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def brier(y, p) -> float:
    """Mean squared error of probabilities ``p`` against 0/1 ``y``."""
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    ok = np.isfinite(y) & np.isfinite(p)
    return float(np.mean((p[ok] - y[ok]) ** 2))


def spearman(x, y) -> float:
    """Spearman rank correlation (average ranks for ties), NaN pairs dropped."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return float("nan")
    rx, ry = _avg_ranks(x[ok]), _avg_ranks(y[ok])
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def _sigmoid(z):
    return 0.5 * (1.0 + np.tanh(0.5 * z))


def fit_logistic(X, y, lam: float = 1.0, penalize=None, max_iter: int = 100,
                 tol: float = 1e-9) -> np.ndarray:  # fmt: skip
    """Ridge-penalized logistic regression by Newton-Raphson.

    ``X`` must NOT contain an intercept column; one is added (never penalized).
    Minimizes  -loglik + lam/2 * sum(beta_j^2 over penalized j).  ``penalize`` is a
    boolean mask over the columns of ``X`` (default: all penalized). Returns
    ``[intercept, beta...]``.

    Each Newton step is halved until the objective does not increase (until 2026-10-06
    the step was always taken in full, and one field_classes.py fit diverged to
    |b| ~ 3e6). Converged fits are unchanged.
    """
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n, k = X.shape
    A = np.column_stack([np.ones(n), X])
    pen = np.zeros(k + 1)
    pen[1:] = lam if penalize is None else lam * np.asarray(penalize, float)

    def loss(b):
        eta = A @ b
        return np.sum(np.logaddexp(0.0, eta) - y * eta) + 0.5 * np.sum(pen * b * b)

    ybar = np.clip(y.mean(), 1e-6, 1 - 1e-6)
    b = np.zeros(k + 1)
    b[0] = np.log(ybar / (1 - ybar))
    f = loss(b)
    for _ in range(max_iter):
        p = _sigmoid(A @ b)
        g = A.T @ (y - p) - pen * b
        w = p * (1 - p)
        H = (A * w[:, None]).T @ A + np.diag(pen) + 1e-10 * np.eye(k + 1)
        step = np.linalg.solve(H, g)
        t = 1.0
        while True:
            f_new = loss(b + t * step)
            if f_new <= f + 1e-12 * abs(f) or t < 1e-10:
                break
            t *= 0.5
        b = b + t * step
        f = f_new
        if np.max(np.abs(t * step)) < tol:
            break
    return b


def predict_logistic(b, X) -> np.ndarray:
    X = np.asarray(X, float)
    return _sigmoid(b[0] + X @ b[1:])


def fit_ridge(X, y, lam: float = 1.0, penalize=None) -> np.ndarray:
    """Ridge least squares with an unpenalized intercept; returns ``[b0, beta...]``."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n, k = X.shape
    A = np.column_stack([np.ones(n), X])
    pen = np.zeros(k + 1)
    pen[1:] = lam if penalize is None else lam * np.asarray(penalize, float)
    return np.linalg.solve(A.T @ A + np.diag(pen), A.T @ y)


def predict_linear(b, X) -> np.ndarray:
    return b[0] + np.asarray(X, float) @ b[1:]


def standardize_train(X_train, X_test, cols=None):
    """Scale columns ``cols`` (default all) by the TRAINING mean/sd; constant columns
    are left centred. Returns (train, test) copies."""
    Xtr = np.array(X_train, float, copy=True)
    Xte = np.array(X_test, float, copy=True)
    cols = range(Xtr.shape[1]) if cols is None else cols
    for j in cols:
        m, s = Xtr[:, j].mean(), Xtr[:, j].std()
        s = s if s > 0 else 1.0
        Xtr[:, j] = (Xtr[:, j] - m) / s
        Xte[:, j] = (Xte[:, j] - m) / s
    return Xtr, Xte


def logo_predict(X, y, groups, fit: Callable, predict: Callable) -> np.ndarray:
    """Leave-one-group-out predictions: each group's rows are predicted by a model
    fitted on all the other groups. ``fit(Xtr, ytr) -> model``;
    ``predict(model, Xte) -> yhat``."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    groups = np.asarray(groups)
    out = np.full(len(y), np.nan)
    for g in np.unique(groups):
        te = groups == g
        model = fit(X[~te], y[~te])
        out[te] = predict(model, X[te])
    return out


def group_bootstrap(groups, stat: Callable, n_boot: int = 2000, seed: int = 0) -> np.ndarray:
    """Resample whole groups with replacement; ``stat(idx)`` gets the row indices of
    the resample (a group drawn twice appears twice). Returns the n_boot statistics."""
    groups = np.asarray(groups)
    ug = np.unique(groups)
    rows = {g: np.flatnonzero(groups == g) for g in ug}
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.choice(ug, size=len(ug), replace=True)
        out[i] = stat(np.concatenate([rows[g] for g in pick]))
    return out


def normal_score_anomaly(values: pd.Series, by) -> pd.Series:
    """Within-group rank anomaly as a normal score: rank r of n in each group
    (average ranks for ties) mapped to Phi^-1((r - 0.5) / n). Robust to the heavy
    tails of ponding / intensity metrics, and comparable across predictors. NaNs
    stay NaN and are not counted in n."""
    from statistics import NormalDist

    inv = NormalDist().inv_cdf

    def one(s: pd.Series) -> pd.Series:
        ok = s.notna()
        res = pd.Series(np.nan, index=s.index)
        n = int(ok.sum())
        if n == 0:
            return res
        r = _avg_ranks(s[ok].to_numpy())
        res[ok] = [inv((ri - 0.5) / n) for ri in r]
        return res

    return values.groupby(by, group_keys=False).apply(one).reindex(values.index)
