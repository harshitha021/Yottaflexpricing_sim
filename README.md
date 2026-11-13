# Pricing & Promotion Simulation – Synthetic Dataset

Fully synthetic, deterministic dataset for simulating price decisions using demand, stock, competitor observations, promotion
rules and margin constraints. No external data, no personal data.

## Layout

| Path | Content |
|---|---|
| `src/generate.py` | Generator (same code for starter and full scale) |
| `src/schema.py` | Data dictionary, enums, keys, DDL (single source of truth) |
| `src/bundles.py` | Inventory-age (FIFO) and bundle business rules as pure functions (used by generator, validator, tests) |
| `src/validate.py` | Validation (190 checks), rule-based anomaly detectors, business metrics |
| `src/reproduce.py` | Regenerates twice and compares row counts + SHA-256 |
| `tests/test_bundles.py` | 19 unit + data tests for the bundling feature (`python -m unittest discover -s tests -v`) |
| `data_full/` | 5,000 SKUs, 180 days, 2,000 promotions (CSV, ~350 MB) |
| `data_starter/` | 500 SKUs, 60 days, 150 promotions (CSV + `seed.sql`, ~30 MB) |
| `<data>/ground_truth/` | `ground_truth_anomalies.csv/.json`, `ground_truth_decisions.csv` – **never join into input features** |
| `<data>/` docs | `data_dictionary.md/.json`, `schema.sql`, `rules_config.json`, `source_manifest.json`, `generator_command.txt`, `validation_summary.md/.json`, `metrics.json`, `reproducibility_report.json` |

## Generator command (fixed seed 20261022)

```
cd src
python generate.py --skus 5000 --days 180 --promos 2000 --seed 20261022 --out ../data_full
python generate.py --skus 500  --days 60  --promos 150  --seed 20261022 --out ../data_starter --sql   # --sql also emits seed.sql
python validate.py ../data_full
python reproduce.py ../data_full/reproducibility_report.json --skus 5000 --days 180 --promos 2000 --seed 20261022
cd .. && python -m unittest discover -s tests -v      # bundling tests (generate a small dataset in a temp dir)
```
Window: 2026-04-26 … (+days−1). Requires Python 3.10+, numpy, pandas. `seed.sql` is emitted for the starter set; add `--sql` for full
(≈1M-row INSERT file) or load the CSVs against `schema.sql`.

## Entities & relationships

```
Product 1─N AnnualPriceHistory (5 rows)   Product 1─1 PriceGradient (derived)
Product 1─N CostRecord            Product 1─N PriceHistory      PriceDecision 1─N PriceHistory (governing decision)
Product 1─N InventorySnapshot     Product 1─N CompetitorObservation
Product 1─N PriceDecision         PriceDecision N─M Promotion via DecisionPromotion (APPLIED / REJECTED + reason)
Promotion N─M Product via PromotionProduct          Promotion N─M Promotion via PromotionExclusion (conflicting coupons)
Promotion 1─N PromotionRule (>=1)                   Promotion 1─N PromotionEvent (append-only lifecycle)
Product 1─N Orders ; PriceHistory 1─N Orders ; PriceDecision 1─N Orders
Product 1─N InventoryLot (FIFO receipt lots)          Product 1─N ProductBundle (as primary AND as secondary SKU)
ProductBundle 1─N BundleOrder ; BundleOrder 1─2 Orders (one line per component SKU, Orders.bundle_order_id)
```
Optional relationships: `PriceHistory.decision_id`/`Orders.decision_id` (nullable), `PriceDecision.competitor_obs_id` (null when no
usable observation). Lifecycles: Promotion `DRAFT→SCHEDULED→ACTIVE→ENDED` or `SCHEDULED→CANCELLED`; Product `ACTIVE→DISCONTINUED`;
CostRecord effective-dated monthly; nothing is overwritten (price ledger and events are append-only). Full field-level
dictionary: `data_dictionary.md`.

IDs: `SKU-000001`, `COST-SKU-000001-2026-04`, `PRC-SKU-000001-20260426`, `PROMO-2026-000001`, `DEC-2026-000001`, plus
`COBS-2026-…`, `ORD-2026-…`, `PRULE-2026-…`, `INV-<sku>-<yyyymmdd>`, `PEVT-<promo_id>-NN`, `LOT-<sku>-<yyyymmdd>`, `BNDL-2026-000001`, `BORD-2026-000001`.
`Orders` ↔ `BundleOrder` reference each other, so those three FKs are `DEFERRABLE INITIALLY DEFERRED` in `schema.sql`.

## Business logic (all in `rules_config.json` + `PromotionRule`)

* **Margin basis (consistent everywhere):** `margin = (net_price − unit_cost) / net_price`, net = base − all promo discounts, cost = CostRecord of the decision month.
* **Guardrails:** `effective_floor = max(price_floor_abs, ceil_cent(cost / (1 − min_margin)))`; ceiling = `max(price_ceiling, floor)`; max ±10 % step per decision.
* **5-year gradient rules (new):** `AnnualPriceHistory` holds 2021–2025 annual reference price/cost per SKU with year-over-year %; `PriceGradient` derives avg/CAGR/max/min/stdev (recomputed by the validator). Category and brand drive different trends (e.g. Electronics ≈ +1.9 %/yr, Grocery ≈ +3.9 %/yr). Rules: (1) **gradient ceiling** = `last_ref_price × (1 + max_yoy + 3 %)`, applied ceiling = `max(min(price_ceiling, gradient_ceiling), effective_floor)` so the margin floor always wins; (2) **gradient recovery** – with no competitor/stock signal (or inside the competitor band) a price more than 3 % below the expected gradient price moves back toward `min(gradient_ref_price, competitor price)`, only if the gain is ≥ 1 %; (3) **cost drift** follows each SKU's historical cost CAGR; (4) `list_price` and opening cost are consistent with the history. Each decision stores `gradient_ref_price`, `gradient_ceiling` and the flag `GRADIENT_CAPPED`.
* **Decision policy (weekly review + off-cycle review on cost change):** low stock (cover < 5 d) → +4 % → fresh competitor (≤ 7 d, in stock) match/raise with ±3 %/7 % band → overstock (cover > 75 d) −5 % → hold (stale competitor / no signal) → cost pass-through when holding and cost moved. Each decision stores every input (cost, stock, demand, competitor obs + age, floor, ceiling) and a `reason_code`.
* **Promotion stacking:** ≤ 2 promos, one per stack group, `EXCLUSIVE` rule blocks combining, `PromotionExclusion` pairs never co-apply, total discount ≤ 35 % of base, `MIN_STOCK_UNITS`, `MIN_MARGIN_PCT`, and net ≥ floor. Evaluated in a documented order; every candidate and its rejection reason is stored in `DecisionPromotion`, so eligibility is replayable (validator replays all of them).
* **Inventory age (FIFO lots):** every receipt (plus the opening balance) is an `InventoryLot`; sales consume the oldest lot first. `InventorySnapshot` carries `oldest_stock_age_days`, `slow_moving_units` (61–90 d), `aged_units` (>90 d) and `stock_age_class` (FRESH 0–30, NORMAL 31–60, SLOW_MOVING 61–90, AGED >90, NO_STOCK). Thresholds are in `rules_config.json`; the validator replays FIFO from the lot table and must reproduce every snapshot value.
* **Inventory-clearance bundles (separate from single-SKU pricing):** on weekly review days (after ≥ 7 days of history) the oldest SLOW_MOVING/AGED SKUs (≥ 5 aged/slow units, top 3 % of SKUs) are paired with a **high-demand complementary** SKU (30-day demand ≥ category 75th percentile and ≥ 0.5/day; category pairs from `bundle_complement_map`, add-on price ≤ 1.25 × main item, ≤ 3 bundles per primary per review). Rules, in rejection order: `COMPONENT_DISCONTINUED` → `INSUFFICIENT_STOCK` (sellable = on hand × (1 − 10 % reserve) must be ≥ 10 for both; bundle cap = the lower sellable stock) → `DUPLICATE_ACTIVE_BUNDLE` (same pair already accepted and still valid) → `BELOW_PRICE_FLOOR` (bundle price < sum of both effective floors) → `BELOW_MIN_MARGIN` (`(bundle_price − combined_cost)/bundle_price` < the stricter of both `min_margin_pct`). Price = `(A + B) × (1 − discount)`, discount 8 % / 12 % / 15 % by stock age (configurable, 5–15 %). Every evaluated candidate is stored in `ProductBundle`; rejected ones are `CANCELLED` with a `rejection_reason`. Accepted bundles are valid 14 days (`valid_from` = next day), then `EXPIRED`; only accepted bundles inside their window sell. Bundle sales are extra demand for **both** SKUs served from the same stock (they show up in `InventorySnapshot.units_sold`, FIFO consumption and `Orders`); the two `Orders` lines carry the allocated bundle price. Bundles never touch `PriceHistory`/`PriceDecision`, do not stack with promotions, and do not replace `MIN_STOCK_UNITS`/`MIN_MARGIN_PCT`.
* **Demand/inventory:** Poisson demand with weekday/season effects, price elasticity vs market reference, promo uplift; (s,Q) replenishment with supplier disruptions → stockouts and lost sales. Orders reconcile exactly to `units_sold`.
* **Derived values** (totals, margins, cover, lags, line totals, statuses) are computed from source records, not drawn independently.

## Injected, labelled edge cases (ground truth only)

Baseline records are produced first; anomalies are produced by perturbing the documented computation at decision time, so downstream
price history/orders stay internally consistent and unrelated rows are untouched. Full volume: `PRICE_CHANGE_WITHOUT_REASON` 736,
`PRICE_BELOW_FLOOR` 569, `PRICE_ABOVE_GRADIENT_CEILING` 414, `MARGIN_BEFORE_DISCOUNT` 158, `STALE_OBSERVATION_AS_CURRENT` 136, `PROMO_STACK_VIOLATION` 78
(≈ 1.5 % of decisions) plus `BUNDLE_BELOW_MARGIN` 47 (an over-deep discount pushes an *approved* bundle below its margin requirement; entity `ProductBundle`). `ground_truth_decisions.csv` holds the *expected clean* base/net price, promos and reason for every decision.
Natural (unlabelled) coverage: monthly cost changes, competitor feed outages (stale data → `HOLD_STALE_COMPETITOR`), stockouts and lost sales,
conflicting coupons (`SAME_GROUP`/`CONFLICT_PAIR` rejections), cancelled/future promos, discontinued SKUs, floor/ceiling clamps.

## Validation, evaluation, reproducibility

* `validate.py` → `validation_summary.md`: PK uniqueness, FK integrity (all 25 relationships), enums, required fields, ID patterns, date ordering, contiguity, arithmetic reconciliation (inventory roll-forward, orders↔inventory↔price↔cost, decision↔price ledger), lifecycle transitions, duplicates, ground-truth leak check.
* 58 bundle/lot checks: FIFO replay of every snapshot age value, lot↔receipt reconciliation, bundle price/margin/floor formulas, complementarity, high-demand and stock-availability replay at `created_at`, no overlapping duplicate pairs, sales only inside validity and within `max_bundle_units`, two Orders lines per bundle sale, revenue/cost/profit, `aged_units_cleared` FIFO replay.
* Independent rule-based detectors recompute each anomaly from input tables only and are scored against ground truth (precision/recall = 1.0 on all seven types).
* `metrics.json` (bundle metrics: `bundles_evaluated/created/active`, `bundle_units_sold`, `aged_inventory_units_cleared`, `bundle_revenue`, `bundle_gross_profit`, `bundle_avg_discount_pct`, `bundle_realised_margin_pct`, `aged_inventory_reduction_pct`, `bundle_rejections_by_reason`): revenue, gross margin %, promo unit share, stockout rate, lost-sales share, decisions by reason, promo rejections by reason, stale-data share, guardrail pass rate, price-vs-competitor index, eligibility-replay agreement.
* `reproducibility_report.json`: two independent regenerations with seed 20261022 – identical row counts and SHA-256 for every file.

## Provenance

Synthetic only (`source_manifest.json` → `external_data: []`). No public datasets, scraping or personal data were used; competitor names are generic (`COMP-A…D`).

## Known simplifications

Bundle take-up is a simulation parameter (attach rate × primary demand × discount), not an observed behaviour; "aged inventory reduction" also includes aged stock sold through regular sales, so use `aged_inventory_units_cleared` for the bundle effect. Reserved/damaged stock is modelled only as a protected reserve (10 % of on-hand), and no impression/conversion data exists. Order lines are generated per SKU-day-channel (fulfilled only, no cancellations/returns); promotions are week-aligned; competitors are tracked
by 2 of 4 anonymous competitor feeds per SKU; demand/elasticity parameters are internal to the generator and not exported.

## Full dataset not included in the repository

`data_full/` is about 890 MB (`seed.sql` alone is 546 MB), above GitHub's 100 MB per-file limit, so its large CSVs and `seed.sql` are git-ignored. The documentation, validation summary, metrics, ground truth and reproducibility report for the full set are committed. Regenerate the data in about 2 minutes with the command above (add `--sql` for `seed.sql`); the SHA-256 of every file is recorded in `data_full/reproducibility_report.json`. `data_starter/` is committed in full.
