"""Recommend a launch price for a NEW product using the simulator's pricing rules.

The product has no price history, so the category parameters (typical margin, price trend, minimum
margin) are derived from the existing dataset and the same guardrails as generate.py are applied:
margin floor, competitor band, stock signals, gradient ceiling and promotion guardrails.
Rules-based and deterministic, no model training. Standard library only.

Example:
  python price_new_product.py --category Electronics --cost 40 --competitor-price 64.99 \
      --competitor-age-days 2 --stock 300 --daily-demand 6 --promo-pct 0.10
"""
import argparse
import csv
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.normpath(os.path.join(HERE, "..", "data_starter"))

# Constants mirror rules_config.json / generate.py
STALE_DAYS = 7.0
COMP_UPPER, COMP_LOWER = 1.03, 0.93
LOW_COVER_DAYS, OVER_COVER_DAYS = 5.0, 75.0
LOW_STOCK_MARKUP, OVERSTOCK_MARKDOWN = 1.04, 0.95
GRADIENT_TOLERANCE = 0.03
MAX_TOTAL_DISCOUNT = 0.35


def ceil_cent(x):
    return math.ceil(round(x * 100, 6)) / 100.0


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def category_params(data_dir):
    """Per-category medians from the existing dataset (product, price_gradient, cost_record)."""
    prod = {r["sku"]: r for r in read_csv(os.path.join(data_dir, "product.csv"))}
    grad = {r["sku"]: r for r in read_csv(os.path.join(data_dir, "price_gradient.csv"))}
    first_cost = {}
    for r in read_csv(os.path.join(data_dir, "cost_record.csv")):
        first_cost.setdefault(r["sku"], float(r["unit_cost"]))
    acc = {}
    for sku, p in prod.items():
        g = grad.get(sku)
        if g is None or sku not in first_cost:
            continue
        a = acc.setdefault(p["category"], {"min_margin": [], "cost_margin": [], "max_yoy": [], "cagr": []})
        lp = float(p["list_price"])
        a["min_margin"].append(float(p["min_margin_pct"]))
        a["cost_margin"].append((lp - first_cost[sku]) / lp)
        a["max_yoy"].append(float(g["max_yoy_price_pct"]))
        a["cagr"].append(float(g["price_cagr_5y"]))
    return {c: {k: statistics.median(v) for k, v in d.items()} | {"n_products": len(d["cagr"])}
            for c, d in acc.items()}


def recommend(a, params):
    cp = params[a.category]
    steps, flags = [], []
    min_margin = a.min_margin if a.min_margin is not None else cp["min_margin"]
    cost = a.cost

    # 1. Guardrail: effective floor (margin floor always wins)
    floor = max(a.price_floor_abs or 0.0, ceil_cent(cost / (1 - min_margin)))
    steps.append(f"Margin floor ${floor:.2f} = max(abs floor {a.price_floor_abs or 0:.2f}, "
                 f"cost / (1 - {min_margin:.0%} min margin))")

    # 2. Starting price
    if a.list_price:
        p0, p0_src = a.list_price, "intended list price"
    else:
        p0 = ceil_cent(cost / (1 - cp["cost_margin"]))
        p0_src = f"category cost-plus ({cp['cost_margin']:.0%} typical margin in {a.category})"
    steps.append(f"Starting price ${p0:.2f} from {p0_src}")

    # 3. Competitor / stock signals (same order as generate.py core())
    ref, stale = None, False
    if a.competitor_price:
        if a.competitor_age_days <= STALE_DAYS:
            ref = min(a.competitor_price)
            steps.append(f"Fresh competitor ({a.competitor_age_days:g}d <= {STALE_DAYS:g}d): lowest price "
                         f"${ref:.2f} used as reference")
        else:
            stale = True
            flags.append("STALE_COMPETITOR")
            steps.append(f"Competitor data is {a.competitor_age_days:g}d old (> {STALE_DAYS:g}d): ignored")
    cover = None
    if a.stock is not None and a.daily_demand:
        cover = a.stock / max(a.daily_demand, 0.05)
        steps.append(f"Stock cover {cover:.0f} days ({a.stock:g} units / {a.daily_demand:g} per day)")

    if cover is not None and cover < LOW_COVER_DAYS and a.daily_demand > 0.2:
        target, reason = p0 * LOW_STOCK_MARKUP, "LOW_STOCK_MARKUP"
    elif ref is not None:
        if a.list_price is None:
            target, reason = ref * 0.995, "COMP_MATCH"
            steps.append(f"No list price given: priced 0.5% under competitor ${ref:.2f}")
        elif p0 > ref * COMP_UPPER:
            target, reason = ref * 0.995, "COMP_MATCH_DOWN"
            steps.append(f"List price is above competitor band (+3%): match down to ${ref * 0.995:.2f}")
        elif p0 < ref * COMP_LOWER:
            target, reason = ref * 0.96, "COMP_RAISE"
            steps.append(f"List price is below competitor band (-7%): raise to ${ref * 0.96:.2f}")
        else:
            target, reason = p0, "HOLD_IN_COMP_BAND"
            steps.append("List price is inside the competitor band: keep it")
    elif cover is not None and cover > OVER_COVER_DAYS:
        target, reason = p0 * OVERSTOCK_MARKDOWN, "OVERSTOCK_MARKDOWN"
    elif stale:
        target, reason = p0, "HOLD_STALE_COMPETITOR"
    else:
        target, reason = p0, "NEW_PRODUCT_NO_SIGNAL"
        flags.append("NO_COMPETITOR_DATA")

    # 4. Ceiling: gradient ceiling on the launch reference, never below the floor
    ref_for_ceiling = ref if ref is not None else p0
    gradient_ceiling = ref_for_ceiling * (1 + cp["max_yoy"] + GRADIENT_TOLERANCE)
    hard_ceiling = a.price_ceiling if a.price_ceiling else gradient_ceiling
    ceiling = max(min(hard_ceiling, gradient_ceiling), floor)
    steps.append(f"Ceiling ${ceiling:.2f} = reference ${ref_for_ceiling:.2f} x (1 + {cp['max_yoy']:.1%} max yoy "
                 f"+ {GRADIENT_TOLERANCE:.0%}), never below the floor")

    price = target
    if price < floor:
        price = floor
        flags.append("FLOOR_CLAMPED")
        if ref is not None and floor > ref:
            flags.append("FLOORED_ABOVE_COMPETITOR")
    elif price > ceiling:
        price = ceiling
        flags.append("GRADIENT_CAPPED" if ceiling < hard_ceiling - 1e-9 or not a.price_ceiling else "CEILING_CLAMPED")
    price = round(price, 2)
    margin = (price - cost) / price

    out = {
        "product_name": a.name, "category": a.category, "unit_cost": cost,
        "recommended_price": price, "reason_code": reason, "margin_pct": round(margin, 4),
        "effective_floor": round(floor, 2), "ceiling": round(ceiling, 2),
        "min_margin_pct": round(min_margin, 4),
        "guardrails_pass": bool(floor - 1e-9 <= price <= ceiling + 1e-9 and margin >= min_margin - 1e-9),
        "flags": flags, "steps": steps,
        "category_basis": {"n_products": int(cp["n_products"]), "typical_margin": round(cp["cost_margin"], 4),
                           "max_yoy_price_pct": round(cp["max_yoy"], 4)},
        "promotion": None,
    }

    # 5. Optional promotion check (same guardrail order as eval_promos)
    if a.promo_pct:
        net = round(price * (1 - a.promo_pct), 2)
        reject = None
        if a.promo_pct > MAX_TOTAL_DISCOUNT:
            reject = "MAX_TOTAL_DISCOUNT"
        elif net < floor - 1e-9:
            reject = "FLOOR_GUARDRAIL"
        elif a.promo_min_margin_pct and (net - cost) / net < a.promo_min_margin_pct - 1e-12:
            reject = "MARGIN_GUARDRAIL"
        out["promotion"] = {
            "discount_pct": a.promo_pct, "status": "REJECTED" if reject else "APPLIED",
            "reject_reason": reject, "net_price": price if reject else net,
            "net_margin_pct": round(((price if reject else net) - cost) / (price if reject else net), 4),
        }
    return out


def render(o):
    L = ["NEW PRODUCT PRICE RECOMMENDATION", "=" * 33]
    if o["product_name"]:
        L.append(f"Product:              {o['product_name']} ({o['category']})")
    L += [f"Recommended price:    ${o['recommended_price']:.2f}        reason: {o['reason_code']}",
          f"Margin at that price: {o['margin_pct']:.1%}        (cost {o['unit_cost']:.2f})", "",
          "Guardrails",
          f"  Margin floor   ${o['effective_floor']:.2f}   (min margin {o['min_margin_pct']:.0%})",
          f"  Ceiling        ${o['ceiling']:.2f}",
          f"  Result         {'PASS' if o['guardrails_pass'] else 'FAIL'}", "", "How the price was chosen"]
    L += [f"  {i}. {s}" for i, s in enumerate(o["steps"], 1)]
    b = o["category_basis"]
    L.append(f"  (category parameters from {b['n_products']} existing {o['category']} products)")
    if o["promotion"]:
        p = o["promotion"]
        L += ["", "Promotion check",
              f"  {p['discount_pct']:.0%} off: {p['status']}"
              + (f"   reason: {p['reject_reason']}" if p["reject_reason"] else "")
              + f"   net price ${p['net_price']:.2f}, net margin {p['net_margin_pct']:.1%}"]
    L += ["", "Exceptions / flags", "  " + (", ".join(o["flags"]) if o["flags"] else "none")]
    return "\n".join(L)


def build_parser(categories):
    p = argparse.ArgumentParser(description="Recommend a price for a new product.")
    p.add_argument("--category", required=True, choices=categories)
    p.add_argument("--cost", required=True, type=float, help="unit cost (> 0)")
    p.add_argument("--name", default="", help="optional product name (label only)")
    p.add_argument("--list-price", type=float, help="intended list price; otherwise category cost-plus")
    p.add_argument("--competitor-price", type=float, nargs="+", help="one or more observed competitor prices")
    p.add_argument("--competitor-age-days", type=float, default=0.0, help="age of the observation (default 0)")
    p.add_argument("--stock", type=float, help="starting stock units")
    p.add_argument("--daily-demand", type=float, help="expected units per day")
    p.add_argument("--min-margin", type=float, help="override minimum margin, e.g. 0.2 (default: category median)")
    p.add_argument("--price-floor-abs", type=float, help="absolute price floor")
    p.add_argument("--price-ceiling", type=float, help="absolute price ceiling")
    p.add_argument("--promo-pct", type=float, help="promotion discount to test, e.g. 0.10")
    p.add_argument("--promo-min-margin-pct", type=float, help="promotion's own margin requirement, e.g. 0.2")
    p.add_argument("--data-dir", default=DEFAULT_DATA, help="dataset folder (default: ../data_starter)")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")
    return p


def main(argv=None):
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--data-dir", default=DEFAULT_DATA)
    known, _ = pre.parse_known_args(argv)
    try:
        params = category_params(known.data_dir)
    except FileNotFoundError as e:
        sys.exit(f"error: dataset file not found ({e.filename}); use --data-dir")
    parser = build_parser(sorted(params))
    a = parser.parse_args(argv)

    def bad(msg):
        parser.error(msg)
    if a.cost <= 0:
        bad("--cost must be > 0")
    for n in ("list_price", "price_floor_abs", "price_ceiling"):
        v = getattr(a, n)
        if v is not None and v <= 0:
            bad(f"--{n.replace('_', '-')} must be > 0")
    if a.competitor_price and any(x <= 0 for x in a.competitor_price):
        bad("--competitor-price values must be > 0")
    if a.competitor_age_days < 0:
        bad("--competitor-age-days must be >= 0")
    if a.stock is not None and a.stock < 0:
        bad("--stock must be >= 0")
    if a.daily_demand is not None and a.daily_demand < 0:
        bad("--daily-demand must be >= 0")
    for n in ("min_margin", "promo_pct", "promo_min_margin_pct"):
        v = getattr(a, n)
        if v is not None and not 0 < v < 1:
            bad(f"--{n.replace('_', '-')} must be between 0 and 1 (e.g. 0.2)")

    out = recommend(a, params)
    print(json.dumps(out, indent=2) if a.json else render(out))


if __name__ == "__main__":
    main()
