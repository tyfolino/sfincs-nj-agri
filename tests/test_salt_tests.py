"""Pooling NJ + DE in scripts/salt_tests.py: keys, storm-list check, within-state weights and
the per-state subsets. Synthetic tables, no files, no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import salt_tests as S  # noqa: E402

from agri_sfincs import panel  # noqa: E402

YEARS = list(range(2008, 2016))


def part(n: int, seed: int, spring=None, quiet=None, storms=None) -> dict:
    """One state's load_state-like dict: n fields with ids 1..n."""
    rng = np.random.default_rng(seed)
    ix = pd.Index(range(1, n + 1), name="field_id")
    f = pd.DataFrame({"ha": rng.uniform(0.5, 5, n), "m_above_mhhw": rng.uniform(0, 1.4, n),
                      "km": rng.uniform(0, 120, n), "n_storms_tide": rng.integers(0, 3, n)}, index=ix)  # fmt: skip
    spring = spring or {2010: "storm2010mar", 2011: "storm2011apr"}
    tide = pd.DataFrame(rng.integers(0, 2, (n, len(YEARS))), index=ix, columns=YEARS)
    tide = tide.mul((f.n_storms_tide > 0).astype(int), axis=0)
    y = {o: pd.DataFrame(rng.uniform(0, 1, (n, len(YEARS))), index=ix, columns=YEARS) for o in S.OUTCOMES}
    return {"f": f, "y": y, "sp": {"tide": tide, "rain": tide * 0}, "spring": spring,
            "quiet": quiet or [2008, 2009, 2013, 2014, 2015],
            "share": {yr: pd.Series(rng.uniform(0, 1, n), index=ix) for yr in spring},
            "storms": storms or [("storm2010mar", "2010-03-13 14:00"), ("storm2011apr", "2011-04-17 02:00")],
            "no_chronic": False}  # fmt: skip


class TestKeys(unittest.TestCase):
    def test_key_index(self):
        k = S.key_index(pd.Index([1, 2, 45]), "DE")
        self.assertEqual(list(k), ["DE-1", "DE-2", "DE-45"])
        self.assertEqual(k.name, "field_key")

    def test_ids_collide_keys_do_not(self):
        c = S.combine({"NJ": part(30, 1), "DE": part(20, 2)})
        self.assertEqual(len(c["f"]), 50)
        self.assertTrue(c["f"].index.is_unique)
        self.assertEqual(c["f"].index[0], "NJ-1")
        self.assertEqual(c["f"].index[30], "DE-1")
        self.assertEqual(c["state"].value_counts().to_dict(), {"NJ": 30, "DE": 20})
        for tbl in (*c["y"].values(), *c["sp"].values(), *c["share"].values()):
            self.assertTrue(tbl.index.equals(c["f"].index))

    def test_values_follow_their_field(self):
        nj, de = part(30, 1), part(20, 2)
        c = S.combine({"NJ": nj, "DE": de})
        self.assertEqual(c["f"].loc["DE-7", "ha"], de["f"].loc[7, "ha"])
        self.assertEqual(c["y"]["corn"].loc["NJ-7", 2012], nj["y"]["corn"].loc[7, 2012])
        self.assertEqual(c["sp"]["tide"].loc["DE-3", 2011], de["sp"]["tide"].loc[3, 2011])


class TestSameStorms(unittest.TestCase):
    def test_storm_list(self):
        ev = pd.DataFrame({"event": ["b", "a", "b", "a"], "peak": ["2", "1", "3", "1"]})
        self.assertEqual(S.storm_list(ev), [("a", "1"), ("b", "2"), ("b", "3")])

    def test_differences_raise(self):
        S.check_same({"NJ": part(10, 1), "DE": part(10, 2)})  # same storms: no error
        cases = [{"storms": [("storm2010mar", "2010-03-13 14:00")]},
                 {"spring": {2010: "storm2010mar"}}, {"quiet": [2008, 2009]}]  # fmt: skip
        for kw in cases:
            with self.subTest(kw=list(kw)), self.assertRaises(ValueError):
                S.combine({"NJ": part(10, 1), "DE": part(10, 2, **kw)})


class TestStrata(unittest.TestCase):
    def test_none_is_unchanged(self):
        p = part(40, 3)["f"]
        t, c = p.n_storms_tide == 1, p.n_storms_tide == 0
        a = panel.height_weights(p.m_above_mhhw, p.ha, t, c)
        b = panel.height_weights(p.m_above_mhhw, p.ha, t, c, strata=None)
        self.assertTrue(a.equals(b))

    def test_within_state_mix(self):
        """Comparison fields take the target's state x height mix; a stratum the target lacks gets 0."""
        h = pd.Series([0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
        ha = pd.Series([1.0, 3.0, 2.0, 2.0, 5.0, 1.0])
        st = pd.Series(["NJ", "DE", "NJ", "NJ", "DE", "XX"])
        t = pd.Series([True, True, False, False, False, False])
        c = ~t
        w = panel.height_weights(h, ha, t, c, strata=st)
        self.assertEqual(w[:2].tolist(), [1.0, 3.0])
        self.assertEqual(w[5], 0.0)  # its stratum has no target field
        cw = w[c].groupby(st[c]).sum()
        self.assertAlmostEqual(cw["NJ"] / cw.sum(), 0.25)  # target: 1 of 4 ha in NJ
        self.assertAlmostEqual(cw["DE"] / cw.sum(), 0.75)
        # without strata, the one height bin would keep the comparison's own state mix
        w0 = panel.height_weights(h, ha, t, c)
        self.assertAlmostEqual(w0[c].groupby(st[c]).sum()["DE"] / w0[c].sum(), 0.5)


class TestPooledPanel(unittest.TestCase):
    def setUp(self):
        self.nj, self.de = part(60, 4), part(40, 5)
        self.p = S.Panel.from_parts({"NJ": self.nj, "DE": self.de})

    def test_single_state_keeps_field_ids(self):
        p = S.Panel.from_parts({"NJ": self.nj})
        self.assertIsNone(p.state)
        self.assertTrue(p.f.index.equals(self.nj["f"].index))

    def test_nj_rows_keep_nj_only_draws(self):
        """NJ comes first, so the pooled NJ subset uses exactly the NJ-only bootstrap draws."""
        nj_only = S.Panel.from_parts({"NJ": self.nj})
        np.testing.assert_array_equal(self.p.subset("NJ").boot, nj_only.boot)

    def test_subset_matches_single_state(self):
        sub, nj_only = self.p.subset("NJ"), S.Panel.from_parts({"NJ": self.nj})
        self.assertIsNone(sub.state)
        self.assertEqual(len(sub.f), 60)
        for o in ("corn", "left farmland"):
            g = lambda q: lambda yr: (q.sp["tide"][yr] == 1, q.prone & (q.sp["tide"][yr] != 1))  # noqa: E731
            a, n = sub.pooled(g(sub), o, 0)
            b, m = nj_only.pooled(g(nj_only), o, 0)
            self.assertEqual(n, m)
            np.testing.assert_allclose(a, b)

    def test_thin_state_sits_out(self):
        """A state with fewer than MIN_FIELDS comparison fields in a storm drops out of that storm's
        pooled contrast, which then equals the other state's own."""
        de = part(40, 5)
        de["sp"]["tide"][2010] = (de["f"].n_storms_tide > 0).astype(int)  # every prone DE field floods: no prone-dry
        p = S.Panel.from_parts({"NJ": self.nj, "DE": de})
        g = lambda q: lambda yr: (q.sp["tide"][yr] == 1, q.prone & (q.sp["tide"][yr] != 1))  # noqa: E731
        a, n = p.pooled(g(p), "corn", 0, [2010])
        self.assertEqual(p.used, ["NJ"])
        nj = p.subset("NJ")
        b, m = nj.pooled(g(nj), "corn", 0, [2010])
        self.assertEqual((n, m), (1, 1))
        np.testing.assert_allclose(a, b)
        self.assertEqual(p.tag(), {"by_state": "NJ:1 DE:0"})
        self.assertEqual(nj.tag(), {})

    def test_run_all_states(self):
        res = S.run_all(self.p)
        self.assertEqual(res.columns[0], "state")
        self.assertEqual(list(res.state.unique()), ["all", "NJ", "DE"])
        sizes = res.groupby("state").size()
        self.assertEqual(sizes["all"], sizes["NJ"])
        self.assertEqual(sizes["NJ"], sizes["DE"])

    def test_counts_by_state(self):
        c = S.counts_pooled(self.p)
        self.assertEqual(c.index.names, ["storm", "state"])
        lo = self.p.f.km < self.p.split
        t = self.p.sp["tide"][2010] == 1
        self.assertEqual(c.loc[("storm2010mar", "DE"), "flooded lower"], int((t & lo & (self.p.state == "DE")).sum()))
        self.assertEqual(c.xs("storm2011apr", level="storm")[["flooded lower", "flooded upper"]].to_numpy().sum(),
                         int((self.p.sp["tide"][2011] == 1).sum()))  # fmt: skip


if __name__ == "__main__":
    unittest.main()
