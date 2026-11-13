# Data Dictionary

R = required, O = optional. Allowed lists are enforced by `validate.py`.

## Product (`product.csv`)

Master SKU. 1:N CostRecord, PriceHistory, InventorySnapshot, CompetitorObservation, Orders, PriceDecision; N:M Promotion via PromotionProduct.

**PK:** sku  
**FKs:** none

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| sku | string | R | SKU-000001.. |  | PK | regex ^SKU-\d{6}$, immutable |
| product_name | string | R |  |  |  |  |
| category | string | R | Electronics, Home & Kitchen, Grocery, Apparel, Beauty, Sports, Toys, Office |  |  |  |
| brand | string | R |  |  |  |  |
| uom | string | R | EA |  |  |  |
| currency | string | R | USD |  |  |  |
| launch_date | date | R |  |  |  | < first price_date |
| status | string | R | ACTIVE, DISCONTINUED |  |  | lifecycle ACTIVE -> DISCONTINUED (terminal) |
| discontinued_date | date | O |  |  |  | required iff status=DISCONTINUED; first inactive day, no price/inventory/order rows on/after it |
| list_price | decimal | R | >0 | USD |  | opening base price on first day; <= price_ceiling |
| price_floor_abs | decimal | R | >0 | USD |  | absolute floor = 1.05 x opening unit cost |
| price_ceiling | decimal | R | >0 | USD |  | >= list_price (1.30 x list) |
| min_margin_pct | decimal | R | 0.05..0.40 | fraction of net price |  | margin on NET price after all discounts |
| lead_time_days | int | R | 3..30 | days |  |  |

## AnnualPriceHistory (`annual_price_history.csv`)

Five years (2021-2025) of annual reference price/cost per SKU with year-over-year % change. Product 1:N (exactly 5 rows).

**PK:** aph_id  
**FKs:** sku -> Product.sku

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| aph_id | string | R |  |  | PK | APH-<sku>-YYYY |
| sku | string | R |  |  |  | FK Product.sku |
| year | int | R | 2021..2025 |  | unique with sku | 5 consecutive years ending the year before the window |
| ref_price | decimal | R | >0 | USD |  | annual average selling price (anchored mid-year) |
| prev_year_price | decimal | R | >0 | USD |  | = previous year's ref_price (2020 base for 2021) |
| yoy_price_pct | decimal | R |  | fraction |  | derived: ref_price/prev_year_price - 1 |
| ref_cost | decimal | R | >0 | USD |  | annual average unit cost |
| prev_year_cost | decimal | R | >0 | USD |  |  |
| yoy_cost_pct | decimal | R |  | fraction |  | derived: ref_cost/prev_year_cost - 1 |

## PriceGradient (`price_gradient.csv`)

Derived per-SKU gradient of the 5-year history (1:1 with Product). Recomputable from AnnualPriceHistory.

**PK:** sku  
**FKs:** sku -> Product.sku

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| sku | string | R |  |  | PK | FK Product.sku |
| basis_start_year | int | R | 2021 |  |  |  |
| basis_end_year | int | R | 2025 |  |  |  |
| years_of_history | int | R | 5 |  |  |  |
| avg_yoy_price_pct | decimal | R |  | fraction |  | mean of the 5 yoy_price_pct |
| price_cagr_5y | decimal | R |  | fraction/yr |  | (ref_price 2025 / prev_year_price 2021)^(1/5) - 1 |
| max_yoy_price_pct | decimal | R |  | fraction |  |  |
| min_yoy_price_pct | decimal | R |  | fraction |  |  |
| yoy_price_stdev | decimal | R | >=0 | fraction |  | sample stdev (n-1) |
| cost_cagr_5y | decimal | R |  | fraction/yr |  |  |
| last_ref_price | decimal | R | >0 | USD |  | = ref_price of 2025 |
| gradient_ceiling | decimal | R | >0 | USD |  | last_ref_price*(1+max_yoy_price_pct+0.03) |

## CostRecord (`cost_record.csv`)

One row per SKU per calendar month (append-only history of unit cost). Product 1:N CostRecord; (sku, cost_month) unique.

**PK:** cost_id  
**FKs:** sku -> Product.sku

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| cost_id | string | R |  |  | PK | COST-<sku>-YYYY-MM |
| sku | string | R |  |  |  | FK Product.sku |
| cost_month | string | R | YYYY-MM |  | unique with sku |  |
| effective_from | date | R |  |  |  | first day of month |
| effective_to | date | R |  |  |  | last day of month; >= effective_from; no overlap per sku |
| unit_cost | decimal | R | >0 | USD |  |  |
| prev_unit_cost | decimal | O |  | USD |  | null for first month |
| cost_change_pct | decimal | O |  | fraction |  | derived: unit_cost/prev_unit_cost-1 |
| cost_change_reason | string | R | INITIAL, NO_CHANGE, SUPPLIER_INCREASE, FX_ADJUSTMENT, FREIGHT_SURCHARGE, NEGOTIATED_REDUCTION, VOLUME_REBATE |  |  |  |

## Promotion (`promotion.csv`)

Promotion/coupon header. N:M with Product via PromotionProduct; N:M with itself via PromotionExclusion; 1:N PromotionRule, PromotionEvent.

**PK:** promo_id  
**FKs:** none

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| promo_id | string | R |  |  | PK | PROMO-2026-000001 |
| promo_name | string | R |  |  |  |  |
| promo_type | string | R | PCT_OFF, FIXED_OFF, COUPON |  |  |  |
| stack_group | string | R | SEASONAL, CLEARANCE, BRAND, LOYALTY, COUPON |  |  | COUPON type must be group COUPON |
| discount_pct | decimal | O | 0.01..0.50 | fraction of current price |  | required for PCT_OFF/COUPON |
| discount_amt | decimal | O | >0 | USD |  | required for FIXED_OFF |
| coupon_code | string | O |  |  | unique when present | required for COUPON |
| scope_category | string | R | Electronics, Home & Kitchen, Grocery, Apparel, Beauty, Sports, Toys, Office |  |  |  |
| start_date | date | R |  |  |  | aligned to review-week boundaries |
| end_date | date | R |  |  |  | >= start_date; multiple of 7 days long |
| created_date | date | R |  |  |  | < start_date |
| status | string | R | DRAFT, SCHEDULED, ACTIVE, ENDED, CANCELLED |  |  | status as of as_of date; derived from last PromotionEvent |

## PromotionRule (`promotion_rule.csv`)

Promotion-specific eligibility/stacking rules. Promotion 1:N (>=1). Global rules are in rules_config.json.

**PK:** rule_id  
**FKs:** promo_id -> Promotion.promo_id

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| rule_id | string | R |  |  | PK | PRULE-2026-000001 |
| promo_id | string | R |  |  |  | FK Promotion.promo_id |
| rule_type | string | R | MIN_STOCK_UNITS, EXCLUSIVE, MIN_MARGIN_PCT |  |  |  |
| rule_value | decimal | R |  | units | flag(1) | fraction |  | MIN_STOCK_UNITS: on_hand >= value; EXCLUSIVE: cannot combine; MIN_MARGIN_PCT: net margin >= value |

## PromotionProduct (`promotion_product.csv`)

Bridge for N:M Promotion <-> Product (eligible assortment).

**PK:** promo_id, sku  
**FKs:** promo_id -> Promotion.promo_id, sku -> Product.sku

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| promo_id | string | R |  |  | PK part | FK Promotion |
| sku | string | R |  |  | PK part | FK Product |
| added_date | date | R |  |  |  | = Promotion.created_date |

## PromotionExclusion (`promotion_exclusion.csv`)

Bridge for N:M Promotion <-> Promotion explicit conflicts (e.g. conflicting coupons). Symmetric; stored once with a<b.

**PK:** promo_id_a, promo_id_b  
**FKs:** promo_id_a -> Promotion.promo_id, promo_id_b -> Promotion.promo_id

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| promo_id_a | string | R |  |  | PK part | FK Promotion; a < b |
| promo_id_b | string | R |  |  | PK part | FK Promotion |
| exclusion_reason | string | R | CONFLICTING_COUPON |  |  |  |

## PromotionEvent (`promotion_event.csv`)

Append-only lifecycle history. Promotion 1:N. DRAFT->SCHEDULED->ACTIVE->ENDED or SCHEDULED->CANCELLED.

**PK:** event_id  
**FKs:** promo_id -> Promotion.promo_id

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| event_id | string | R |  |  | PK | PEVT-<promo_id>-NN |
| promo_id | string | R |  |  |  | FK Promotion |
| event_seq | int | R | >=1 |  | unique with promo_id |  |
| event_date | date | R |  |  |  | non-decreasing in event_seq; <= as_of |
| from_status | string | O | DRAFT, SCHEDULED, ACTIVE, ENDED, CANCELLED |  |  |  |
| to_status | string | R | DRAFT, SCHEDULED, ACTIVE, ENDED, CANCELLED |  |  | must be an allowed transition |

## CompetitorObservation (`competitor_observation.csv`)

Competitor price snapshots with source timestamp (observed_at) and ingestion timestamp (captured_at). Product 1:N.

**PK:** obs_id  
**FKs:** sku -> Product.sku

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| obs_id | string | R |  |  | PK | COBS-2026-000001, ordered by captured_at |
| sku | string | R |  |  |  | FK Product.sku |
| competitor_id | string | R | COMP-A, COMP-B, COMP-C, COMP-D |  |  |  |
| observed_at | datetime | R |  |  | unique with sku+competitor | source timestamp |
| captured_at | datetime | R |  |  |  | >= observed_at |
| competitor_price | decimal | R | >0 | USD |  |  |
| in_stock | bool | R | 0, 1 |  |  |  |
| source | string | R | SCRAPE_FEED, PARTNER_API, MANUAL_CHECK |  |  |  |
| source_lag_hours | decimal | R | >=0 | hours |  | derived: captured_at - observed_at |

## InventoryLot (`inventory_lot.csv`)

Stock receipt lots (opening balance + every replenishment receipt) used for FIFO inventory age. Product 1:N. Sales consume the oldest lot first.

**PK:** lot_id  
**FKs:** sku -> Product.sku

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| lot_id | string | R |  |  | PK | LOT-<sku>-YYYYMMDD (receipt date; opening lot is dated before the window) |
| sku | string | R |  |  | unique with received_date | FK Product.sku |
| received_date | date | R |  |  |  | unique per sku; replenishment lots = InventorySnapshot.units_received days |
| received_units | int | R | >=1 | units |  | replenishment lots: = InventorySnapshot.units_received that day |
| source | string | R | OPENING_BALANCE, REPLENISHMENT |  |  |  |
| unit_cost | decimal | R | >0 | USD |  | CostRecord unit cost in the receipt month (opening lot: first window month) |
| remaining_units | int | R | >=0 | units |  | derived: FIFO units still in stock on the SKU's last active day |
| lot_status | string | R | OPEN, DEPLETED |  |  | OPEN iff remaining_units > 0 |

## InventorySnapshot (`inventory_snapshot.csv`)

Daily end-of-day stock and demand signal per active SKU. Product 1:N.

**PK:** snapshot_id  
**FKs:** sku -> Product.sku

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| snapshot_id | string | R |  |  | PK | INV-<sku>-YYYYMMDD |
| sku | string | R |  |  |  | FK Product.sku |
| snapshot_date | date | R |  |  | unique with sku |  |
| opening_on_hand | int | R | >=0 | units |  | = previous closing_on_hand |
| units_received | int | R | >=0 | units |  |  |
| demand_units | int | R | >=0 | units |  | customer demand incl. unmet |
| units_sold | int | R | >=0 | units |  | = min(opening+received, demand); = sum(Orders.quantity) that day |
| lost_sales_units | int | R | >=0 | units |  | derived: demand_units - units_sold |
| closing_on_hand | int | R | >=0 | units |  | derived: opening + received - sold |
| on_order_units | int | R | >=0 | units |  | open replenishment quantity at end of day |
| stockout_flag | int | R | 0, 1 |  |  | derived: closing_on_hand = 0 |
| avg_demand_7d | decimal | R | >=0 | units/day |  | derived: trailing 7-day mean of demand_units (min periods 1) |
| days_of_cover | decimal | R | 0..999 | days |  | derived: closing_on_hand / max(avg_demand_7d,0.05), capped |
| oldest_stock_age_days | int | R | >=0 | days |  | derived (FIFO over InventoryLot): age on snapshot_date of the oldest lot still in stock; 0 when no stock |
| slow_moving_units | int | R | >=0 | units |  | derived: closing units in lots aged 61-90 days |
| aged_units | int | R | >=0 | units |  | derived: closing units in lots older than 90 days |
| stock_age_class | string | R | FRESH, NORMAL, SLOW_MOVING, AGED, NO_STOCK |  |  | derived: class of oldest_stock_age_days (NO_STOCK when closing_on_hand = 0) |

## PriceDecision (`price_decision.csv`)

Stored decision inputs and outcomes. Product 1:N; N:M Promotion via DecisionPromotion. Weekly review plus off-cycle COST_CHANGE reviews.

**PK:** decision_id  
**FKs:** sku -> Product.sku, cost_id -> CostRecord.cost_id, competitor_obs_id -> CompetitorObservation.obs_id

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| decision_id | string | R |  |  | PK | DEC-2026-000001 chronological |
| sku | string | R |  |  |  | FK Product |
| decision_date | date | R |  |  |  |  |
| decided_at | datetime | R |  |  |  | decision_date 06:00:00 |
| trigger | string | R | WEEKLY_REVIEW, COST_CHANGE |  |  |  |
| valid_from | date | R |  |  |  | = decision_date |
| valid_to | date | R |  |  |  | >= valid_from; day before next weekly review or window end |
| cost_id | string | R |  |  |  | FK CostRecord covering decision_date |
| unit_cost | decimal | R | >0 | USD |  | = CostRecord.unit_cost |
| price_before | decimal | R | >0 | USD |  | base price in force before decision |
| on_hand_units | int | R | >=0 | units |  | stock at decision time (opening + receipts of the day) |
| avg_daily_demand_7d | decimal | R | >=0 | units/day |  |  |
| days_of_cover | decimal | R | 0..999 | days |  |  |
| competitor_obs_id | string | O |  |  |  | FK CompetitorObservation considered (fresh min, else freshest stale) |
| competitor_price | decimal | O | >0 | USD |  | = obs.competitor_price |
| competitor_obs_age_days | decimal | O | >=0 | days |  | derived: (decided_at - observed_at)/24h |
| effective_floor | decimal | R | >0 | USD |  | max(price_floor_abs, ceil_cent(unit_cost/(1-min_margin_pct))) |
| price_ceiling | decimal | R | >0 | USD |  | static ceiling = max(Product.price_ceiling, effective_floor) |
| gradient_ref_price | decimal | R | >0 | USD |  | expected price from 5-yr gradient at decision date |
| gradient_ceiling | decimal | R | >0 | USD |  | = PriceGradient.gradient_ceiling; applied ceiling = max(min(price_ceiling, gradient_ceiling), effective_floor) |
| min_margin_pct | decimal | R |  | fraction |  | = Product.min_margin_pct |
| candidate_base_price | decimal | R | >0 | USD |  | policy target before step-limit and guardrails |
| base_price | decimal | R | >0 | USD |  | chosen list/base price |
| promo_discount_amt | decimal | R | >=0 | USD |  | sum of DecisionPromotion.discount_amt where APPLIED |
| net_price | decimal | R | >0 | USD |  | = base_price - promo_discount_amt |
| margin_pct | decimal | R |  | fraction of net price |  | (net_price - unit_cost)/net_price |
| guardrail_flags | string | O | STEP_LIMITED|FLOOR_CLAMPED|CEILING_CLAMPED|GRADIENT_CAPPED |  |  | pipe-separated |
| reason_code | string | R | COMP_MATCH_DOWN, COMP_RAISE, HOLD_IN_COMP_BAND, LOW_STOCK_MARKUP, OVERSTOCK_MARKDOWN, COST_PASS_THROUGH, GRADIENT_RECOVERY, FLOOR_REPAIR, CEILING_REPAIR, HOLD_STALE_COMPETITOR, HOLD_NO_SIGNAL |  |  |  |
| outcome | string | R | PRICE_CHANGED, PRICE_HELD |  |  | PRICE_CHANGED iff base_price != price_before |

## PriceHistory (`price_history.csv`)

Daily price ledger (one row per active SKU-day, never overwritten). Product 1:N PriceHistory; PriceDecision 1:N PriceHistory (governing decision).

**PK:** price_id  
**FKs:** sku -> Product.sku, decision_id -> PriceDecision.decision_id

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| price_id | string | R |  |  | PK | PRC-<sku>-YYYYMMDD |
| sku | string | R |  |  |  | FK Product.sku |
| price_date | date | R |  |  | unique with sku | contiguous per sku within active period |
| base_price | decimal | R | >0 | USD |  |  |
| promo_discount_amt | decimal | R | >=0 | USD |  | total of applied promo discounts |
| net_price | decimal | R | >0 | USD |  | = base_price - promo_discount_amt |
| applied_promo_ids | string | O |  |  |  | pipe-separated Promotion ids; empty if none |
| price_event | string | R | CARRY_FORWARD, DECISION_CHANGE, PROMO_CHANGE, DECISION_HOLD, MANUAL_CHANGE |  |  |  |
| change_reason_code | string | O | COMP_MATCH_DOWN, COMP_RAISE, HOLD_IN_COMP_BAND, LOW_STOCK_MARKUP, OVERSTOCK_MARKDOWN, COST_PASS_THROUGH, GRADIENT_RECOVERY, FLOOR_REPAIR, CEILING_REPAIR, HOLD_STALE_COMPETITOR, HOLD_NO_SIGNAL, PROMO_APPLIED, PROMO_ENDED, PROMO_CHANGED, MANUAL_OVERRIDE, PRICE_MATCH_STORE, ERROR_CORRECTION |  |  | required whenever price_event in DECISION_CHANGE/PROMO_CHANGE/MANUAL_CHANGE |
| decision_id | string | O |  |  |  | FK PriceDecision.decision_id (governing decision) |

## ProductBundle (`product_bundle.csv`)

Inventory-clearance bundle: one high-demand (primary) SKU + one aged/slow-moving complementary (secondary) SKU. Every evaluated candidate is stored; rejected ones have status CANCELLED and a rejection_reason (audit trail). Product 1:N (twice); 1:N BundleOrder.

**PK:** bundle_id  
**FKs:** primary_sku -> Product.sku, secondary_sku -> Product.sku

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| bundle_id | string | R |  |  | PK | BNDL-2026-000001, chronological |
| primary_sku | string | R |  |  |  | FK Product.sku; high-demand component |
| secondary_sku | string | R |  |  |  | FK Product.sku; slow-moving/aged component; != primary_sku; at most one accepted bundle per pair at a time |
| bundle_discount_pct | decimal | R | 0.05..0.15 | fraction |  | configurable; grows with secondary stock age |
| primary_unit_price | decimal | R | >0 | USD |  | = PriceHistory.base_price of primary on created_at date |
| secondary_unit_price | decimal | R | >0 | USD |  | = PriceHistory.base_price of secondary on created_at date |
| individual_total_price | decimal | R | >0 | USD |  | derived: primary_unit_price + secondary_unit_price |
| bundle_price | decimal | R | >0 | USD |  | derived: round(individual_total_price x (1 - bundle_discount_pct), 2) |
| combined_cost | decimal | R | >0 | USD |  | derived: unit costs of both SKUs in the valid_from month (CostRecord) |
| bundle_margin_pct | decimal | R |  | fraction of bundle price |  | derived: (bundle_price - combined_cost) / bundle_price |
| required_margin_pct | decimal | R |  | fraction |  | max(Product.min_margin_pct of both components) |
| valid_from | date | R |  |  |  | day after created_at |
| valid_to | date | R |  |  |  | >= valid_from; <= valid_from + validity - 1; <= last active day of both SKUs |
| bundle_status | string | R | DRAFT, ACTIVE, EXPIRED, CANCELLED |  |  | CANCELLED iff rejection_reason set; else EXPIRED if valid_to < as_of, DRAFT if valid_from > as_of, else ACTIVE |
| rejection_reason | string | O | COMPONENT_DISCONTINUED, INSUFFICIENT_STOCK, DUPLICATE_ACTIVE_BUNDLE, BELOW_PRICE_FLOOR, BELOW_MIN_MARGIN |  |  | first failing rule in documented order; empty when accepted |
| created_at | datetime | R |  |  |  | review date 06:00:00 |
| primary_avg_demand_30d | decimal | R | >=0 | units/day |  | derived: mean InventorySnapshot.demand_units of the previous min(30, day) days |
| primary_demand_threshold | decimal | R | >=0 | units/day |  | category percentile of that metric among live SKUs on created_at date |
| primary_sellable_units | int | R | >=0 | units |  | derived: floor(on_hand_units x (1 - reserve)); on_hand = opening + received on created_at date |
| secondary_sellable_units | int | R | >=0 | units |  | derived: same for the secondary SKU |
| max_bundle_units | int | R | >=0 | bundles |  | derived: min(primary_sellable_units, secondary_sellable_units); cap on bundles sold |
| secondary_oldest_age_days | int | R | >=0 | days |  | derived (FIFO replay): age of the oldest lot of the secondary at created_at |
| secondary_stock_age_class | string | R | FRESH, NORMAL, SLOW_MOVING, AGED, NO_STOCK |  |  |  |
| secondary_slow_units | int | R | >=0 | units |  | derived: secondary units in lots aged 61-90 days at created_at |
| secondary_aged_units | int | R | >=0 | units |  | derived: secondary units in lots older than 90 days at created_at |

## Orders (`orders.csv`)

Fulfilled order lines per SKU-day-channel. Product 1:N; PriceHistory 1:N; every line priced from the PriceHistory row of its day.

**PK:** order_id  
**FKs:** sku -> Product.sku, price_id -> PriceHistory.price_id, decision_id -> PriceDecision.decision_id, bundle_order_id -> BundleOrder.bundle_order_id

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| order_id | string | R |  |  | PK | ORD-2026-000001 |
| order_date | date | R |  |  |  |  |
| sku | string | R |  |  |  | FK Product |
| price_id | string | R |  |  |  | FK PriceHistory; = PRC-<sku>-<order_date> |
| decision_id | string | O |  |  |  | FK PriceDecision; = PriceHistory.decision_id |
| channel | string | R | WEB, STORE, MARKETPLACE |  |  |  |
| customer_segment | string | R | CONSUMER, BUSINESS, LOYALTY_MEMBER |  |  |  |
| quantity | int | R | >=1 | units |  |  |
| unit_base_price | decimal | R | >0 | USD |  | = PriceHistory.base_price |
| unit_net_price | decimal | R | >0 | USD |  | = PriceHistory.net_price |
| unit_cost | decimal | R | >0 | USD |  | = CostRecord.unit_cost of the order month |
| line_total | decimal | R | >0 | USD |  | derived: quantity * unit_net_price |
| order_status | string | R | FULFILLED |  |  | only fulfilled lines are generated (reconcile to units_sold) |
| bundle_order_id | string | O |  |  |  | FK BundleOrder; set on the two component lines (one per SKU) of a bundle sale, else empty. Bundle lines: unit_net_price = allocated bundle price, not PriceHistory.net_price |

## BundleOrder (`bundle_order.csv`)

Bundle sales: one row per bundle per day. Each row has exactly two Orders lines (primary and secondary SKU) with the same quantity, so both SKUs' units_sold / InventorySnapshot move. ProductBundle 1:N; Orders 1:2.

**PK:** bundle_order_id  
**FKs:** bundle_id -> ProductBundle.bundle_id, order_id -> Orders.order_id, secondary_order_id -> Orders.order_id

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| bundle_order_id | string | R |  |  | PK | BORD-2026-000001 |
| bundle_id | string | R |  |  |  | FK ProductBundle; bundle must be accepted and order_date within [valid_from, valid_to] |
| order_id | string | R |  |  |  | FK Orders: line of the primary SKU |
| secondary_order_id | string | R |  |  |  | FK Orders: line of the secondary SKU |
| order_date | date | R |  |  |  |  |
| channel | string | R | WEB, STORE, MARKETPLACE |  |  |  |
| quantity | int | R | >=1 | bundles |  | units of EACH component; cumulative per bundle <= max_bundle_units |
| bundle_selling_price | decimal | R | >0 | USD |  | = ProductBundle.bundle_price |
| total_revenue | decimal | R | >0 | USD |  | derived: quantity x bundle_selling_price |
| total_cost | decimal | R | >0 | USD |  | derived: quantity x (unit_cost primary + unit_cost secondary) of the order month |
| gross_profit | decimal | R |  | USD |  | derived: total_revenue - total_cost |
| aged_units_cleared | int | R | >=0 | units |  | derived (FIFO replay): secondary units of this sale taken from lots older than 90 days |

## DecisionPromotion (`decision_promotion.csv`)

Bridge N:M PriceDecision <-> Promotion: every candidate promotion evaluated, with status and reason (eligibility is reproducible from these + rules).

**PK:** decision_id, promo_id  
**FKs:** decision_id -> PriceDecision.decision_id, promo_id -> Promotion.promo_id

| Field | Type | Req | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| decision_id | string | R |  |  | PK part | FK PriceDecision |
| promo_id | string | R |  |  | PK part | FK Promotion |
| evaluation_status | string | R | APPLIED, REJECTED |  |  |  |
| rejection_reason | string | O | MIN_STOCK, EXCLUSIVE_WITH_OTHER, SAME_GROUP, CONFLICT_PAIR, MAX_STACK, MAX_TOTAL_DISCOUNT, FLOOR_GUARDRAIL, MARGIN_GUARDRAIL |  |  | required iff REJECTED |
| apply_sequence | int | O | >=1 |  |  | required iff APPLIED |
| discount_amt | decimal | R | >=0 | USD |  | 0 when rejected |
