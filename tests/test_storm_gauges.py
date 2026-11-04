"""Gauge tables of scripts/validate_storm_gauges.py, both sides — no network, no runs."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate_storm_gauges as V  # noqa: E402

from agri_sfincs import config  # noqa: E402
from agri_sfincs.events import EVENTS, wind_suffix  # noqa: E402

FETCH_CODES = {"discharge": "00060", "gage height": "00065", "tidal elevation": "72279",
               "estuary elevation NAVD88": "62620", "stream elevation NAVD88": "63160"}  # fmt: skip


class TestGauges(unittest.TestCase):
    def test_nj_unchanged(self):
        g = V.gauges("nj")
        self.assertEqual(list(g), list(V.GAUGES))
        self.assertEqual({p for _, p in g.values()}, {"72279"})
        self.assertEqual([n for n, _ in g.values()], list(V.GAUGES.values()))

    def test_de_series_exist_in_inventory(self):
        """Every DE gauge's parameter is an instantaneous series in usgs_series_de.csv, so
        fetch_usgs_event.py --side de fetches it."""
        inv = pd.read_csv(config.GAUGE_DIR / "usgs_series_de.csv", dtype={"site": str})
        inv = inv[inv.computation_period_identifier == "Points"]
        have = set(zip(inv.site, inv.what.map(FETCH_CODES)))
        for site, (_, param) in V.gauges("de").items():
            self.assertIn((site, param), have, site)

    def test_storm_lists(self):
        self.assertEqual(V.ALL_STORMS[: len(V.STORMS)], V.STORMS)
        self.assertEqual(len(set(V.ALL_STORMS)), len(V.ALL_STORMS))
        for s in V.ALL_STORMS:
            self.assertIn(s, EVENTS)
        # the DE runs mix the two wind sources by storm
        self.assertEqual(wind_suffix("storm2012dec"), "_era5")
        self.assertEqual(wind_suffix("storm2016jan"), "_hrrr")


if __name__ == "__main__":
    unittest.main()
