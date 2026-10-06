"""Skill-score helpers (agri_sfincs.skill) — synthetic, no network."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from agri_sfincs import skill as S


class TestAuc(unittest.TestCase):
    def test_perfect_random_and_reversed(self):
        y = [0, 0, 1, 1]
        self.assertEqual(S.auc(y, [1, 2, 3, 4]), 1.0)
        self.assertEqual(S.auc(y, [4, 3, 2, 1]), 0.0)
        self.assertEqual(S.auc(y, [1, 1, 1, 1]), 0.5)

    def test_ties_count_half_and_nans_drop(self):
        # positives 2,3 ; negatives 1,2 -> pairs: (2>1)=1,(2=2)=.5,(3>1)=1,(3>2)=1 -> 3.5/4
        self.assertAlmostEqual(S.auc([0, 0, 1, 1, 1], [1, 2, 2, 3, np.nan]), 0.875)

    def test_one_class_is_nan(self):
        self.assertTrue(np.isnan(S.auc([1, 1], [0.2, 0.3])))

    def test_matches_brute_force(self):
        rng = np.random.default_rng(1)
        y = rng.integers(0, 2, 60)
        s = rng.integers(0, 8, 60).astype(float)
        pos, neg = s[y == 1], s[y == 0]
        brute = np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg])
        self.assertAlmostEqual(S.auc(y, s), brute)


class TestScores(unittest.TestCase):
    def test_brier(self):
        self.assertAlmostEqual(S.brier([0, 1], [0.2, 0.6]), (0.04 + 0.16) / 2)

    def test_spearman_monotone_and_ties(self):
        self.assertAlmostEqual(S.spearman([1, 2, 3, 4], [10, 20, 30, 100]), 1.0)
        self.assertAlmostEqual(S.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertTrue(np.isnan(S.spearman([1, 1, 1], [1, 2, 3])))


class TestLogistic(unittest.TestCase):
    def test_recovers_coefficients_unpenalized(self):
        rng = np.random.default_rng(0)
        x = rng.normal(size=(20000, 2))
        p = 1 / (1 + np.exp(-(-1.0 + 1.5 * x[:, 0] - 0.5 * x[:, 1])))
        y = (rng.random(20000) < p).astype(float)
        b = S.fit_logistic(x, y, lam=0.0)
        np.testing.assert_allclose(b, [-1.0, 1.5, -0.5], atol=0.08)

    def test_penalty_shrinks_only_masked_columns(self):
        rng = np.random.default_rng(2)
        x = rng.normal(size=(300, 2))
        y = (x[:, 0] + x[:, 1] + rng.normal(size=300) > 0).astype(float)
        b0 = S.fit_logistic(x, y, lam=0.0)
        b = S.fit_logistic(x, y, lam=1e6, penalize=[True, False])
        self.assertLess(abs(b[1]), 0.01)
        self.assertGreater(abs(b[2]), 0.5)
        self.assertGreater(abs(b0[1]), 0.5)

    def test_separable_data_stays_finite_with_ridge(self):
        x = np.array([[-2.0], [-1.0], [1.0], [2.0]])
        y = np.array([0.0, 0.0, 1.0, 1.0])
        b = S.fit_logistic(x, y, lam=1.0)
        self.assertTrue(np.all(np.isfinite(b)))
        p = S.predict_logistic(b, x)
        self.assertTrue(p[0] < 0.5 < p[3])

    def test_high_leverage_rows_converge(self):
        # an undamped Newton step from the start point diverges to |b| ~ 1e10 here
        x = np.array([[116.0, -42.6, -9.9], [-6360.9, -4596.0, -242.9], [-135.0, 100.8, -13.3],
                      [108.3, -46.0, -5.4], [-173.0, 30.5, 7.5], [7.0, -12.5, -2.4],
                      [2.6, -48.3, 5.5], [128.9, 94.4, -21.5], [-74.3, -66.8, 5.2],
                      [-180.5, -87.8, 1.5], [-175.8, 134.6, 10.3], [-95.5, -32.8, -3.6],
                      [-58.6, -131.5, 18.2], [38.8, -131.7, -12.3], [7714.0, -5166.2, -655.4]])  # fmt: skip
        y = np.array([0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 0], float)
        b = S.fit_logistic(x, y, lam=1.0)
        self.assertLess(np.abs(b).max(), 100)
        grad = np.column_stack([np.ones(len(y)), x]).T @ (y - S.predict_logistic(b, x)) - np.r_[0, b[1:]]
        np.testing.assert_allclose(grad, 0, atol=1e-6)


class TestRidge(unittest.TestCase):
    def test_ols_limit(self):
        rng = np.random.default_rng(3)
        x = rng.normal(size=(500, 1))
        y = 2.0 + 3.0 * x[:, 0]
        np.testing.assert_allclose(S.fit_ridge(x, y, lam=0.0), [2.0, 3.0], atol=1e-9)


class TestCrossValidation(unittest.TestCase):
    def test_logo_never_sees_its_own_group(self):
        X = np.zeros((6, 1))
        y = np.array([1.0, 1.0, 2.0, 2.0, 3.0, 3.0])
        g = np.array([0, 0, 1, 1, 2, 2])
        pred = S.logo_predict(X, y, g, fit=lambda X, y: y.mean(), predict=lambda m, X: np.full(len(X), m))
        np.testing.assert_allclose(pred, [2.5, 2.5, 2.0, 2.0, 1.5, 1.5])

    def test_group_bootstrap_resamples_whole_groups(self):
        g = np.array([0, 0, 1, 1, 1])
        sizes = S.group_bootstrap(g, lambda idx: len(idx), n_boot=200, seed=4)
        self.assertTrue(set(np.unique(sizes)) <= {4, 5, 6})

    def test_standardize_uses_training_stats(self):
        tr, te = S.standardize_train(np.array([[0.0], [2.0]]), np.array([[4.0]]))
        np.testing.assert_allclose(tr[:, 0], [-1, 1])
        np.testing.assert_allclose(te[:, 0], [3.0])


class TestAnomaly(unittest.TestCase):
    def test_normal_scores_within_groups(self):
        v = pd.Series([1.0, 2.0, 3.0, 100.0, 200.0, np.nan])
        grp = pd.Series(["a", "a", "a", "b", "b", "b"])
        z = S.normal_score_anomaly(v, grp)
        self.assertAlmostEqual(z[1], 0.0)
        self.assertAlmostEqual(z[0], -z[2])
        self.assertAlmostEqual(z[3], -z[4])  # n = 2 in b (NaN not counted)
        self.assertTrue(np.isnan(z[5]))
        self.assertLess(z[0], 0)


if __name__ == "__main__":
    unittest.main()
