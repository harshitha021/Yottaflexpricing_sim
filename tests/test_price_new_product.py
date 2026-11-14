"""Tests for src/price_new_product.py (run: python -m unittest discover -s tests -v)."""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import price_new_product as P  # noqa: E402

PARAMS = P.category_params(os.path.join(ROOT, "data_starter"))


def run(**kw):
    base = dict(name="", category="Electronics", cost=40.0, list_price=None, competitor_price=None,
                competitor_age_days=0.0, stock=None, daily_demand=None, stock_age_days=None,
                strategy="balanced", price_ending="none", current_price=None, days_since_change=None,
                elasticity=None, min_margin=None, price_floor_abs=None, price_ceiling=None,
                promo_pct=None, promo_min_margin_pct=None)
    base.update(kw)
    return P.recommend(argparse.Namespace(**base), PARAMS)


class TestCoreRules(unittest.TestCase):
    def test_floor_always_wins(self):
        o = run(competitor_price=[42.0])
        self.assertEqual(o["recommended_price"], o["effective_floor"])
        self.assertIn("FLOOR_CLAMPED", o["flags"])
        self.assertIn("FLOORED_ABOVE_COMPETITOR", o["flags"])

    def test_competitor_match(self):
        o = run(competitor_price=[64.99], competitor_age_days=2)
        self.assertEqual(o["reason_code"], "COMP_MATCH")
        self.assertLess(o["recommended_price"], 64.99)
        self.assertTrue(o["guardrails_pass"])

    def test_stale_competitor_ignored(self):
        o = run(competitor_price=[64.99], competitor_age_days=20)
        self.assertEqual(o["reason_code"], "HOLD_STALE_COMPETITOR")
        self.assertIn("STALE_COMPETITOR", o["flags"])

    def test_no_signal_flag(self):
        o = run()
        self.assertEqual(o["reason_code"], "NEW_PRODUCT_NO_SIGNAL")
        self.assertIn("NO_COMPETITOR_DATA", o["flags"])

    def test_low_stock_markup_and_overstock_markdown(self):
        self.assertEqual(run(stock=2, daily_demand=5)["reason_code"], "LOW_STOCK_MARKUP")
        self.assertEqual(run(stock=4000, daily_demand=40)["reason_code"], "OVERSTOCK_MARKDOWN")


class TestNewRules(unittest.TestCase):
    def test_suspect_competitor_ignored(self):
        o = run(competitor_price=[5.0], competitor_age_days=1)
        self.assertIn("SUSPECT_COMPETITOR_PRICE", o["flags"])
        self.assertIn("NO_COMPETITOR_DATA", o["flags"])
        self.assertNotEqual(o["reason_code"], "COMP_MATCH")

    def test_suspect_outlier_among_several(self):
        o = run(competitor_price=[64.99, 20.0], competitor_age_days=1)
        self.assertIn("SUSPECT_COMPETITOR_PRICE", o["flags"])
        self.assertEqual(o["reason_code"], "COMP_MATCH")

    def test_strategy_ordering(self):
        kw = dict(competitor_price=[64.99], competitor_age_days=1)
        pen, bal, skim = (run(strategy=s, **kw)["recommended_price"] for s in ("penetration", "balanced", "skim"))
        self.assertLess(pen, bal)
        self.assertLess(bal, skim)
        for s in P.STRATEGIES:
            self.assertTrue(run(strategy=s, **kw)["guardrails_pass"])

    def test_price_ending_inside_limits(self):
        o = run(competitor_price=[64.99], competitor_age_days=1, price_ending="99")
        self.assertTrue(f"{o['recommended_price']:.2f}".endswith(".99"))
        self.assertTrue(o["guardrails_pass"])
        o = run(competitor_price=[42.0], competitor_age_days=1, price_ending="49")
        self.assertGreaterEqual(o["recommended_price"], o["effective_floor"])

    def test_cooldown_holds_price(self):
        o = run(competitor_price=[64.99], competitor_age_days=1, current_price=60.0, days_since_change=3)
        self.assertEqual(o["reason_code"], "COOLDOWN_HOLD")
        self.assertEqual(o["recommended_price"], 60.0)

    def test_cooldown_does_not_block_forced_change(self):
        o = run(current_price=45.0, days_since_change=1)      # current price is below the floor
        self.assertNotEqual(o["reason_code"], "COOLDOWN_HOLD")
        self.assertGreaterEqual(o["recommended_price"], o["effective_floor"])

    def test_step_limit(self):
        o = run(competitor_price=[64.99], competitor_age_days=1, current_price=55.0, days_since_change=30)
        self.assertIn("STEP_LIMITED", o["flags"])
        self.assertLessEqual(o["recommended_price"], 55.0 * 1.1 + 0.005)

    def test_stock_age_markdown_ladder(self):
        base = run()["recommended_price"]
        slow = run(stock_age_days=75)
        aged = run(stock_age_days=120)
        self.assertEqual(slow["reason_code"], "SLOW_STOCK_MARKDOWN")
        self.assertEqual(aged["reason_code"], "AGED_STOCK_MARKDOWN")
        self.assertLess(aged["recommended_price"], slow["recommended_price"])
        self.assertLessEqual(slow["recommended_price"], base)
        self.assertTrue(aged["guardrails_pass"])

    def test_options_table_has_floor_and_recommended(self):
        o = run(competitor_price=[64.99], competitor_age_days=1, stock=300, daily_demand=6)
        prices = [x["price"] for x in o["price_options"]["options"]]
        self.assertIn(o["effective_floor"], prices)
        self.assertIn(o["recommended_price"], prices)
        self.assertEqual(o["price_options"]["units_basis"], "units/day")

    def test_best_promo_picker(self):
        o = run(competitor_price=[64.99], competitor_age_days=1, promo_pct=[0.05, 0.10, 0.25],
                promo_min_margin_pct=0.2)
        by = {p["discount_pct"]: p for p in o["promotion_options"]}
        self.assertEqual(by[0.25]["status"], "REJECTED")
        self.assertEqual(by[0.25]["reject_reason"], "MARGIN_GUARDRAIL")
        self.assertEqual(o["promotion"]["discount_pct"], 0.05)
        self.assertTrue(o["promotion"]["chosen"])

    def test_promo_max_total_discount(self):
        o = run(promo_pct=[0.40])
        self.assertEqual(o["promotion"]["reject_reason"], "MAX_TOTAL_DISCOUNT")

    def test_similar_products_check(self):
        o = run()
        s = o["similar_products"]
        self.assertEqual(s["n"], 10)
        self.assertEqual(s["within_range"], "PRICE_OUTLIER_VS_SIMILAR" not in o["flags"])

    def test_confidence_levels(self):
        self.assertEqual(run()["confidence"], "LOW")
        self.assertEqual(run(competitor_price=[64.99], competitor_age_days=1)["confidence"], "MEDIUM")
        self.assertEqual(run(competitor_price=[64.99], competitor_age_days=1, stock=300,
                             daily_demand=6)["confidence"], "HIGH")

    def test_deterministic(self):
        kw = dict(competitor_price=[64.99, 66.5], competitor_age_days=2, stock=300, daily_demand=6)
        self.assertEqual(json.dumps(run(**kw)), json.dumps(run(**kw)))


class TestInputs(unittest.TestCase):
    def cli(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            P.main(argv)
        return buf.getvalue()

    def test_json_single_and_batch_and_csv(self):
        with tempfile.TemporaryDirectory() as d:
            single = os.path.join(d, "one.json")
            batch = os.path.join(d, "many.json")
            csvf = os.path.join(d, "p.csv")
            with open(single, "w") as f:
                json.dump({"category": "Toys", "cost": 10, "promo_pct": 0.1, "price_ending": 99}, f)
            with open(batch, "w") as f:
                json.dump([{"category": "Toys", "cost": 10}, {"category": "Office", "cost": 8}], f)
            with open(csvf, "w") as f:
                f.write("category,cost,competitor_price,promo_pct\nToys,10,15.5;16,0.05;0.1\nOffice,8,,\n")
            self.assertEqual(json.loads(self.cli(["--input", single, "--json"]))["category"], "Toys")
            self.assertEqual(len(json.loads(self.cli(["--input", batch, "--json"]))), 2)
            out = os.path.join(d, "res.csv")
            res = json.loads(self.cli(["--input", csvf, "--json", "--out-csv", out]))
            self.assertEqual(len(res), 2)
            self.assertEqual(len(res[0]["promotion_options"]), 2)
            with open(out) as f:
                self.assertEqual(len(f.read().strip().splitlines()), 3)

    def test_bad_input_exits(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            for payload in ({"category": "Toys", "cost": "abc"}, {"category": "Toys", "cost": 5, "colour": "red"},
                            {"category": "Cars", "cost": 5}, {"category": "Toys", "cost": -1},
                            {"category": "Toys", "cost": 5, "strategy": "wild"}):
                with open(bad, "w") as f:
                    json.dump(payload, f)
                with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                    P.main(["--input", bad])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            P.main(["--category", "Toys", "--cost", "10", "--elasticity", "1.5"])


if __name__ == "__main__":
    unittest.main()
