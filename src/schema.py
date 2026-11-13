"""Single source of truth: data dictionary, enums, keys, DDL. Used by generator and validator."""
import json

CATEGORIES = ["Electronics", "Home & Kitchen", "Grocery", "Apparel", "Beauty", "Sports", "Toys", "Office"]
REASONS = ["COMP_MATCH_DOWN", "COMP_RAISE", "HOLD_IN_COMP_BAND", "LOW_STOCK_MARKUP", "OVERSTOCK_MARKDOWN",
           "COST_PASS_THROUGH", "GRADIENT_RECOVERY", "FLOOR_REPAIR", "CEILING_REPAIR", "HOLD_STALE_COMPETITOR", "HOLD_NO_SIGNAL"]
COMP_REASONS = ["COMP_MATCH_DOWN", "COMP_RAISE", "HOLD_IN_COMP_BAND"]  # reasons that rely on a competitor price
CHANGE_REASONS = REASONS + ["PROMO_APPLIED", "PROMO_ENDED", "PROMO_CHANGED",
                            "MANUAL_OVERRIDE", "PRICE_MATCH_STORE", "ERROR_CORRECTION"]
REJECT_REASONS = ["MIN_STOCK", "EXCLUSIVE_WITH_OTHER", "SAME_GROUP", "CONFLICT_PAIR", "MAX_STACK",
                  "MAX_TOTAL_DISCOUNT", "FLOOR_GUARDRAIL", "MARGIN_GUARDRAIL"]
STACK_REASONS = ["EXCLUSIVE_WITH_OTHER", "SAME_GROUP", "CONFLICT_PAIR", "MAX_STACK", "MAX_TOTAL_DISCOUNT"]
STACK_GROUPS = ["SEASONAL", "CLEARANCE", "BRAND", "LOYALTY", "COUPON"]
PROMO_STATUS = ["DRAFT", "SCHEDULED", "ACTIVE", "ENDED", "CANCELLED"]
PROMO_TRANSITIONS = {None: ["DRAFT"], "DRAFT": ["SCHEDULED"], "SCHEDULED": ["ACTIVE", "CANCELLED"],
                     "ACTIVE": ["ENDED"], "ENDED": [], "CANCELLED": []}
PRICE_EVENTS = ["CARRY_FORWARD", "DECISION_CHANGE", "PROMO_CHANGE", "DECISION_HOLD", "MANUAL_CHANGE"]
COMPETITORS = ["COMP-A", "COMP-B", "COMP-C", "COMP-D"]
STOCK_AGE_CLASSES = ["FRESH", "NORMAL", "SLOW_MOVING", "AGED"]
BUNDLE_STOCK_CLASSES = STOCK_AGE_CLASSES + ["NO_STOCK"]
BUNDLE_STATUS = ["DRAFT", "ACTIVE", "EXPIRED", "CANCELLED"]
BUNDLE_REJECT_REASONS = ["COMPONENT_DISCONTINUED", "INSUFFICIENT_STOCK", "DUPLICATE_ACTIVE_BUNDLE", "BELOW_PRICE_FLOOR", "BELOW_MIN_MARGIN"]

# Global (non-promo-specific) stacking / guardrail rules, exported as rules_config.json
GLOBAL_RULES = {
    "max_promos_stacked": 2,
    "max_total_discount_pct_of_base": 0.35,
    "one_promo_per_stack_group": True,
    "competitor_staleness_threshold_days": 7.0,
    "decision_timestamp_local": "06:00:00",
    "margin_definition": "(net_price - unit_cost) / net_price, net_price = base_price - all promo discounts",
    "effective_floor": "max(price_floor_abs, ceil_to_cent(unit_cost / (1 - min_margin_pct)))",
    "effective_ceiling": "max(price_ceiling, effective_floor)",
    "max_step_change_pct_per_decision": 0.10,
    "promo_application_order": "sorted by descending discount pct-equivalent then promo_id; percent applied sequentially, fixed amount subtracted",
    "stale_definition": "decision_ts - observed_at > 7 days",
    "gradient_history_years": 5,
    "gradient_anchor_date": "2025-07-01",
    "gradient_definition": "yoy_price_pct(y) = ref_price(y)/ref_price(y-1) - 1 over 2021..2025; price_cagr_5y = (ref_price(2025)/ref_price(2020))^(1/5) - 1",
    "gradient_ref_price": "last_ref_price * (1 + price_cagr_5y) ^ ((decision_date - anchor_date)/365.25)",
    "gradient_ceiling": "last_ref_price * (1 + max_yoy_price_pct + gradient_ceiling_tolerance)",
    "gradient_ceiling_tolerance": 0.03,
    "gradient_ceiling_applies": "applied ceiling = max(min(price_ceiling, gradient_ceiling), effective_floor) - the margin floor always wins",
    "gradient_recovery_band": 0.03,
    "gradient_recovery": "with no competitor/stock signal (or inside the competitor band), if base < gradient_ref_price*(1-band) move toward min(gradient_ref_price, the competitor price)",
    "cost_gradient": "monthly cost drift mean = cost_cagr_5y / (12 * 0.30)",
    # ---- inventory age (FIFO lots) and inventory-clearance bundles (all configurable)
    "stock_age_fresh_max_days": 30,
    "stock_age_normal_max_days": 60,
    "stock_age_slow_max_days": 90,
    "stock_age_definition": "FIFO: sales consume the oldest lot first; age = days since lot receipt. FRESH 0-30, NORMAL 31-60, SLOW_MOVING 61-90, AGED >90; a SKU's class is the class of its oldest lot still in stock",
    "bundle_review_min_history_days": 7,
    "bundle_review_cadence": "weekly review days (day index % 7 == 0) with at least bundle_review_min_history_days of demand history; bundles are valid from the next day",
    "bundle_eligible_secondary_classes": ["SLOW_MOVING", "AGED"],
    "bundle_min_secondary_aged_units": 5,
    "bundle_high_demand_percentile": 0.75,
    "bundle_min_daily_demand": 0.5,
    "bundle_high_demand_definition": "mean demand_units of the previous min(30, day) days >= the category percentile among live SKUs, and >= bundle_min_daily_demand",
    "bundle_complement_map": {"Electronics": ["Office"], "Home & Kitchen": ["Grocery"], "Grocery": ["Home & Kitchen"],
                              "Apparel": ["Sports", "Beauty"], "Sports": ["Apparel"], "Beauty": ["Apparel"],
                              "Toys": ["Office"], "Office": ["Electronics"]},
    "bundle_complement_map_meaning": "primary (high-demand) category -> categories whose aged stock may be attached to it",
    "bundle_max_secondary_to_primary_price_ratio": 1.25,
    "bundle_min_component_stock": 10,
    "bundle_stock_reserve_pct": 0.10,
    "bundle_sellable_definition": "sellable = floor(on_hand_units x (1 - bundle_stock_reserve_pct)); the reserve is protected for regular sales; both components need >= bundle_min_component_stock",
    "bundle_discount_min": 0.05,
    "bundle_discount_max": 0.15,
    "bundle_discount_slow_moving": 0.08,
    "bundle_discount_aged": 0.12,
    "bundle_discount_very_aged": 0.15,
    "bundle_very_aged_days": 120,
    "bundle_price": "(primary_unit_price + secondary_unit_price) x (1 - bundle_discount_pct), unit price = base_price on the review day",
    "bundle_margin_definition": "(bundle_price - combined_cost) / bundle_price, combined_cost = unit costs of both SKUs in the valid_from month",
    "bundle_required_margin": "max(min_margin_pct of primary, min_margin_pct of secondary)",
    "bundle_floor_rule": "bundle_price >= effective_floor(primary) + effective_floor(secondary) (same floor as single-SKU price decisions)",
    "bundle_validity_days": 14,
    "bundle_review_cap_pct_of_skus": 0.03,
    "bundle_max_per_primary_per_review": 3,
    "bundle_rejection_order": "COMPONENT_DISCONTINUED, INSUFFICIENT_STOCK, DUPLICATE_ACTIVE_BUNDLE, BELOW_PRICE_FLOOR, BELOW_MIN_MARGIN",
    "bundle_promotion_interaction": "bundle sales are a separate offer priced from base_price; they do not stack with promotions and never change PriceHistory / PriceDecision of either SKU",
}


def f(name, typ, req, allowed="", unit="", uniq="", rule=""):
    return dict(name=name, type=typ, required=req, allowed=allowed, unit=unit, unique=uniq, rule=rule)


R, O = "R", "O"
ENTITIES = {
    "Product": dict(file="product.csv", table="Product", pk=["sku"], fks=[],
        desc="Master SKU. 1:N CostRecord, PriceHistory, InventorySnapshot, CompetitorObservation, Orders, PriceDecision; N:M Promotion via PromotionProduct.",
        fields=[
            f("sku", "string", R, "SKU-000001..", "", "PK", "regex ^SKU-\\d{6}$, immutable"),
            f("product_name", "string", R),
            f("category", "string", R, CATEGORIES),
            f("brand", "string", R),
            f("uom", "string", R, ["EA"]),
            f("currency", "string", R, ["USD"]),
            f("launch_date", "date", R, "", "", "", "< first price_date"),
            f("status", "string", R, ["ACTIVE", "DISCONTINUED"], "", "", "lifecycle ACTIVE -> DISCONTINUED (terminal)"),
            f("discontinued_date", "date", O, "", "", "", "required iff status=DISCONTINUED; first inactive day, no price/inventory/order rows on/after it"),
            f("list_price", "decimal", R, ">0", "USD", "", "opening base price on first day; <= price_ceiling"),
            f("price_floor_abs", "decimal", R, ">0", "USD", "", "absolute floor = 1.05 x opening unit cost"),
            f("price_ceiling", "decimal", R, ">0", "USD", "", ">= list_price (1.30 x list)"),
            f("min_margin_pct", "decimal", R, "0.05..0.40", "fraction of net price", "", "margin on NET price after all discounts"),
            f("lead_time_days", "int", R, "3..30", "days"),
        ]),
    "AnnualPriceHistory": dict(file="annual_price_history.csv", table="AnnualPriceHistory", pk=["aph_id"], fks=[("sku", "Product", "sku")],
        desc="Five years (2021-2025) of annual reference price/cost per SKU with year-over-year % change. Product 1:N (exactly 5 rows).",
        fields=[
            f("aph_id", "string", R, "", "", "PK", "APH-<sku>-YYYY"),
            f("sku", "string", R, "", "", "", "FK Product.sku"),
            f("year", "int", R, "2021..2025", "", "unique with sku", "5 consecutive years ending the year before the window"),
            f("ref_price", "decimal", R, ">0", "USD", "", "annual average selling price (anchored mid-year)"),
            f("prev_year_price", "decimal", R, ">0", "USD", "", "= previous year's ref_price (2020 base for 2021)"),
            f("yoy_price_pct", "decimal", R, "", "fraction", "", "derived: ref_price/prev_year_price - 1"),
            f("ref_cost", "decimal", R, ">0", "USD", "", "annual average unit cost"),
            f("prev_year_cost", "decimal", R, ">0", "USD"),
            f("yoy_cost_pct", "decimal", R, "", "fraction", "", "derived: ref_cost/prev_year_cost - 1"),
        ]),
    "PriceGradient": dict(file="price_gradient.csv", table="PriceGradient", pk=["sku"], fks=[("sku", "Product", "sku")],
        desc="Derived per-SKU gradient of the 5-year history (1:1 with Product). Recomputable from AnnualPriceHistory.",
        fields=[
            f("sku", "string", R, "", "", "PK", "FK Product.sku"),
            f("basis_start_year", "int", R, [2021]),
            f("basis_end_year", "int", R, [2025]),
            f("years_of_history", "int", R, [5]),
            f("avg_yoy_price_pct", "decimal", R, "", "fraction", "", "mean of the 5 yoy_price_pct"),
            f("price_cagr_5y", "decimal", R, "", "fraction/yr", "", "(ref_price 2025 / prev_year_price 2021)^(1/5) - 1"),
            f("max_yoy_price_pct", "decimal", R, "", "fraction"),
            f("min_yoy_price_pct", "decimal", R, "", "fraction"),
            f("yoy_price_stdev", "decimal", R, ">=0", "fraction", "", "sample stdev (n-1)"),
            f("cost_cagr_5y", "decimal", R, "", "fraction/yr"),
            f("last_ref_price", "decimal", R, ">0", "USD", "", "= ref_price of 2025"),
            f("gradient_ceiling", "decimal", R, ">0", "USD", "", "last_ref_price*(1+max_yoy_price_pct+0.03)"),
        ]),
    "CostRecord": dict(file="cost_record.csv", table="CostRecord", pk=["cost_id"], fks=[("sku", "Product", "sku")],
        desc="One row per SKU per calendar month (append-only history of unit cost). Product 1:N CostRecord; (sku, cost_month) unique.",
        fields=[
            f("cost_id", "string", R, "", "", "PK", "COST-<sku>-YYYY-MM"),
            f("sku", "string", R, "", "", "", "FK Product.sku"),
            f("cost_month", "string", R, "YYYY-MM", "", "unique with sku"),
            f("effective_from", "date", R, "", "", "", "first day of month"),
            f("effective_to", "date", R, "", "", "", "last day of month; >= effective_from; no overlap per sku"),
            f("unit_cost", "decimal", R, ">0", "USD"),
            f("prev_unit_cost", "decimal", O, "", "USD", "", "null for first month"),
            f("cost_change_pct", "decimal", O, "", "fraction", "", "derived: unit_cost/prev_unit_cost-1"),
            f("cost_change_reason", "string", R, ["INITIAL", "NO_CHANGE", "SUPPLIER_INCREASE", "FX_ADJUSTMENT", "FREIGHT_SURCHARGE",
                                                   "NEGOTIATED_REDUCTION", "VOLUME_REBATE"]),
        ]),
    "PriceHistory": dict(file="price_history.csv", table="PriceHistory", pk=["price_id"],
        fks=[("sku", "Product", "sku"), ("decision_id", "PriceDecision", "decision_id")],
        desc="Daily price ledger (one row per active SKU-day, never overwritten). Product 1:N PriceHistory; PriceDecision 1:N PriceHistory (governing decision).",
        fields=[
            f("price_id", "string", R, "", "", "PK", "PRC-<sku>-YYYYMMDD"),
            f("sku", "string", R, "", "", "", "FK Product.sku"),
            f("price_date", "date", R, "", "", "unique with sku", "contiguous per sku within active period"),
            f("base_price", "decimal", R, ">0", "USD"),
            f("promo_discount_amt", "decimal", R, ">=0", "USD", "", "total of applied promo discounts"),
            f("net_price", "decimal", R, ">0", "USD", "", "= base_price - promo_discount_amt"),
            f("applied_promo_ids", "string", O, "", "", "", "pipe-separated Promotion ids; empty if none"),
            f("price_event", "string", R, PRICE_EVENTS),
            f("change_reason_code", "string", O, CHANGE_REASONS, "", "", "required whenever price_event in DECISION_CHANGE/PROMO_CHANGE/MANUAL_CHANGE"),
            f("decision_id", "string", O, "", "", "", "FK PriceDecision.decision_id (governing decision)"),
        ]),
    "CompetitorObservation": dict(file="competitor_observation.csv", table="CompetitorObservation", pk=["obs_id"],
        fks=[("sku", "Product", "sku")],
        desc="Competitor price snapshots with source timestamp (observed_at) and ingestion timestamp (captured_at). Product 1:N.",
        fields=[
            f("obs_id", "string", R, "", "", "PK", "COBS-2026-000001, ordered by captured_at"),
            f("sku", "string", R, "", "", "", "FK Product.sku"),
            f("competitor_id", "string", R, COMPETITORS),
            f("observed_at", "datetime", R, "", "", "unique with sku+competitor", "source timestamp"),
            f("captured_at", "datetime", R, "", "", "", ">= observed_at"),
            f("competitor_price", "decimal", R, ">0", "USD"),
            f("in_stock", "bool", R, [0, 1]),
            f("source", "string", R, ["SCRAPE_FEED", "PARTNER_API", "MANUAL_CHECK"]),
            f("source_lag_hours", "decimal", R, ">=0", "hours", "", "derived: captured_at - observed_at"),
        ]),
    "InventorySnapshot": dict(file="inventory_snapshot.csv", table="InventorySnapshot", pk=["snapshot_id"],
        fks=[("sku", "Product", "sku")],
        desc="Daily end-of-day stock and demand signal per active SKU. Product 1:N.",
        fields=[
            f("snapshot_id", "string", R, "", "", "PK", "INV-<sku>-YYYYMMDD"),
            f("sku", "string", R, "", "", "", "FK Product.sku"),
            f("snapshot_date", "date", R, "", "", "unique with sku"),
            f("opening_on_hand", "int", R, ">=0", "units", "", "= previous closing_on_hand"),
            f("units_received", "int", R, ">=0", "units"),
            f("demand_units", "int", R, ">=0", "units", "", "customer demand incl. unmet"),
            f("units_sold", "int", R, ">=0", "units", "", "= min(opening+received, demand); = sum(Orders.quantity) that day"),
            f("lost_sales_units", "int", R, ">=0", "units", "", "derived: demand_units - units_sold"),
            f("closing_on_hand", "int", R, ">=0", "units", "", "derived: opening + received - sold"),
            f("on_order_units", "int", R, ">=0", "units", "", "open replenishment quantity at end of day"),
            f("stockout_flag", "int", R, [0, 1], "", "", "derived: closing_on_hand = 0"),
            f("avg_demand_7d", "decimal", R, ">=0", "units/day", "", "derived: trailing 7-day mean of demand_units (min periods 1)"),
            f("days_of_cover", "decimal", R, "0..999", "days", "", "derived: closing_on_hand / max(avg_demand_7d,0.05), capped"),
            f("oldest_stock_age_days", "int", R, ">=0", "days", "", "derived (FIFO over InventoryLot): age on snapshot_date of the oldest lot still in stock; 0 when no stock"),
            f("slow_moving_units", "int", R, ">=0", "units", "", "derived: closing units in lots aged 61-90 days"),
            f("aged_units", "int", R, ">=0", "units", "", "derived: closing units in lots older than 90 days"),
            f("stock_age_class", "string", R, BUNDLE_STOCK_CLASSES, "", "", "derived: class of oldest_stock_age_days (NO_STOCK when closing_on_hand = 0)"),
        ]),
    "InventoryLot": dict(file="inventory_lot.csv", table="InventoryLot", pk=["lot_id"], fks=[("sku", "Product", "sku")],
        desc="Stock receipt lots (opening balance + every replenishment receipt) used for FIFO inventory age. Product 1:N. Sales consume the oldest lot first.",
        fields=[
            f("lot_id", "string", R, "", "", "PK", "LOT-<sku>-YYYYMMDD (receipt date; opening lot is dated before the window)"),
            f("sku", "string", R, "", "", "unique with received_date", "FK Product.sku"),
            f("received_date", "date", R, "", "", "", "unique per sku; replenishment lots = InventorySnapshot.units_received days"),
            f("received_units", "int", R, ">=1", "units", "", "replenishment lots: = InventorySnapshot.units_received that day"),
            f("source", "string", R, ["OPENING_BALANCE", "REPLENISHMENT"]),
            f("unit_cost", "decimal", R, ">0", "USD", "", "CostRecord unit cost in the receipt month (opening lot: first window month)"),
            f("remaining_units", "int", R, ">=0", "units", "", "derived: FIFO units still in stock on the SKU's last active day"),
            f("lot_status", "string", R, ["OPEN", "DEPLETED"], "", "", "OPEN iff remaining_units > 0"),
        ]),
    "Promotion": dict(file="promotion.csv", table="Promotion", pk=["promo_id"], fks=[],
        desc="Promotion/coupon header. N:M with Product via PromotionProduct; N:M with itself via PromotionExclusion; 1:N PromotionRule, PromotionEvent.",
        fields=[
            f("promo_id", "string", R, "", "", "PK", "PROMO-2026-000001"),
            f("promo_name", "string", R),
            f("promo_type", "string", R, ["PCT_OFF", "FIXED_OFF", "COUPON"]),
            f("stack_group", "string", R, STACK_GROUPS, "", "", "COUPON type must be group COUPON"),
            f("discount_pct", "decimal", O, "0.01..0.50", "fraction of current price", "", "required for PCT_OFF/COUPON"),
            f("discount_amt", "decimal", O, ">0", "USD", "", "required for FIXED_OFF"),
            f("coupon_code", "string", O, "", "", "unique when present", "required for COUPON"),
            f("scope_category", "string", R, CATEGORIES),
            f("start_date", "date", R, "", "", "", "aligned to review-week boundaries"),
            f("end_date", "date", R, "", "", "", ">= start_date; multiple of 7 days long"),
            f("created_date", "date", R, "", "", "", "< start_date"),
            f("status", "string", R, PROMO_STATUS, "", "", "status as of as_of date; derived from last PromotionEvent"),
        ]),
    "PromotionRule": dict(file="promotion_rule.csv", table="PromotionRule", pk=["rule_id"], fks=[("promo_id", "Promotion", "promo_id")],
        desc="Promotion-specific eligibility/stacking rules. Promotion 1:N (>=1). Global rules are in rules_config.json.",
        fields=[
            f("rule_id", "string", R, "", "", "PK", "PRULE-2026-000001"),
            f("promo_id", "string", R, "", "", "", "FK Promotion.promo_id"),
            f("rule_type", "string", R, ["MIN_STOCK_UNITS", "EXCLUSIVE", "MIN_MARGIN_PCT"]),
            f("rule_value", "decimal", R, "", "units | flag(1) | fraction", "", "MIN_STOCK_UNITS: on_hand >= value; EXCLUSIVE: cannot combine; MIN_MARGIN_PCT: net margin >= value"),
        ]),
    "PromotionProduct": dict(file="promotion_product.csv", table="PromotionProduct", pk=["promo_id", "sku"],
        fks=[("promo_id", "Promotion", "promo_id"), ("sku", "Product", "sku")],
        desc="Bridge for N:M Promotion <-> Product (eligible assortment).",
        fields=[
            f("promo_id", "string", R, "", "", "PK part", "FK Promotion"),
            f("sku", "string", R, "", "", "PK part", "FK Product"),
            f("added_date", "date", R, "", "", "", "= Promotion.created_date"),
        ]),
    "PromotionExclusion": dict(file="promotion_exclusion.csv", table="PromotionExclusion", pk=["promo_id_a", "promo_id_b"],
        fks=[("promo_id_a", "Promotion", "promo_id"), ("promo_id_b", "Promotion", "promo_id")],
        desc="Bridge for N:M Promotion <-> Promotion explicit conflicts (e.g. conflicting coupons). Symmetric; stored once with a<b.",
        fields=[
            f("promo_id_a", "string", R, "", "", "PK part", "FK Promotion; a < b"),
            f("promo_id_b", "string", R, "", "", "PK part", "FK Promotion"),
            f("exclusion_reason", "string", R, ["CONFLICTING_COUPON"]),
        ]),
    "PromotionEvent": dict(file="promotion_event.csv", table="PromotionEvent", pk=["event_id"], fks=[("promo_id", "Promotion", "promo_id")],
        desc="Append-only lifecycle history. Promotion 1:N. DRAFT->SCHEDULED->ACTIVE->ENDED or SCHEDULED->CANCELLED.",
        fields=[
            f("event_id", "string", R, "", "", "PK", "PEVT-<promo_id>-NN"),
            f("promo_id", "string", R, "", "", "", "FK Promotion"),
            f("event_seq", "int", R, ">=1", "", "unique with promo_id"),
            f("event_date", "date", R, "", "", "", "non-decreasing in event_seq; <= as_of"),
            f("from_status", "string", O, PROMO_STATUS),
            f("to_status", "string", R, PROMO_STATUS, "", "", "must be an allowed transition"),
        ]),
    "Orders": dict(file="orders.csv", table="Orders", pk=["order_id"],
        fks=[("sku", "Product", "sku"), ("price_id", "PriceHistory", "price_id"), ("decision_id", "PriceDecision", "decision_id"),
             ("bundle_order_id", "BundleOrder", "bundle_order_id")],
        desc="Fulfilled order lines per SKU-day-channel. Product 1:N; PriceHistory 1:N; every line priced from the PriceHistory row of its day.",
        fields=[
            f("order_id", "string", R, "", "", "PK", "ORD-2026-000001"),
            f("order_date", "date", R),
            f("sku", "string", R, "", "", "", "FK Product"),
            f("price_id", "string", R, "", "", "", "FK PriceHistory; = PRC-<sku>-<order_date>"),
            f("decision_id", "string", O, "", "", "", "FK PriceDecision; = PriceHistory.decision_id"),
            f("channel", "string", R, ["WEB", "STORE", "MARKETPLACE"]),
            f("customer_segment", "string", R, ["CONSUMER", "BUSINESS", "LOYALTY_MEMBER"]),
            f("quantity", "int", R, ">=1", "units"),
            f("unit_base_price", "decimal", R, ">0", "USD", "", "= PriceHistory.base_price"),
            f("unit_net_price", "decimal", R, ">0", "USD", "", "= PriceHistory.net_price"),
            f("unit_cost", "decimal", R, ">0", "USD", "", "= CostRecord.unit_cost of the order month"),
            f("line_total", "decimal", R, ">0", "USD", "", "derived: quantity * unit_net_price"),
            f("order_status", "string", R, ["FULFILLED"], "", "", "only fulfilled lines are generated (reconcile to units_sold)"),
            f("bundle_order_id", "string", O, "", "", "", "FK BundleOrder; set on the two component lines (one per SKU) of a bundle sale, else empty. Bundle lines: unit_net_price = allocated bundle price, not PriceHistory.net_price"),
        ]),
    "ProductBundle": dict(file="product_bundle.csv", table="ProductBundle", pk=["bundle_id"],
        fks=[("primary_sku", "Product", "sku"), ("secondary_sku", "Product", "sku")],
        desc="Inventory-clearance bundle: one high-demand (primary) SKU + one aged/slow-moving complementary (secondary) SKU. Every evaluated candidate is stored; rejected ones have status CANCELLED and a rejection_reason (audit trail). Product 1:N (twice); 1:N BundleOrder.",
        fields=[
            f("bundle_id", "string", R, "", "", "PK", "BNDL-2026-000001, chronological"),
            f("primary_sku", "string", R, "", "", "", "FK Product.sku; high-demand component"),
            f("secondary_sku", "string", R, "", "", "", "FK Product.sku; slow-moving/aged component; != primary_sku; at most one accepted bundle per pair at a time"),
            f("bundle_discount_pct", "decimal", R, "0.05..0.15", "fraction", "", "configurable; grows with secondary stock age"),
            f("primary_unit_price", "decimal", R, ">0", "USD", "", "= PriceHistory.base_price of primary on created_at date"),
            f("secondary_unit_price", "decimal", R, ">0", "USD", "", "= PriceHistory.base_price of secondary on created_at date"),
            f("individual_total_price", "decimal", R, ">0", "USD", "", "derived: primary_unit_price + secondary_unit_price"),
            f("bundle_price", "decimal", R, ">0", "USD", "", "derived: round(individual_total_price x (1 - bundle_discount_pct), 2)"),
            f("combined_cost", "decimal", R, ">0", "USD", "", "derived: unit costs of both SKUs in the valid_from month (CostRecord)"),
            f("bundle_margin_pct", "decimal", R, "", "fraction of bundle price", "", "derived: (bundle_price - combined_cost) / bundle_price"),
            f("required_margin_pct", "decimal", R, "", "fraction", "", "max(Product.min_margin_pct of both components)"),
            f("valid_from", "date", R, "", "", "", "day after created_at"),
            f("valid_to", "date", R, "", "", "", ">= valid_from; <= valid_from + validity - 1; <= last active day of both SKUs"),
            f("bundle_status", "string", R, BUNDLE_STATUS, "", "", "CANCELLED iff rejection_reason set; else EXPIRED if valid_to < as_of, DRAFT if valid_from > as_of, else ACTIVE"),
            f("rejection_reason", "string", O, BUNDLE_REJECT_REASONS, "", "", "first failing rule in documented order; empty when accepted"),
            f("created_at", "datetime", R, "", "", "", "review date 06:00:00"),
            f("primary_avg_demand_30d", "decimal", R, ">=0", "units/day", "", "derived: mean InventorySnapshot.demand_units of the previous min(30, day) days"),
            f("primary_demand_threshold", "decimal", R, ">=0", "units/day", "", "category percentile of that metric among live SKUs on created_at date"),
            f("primary_sellable_units", "int", R, ">=0", "units", "", "derived: floor(on_hand_units x (1 - reserve)); on_hand = opening + received on created_at date"),
            f("secondary_sellable_units", "int", R, ">=0", "units", "", "derived: same for the secondary SKU"),
            f("max_bundle_units", "int", R, ">=0", "bundles", "", "derived: min(primary_sellable_units, secondary_sellable_units); cap on bundles sold"),
            f("secondary_oldest_age_days", "int", R, ">=0", "days", "", "derived (FIFO replay): age of the oldest lot of the secondary at created_at"),
            f("secondary_stock_age_class", "string", R, BUNDLE_STOCK_CLASSES),
            f("secondary_slow_units", "int", R, ">=0", "units", "", "derived: secondary units in lots aged 61-90 days at created_at"),
            f("secondary_aged_units", "int", R, ">=0", "units", "", "derived: secondary units in lots older than 90 days at created_at"),
        ]),
    "BundleOrder": dict(file="bundle_order.csv", table="BundleOrder", pk=["bundle_order_id"],
        fks=[("bundle_id", "ProductBundle", "bundle_id"), ("order_id", "Orders", "order_id"), ("secondary_order_id", "Orders", "order_id")],
        desc="Bundle sales: one row per bundle per day. Each row has exactly two Orders lines (primary and secondary SKU) with the same quantity, so both SKUs' units_sold / InventorySnapshot move. ProductBundle 1:N; Orders 1:2.",
        fields=[
            f("bundle_order_id", "string", R, "", "", "PK", "BORD-2026-000001"),
            f("bundle_id", "string", R, "", "", "", "FK ProductBundle; bundle must be accepted and order_date within [valid_from, valid_to]"),
            f("order_id", "string", R, "", "", "", "FK Orders: line of the primary SKU"),
            f("secondary_order_id", "string", R, "", "", "", "FK Orders: line of the secondary SKU"),
            f("order_date", "date", R),
            f("channel", "string", R, ["WEB", "STORE", "MARKETPLACE"]),
            f("quantity", "int", R, ">=1", "bundles", "", "units of EACH component; cumulative per bundle <= max_bundle_units"),
            f("bundle_selling_price", "decimal", R, ">0", "USD", "", "= ProductBundle.bundle_price"),
            f("total_revenue", "decimal", R, ">0", "USD", "", "derived: quantity x bundle_selling_price"),
            f("total_cost", "decimal", R, ">0", "USD", "", "derived: quantity x (unit_cost primary + unit_cost secondary) of the order month"),
            f("gross_profit", "decimal", R, "", "USD", "", "derived: total_revenue - total_cost"),
            f("aged_units_cleared", "int", R, ">=0", "units", "", "derived (FIFO replay): secondary units of this sale taken from lots older than 90 days"),
        ]),
    "PriceDecision": dict(file="price_decision.csv", table="PriceDecision", pk=["decision_id"],
        fks=[("sku", "Product", "sku"), ("cost_id", "CostRecord", "cost_id"), ("competitor_obs_id", "CompetitorObservation", "obs_id")],
        desc="Stored decision inputs and outcomes. Product 1:N; N:M Promotion via DecisionPromotion. Weekly review plus off-cycle COST_CHANGE reviews.",
        fields=[
            f("decision_id", "string", R, "", "", "PK", "DEC-2026-000001 chronological"),
            f("sku", "string", R, "", "", "", "FK Product"),
            f("decision_date", "date", R),
            f("decided_at", "datetime", R, "", "", "", "decision_date 06:00:00"),
            f("trigger", "string", R, ["WEEKLY_REVIEW", "COST_CHANGE"]),
            f("valid_from", "date", R, "", "", "", "= decision_date"),
            f("valid_to", "date", R, "", "", "", ">= valid_from; day before next weekly review or window end"),
            f("cost_id", "string", R, "", "", "", "FK CostRecord covering decision_date"),
            f("unit_cost", "decimal", R, ">0", "USD", "", "= CostRecord.unit_cost"),
            f("price_before", "decimal", R, ">0", "USD", "", "base price in force before decision"),
            f("on_hand_units", "int", R, ">=0", "units", "", "stock at decision time (opening + receipts of the day)"),
            f("avg_daily_demand_7d", "decimal", R, ">=0", "units/day"),
            f("days_of_cover", "decimal", R, "0..999", "days"),
            f("competitor_obs_id", "string", O, "", "", "", "FK CompetitorObservation considered (fresh min, else freshest stale)"),
            f("competitor_price", "decimal", O, ">0", "USD", "", "= obs.competitor_price"),
            f("competitor_obs_age_days", "decimal", O, ">=0", "days", "", "derived: (decided_at - observed_at)/24h"),
            f("effective_floor", "decimal", R, ">0", "USD", "", "max(price_floor_abs, ceil_cent(unit_cost/(1-min_margin_pct)))"),
            f("price_ceiling", "decimal", R, ">0", "USD", "", "static ceiling = max(Product.price_ceiling, effective_floor)"),
            f("gradient_ref_price", "decimal", R, ">0", "USD", "", "expected price from 5-yr gradient at decision date"),
            f("gradient_ceiling", "decimal", R, ">0", "USD", "", "= PriceGradient.gradient_ceiling; applied ceiling = max(min(price_ceiling, gradient_ceiling), effective_floor)"),
            f("min_margin_pct", "decimal", R, "", "fraction", "", "= Product.min_margin_pct"),
            f("candidate_base_price", "decimal", R, ">0", "USD", "", "policy target before step-limit and guardrails"),
            f("base_price", "decimal", R, ">0", "USD", "", "chosen list/base price"),
            f("promo_discount_amt", "decimal", R, ">=0", "USD", "", "sum of DecisionPromotion.discount_amt where APPLIED"),
            f("net_price", "decimal", R, ">0", "USD", "", "= base_price - promo_discount_amt"),
            f("margin_pct", "decimal", R, "", "fraction of net price", "", "(net_price - unit_cost)/net_price"),
            f("guardrail_flags", "string", O, "STEP_LIMITED|FLOOR_CLAMPED|CEILING_CLAMPED|GRADIENT_CAPPED", "", "", "pipe-separated"),
            f("reason_code", "string", R, REASONS),
            f("outcome", "string", R, ["PRICE_CHANGED", "PRICE_HELD"], "", "", "PRICE_CHANGED iff base_price != price_before"),
        ]),
    "DecisionPromotion": dict(file="decision_promotion.csv", table="DecisionPromotion", pk=["decision_id", "promo_id"],
        fks=[("decision_id", "PriceDecision", "decision_id"), ("promo_id", "Promotion", "promo_id")],
        desc="Bridge N:M PriceDecision <-> Promotion: every candidate promotion evaluated, with status and reason (eligibility is reproducible from these + rules).",
        fields=[
            f("decision_id", "string", R, "", "", "PK part", "FK PriceDecision"),
            f("promo_id", "string", R, "", "", "PK part", "FK Promotion"),
            f("evaluation_status", "string", R, ["APPLIED", "REJECTED"]),
            f("rejection_reason", "string", O, REJECT_REASONS, "", "", "required iff REJECTED"),
            f("apply_sequence", "int", O, ">=1", "", "", "required iff APPLIED"),
            f("discount_amt", "decimal", R, ">=0", "USD", "", "0 when rejected"),
        ]),
}
ORDER = ["Product", "AnnualPriceHistory", "PriceGradient", "CostRecord", "Promotion", "PromotionRule", "PromotionProduct", "PromotionExclusion", "PromotionEvent",
         "CompetitorObservation", "InventoryLot", "InventorySnapshot", "PriceDecision", "PriceHistory", "ProductBundle", "Orders", "BundleOrder", "DecisionPromotion"]
DEFERRED_FKS = {("BundleOrder", "order_id"), ("BundleOrder", "secondary_order_id"), ("Orders", "bundle_order_id")}  # Orders <-> BundleOrder cycle

SQLT = {"string": "TEXT", "date": "TEXT", "datetime": "TEXT", "int": "INTEGER", "bool": "INTEGER", "decimal": "REAL"}


def ddl():
    out = []
    for name in ORDER:
        e = ENTITIES[name]
        cols = [f'  {x["name"]} {SQLT[x["type"]]}{" NOT NULL" if x["required"] == "R" else ""}' for x in e["fields"]]
        cols.append(f'  PRIMARY KEY ({", ".join(e["pk"])})')
        for c, rt, rc in e["fks"]:
            cols.append(f"  FOREIGN KEY ({c}) REFERENCES {rt}({rc})" + (" DEFERRABLE INITIALLY DEFERRED" if (name, c) in DEFERRED_FKS else ""))
        out.append(f'CREATE TABLE {e["table"]} (\n' + ",\n".join(cols) + "\n);")
    return "\n\n".join(out) + "\n"


def dictionary_json():
    return json.dumps({k: dict(file=v["file"], primary_key=v["pk"], foreign_keys=[dict(column=c, references=f"{t}.{r}") for c, t, r in v["fks"]],
                               description=v["desc"], fields=v["fields"]) for k, v in ENTITIES.items()}, indent=2)


def dictionary_md():
    L = ["# Data Dictionary", "", "R = required, O = optional. Allowed lists are enforced by `validate.py`.", ""]
    for name in ORDER:
        e = ENTITIES[name]
        L += [f"## {name} (`{e['file']}`)", "", e["desc"], "", f"**PK:** {', '.join(e['pk'])}  ",
              "**FKs:** " + (", ".join(f"{c} -> {t}.{r}" for c, t, r in e["fks"]) or "none"), "",
              "| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |", "|---|---|---|---|---|---|---|"]
        for x in e["fields"]:
            a = x["allowed"]
            a = ", ".join(map(str, a)) if isinstance(a, list) else a
            L.append(f"| {x['name']} | {x['type']} | {x['required']} | {a} | {x['unit']} | {x['unique']} | {x['rule']} |")
        L.append("")
    return "\n".join(L)
