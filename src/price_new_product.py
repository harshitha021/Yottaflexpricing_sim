"""Recommend a launch price for a NEW product using the simulator's pricing rules.

The product has no price history, so the category parameters (typical margin, price trend, minimum
margin) are derived from the existing dataset and the same guardrails as generate.py are applied:
margin floor, competitor band, stock signals, gradient ceiling and promotion guardrails.

Extra rules for impact: suspect-competitor check, launch strategy, price endings, price-change
cooldown + step limit, stock-age markdown, price-options table (assumed elasticity), best-promotion
picker, similar-products check and a confidence label.
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
MAX_STEP = 0.10                      # max price change per decision
# Extra rules (new-product script only; the generated datasets are not affected)
COOLDOWN_DAYS = 7.0                  # no second price change inside this window unless forced
SLOW_AGE_DAYS, AGED_AGE_DAYS = 60, 90
SLOW_MARKDOWN, AGED_MARKDOWN = 0.95, 0.90
PENETRATION_SHARE = 0.35             # penetration: floor + 35% of the way to the balanced price
SKIM_SHARE = 0.50                    # skim: balanced price + 50% of the way to the ceiling
SUSPECT_VS_COSTPLUS = 0.5            # competitor below 50% of cost-plus price is suspect
SUSPECT_VS_MEDIAN = (0.5, 2.0)       # competitor outside 0.5x..2x of the median is suspect
SIMILAR_N = 10
# ASSUMED price elasticity per category (the generator does not export its own); override with --elasticity
ELASTICITY = {"Electronics": -1.8, "Apparel": -1.6, "Grocery": -1.1, "Home & Kitchen": -1.3,
              "Beauty": -1.4, "Office": -1.2, "Sports": -1.4, "Toys": -1.5}
DEFAULT_ELASTICITY = -1.4
STRATEGIES = ("balanced", "penetration", "skim")
ENDINGS = ("none", "99", "49")


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
        a = acc.setdefault(p["category"], {"min_margin": [], "cost_margin": [], "max_yoy": [], "cagr": [],
                                           "pairs": []})
        lp = float(p["list_price"])
        a["min_margin"].append(float(p["min_margin_pct"]))
        a["cost_margin"].append((lp - first_cost[sku]) / lp)
        a["max_yoy"].append(float(g["max_yoy_price_pct"]))
        a["cagr"].append(float(g["price_cagr_5y"]))
        a["pairs"].append((first_cost[sku], lp))
    out = {}
    for c, d in acc.items():
        out[c] = {k: statistics.median(v) for k, v in d.items() if k != "pairs"}
        out[c]["n_products"] = len(d["cagr"])
        out[c]["pairs"] = d["pairs"]
    return out


def filter_competitors(prices, cost_plus):
    """Split competitor prices into plausible and suspect ones (bad feeds, typos, loss-leaders)."""
    med = statistics.median(prices) if len(prices) > 1 else None
    valid, suspect = [], []
    for x in prices:
        bad = x < SUSPECT_VS_COSTPLUS * cost_plus
        if med is not None and not (SUSPECT_VS_MEDIAN[0] * med <= x <= SUSPECT_VS_MEDIAN[1] * med):
            bad = True
        (suspect if bad else valid).append(x)
    return valid, suspect


def apply_ending(price, ending, lo, hi):
    """Nearest .99 / .49 price inside [lo, hi]; keep the price if none fits."""
    if ending == "none":
        return price, False
    frac = int(ending) / 100.0
    best = None
    for n in range(int(price) - 1, int(price) + 2):
        c = round(n + frac, 2)
        if c > 0 and lo - 1e-9 <= c <= hi + 1e-9 and (best is None or abs(c - price) < abs(best - price) - 1e-12):
            best = c
    return (best, True) if best is not None else (price, False)


def est_profit(price, ref_price, q0, cost, e):
    q = q0 * (price / ref_price) ** e
    return q, (price - cost) * q


def recommend(a, params):
    cp = params[a.category]
    steps, flags = [], []
    min_margin = a.min_margin if a.min_margin is not None else cp["min_margin"]
    cost = a.cost
    strategy = getattr(a, "strategy", "balanced") or "balanced"
    ending = getattr(a, "price_ending", "none") or "none"
    e = getattr(a, "elasticity", None) or ELASTICITY.get(a.category, DEFAULT_ELASTICITY)

    # 1. Guardrail: effective floor (margin floor always wins)
    floor = max(a.price_floor_abs or 0.0, ceil_cent(cost / (1 - min_margin)))
    steps.append(f"Margin floor ${floor:.2f} = max(abs floor {a.price_floor_abs or 0:.2f}, "
                 f"cost / (1 - {min_margin:.0%} min margin))")

    # 2. Starting price
    cost_plus = ceil_cent(cost / (1 - cp["cost_margin"]))
    if a.list_price:
        p0, p0_src = a.list_price, "intended list price"
    else:
        p0 = cost_plus
        p0_src = f"category cost-plus ({cp['cost_margin']:.0%} typical margin in {a.category})"
    steps.append(f"Starting price ${p0:.2f} from {p0_src}")

    # 3. Competitor signal, with a sanity check on the observed prices
    ref, stale = None, False
    if a.competitor_price:
        if a.competitor_age_days > STALE_DAYS:
            stale = True
            flags.append("STALE_COMPETITOR")
            steps.append(f"Competitor data is {a.competitor_age_days:g}d old (> {STALE_DAYS:g}d): ignored")
        else:
            valid, suspect = filter_competitors(a.competitor_price, cost_plus)
            if suspect:
                flags.append("SUSPECT_COMPETITOR_PRICE")
                steps.append("Suspect competitor price(s) ignored: "
                             + ", ".join(f"${x:.2f}" for x in suspect)
                             + f" (below {SUSPECT_VS_COSTPLUS:.0%} of cost-plus ${cost_plus:.2f} or "
                               f"far from the other competitors)")
            if valid:
                ref = min(valid)
                steps.append(f"Fresh competitor ({a.competitor_age_days:g}d <= {STALE_DAYS:g}d): lowest price "
                             f"${ref:.2f} used as reference")
            else:
                flags.append("NO_COMPETITOR_DATA")
                steps.append("No usable competitor price left after the sanity check")
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
        if "NO_COMPETITOR_DATA" not in flags:
            flags.append("NO_COMPETITOR_DATA")

    # 4. Stock-age markdown ladder (old stock is cleared before it becomes dead stock)
    age = getattr(a, "stock_age_days", None)
    if age is not None and reason != "LOW_STOCK_MARKUP" and age > SLOW_AGE_DAYS:
        factor, code = (AGED_MARKDOWN, "AGED_STOCK_MARKDOWN") if age > AGED_AGE_DAYS \
            else (SLOW_MARKDOWN, "SLOW_STOCK_MARKDOWN")
        target *= factor
        reason = code
        steps.append(f"Oldest stock is {age:g} days old: markdown {1 - factor:.0%} ({code})")

    # 5. Ceiling: gradient ceiling on the launch reference, never below the floor
    ref_for_ceiling = ref if ref is not None else p0
    gradient_ceiling = ref_for_ceiling * (1 + cp["max_yoy"] + GRADIENT_TOLERANCE)
    hard_ceiling = a.price_ceiling if a.price_ceiling else gradient_ceiling
    ceiling = max(min(hard_ceiling, gradient_ceiling), floor)
    steps.append(f"Ceiling ${ceiling:.2f} = reference ${ref_for_ceiling:.2f} x (1 + {cp['max_yoy']:.1%} max yoy "
                 f"+ {GRADIENT_TOLERANCE:.0%}), never below the floor")

    # 6. Launch strategy moves the price inside the allowed range
    balanced = min(max(target, floor), ceiling)
    if strategy == "penetration":
        target = floor + PENETRATION_SHARE * (balanced - floor)
        flags.append("STRATEGY_PENETRATION")
        steps.append(f"Strategy penetration: price set {PENETRATION_SHARE:.0%} of the way from the floor "
                     f"${floor:.2f} to the balanced price ${balanced:.2f}")
    elif strategy == "skim":
        target = balanced + SKIM_SHARE * (ceiling - balanced)
        flags.append("STRATEGY_SKIM")
        steps.append(f"Strategy skim: price set {SKIM_SHARE:.0%} of the way from the balanced price "
                     f"${balanced:.2f} to the ceiling ${ceiling:.2f}")

    price = target
    if price < floor:
        price = floor
        flags.append("FLOOR_CLAMPED")
        if ref is not None and floor > ref:
            flags.append("FLOORED_ABOVE_COMPETITOR")
    elif price > ceiling:
        price = ceiling
        flags.append("GRADIENT_CAPPED" if ceiling < hard_ceiling - 1e-9 or not a.price_ceiling else "CEILING_CLAMPED")

    # 7. Re-pricing an existing price: cooldown and max 10% step
    cur = getattr(a, "current_price", None)
    held = False
    lo_b, hi_b = floor, ceiling
    if cur is not None:
        dsc = getattr(a, "days_since_change", None)
        forced = reason == "LOW_STOCK_MARKUP" or cur < floor - 1e-9 or cur > ceiling + 1e-9
        if dsc is not None and dsc < COOLDOWN_DAYS and not forced:
            price, reason, held = cur, "COOLDOWN_HOLD", True
            flags.append("COOLDOWN_HOLD")
            steps.append(f"Last price change was {dsc:g}d ago (< {COOLDOWN_DAYS:g}d) and nothing forces a change: "
                         f"keep ${cur:.2f}")
        else:
            lo, hi = cur * (1 - MAX_STEP), cur * (1 + MAX_STEP)
            if price < lo - 1e-9 or price > hi + 1e-9:
                price = min(max(price, lo), hi)
                flags.append("STEP_LIMITED")
                steps.append(f"Change limited to +/-{MAX_STEP:.0%} of the current price ${cur:.2f}")
            if price < floor:
                price = floor
                if "FLOOR_CLAMPED" not in flags:
                    flags.append("FLOOR_CLAMPED")
            elif price > ceiling:
                price = ceiling
            if max(floor, lo) <= min(ceiling, hi):
                lo_b, hi_b = max(floor, lo), min(ceiling, hi)

    # 8. Price ending (.99 / .49) only if it stays inside every limit
    if ending != "none" and not held:
        new, ok = apply_ending(price, ending, lo_b, hi_b)
        if ok and abs(new - price) > 1e-9:
            steps.append(f"Price ending .{ending}: ${price:.2f} -> ${new:.2f}")
            price = new
        elif not ok:
            steps.append(f"Price ending .{ending} would break a limit: kept ${price:.2f}")
    price = round(price, 2)
    margin = (price - cost) / price

    # 9. Price options table (estimated with an ASSUMED elasticity)
    q0 = a.daily_demand if a.daily_demand else 100.0
    units_basis = "units/day" if a.daily_demand else "index (recommended = 100)"
    comp_match = min(max((ref * 0.995) if ref is not None else p0, floor), ceiling)
    cands = {}
    for label, p in (("Floor", floor), ("Recommended", price), ("Competitor match" if ref is not None
                                                               else "Cost-plus start", comp_match)):
        cands.setdefault(round(p, 2), []).append(label)
    options = []
    for p, labels in sorted(cands.items()):
        q, prof = est_profit(p, price, q0, cost, e)
        options.append({"label": " / ".join(labels), "price": p, "margin_pct": round((p - cost) / p, 4),
                        "est_daily_units": round(q, 2), "est_daily_profit": round(prof, 2)})
    best = max(options, key=lambda o: o["est_daily_profit"])

    # 10. Similar existing products (price-to-cost ratio check)
    near = sorted(cp["pairs"], key=lambda t: (abs(t[0] - cost), t[0]))[:SIMILAR_N]
    ratios = [lp / c for c, lp in near]
    your_ratio = price / cost
    similar = {"n": len(near), "median_ratio": round(statistics.median(ratios), 3),
               "low_ratio": round(min(ratios), 3), "high_ratio": round(max(ratios), 3),
               "your_ratio": round(your_ratio, 3),
               "within_range": bool(min(ratios) - 1e-9 <= your_ratio <= max(ratios) + 1e-9)}
    if not similar["within_range"]:
        flags.append("PRICE_OUTLIER_VS_SIMILAR")

    # 11. Confidence label from how many real signals were available
    signals = int(ref is not None) + int(cover is not None)
    confidence = ("HIGH", "MEDIUM", "LOW")[2 - signals]
    conf_reason = {2: "fresh competitor price and stock/demand data available",
                   1: "only one of competitor price or stock/demand data available",
                   0: "no usable competitor price and no stock/demand data"}[signals]

    out = {
        "product_name": a.name, "category": a.category, "unit_cost": cost,
        "recommended_price": price, "reason_code": reason, "margin_pct": round(margin, 4),
        "effective_floor": round(floor, 2), "ceiling": round(ceiling, 2),
        "min_margin_pct": round(min_margin, 4),
        "guardrails_pass": bool(floor - 1e-9 <= price <= ceiling + 1e-9 and margin >= min_margin - 1e-9),
        "strategy": strategy, "confidence": confidence, "confidence_reason": conf_reason,
        "flags": flags, "steps": steps,
        "price_options": {"elasticity_assumed": e, "units_basis": units_basis, "options": options,
                          "highest_estimated_profit": best["label"]},
        "similar_products": similar,
        "category_basis": {"n_products": int(cp["n_products"]), "typical_margin": round(cp["cost_margin"], 4),
                           "max_yoy_price_pct": round(cp["max_yoy"], 4)},
        "promotion": None, "promotion_options": [],
    }

    # 12. Promotions: check every candidate, then pick the best one that passes all guardrails
    promos = a.promo_pct or []
    _, base_prof = est_profit(price, price, q0, cost, e)
    for pct in promos:
        net = round(price * (1 - pct), 2)
        reject = None
        if pct > MAX_TOTAL_DISCOUNT:
            reject = "MAX_TOTAL_DISCOUNT"
        elif net < floor - 1e-9:
            reject = "FLOOR_GUARDRAIL"
        elif a.promo_min_margin_pct and (net - cost) / net < a.promo_min_margin_pct - 1e-12:
            reject = "MARGIN_GUARDRAIL"
        shown = price if reject else net
        _, prof = est_profit(shown, price, q0, cost, e)
        out["promotion_options"].append({
            "discount_pct": pct, "status": "REJECTED" if reject else "APPLIED", "reject_reason": reject,
            "net_price": shown, "net_margin_pct": round((shown - cost) / shown, 4),
            "est_profit_vs_no_promo_pct": None if reject or base_prof <= 0 else round(100 * (prof / base_prof - 1), 1)})
    if out["promotion_options"]:
        applied = [p for p in out["promotion_options"] if p["status"] == "APPLIED"]
        if applied:
            chosen = max(applied, key=lambda p: (p["est_profit_vs_no_promo_pct"] or -1e9, -p["discount_pct"]))
            out["promotion"] = dict(chosen, chosen=len(promos) > 1)
        else:
            out["promotion"] = dict(out["promotion_options"][0], chosen=False)
    return out


def render(o):
    L = ["NEW PRODUCT PRICE RECOMMENDATION", "=" * 33]
    if o["product_name"]:
        L.append(f"Product:              {o['product_name']} ({o['category']})")
    L += [f"Recommended price:    ${o['recommended_price']:.2f}        reason: {o['reason_code']}",
          f"Margin at that price: {o['margin_pct']:.1%}        (cost {o['unit_cost']:.2f})",
          f"Confidence:           {o['confidence']}  ({o['confidence_reason']})",
          f"Strategy:             {o['strategy']}", "",
          "Guardrails",
          f"  Margin floor   ${o['effective_floor']:.2f}   (min margin {o['min_margin_pct']:.0%})",
          f"  Ceiling        ${o['ceiling']:.2f}",
          f"  Result         {'PASS' if o['guardrails_pass'] else 'FAIL'}", "", "How the price was chosen"]
    L += [f"  {i}. {s}" for i, s in enumerate(o["steps"], 1)]
    b = o["category_basis"]
    L.append(f"  (category parameters from {b['n_products']} existing {o['category']} products)")

    po = o["price_options"]
    L += ["", f"Price options (estimates use an ASSUMED elasticity of {po['elasticity_assumed']:g}; "
              f"units = {po['units_basis']})",
          f"  {'Option':<28}{'Price':>9}{'Margin':>9}{'Units':>9}{'Profit':>10}"]
    for x in po["options"]:
        star = "  <- highest est. profit" if x["label"] == po["highest_estimated_profit"] else ""
        L.append(f"  {x['label']:<28}{x['price']:>9.2f}{x['margin_pct']:>9.1%}{x['est_daily_units']:>9.1f}"
                 f"{x['est_daily_profit']:>10.2f}{star}")
    s = o["similar_products"]
    L += ["", f"Similar products ({s['n']} closest by cost in {o['category']})",
          f"  price/cost ratio: yours {s['your_ratio']:.2f}, similar median {s['median_ratio']:.2f} "
          f"(range {s['low_ratio']:.2f}-{s['high_ratio']:.2f}): "
          f"{'within range' if s['within_range'] else 'OUTSIDE range'}"]
    if o["promotion_options"]:
        L += ["", "Promotion check"]
        chosen = o["promotion"] if o["promotion"] and o["promotion"].get("chosen") else None
        for p in o["promotion_options"]:
            mark = "  <- chosen" if chosen and p["discount_pct"] == chosen["discount_pct"] else ""
            L.append(f"  {p['discount_pct']:.0%} off: {p['status']}"
                     + (f"   reason: {p['reject_reason']}" if p["reject_reason"] else "")
                     + f"   net price ${p['net_price']:.2f}, net margin {p['net_margin_pct']:.1%}"
                     + (f", est. profit {p['est_profit_vs_no_promo_pct']:+.1f}% vs no promo"
                        if p["est_profit_vs_no_promo_pct"] is not None else "") + mark)
        est = [p["est_profit_vs_no_promo_pct"] for p in o["promotion_options"]
               if p["est_profit_vs_no_promo_pct"] is not None]
        if est and max(est) < 0:
            L.append("  Note: every allowed promotion is estimated to earn less profit than the full price; "
                     "use one only for a volume or clearance goal.")
    L += ["", "Exceptions / flags", "  " + (", ".join(o["flags"]) if o["flags"] else "none")]
    return "\n".join(L)


def build_parser(categories):
    p = argparse.ArgumentParser(description="Recommend a price for a new product.")
    p.add_argument("--input", help="JSON file (object or list) or CSV file (one product per row), same field names")
    p.add_argument("--out-csv", help="also write the results to this CSV file")
    p.add_argument("--category", choices=categories)
    p.add_argument("--cost", type=float, help="unit cost (> 0)")
    p.add_argument("--name", default="", help="optional product name (label only)")
    p.add_argument("--list-price", type=float, help="intended list price; otherwise category cost-plus")
    p.add_argument("--competitor-price", type=float, nargs="+", help="one or more observed competitor prices")
    p.add_argument("--competitor-age-days", type=float, default=0.0, help="age of the observation (default 0)")
    p.add_argument("--stock", type=float, help="starting stock units")
    p.add_argument("--daily-demand", type=float, help="expected units per day")
    p.add_argument("--stock-age-days", type=float, help="age of the oldest stock; >60 days marks down 5%%, >90 days 10%%")
    p.add_argument("--strategy", choices=STRATEGIES, default="balanced",
                   help="penetration = near the floor, skim = near the ceiling (default balanced)")
    p.add_argument("--price-ending", choices=ENDINGS, default="none", help="round to .99 or .49 (default none)")
    p.add_argument("--current-price", type=float, help="existing price when re-pricing (enables the 10%% step limit)")
    p.add_argument("--days-since-change", type=float, help="days since the last price change (7-day cooldown)")
    p.add_argument("--elasticity", type=float, help="assumed price elasticity, negative, e.g. -1.5")
    p.add_argument("--min-margin", type=float, help="override minimum margin, e.g. 0.2 (default: category median)")
    p.add_argument("--price-floor-abs", type=float, help="absolute price floor")
    p.add_argument("--price-ceiling", type=float, help="absolute price ceiling")
    p.add_argument("--promo-pct", type=float, nargs="+", help="one or more promotion discounts to test, e.g. 0.05 0.10")
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
    args = parser.parse_args(argv)

    is_batch = False
    if args.input:
        if args.input.lower().endswith(".csv"):
            items = read_csv_products(args.input, parser)
            is_batch = True
        else:
            try:
                with open(args.input, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                parser.error(f"cannot read --input {args.input}: {e}")
            is_batch = isinstance(data, list)
            items = data if is_batch else [data]
        if not items or not all(isinstance(x, dict) for x in items):
            parser.error("--input must hold a JSON object, a list of objects, or a CSV with at least one row")
        products = [from_dict(x, parser, params, f"item {k}" if is_batch else "input")
                    for k, x in enumerate(items, 1)]
    else:
        check(args, parser.error, params)
        products = [args]

    outs = [recommend(a, params) for a in products]
    if args.out_csv:
        write_results_csv(args.out_csv, outs, parser)
    if is_batch:
        print(json.dumps(outs, indent=2) if args.json else ("\n" * 2).join(render(o) for o in outs))
    else:
        print(json.dumps(outs[0], indent=2) if args.json else render(outs[0]))


TEXT_FIELDS = {"name", "category", "strategy", "price_ending"}
LIST_FIELDS = {"competitor_price", "promo_pct"}
FIELDS = {"name": "", "list_price": None, "competitor_price": None, "competitor_age_days": 0.0, "stock": None,
          "daily_demand": None, "stock_age_days": None, "strategy": "balanced", "price_ending": "none",
          "current_price": None, "days_since_change": None, "elasticity": None, "min_margin": None,
          "price_floor_abs": None, "price_ceiling": None, "promo_pct": None, "promo_min_margin_pct": None}


def read_csv_products(path, parser):
    """CSV rows -> dicts. Empty cells are skipped; competitor_price / promo_pct may hold several values separated by ';'."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except OSError as e:
        parser.error(f"cannot read --input {path}: {e}")
    items = []
    for n, row in enumerate(rows, 1):
        d = {}
        for k, v in row.items():
            if k is None or v is None or not v.strip():
                continue
            k, v = k.strip().replace("-", "_"), v.strip()
            if k in TEXT_FIELDS:
                d[k] = v
                continue
            try:
                d[k] = [float(x) for x in v.split(";") if x.strip()] if k in LIST_FIELDS else float(v)
            except ValueError:
                parser.error(f"row {n}: field '{k}' must be a number, got '{v}'")
        items.append(d)
    return items


RESULT_COLS = ["product_name", "category", "unit_cost", "recommended_price", "reason_code", "margin_pct",
               "effective_floor", "ceiling", "min_margin_pct", "guardrails_pass", "confidence", "strategy",
               "flags", "highest_estimated_profit_option", "similar_within_range",
               "promo_status", "promo_reject_reason", "promo_net_price", "promo_net_margin_pct"]


def write_results_csv(path, outs, parser):
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=RESULT_COLS)
            w.writeheader()
            for o in outs:
                p = o["promotion"] or {}
                row = {k: o[k] for k in RESULT_COLS if k in o}
                row["flags"] = ";".join(o["flags"])
                row.update(highest_estimated_profit_option=o["price_options"]["highest_estimated_profit"],
                           similar_within_range=o["similar_products"]["within_range"],
                           promo_status=p.get("status", ""), promo_reject_reason=p.get("reject_reason") or "",
                           promo_net_price=p.get("net_price", ""), promo_net_margin_pct=p.get("net_margin_pct", ""))
                w.writerow(row)
    except OSError as e:
        parser.error(f"cannot write --out-csv {path}: {e}")


def from_dict(d, parser, params, where):
    """Build an argument-like object from a JSON dict (snake_case or kebab-case keys)."""
    d = {k.replace("-", "_"): v for k, v in d.items()}
    unknown = set(d) - set(FIELDS) - {"category", "cost"}
    if unknown:
        parser.error(f"{where}: unknown field(s): {', '.join(sorted(unknown))}")
    vals = dict(FIELDS, **d)
    vals["category"], vals["cost"] = d.get("category"), d.get("cost")
    for k in LIST_FIELDS:
        v = vals[k]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals[k] = [v]
    if vals["price_ending"] is not None and not isinstance(vals["price_ending"], bool):
        vals["price_ending"] = str(vals["price_ending"]).lstrip(".")
    for k, v in vals.items():
        if k in TEXT_FIELDS:
            continue
        items = v if isinstance(v, list) else [v]
        if any(x is not None and (isinstance(x, bool) or not isinstance(x, (int, float))) for x in items):
            parser.error(f"{where}: field '{k}' must be a number")
    ns = argparse.Namespace(**vals)
    ns.cost = None if ns.cost is None else float(ns.cost)
    check(ns, lambda m: parser.error(f"{where}: {m}"), params)
    return ns


def check(a, bad, params):
    if a.category is None:
        bad("category is required")
    if a.category not in params:
        bad(f"invalid category '{a.category}' (choose from {', '.join(sorted(params))})")
    if a.cost is None:
        bad("cost is required")
    if a.cost <= 0:
        bad("cost must be > 0")
    for n in ("list_price", "price_floor_abs", "price_ceiling", "current_price"):
        v = getattr(a, n)
        if v is not None and v <= 0:
            bad(f"{n} must be > 0")
    if a.competitor_price and any(x <= 0 for x in a.competitor_price):
        bad("competitor_price values must be > 0")
    for n in ("competitor_age_days", "stock", "daily_demand", "stock_age_days", "days_since_change"):
        v = getattr(a, n)
        if v is not None and v < 0:
            bad(f"{n} must be >= 0")
    if a.elasticity is not None and a.elasticity >= 0:
        bad("elasticity must be negative (e.g. -1.5)")
    if a.strategy not in STRATEGIES:
        bad(f"strategy must be one of {', '.join(STRATEGIES)}")
    if a.price_ending not in ENDINGS:
        bad(f"price_ending must be one of {', '.join(ENDINGS)}")
    if a.min_margin is not None and not 0 < a.min_margin < 1:
        bad("min_margin must be between 0 and 1 (e.g. 0.2)")
    if a.promo_min_margin_pct is not None and not 0 < a.promo_min_margin_pct < 1:
        bad("promo_min_margin_pct must be between 0 and 1 (e.g. 0.2)")
    if a.promo_pct and any(not 0 < x < 1 for x in a.promo_pct):
        bad("promo_pct values must be between 0 and 1 (e.g. 0.1)")


if __name__ == "__main__":
    main()
