"""Tests for the inventory-clearance bundling feature.  Run:  python -m unittest discover -s tests -v   (from the project root)

Unit tests exercise src/bundles.py (normal, boundary and failure cases); the data tests generate a small deterministic dataset
(same generator, same seed) and check that bundle sales move the inventory of BOTH components and reconcile.
"""
import os, subprocess, sys, tempfile, unittest
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import bundles as B  # noqa: E402
from schema import GLOBAL_RULES as R  # noqa: E402


def ok_kwargs(**kw):
    base = dict(component_discontinued=False, sell_primary=50, sell_secondary=50, duplicate_active=False, price=100.0, floor_sum=80.0,
                margin=0.30, req_margin=0.20, rules=R)
    base.update(kw)
    return base


class TestRules(unittest.TestCase):
    def test_01_aged_stock_over_90_days(self):                                   # normal + boundary
        self.assertEqual([B.classify_age(a) for a in (0, 30, 31, 60, 61, 90, 91, 400)],
                         ["FRESH", "FRESH", "NORMAL", "NORMAL", "SLOW_MOVING", "SLOW_MOVING", "AGED", "AGED"])
        # FIFO lots: opening lot 120 days old (50 units) + receipt on day 10 (30 units); 20 units already sold -> 30 aged units remain
        lot_q = np.zeros((12, 1), np.int64); lot_q[0, 0] = 50; lot_q[11, 0] = 30          # row 11 = receipts of day 10
        lot_cum = np.cumsum(lot_q, axis=0)
        oldest, slow, aged, tot = B.stock_age(lot_q, lot_cum, np.array([110]), 10, np.array([20]))
        self.assertEqual((int(oldest[0]), int(slow[0]), int(aged[0]), int(tot[0])), (120, 0, 30, 60))
        self.assertEqual(B.classify_age_vec(oldest, tot)[0], "AGED")
        # once the old lot is fully sold the oldest stock is the fresh receipt
        oldest, _, aged, _ = B.stock_age(lot_q, lot_cum, np.array([110]), 10, np.array([50]))
        self.assertEqual((int(oldest[0]), int(aged[0])), (0, 0))

    def test_01b_thresholds_are_configurable(self):
        rules = dict(R, stock_age_slow_max_days=120)
        self.assertEqual(B.classify_age(100, rules), "SLOW_MOVING")
        self.assertEqual(B.classify_age(100), "AGED")

    def test_02_high_demand_identified(self):
        dem = np.array([0.1, 0.4, 1.0, 2.0, 5.0, 9.0]); cat = np.zeros(6, int); live = np.ones(6, bool)
        thr = B.category_thresholds(dem, cat, live, 2, 0.75)
        self.assertAlmostEqual(thr[0], np.quantile(dem, 0.75)); self.assertTrue(np.isinf(thr[1]))       # empty category -> never high demand
        self.assertEqual([B.is_high_demand(x, thr[0]) for x in dem], [False, False, False, False, True, True])
        self.assertFalse(B.is_high_demand(0.3, 0.1))                                                      # above threshold but below min demand
        live[5] = False                                                                                   # unavailable product excluded from the percentile
        self.assertLess(B.category_thresholds(dem, cat, live, 2, 0.75)[0], thr[0])

    def test_03_compatible_products_form_a_bundle(self):
        self.assertTrue(B.is_complementary("Electronics", "Office"))
        self.assertTrue(B.is_complementary("Apparel", "Sports"))
        self.assertFalse(B.is_complementary("Electronics", "Grocery"))          # unrelated
        self.assertFalse(B.is_complementary("Office", "Toys"))                  # direction matters (aged add-on category)
        self.assertEqual(B.primary_categories_for("Office"), ["Electronics", "Toys"])
        self.assertTrue(B.price_ratio_ok(100, 125)); self.assertFalse(B.price_ratio_ok(100, 125.01))

    def test_04_insufficient_stock_prevents_bundle(self):                        # failure + boundary
        self.assertEqual(B.evaluate_bundle(**ok_kwargs(sell_primary=9)), "INSUFFICIENT_STOCK")
        self.assertEqual(B.evaluate_bundle(**ok_kwargs(sell_secondary=9)), "INSUFFICIENT_STOCK")
        self.assertIsNone(B.evaluate_bundle(**ok_kwargs(sell_primary=10, sell_secondary=10)))
        self.assertEqual(B.max_bundle_units(40, 12), 12)                           # limited by the lower component stock
        self.assertEqual(B.max_bundle_units(0, 5), 0)

    def test_05_reserved_stock_excluded(self):
        self.assertEqual(B.sellable_units(100), 90)
        self.assertEqual(B.sellable_units(11), 9)                                 # 10 on hand is not enough once the reserve is held back
        self.assertEqual(B.evaluate_bundle(**ok_kwargs(sell_primary=B.sellable_units(11))), "INSUFFICIENT_STOCK")
        self.assertEqual(B.sellable_units(0), 0)
        self.assertEqual(B.sellable_units(100, dict(R, bundle_stock_reserve_pct=0.25)), 75)

    def test_06_discount_and_price_calculation(self):
        self.assertEqual(B.bundle_price(2000, 800, 0.10), 2520.0)                 # the spec example
        self.assertEqual(B.pick_discount(75), R["bundle_discount_slow_moving"])
        self.assertEqual(B.pick_discount(91), R["bundle_discount_aged"])
        self.assertEqual(B.pick_discount(121), R["bundle_discount_very_aged"])
        for age in (61, 90, 91, 120, 121, 999):
            self.assertTrue(R["bundle_discount_min"] <= B.pick_discount(age) <= R["bundle_discount_max"])
        a, b = B.allocate_price(2520.0, 2000, 800)
        self.assertAlmostEqual(a + b, 2520.0); self.assertEqual((a, b), (1800.0, 720.0))

    def test_07_bundle_below_minimum_margin_rejected(self):
        price, cost = 100.0, 82.0
        m = B.bundle_margin(price, cost)
        self.assertAlmostEqual(m, 0.18)
        self.assertEqual(B.evaluate_bundle(**ok_kwargs(price=price, margin=m, req_margin=0.20)), "BELOW_MIN_MARGIN")
        self.assertIsNone(B.evaluate_bundle(**ok_kwargs(price=price, margin=0.20, req_margin=0.20)))      # boundary: exactly at the floor passes
        self.assertEqual(B.required_margin(0.12, 0.25), 0.25)
        self.assertEqual(B.evaluate_bundle(**ok_kwargs(price=79.99, floor_sum=80.0)), "BELOW_PRICE_FLOOR")   # price guardrail comes first
        self.assertEqual(B.effective_floor(10.0, 20.0, 0.20), 25.0)

    def test_08_valid_bundle_created(self):
        self.assertIsNone(B.evaluate_bundle(**ok_kwargs()))
        # rejection order is the documented one
        self.assertEqual(B.evaluate_bundle(**ok_kwargs(component_discontinued=True, sell_primary=0, duplicate_active=True, margin=0.0)), "COMPONENT_DISCONTINUED")
        self.assertEqual(B.evaluate_bundle(**ok_kwargs(sell_primary=0, duplicate_active=True, margin=0.0)), "INSUFFICIENT_STOCK")
        self.assertEqual(B.evaluate_bundle(**ok_kwargs(duplicate_active=True, margin=0.0)), "DUPLICATE_ACTIVE_BUNDLE")

    def test_09_expired_bundles_cannot_sell(self):
        self.assertTrue(B.accepts_sales(None, "2026-05-04", "2026-05-17", "2026-05-04"))     # first day
        self.assertTrue(B.accepts_sales(None, "2026-05-04", "2026-05-17", "2026-05-17"))     # last day
        self.assertFalse(B.accepts_sales(None, "2026-05-04", "2026-05-17", "2026-05-18"))    # expired
        self.assertFalse(B.accepts_sales(None, "2026-05-04", "2026-05-17", "2026-05-03"))    # not started
        self.assertFalse(B.accepts_sales("BELOW_MIN_MARGIN", "2026-05-04", "2026-05-17", "2026-05-10"))   # cancelled/rejected
        self.assertEqual(B.bundle_status(None, "2026-05-04", "2026-05-17", "2026-05-18"), "EXPIRED")
        self.assertEqual(B.bundle_status(None, "2026-05-04", "2026-05-17", "2026-05-17"), "ACTIVE")
        self.assertEqual(B.bundle_status(None, "2026-05-04", "2026-05-17", "2026-05-01"), "DRAFT")
        self.assertEqual(B.bundle_status("INSUFFICIENT_STOCK", "2026-05-04", "2026-05-17", "2026-05-10"), "CANCELLED")

    def test_11_duplicate_active_bundle_prevented(self):
        self.assertEqual(B.evaluate_bundle(**ok_kwargs(duplicate_active=True)), "DUPLICATE_ACTIVE_BUNDLE")

    def test_12_revenue_cost_profit(self):
        q, price, cost_p, cost_s = 7, 2520.0, 1400.0, 500.0
        revenue, cost = q * price, q * (cost_p + cost_s)
        self.assertEqual((revenue, cost, revenue - cost), (17640.0, 13300.0, 4340.0))
        self.assertAlmostEqual(B.bundle_margin(price, cost_p + cost_s), (2520 - 1900) / 2520)

    def test_aged_units_cleared_fifo(self):
        lot_qty, ages = [40, 30, 20], [150, 60, 5]
        self.assertEqual(B.aged_overlap(lot_qty, ages, 0, 10), 10)         # all from the aged lot
        self.assertEqual(B.aged_overlap(lot_qty, ages, 35, 10), 5)         # 5 aged, 5 from the slow lot
        self.assertEqual(B.aged_overlap(lot_qty, ages, 40, 30), 0)         # slow lot only


class TestGeneratedData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        subprocess.run([sys.executable, os.path.join(ROOT, "src", "generate.py"), "--skus", "500", "--days", "60", "--promos", "150",
                        "--seed", "20261022", "--out", cls.tmp.name], check=True, stdout=subprocess.DEVNULL)
        rd = lambda n: pd.read_csv(os.path.join(cls.tmp.name, n), keep_default_na=False, na_values=[""])
        cls.PB, cls.BO, cls.OR, cls.INV, cls.LOT = rd("product_bundle.csv"), rd("bundle_order.csv"), rd("orders.csv"), rd("inventory_snapshot.csv"), rd("inventory_lot.csv")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_data_has_bundles_and_every_status_rule_holds(self):
        self.assertGreater(len(self.PB), 0); self.assertGreater(len(self.BO), 0)
        self.assertEqual(set(self.PB.bundle_status) - {"ACTIVE", "EXPIRED", "CANCELLED", "DRAFT"}, set())
        self.assertTrue(((self.PB.bundle_status == "CANCELLED") == self.PB.rejection_reason.notna()).all())

    def test_10_bundle_sales_update_inventory_of_both_products(self):
        bo = self.BO.merge(self.PB[["bundle_id", "primary_sku", "secondary_sku"]], on="bundle_id")
        ol = self.OR.set_index("order_id")
        self.assertTrue((ol.reindex(bo.order_id).sku.values == bo.primary_sku.values).all())
        self.assertTrue((ol.reindex(bo.secondary_order_id).sku.values == bo.secondary_sku.values).all())
        self.assertEqual(int(self.OR.bundle_order_id.notna().sum()), 2 * len(self.BO))
        iq = self.INV.set_index(["sku", "snapshot_date"]).units_sold
        for col in ("primary_sku", "secondary_sku"):
            q = bo.groupby([col, "order_date"]).quantity.sum()
            q.index.names = ["sku", "snapshot_date"]
            self.assertTrue((iq.reindex(q.index).values >= q.values).all())          # bundle units are inside units_sold of each SKU
        # and the roll-forward still reconciles, with Orders = units_sold for every SKU-day
        self.assertTrue((self.INV.closing_on_hand == self.INV.opening_on_hand + self.INV.units_received - self.INV.units_sold).all())
        oq = self.OR.groupby(["sku", "order_date"]).quantity.sum()
        self.assertTrue(oq.equals(iq[iq > 0].rename("quantity").rename_axis(["sku", "order_date"])))

    def test_11_no_duplicate_active_pair_in_data(self):
        a = self.PB[self.PB.rejection_reason.isna()].copy()
        a["key"] = [tuple(sorted(x)) for x in zip(a.primary_sku, a.secondary_sku)]
        a = a.sort_values(["key", "valid_from"])
        nxt = a.groupby("key").valid_from.shift(-1)
        self.assertFalse((nxt.notna() & (nxt <= a.valid_to)).any())

    def test_09_no_sales_outside_validity(self):
        j = self.BO.merge(self.PB, on="bundle_id")
        self.assertTrue(j.rejection_reason.isna().all())
        self.assertTrue(((j.order_date >= j.valid_from) & (j.order_date <= j.valid_to)).all())

    def test_12_totals_in_data(self):
        bo = self.BO
        self.assertTrue(np.allclose(bo.total_revenue, bo.quantity * bo.bundle_selling_price, atol=0.011))
        self.assertTrue(np.allclose(bo.gross_profit, bo.total_revenue - bo.total_cost, atol=0.011))
        sold = bo.groupby("bundle_id").quantity.sum()
        cap = self.PB.set_index("bundle_id").max_bundle_units.reindex(sold.index)
        self.assertTrue((cap.values >= sold.values).all())

    def test_01_aged_class_in_data(self):
        i = self.INV
        self.assertTrue(((i.oldest_stock_age_days > 90) == (i.stock_age_class == "AGED")).all())
        self.assertTrue((i.aged_units <= i.closing_on_hand).all())
        self.assertTrue(((i.aged_units > 0) <= (i.oldest_stock_age_days > 90)).all())


if __name__ == "__main__":
    unittest.main(verbosity=2)
