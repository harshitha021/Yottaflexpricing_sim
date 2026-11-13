# Validation summary - data_starter_new

**190/190 checks passed**

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | Product: required fields non-null | PASS | {} |
| 2 | Product: enum values allowed | PASS | {} |
| 3 | Product: primary key unique | PASS | dups=0 |
| 4 | Product: sku matches naming convention | PASS |  |
| 5 | AnnualPriceHistory: required fields non-null | PASS | {} |
| 6 | AnnualPriceHistory: enum values allowed | PASS | {} |
| 7 | AnnualPriceHistory: primary key unique | PASS | dups=0 |
| 8 | AnnualPriceHistory: aph_id matches naming convention | PASS |  |
| 9 | AnnualPriceHistory.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 10 | PriceGradient: required fields non-null | PASS | {} |
| 11 | PriceGradient: enum values allowed | PASS | {} |
| 12 | PriceGradient: primary key unique | PASS | dups=0 |
| 13 | PriceGradient.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 14 | CostRecord: required fields non-null | PASS | {} |
| 15 | CostRecord: enum values allowed | PASS | {} |
| 16 | CostRecord: primary key unique | PASS | dups=0 |
| 17 | CostRecord: cost_id matches naming convention | PASS |  |
| 18 | CostRecord.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 19 | Promotion: required fields non-null | PASS | {} |
| 20 | Promotion: enum values allowed | PASS | {} |
| 21 | Promotion: primary key unique | PASS | dups=0 |
| 22 | Promotion: promo_id matches naming convention | PASS |  |
| 23 | PromotionRule: required fields non-null | PASS | {} |
| 24 | PromotionRule: enum values allowed | PASS | {} |
| 25 | PromotionRule: primary key unique | PASS | dups=0 |
| 26 | PromotionRule: rule_id matches naming convention | PASS |  |
| 27 | PromotionRule.promo_id -> Promotion.promo_id FK integrity | PASS | orphans=0 |
| 28 | PromotionProduct: required fields non-null | PASS | {} |
| 29 | PromotionProduct: enum values allowed | PASS | {} |
| 30 | PromotionProduct: primary key unique | PASS | dups=0 |
| 31 | PromotionProduct.promo_id -> Promotion.promo_id FK integrity | PASS | orphans=0 |
| 32 | PromotionProduct.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 33 | PromotionExclusion: required fields non-null | PASS | {} |
| 34 | PromotionExclusion: enum values allowed | PASS | {} |
| 35 | PromotionExclusion: primary key unique | PASS | dups=0 |
| 36 | PromotionExclusion.promo_id_a -> Promotion.promo_id FK integrity | PASS | orphans=0 |
| 37 | PromotionExclusion.promo_id_b -> Promotion.promo_id FK integrity | PASS | orphans=0 |
| 38 | PromotionEvent: required fields non-null | PASS | {} |
| 39 | PromotionEvent: enum values allowed | PASS | {} |
| 40 | PromotionEvent: primary key unique | PASS | dups=0 |
| 41 | PromotionEvent.promo_id -> Promotion.promo_id FK integrity | PASS | orphans=0 |
| 42 | CompetitorObservation: required fields non-null | PASS | {} |
| 43 | CompetitorObservation: enum values allowed | PASS | {} |
| 44 | CompetitorObservation: primary key unique | PASS | dups=0 |
| 45 | CompetitorObservation: obs_id matches naming convention | PASS |  |
| 46 | CompetitorObservation.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 47 | InventoryLot: required fields non-null | PASS | {} |
| 48 | InventoryLot: enum values allowed | PASS | {} |
| 49 | InventoryLot: primary key unique | PASS | dups=0 |
| 50 | InventoryLot: lot_id matches naming convention | PASS |  |
| 51 | InventoryLot.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 52 | InventorySnapshot: required fields non-null | PASS | {} |
| 53 | InventorySnapshot: enum values allowed | PASS | {} |
| 54 | InventorySnapshot: primary key unique | PASS | dups=0 |
| 55 | InventorySnapshot: snapshot_id matches naming convention | PASS |  |
| 56 | InventorySnapshot.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 57 | PriceDecision: required fields non-null | PASS | {} |
| 58 | PriceDecision: enum values allowed | PASS | {} |
| 59 | PriceDecision: primary key unique | PASS | dups=0 |
| 60 | PriceDecision: decision_id matches naming convention | PASS |  |
| 61 | PriceDecision.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 62 | PriceDecision.cost_id -> CostRecord.cost_id FK integrity | PASS | orphans=0 |
| 63 | PriceDecision.competitor_obs_id -> CompetitorObservation.obs_id FK integrity | PASS | orphans=0 |
| 64 | PriceHistory: required fields non-null | PASS | {} |
| 65 | PriceHistory: enum values allowed | PASS | {} |
| 66 | PriceHistory: primary key unique | PASS | dups=0 |
| 67 | PriceHistory: price_id matches naming convention | PASS |  |
| 68 | PriceHistory.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 69 | PriceHistory.decision_id -> PriceDecision.decision_id FK integrity | PASS | orphans=0 |
| 70 | ProductBundle: required fields non-null | PASS | {} |
| 71 | ProductBundle: enum values allowed | PASS | {} |
| 72 | ProductBundle: primary key unique | PASS | dups=0 |
| 73 | ProductBundle: bundle_id matches naming convention | PASS |  |
| 74 | ProductBundle.primary_sku -> Product.sku FK integrity | PASS | orphans=0 |
| 75 | ProductBundle.secondary_sku -> Product.sku FK integrity | PASS | orphans=0 |
| 76 | Orders: required fields non-null | PASS | {} |
| 77 | Orders: enum values allowed | PASS | {} |
| 78 | Orders: primary key unique | PASS | dups=0 |
| 79 | Orders: order_id matches naming convention | PASS |  |
| 80 | Orders.sku -> Product.sku FK integrity | PASS | orphans=0 |
| 81 | Orders.price_id -> PriceHistory.price_id FK integrity | PASS | orphans=0 |
| 82 | Orders.decision_id -> PriceDecision.decision_id FK integrity | PASS | orphans=0 |
| 83 | Orders.bundle_order_id -> BundleOrder.bundle_order_id FK integrity | PASS | orphans=0 |
| 84 | BundleOrder: required fields non-null | PASS | {} |
| 85 | BundleOrder: enum values allowed | PASS | {} |
| 86 | BundleOrder: primary key unique | PASS | dups=0 |
| 87 | BundleOrder: bundle_order_id matches naming convention | PASS |  |
| 88 | BundleOrder.bundle_id -> ProductBundle.bundle_id FK integrity | PASS | orphans=0 |
| 89 | BundleOrder.order_id -> Orders.order_id FK integrity | PASS | orphans=0 |
| 90 | BundleOrder.secondary_order_id -> Orders.order_id FK integrity | PASS | orphans=0 |
| 91 | DecisionPromotion: required fields non-null | PASS | {} |
| 92 | DecisionPromotion: enum values allowed | PASS | {} |
| 93 | DecisionPromotion: primary key unique | PASS | dups=0 |
| 94 | DecisionPromotion.decision_id -> PriceDecision.decision_id FK integrity | PASS | orphans=0 |
| 95 | DecisionPromotion.promo_id -> Promotion.promo_id FK integrity | PASS | orphans=0 |
| 96 | PriceHistory (sku, price_date) unique | PASS |  |
| 97 | InventorySnapshot (sku, snapshot_date) unique | PASS |  |
| 98 | CostRecord (sku, cost_month) unique | PASS |  |
| 99 | CompetitorObservation no duplicate (sku, competitor, observed_at) | PASS |  |
| 100 | Promotion coupon_code unique | PASS |  |
| 101 | Promotion coupon_code present iff COUPON | PASS |  |
| 102 | Promotion discount field matches type | PASS |  |
| 103 | Promotion start<=end, created<start | PASS |  |
| 104 | CostRecord effective_from<=effective_to | PASS |  |
| 105 | Observation observed_at<=captured_at | PASS |  |
| 106 | Observation source_lag_hours reconciles | PASS |  |
| 107 | PriceDecision valid_from<=valid_to and = decision_date | PASS |  |
| 108 | Product launch_date < first price_date | PASS |  |
| 109 | Discontinued SKUs: no rows on/after discontinued_date; status/date consistent | PASS |  |
| 110 | Orders/Inventory only on active days | PASS |  |
| 111 | PriceHistory contiguous daily per SKU | PASS | gaps=0 |
| 112 | PriceHistory/Inventory same SKU-days | PASS |  |
| 113 | PriceHistory net = base - discount | PASS |  |
| 114 | PriceDecision net = base - discount | PASS |  |
| 115 | Decision promo_discount_amt = sum applied DecisionPromotion | PASS |  |
| 116 | DecisionPromotion APPLIED/REJECTED field consistency | PASS |  |
| 117 | INV closing = opening + received - sold | PASS |  |
| 118 | INV sold<=demand, lost=demand-sold, stockout flag | PASS |  |
| 119 | INV opening(t) = closing(t-1) | PASS |  |
| 120 | INV days_of_cover = closing/max(avg7,0.05) | PASS |  |
| 121 | Orders qty by SKU-day = InventorySnapshot.units_sold | PASS |  |
| 122 | Orders line_total = qty * net | PASS |  |
| 123 | Orders (non-bundle) price/decision match PriceHistory | PASS |  |
| 124 | Orders unit_cost = CostRecord for month | PASS |  |
| 125 | CostRecord prev/change_pct derived | PASS |  |
| 126 | Decision unit_cost/cost_id match CostRecord | PASS |  |
| 127 | Decision competitor_price/age derived from observation | PASS |  |
| 128 | Decision uses only already-captured observations | PASS |  |
| 129 | Decision outcome consistent with price_before/base_price | PASS |  |
| 130 | PriceHistory decision-day rows equal PriceDecision outcome | PASS |  |
| 131 | AnnualPriceHistory: 5 consecutive years 2021-2025 for every SKU | PASS |  |
| 132 | AnnualPriceHistory: yoy % = ref/prev - 1 (price and cost) | PASS |  |
| 133 | AnnualPriceHistory: prev_year = previous year's ref (chain continuity) | PASS |  |
| 134 | PriceGradient derived from AnnualPriceHistory (avg, CAGR, max, min, stdev, cost CAGR, ceiling) | PASS |  |
| 135 | Product.list_price consistent with 5-year gradient (within 5%) | PASS | min=0.975 max=1.026 |
| 136 | Opening unit cost consistent with 5-year cost gradient (within 10%) | PASS | min=0.995 max=1.004 |
| 137 | Decision gradient_ref_price / gradient_ceiling reproducible from PriceGradient | PASS |  |
| 138 | Promotion lifecycle transitions valid & chronological | PASS | bad=0 |
| 139 | Promotion.status = last PromotionEvent | PASS |  |
| 140 | PromotionEvent dates <= as_of | PASS |  |
| 141 | Cancelled/draft promos never applied | PASS |  |
| 142 | Evaluated promos active over decision window | PASS |  |
| 143 | Evaluated promos target the SKU (PromotionProduct) | PASS |  |
| 144 | PromotionExclusion a<b | PASS |  |
| 145 | InventoryLot: at most one opening lot per SKU, dated before the window | PASS |  |
| 146 | InventoryLot: replenishment lots dated inside the window | PASS |  |
| 147 | InventoryLot (sku, received_date) unique | PASS |  |
| 148 | InventoryLot: receipts = InventorySnapshot.units_received; opening lot = first opening_on_hand | PASS |  |
| 149 | InventoryLot: FIFO lots reconcile to closing_on_hand | PASS |  |
| 150 | InventorySnapshot oldest_stock_age_days / slow_moving_units / aged_units reproduce from InventoryLot FIFO replay | PASS | mismatches=0 |
| 151 | InventorySnapshot stock_age_class = threshold class of oldest lot | PASS |  |
| 152 | InventorySnapshot aged/slow units <= closing_on_hand | PASS |  |
| 153 | InventoryLot remaining_units / lot_status derived from FIFO | PASS |  |
| 154 | InventoryLot unit_cost = CostRecord of receipt month | PASS |  |
| 155 | ProductBundle: primary != secondary SKU | PASS |  |
| 156 | ProductBundle: categories are complementary (bundle_complement_map) | PASS |  |
| 157 | ProductBundle: secondary price <= ratio x primary price | PASS |  |
| 158 | ProductBundle: rejection_reason set iff status CANCELLED | PASS |  |
| 159 | ProductBundle: status derived from validity window vs as_of | PASS |  |
| 160 | ProductBundle: valid_from = day after created_at; valid_to within validity window | PASS |  |
| 161 | ProductBundle: accepted bundles end on/before last active day of both SKUs | PASS |  |
| 162 | ProductBundle: created on review days with >= min history | PASS |  |
| 163 | ProductBundle: unit prices = PriceHistory.base_price on created_at date | PASS |  |
| 164 | ProductBundle: individual_total_price and bundle_price formula | PASS |  |
| 165 | ProductBundle: combined_cost = CostRecord of both SKUs in valid_from month | PASS |  |
| 166 | ProductBundle: bundle_margin_pct = (price - combined_cost)/price (same margin basis) | PASS |  |
| 167 | ProductBundle: required_margin_pct = max(min_margin_pct of components) | PASS |  |
| 168 | ProductBundle: accepted bundle_price >= sum of effective floors (price guardrail) | PASS |  |
| 169 | ProductBundle: discount within configured range (exceptions are only margin-violating approvals) | PASS | outside=1 |
| 170 | ProductBundle: no duplicate overlapping accepted bundle for the same SKU pair | PASS | overlaps=0 |
| 171 | ProductBundle: sellable units / max_bundle_units reproduce from InventorySnapshot (stock net of reserve) | PASS |  |
| 172 | ProductBundle: INSUFFICIENT_STOCK rejection iff a component lacks stock; accepted bundles always have stock | PASS |  |
| 173 | ProductBundle: primary demand metric and category threshold reproduce from InventorySnapshot | PASS | mismatches=0 |
| 174 | ProductBundle: primary is a high-demand product (>= category percentile and min demand) | PASS | violations=0 |
| 175 | ProductBundle: secondary stock age (FIFO replay) matches and secondary is slow-moving/aged | PASS | age mismatches=0; ineligible=0 |
| 176 | BundleOrder: only accepted bundles sell, only inside valid_from..valid_to (expired/cancelled/draft cannot) | PASS |  |
| 177 | BundleOrder: cumulative quantity per bundle <= max_bundle_units (limited by lower stock) | PASS |  |
| 178 | BundleOrder: two Orders lines (primary + secondary SKU) per bundle sale with same date/qty/channel/link | PASS |  |
| 179 | BundleOrder: component Orders lines carry the allocated bundle price (sum = bundle_price) | PASS |  |
| 180 | BundleOrder: revenue, cost, gross profit derived correctly | PASS |  |
| 181 | Bundle sales are part of InventorySnapshot.units_sold of BOTH SKUs (<= units_sold; Orders reconcile) | PASS |  |
| 182 | BundleOrder: aged_units_cleared reproduces from FIFO replay | PASS | mismatches=0 |
| 183 | Bundle sales do not alter PriceHistory / PriceDecision (bundle price is a separate offer) | PASS |  |
| 184 | Decision effective_floor reproducible from Product+CostRecord | PASS |  |
| 185 | Every price move has a change_reason_code (excluding labelled anomalies) | PASS | scored below |
| 186 | Eligibility replay: mismatches == injected stack/margin anomalies | PASS | replayed=1374 decisions; mismatches=7; injected=7 |
| 187 | Detectors recover every injected anomaly (recall=1, precision=1) | PASS | {"PRICE_BELOW_FLOOR": [1.0, 1.0], "PROMO_STACK_VIOLATION": [1.0, 1.0], "STALE_OBSERVATION_AS_CURRENT": [1.0, 1.0], "MARGIN_BEFORE_DISCOUNT": |
| 188 | Clean decisions match expected ground-truth decisions (base, net, reason) | PASS |  |
| 189 | Guardrails enforced on all non-injected decisions | PASS | violations=0 |
| 190 | No ground-truth columns leaked into input tables | PASS |  |

## Anomaly detector scores (rule-based detectors vs ground truth)

| Issue | Injected | Detected | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|---|---|
| PRICE_BELOW_FLOOR | 19 | 19 | 19 | 0 | 0 | 1.0 | 1.0 |
| PROMO_STACK_VIOLATION | 4 | 4 | 4 | 0 | 0 | 1.0 | 1.0 |
| STALE_OBSERVATION_AS_CURRENT | 6 | 6 | 6 | 0 | 0 | 1.0 | 1.0 |
| MARGIN_BEFORE_DISCOUNT | 3 | 3 | 3 | 0 | 0 | 1.0 | 1.0 |
| PRICE_CHANGE_WITHOUT_REASON | 29 | 29 | 29 | 0 | 0 | 1.0 | 1.0 |
| PRICE_ABOVE_GRADIENT_CEILING | 15 | 15 | 15 | 0 | 0 | 1.0 | 1.0 |
| BUNDLE_BELOW_MARGIN | 1 | 1 | 1 | 0 | 0 | 1.0 | 1.0 |
