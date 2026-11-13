"""Inventory-clearance bundling: pure, side-effect-free business rules (used by generate.py, validate.py and tests).

All thresholds come from schema.GLOBAL_RULES (exported as rules_config.json). Margin basis is the project-wide one:
margin = (price - cost) / price.
"""
import math
import numpy as np

from schema import GLOBAL_RULES, BUNDLE_STOCK_CLASSES


def ceil_cent(x):
    return math.ceil(x * 100 - 1e-9) / 100


# ------------------------------------------------------------------ Rule 1: inventory age
def classify_age(age_days, rules=GLOBAL_RULES):
    """FRESH 0-30, NORMAL 31-60, SLOW_MOVING 61-90, AGED >90 days (thresholds configurable)."""
    if age_days <= rules["stock_age_fresh_max_days"]:
        return "FRESH"
    if age_days <= rules["stock_age_normal_max_days"]:
        return "NORMAL"
    if age_days <= rules["stock_age_slow_max_days"]:
        return "SLOW_MOVING"
    return "AGED"


def classify_age_vec(age, total_units, rules=GLOBAL_RULES):
    """Vectorised class of the OLDEST lot still in stock; NO_STOCK when nothing is on hand."""
    age = np.asarray(age)
    cls = np.select([age <= rules["stock_age_fresh_max_days"], age <= rules["stock_age_normal_max_days"],
                     age <= rules["stock_age_slow_max_days"]], ["FRESH", "NORMAL", "SLOW_MOVING"], "AGED").astype(object)
    return np.where(np.asarray(total_units) > 0, cls, "NO_STOCK")


def stock_age(lot_q, lot_cum, age_open, d, cso, rules=GLOBAL_RULES):
    """FIFO stock-age profile on day index d.

    lot_q[j, s]   units of lot j (row 0 = opening balance, row j>=1 = receipts of day j-1)
    lot_cum[j, s] cumulative lot units through lot j
    age_open[s]   age (days) of the opening lot on day 0
    cso[s]        cumulative units sold BEFORE the point of measurement (FIFO consumes oldest lots first)
    Returns (oldest_age, slow_units, aged_units, total_units); ages are days since receipt on day d.
    """
    n = d + 2
    rem = np.clip(lot_cum[:n] - np.asarray(cso)[None, :], 0, lot_q[:n])
    ages = np.empty(rem.shape, dtype=np.int64)
    ages[0] = d + np.asarray(age_open)
    ages[1:] = (d - np.arange(d + 1))[:, None]
    aged_m = ages > rules["stock_age_slow_max_days"]
    slow_m = (ages > rules["stock_age_normal_max_days"]) & ~aged_m
    tot = rem.sum(0)
    first = (rem > 0).argmax(0)
    oldest = np.where(tot > 0, ages[first, np.arange(rem.shape[1])], 0)
    return oldest, (rem * slow_m).sum(0), (rem * aged_m).sum(0), tot


def lot_ages(d, age_open_s):
    """Ages (days) on day d of one SKU's lots: opening lot then receipts of days 0..d."""
    return np.concatenate([[d + int(age_open_s)], d - np.arange(d + 1)]).astype(np.int64)


def aged_overlap(lot_qty, ages, pos, qty, rules=GLOBAL_RULES):
    """Units among the next `qty` FIFO units (starting at cumulative position `pos`) that come from lots older than the AGED threshold."""
    lot_qty = np.asarray(lot_qty, dtype=np.int64)
    cum = np.cumsum(lot_qty); start = cum - lot_qty
    ov = np.clip(np.minimum(cum, pos + qty) - np.maximum(start, pos), 0, None)
    return int(ov[np.asarray(ages) > rules["stock_age_slow_max_days"]].sum())


# ------------------------------------------------------------------ Rule 2: high demand
def category_thresholds(demand, cat_idx, live, n_cat, pct):
    """Per-category demand percentile among live SKUs (inf when a category has no live SKU)."""
    thr = np.full(n_cat, np.inf)
    for c in range(n_cat):
        v = demand[live & (cat_idx == c)]
        if len(v):
            thr[c] = np.quantile(v, pct)
    return thr


def is_high_demand(avg_daily_demand, category_threshold, rules=GLOBAL_RULES):
    return avg_daily_demand >= category_threshold and avg_daily_demand >= rules["bundle_min_daily_demand"]


# ------------------------------------------------------------------ Rule 3: compatibility
def is_complementary(primary_category, secondary_category, rules=GLOBAL_RULES):
    return secondary_category in rules["bundle_complement_map"].get(primary_category, [])


def primary_categories_for(secondary_category, rules=GLOBAL_RULES):
    return [p for p, sec in rules["bundle_complement_map"].items() if secondary_category in sec]


def price_ratio_ok(primary_price, secondary_price, rules=GLOBAL_RULES):
    """The aged add-on must not be (much) pricier than the main item."""
    return secondary_price <= rules["bundle_max_secondary_to_primary_price_ratio"] * primary_price + 1e-9


# ------------------------------------------------------------------ Rule 4: availability
def sellable_units(on_hand, rules=GLOBAL_RULES):
    """Units offered to bundles = on_hand minus the protected reserve (reserved/damaged-style safety stock)."""
    return int(math.floor(on_hand * (1 - rules["bundle_stock_reserve_pct"]) + 1e-9))


def max_bundle_units(sell_primary, sell_secondary):
    """A bundle needs one unit of each component: limited by the lower availability."""
    return max(0, min(sell_primary, sell_secondary))


def stock_sufficient(sell_primary, sell_secondary, rules=GLOBAL_RULES):
    m = rules["bundle_min_component_stock"]
    return sell_primary >= m and sell_secondary >= m


# ------------------------------------------------------------------ Rule 5/6: price and profitability
def pick_discount(oldest_age, rules=GLOBAL_RULES):
    """Discount grows with stock age; always inside [bundle_discount_min, bundle_discount_max]."""
    if oldest_age > rules["bundle_very_aged_days"]:
        d = rules["bundle_discount_very_aged"]
    elif oldest_age > rules["stock_age_slow_max_days"]:
        d = rules["bundle_discount_aged"]
    else:
        d = rules["bundle_discount_slow_moving"]
    return min(max(d, rules["bundle_discount_min"]), rules["bundle_discount_max"])


def bundle_price(price_primary, price_secondary, discount):
    """Bundle Price = (A + B) x (1 - discount)."""
    return round((price_primary + price_secondary) * (1 - discount), 2)


def bundle_margin(price, combined_cost):
    """Bundle Margin = (Bundle Price - Combined Cost) / Bundle Price   (fraction; x100 for %)."""
    return (price - combined_cost) / price


def required_margin(min_margin_primary, min_margin_secondary):
    """The stricter of the two components' configured minimum margins."""
    return max(min_margin_primary, min_margin_secondary)


def effective_floor(abs_floor, unit_cost, min_margin):
    """Same guardrail as PriceDecision.effective_floor."""
    return max(abs_floor, ceil_cent(unit_cost / (1 - min_margin)))


def evaluate_bundle(*, component_discontinued, sell_primary, sell_secondary, duplicate_active, price, floor_sum, margin, req_margin,
                    rules=GLOBAL_RULES):
    """Returns None when the bundle is acceptable, else the first failing rejection reason (documented order)."""
    if component_discontinued:
        return "COMPONENT_DISCONTINUED"
    if not stock_sufficient(sell_primary, sell_secondary, rules):
        return "INSUFFICIENT_STOCK"
    if duplicate_active:
        return "DUPLICATE_ACTIVE_BUNDLE"
    if price < floor_sum - 1e-9:
        return "BELOW_PRICE_FLOOR"
    if margin < req_margin - 1e-12:
        return "BELOW_MIN_MARGIN"
    return None


def allocate_price(bundle_price_, price_primary, price_secondary):
    """Split the bundle price over the two Orders lines proportionally to list prices; the parts sum to the bundle price."""
    a = round(bundle_price_ * price_primary / (price_primary + price_secondary), 2)
    return a, round(bundle_price_ - a, 2)


# ------------------------------------------------------------------ Rule 7: lifecycle
def bundle_status(rejection_reason, valid_from, valid_to, as_of, created_on=None):
    """CANCELLED = rejected at creation; DRAFT = created but not yet valid; ACTIVE inside the window; EXPIRED after valid_to (ISO date strings)."""
    if rejection_reason:
        return "CANCELLED"
    if valid_to < as_of:
        return "EXPIRED"
    if valid_from > as_of:
        return "DRAFT"
    return "ACTIVE"


def accepts_sales(rejection_reason, valid_from, valid_to, on_date):
    """Only accepted bundles inside [valid_from, valid_to] may sell - expired/cancelled/draft ones cannot."""
    return (not rejection_reason) and valid_from <= on_date <= valid_to
