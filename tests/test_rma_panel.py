"""RMA Summary of Business layout and the loss-panel builder — synthetic rows, no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_loss_panel as blp  # noqa: E402
import fetch_rma_sob  # noqa: E402

SOB_LINE = (
    "2024|02|AK|240|Southeast Fairbanks           |9999|All Other Crops               "
    "|90|APH       |A    |RBUP|.5000|2|1|0|1|0|Acres                    |150|0|34830|1176"
    "|788|0|0|0|0|.00\n"
)


def _col(**kw):
    row = dict(fips="34033", commodity_year=2020, commodity_code="0081", col_code="31",
               stage_code="H", month_of_loss=6, year_of_loss=2020, indemnity=100.0,
               policies_indemnified=1.0, county_code="033")  # fmt: skip
    row.update(kw)
    return row


def _sob(**kw):
    row = dict(fips="34033", commodity_year=2020, commodity_code="0081",
               insurance_plan_abbr="RP", quantity_type="Acres", liability=1000.0,
               total_premium=50.0, net_reported_qty=10.0, policies_earning_premium=2.0,
               indemnity=0.0)  # fmt: skip
    row.update(kw)
    return row


class TestSobLayout(unittest.TestCase):
    def test_real_line_parses_to_28_named_fields(self):
        f = fetch_rma_sob.parse_line(SOB_LINE)
        self.assertEqual(len(fetch_rma_sob.COLUMNS), 28)
        r = dict(zip(fetch_rma_sob.COLUMNS, f))
        self.assertEqual(r["commodity_year"], "2024")
        self.assertEqual(r["county_name"], "Southeast Fairbanks")
        self.assertEqual(r["coverage_level"], ".5000")
        self.assertEqual(r["quantity_type"], "Acres")
        self.assertEqual(r["liability"], "34830")
        self.assertEqual(r["loss_ratio"], ".00")

    def test_wrong_field_count_raises(self):
        with self.assertRaisesRegex(RuntimeError, "layout"):
            fetch_rma_sob.parse_line("2024|02|AK\n")


class TestRules(unittest.TestCase):
    def test_crop_groups(self):
        self.assertEqual(blp.crop_group("0081"), "soybeans")
        self.assertEqual(blp.crop_group("41"), "corn")
        self.assertEqual(blp.crop_group("0011"), "wheat")
        self.assertEqual(blp.crop_group("0091"), "other")  # barley
        self.assertEqual(blp.crop_group("9999"), "other")

    def test_exposure_year_fall_seeded_only_sep_dec(self):
        self.assertEqual(blp.exposure_year("0011", 2018, 10), 2019)
        self.assertEqual(blp.exposure_year("0011", 2018, 9), 2019)
        self.assertEqual(blp.exposure_year("0011", 2018, 6), 2018)
        self.assertEqual(blp.exposure_year("0091", 2018, 11), 2019)
        self.assertEqual(blp.exposure_year("0041", 2018, 11), 2018)

    def test_area_plans(self):
        for a in ("SCO-YP", "ECO-RP", "RI", "GRIP", "GRIP-HR", "HIP-WI", "STAX", "GRP"):
            self.assertTrue(blp.is_area_plan(a), a)
        for a in ("RP", "YP", "APH", "RPHPE", "DO", "WFRP", "ARC"):
            self.assertFalse(blp.is_area_plan(a), a)


class TestPanel(unittest.TestCase):
    def setUp(self):
        rows = [
            _col(),  # soy June 31
            _col(col_code="44", indemnity=50.0, stage_code="PF"),  # broad wet, PP
            _col(col_code="11", indemnity=30.0),  # drought
            _col(commodity_code="0011", commodity_year=2021, month_of_loss=10,
                 indemnity=40.0, policies_indemnified=2.0),  # fall wheat, cy+1
            _col(commodity_code="0011", commodity_year=2020, month_of_loss=10,
                 indemnity=5.0),  # wheat booked to the "wrong" cy
            _col(col_code="31", indemnity=-10.0),  # signed correction
        ]  # fmt: skip
        col = pd.DataFrame(rows)
        self.col, self.drop = blp.select_col(col, ["34033", "34011"], 2020, 2020)
        sob = pd.DataFrame([
            _sob(),
            _sob(insurance_plan_abbr="SCO-RP", liability=500.0),
            _sob(commodity_code="0011", liability=200.0),
            _sob(commodity_code="0011", commodity_year=2021, liability=300.0),
            _sob(commodity_code="0091", commodity_year=2021, liability=7.0),
        ])  # fmt: skip
        sob["area_plan"] = sob.insurance_plan_abbr.map(blp.is_area_plan)
        liab = blp.liability_by_commodity(sob, ["34033", "34011"])
        self.p = blp.build_panel(self.col, liab, ["34033", "34011"], range(2020, 2021))

    def cell(self, fips, month, group):
        q = self.p[(self.p.fips == fips) & (self.p.month == month) & (self.p.crop_group == group)]
        self.assertEqual(len(q), 1)
        return q.iloc[0]

    def test_complete_zero_filled(self):
        self.assertEqual(len(self.p), 2 * 1 * 12 * 5)
        self.assertFalse(self.p.duplicated(["fips", "year", "month", "crop_group"]).any())
        z = self.cell("34011", 3, "corn")
        self.assertEqual(z.indemnity_total, 0.0)
        self.assertTrue(pd.isna(z.lr_wet_broad))  # no liability in that county

    def test_wet_definitions_and_signed(self):
        c = self.cell("34033", 6, "soybeans")
        self.assertEqual(c.indemnity_total, 170.0)  # 100 + 50 + 30 - 10
        self.assertEqual(c.indemnity_wet_31_51, 90.0)
        self.assertEqual(c.indemnity_wet_broad, 140.0)
        self.assertEqual(c.indemnity_wet_broad_pp, 50.0)
        self.assertEqual(c.n_policies_wet_broad, 3.0)
        self.assertEqual(c.liability, 1000.0)  # SCO excluded
        self.assertEqual(c.liability_all_plans, 1500.0)
        self.assertAlmostEqual(c.lr_wet_broad, 0.14)

    def test_fall_wheat_uses_next_commodity_year(self):
        w = self.cell("34033", 10, "wheat")
        self.assertEqual(w.liability_commodity_year, 2021)
        self.assertEqual(w.liability, 300.0)
        self.assertEqual(w.indemnity_total, 45.0)
        self.assertEqual(w.indemnity_other_cy, 5.0)
        self.assertEqual(self.cell("34033", 6, "wheat").liability, 200.0)
        # Barley sits in "other" and also shifts: Oct 2020 -> cy 2021.
        self.assertEqual(self.cell("34033", 10, "other").liability, 7.0)
        self.assertEqual(self.cell("34033", 6, "other").liability, 0.0)

    def test_all_is_sum_of_groups(self):
        a = self.cell("34033", 10, "all")
        self.assertEqual(a.liability, 1000.0 + 300.0 + 7.0)
        self.assertEqual(a.indemnity_total, 45.0)


class TestSelect(unittest.TestCase):
    def test_drops_month0_and_missing_year(self):
        col = pd.DataFrame([_col(), _col(month_of_loss=0), _col(year_of_loss=None),
                            _col(fips="34999"), _col(year_of_loss=2026)])  # fmt: skip
        col["year_of_loss"] = pd.to_numeric(col.year_of_loss)
        d, drop = blp.select_col(col, ["34033"], 2003, 2025)
        self.assertEqual(len(d), 1)
        self.assertEqual(drop["month 0 / unknown"][0], 1)
        self.assertEqual(drop["no year of loss (commodity year >= start)"][0], 1)
        self.assertEqual(drop["year of loss outside 2003-2025"][0], 1)


if __name__ == "__main__":
    unittest.main()
