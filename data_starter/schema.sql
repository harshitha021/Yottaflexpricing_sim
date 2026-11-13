CREATE TABLE Product (
  sku TEXT NOT NULL,
  product_name TEXT NOT NULL,
  category TEXT NOT NULL,
  brand TEXT NOT NULL,
  uom TEXT NOT NULL,
  currency TEXT NOT NULL,
  launch_date TEXT NOT NULL,
  status TEXT NOT NULL,
  discontinued_date TEXT,
  list_price REAL NOT NULL,
  price_floor_abs REAL NOT NULL,
  price_ceiling REAL NOT NULL,
  min_margin_pct REAL NOT NULL,
  lead_time_days INTEGER NOT NULL,
  PRIMARY KEY (sku)
);

CREATE TABLE AnnualPriceHistory (
  aph_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  year INTEGER NOT NULL,
  ref_price REAL NOT NULL,
  prev_year_price REAL NOT NULL,
  yoy_price_pct REAL NOT NULL,
  ref_cost REAL NOT NULL,
  prev_year_cost REAL NOT NULL,
  yoy_cost_pct REAL NOT NULL,
  PRIMARY KEY (aph_id),
  FOREIGN KEY (sku) REFERENCES Product(sku)
);

CREATE TABLE PriceGradient (
  sku TEXT NOT NULL,
  basis_start_year INTEGER NOT NULL,
  basis_end_year INTEGER NOT NULL,
  years_of_history INTEGER NOT NULL,
  avg_yoy_price_pct REAL NOT NULL,
  price_cagr_5y REAL NOT NULL,
  max_yoy_price_pct REAL NOT NULL,
  min_yoy_price_pct REAL NOT NULL,
  yoy_price_stdev REAL NOT NULL,
  cost_cagr_5y REAL NOT NULL,
  last_ref_price REAL NOT NULL,
  gradient_ceiling REAL NOT NULL,
  PRIMARY KEY (sku),
  FOREIGN KEY (sku) REFERENCES Product(sku)
);

CREATE TABLE CostRecord (
  cost_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  cost_month TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT NOT NULL,
  unit_cost REAL NOT NULL,
  prev_unit_cost REAL,
  cost_change_pct REAL,
  cost_change_reason TEXT NOT NULL,
  PRIMARY KEY (cost_id),
  FOREIGN KEY (sku) REFERENCES Product(sku)
);

CREATE TABLE Promotion (
  promo_id TEXT NOT NULL,
  promo_name TEXT NOT NULL,
  promo_type TEXT NOT NULL,
  stack_group TEXT NOT NULL,
  discount_pct REAL,
  discount_amt REAL,
  coupon_code TEXT,
  scope_category TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  created_date TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (promo_id)
);

CREATE TABLE PromotionRule (
  rule_id TEXT NOT NULL,
  promo_id TEXT NOT NULL,
  rule_type TEXT NOT NULL,
  rule_value REAL NOT NULL,
  PRIMARY KEY (rule_id),
  FOREIGN KEY (promo_id) REFERENCES Promotion(promo_id)
);

CREATE TABLE PromotionProduct (
  promo_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  added_date TEXT NOT NULL,
  PRIMARY KEY (promo_id, sku),
  FOREIGN KEY (promo_id) REFERENCES Promotion(promo_id),
  FOREIGN KEY (sku) REFERENCES Product(sku)
);

CREATE TABLE PromotionExclusion (
  promo_id_a TEXT NOT NULL,
  promo_id_b TEXT NOT NULL,
  exclusion_reason TEXT NOT NULL,
  PRIMARY KEY (promo_id_a, promo_id_b),
  FOREIGN KEY (promo_id_a) REFERENCES Promotion(promo_id),
  FOREIGN KEY (promo_id_b) REFERENCES Promotion(promo_id)
);

CREATE TABLE PromotionEvent (
  event_id TEXT NOT NULL,
  promo_id TEXT NOT NULL,
  event_seq INTEGER NOT NULL,
  event_date TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  PRIMARY KEY (event_id),
  FOREIGN KEY (promo_id) REFERENCES Promotion(promo_id)
);

CREATE TABLE CompetitorObservation (
  obs_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  competitor_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  competitor_price REAL NOT NULL,
  in_stock INTEGER NOT NULL,
  source TEXT NOT NULL,
  source_lag_hours REAL NOT NULL,
  PRIMARY KEY (obs_id),
  FOREIGN KEY (sku) REFERENCES Product(sku)
);

CREATE TABLE InventoryLot (
  lot_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  received_date TEXT NOT NULL,
  received_units INTEGER NOT NULL,
  source TEXT NOT NULL,
  unit_cost REAL NOT NULL,
  remaining_units INTEGER NOT NULL,
  lot_status TEXT NOT NULL,
  PRIMARY KEY (lot_id),
  FOREIGN KEY (sku) REFERENCES Product(sku)
);

CREATE TABLE InventorySnapshot (
  snapshot_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  snapshot_date TEXT NOT NULL,
  opening_on_hand INTEGER NOT NULL,
  units_received INTEGER NOT NULL,
  demand_units INTEGER NOT NULL,
  units_sold INTEGER NOT NULL,
  lost_sales_units INTEGER NOT NULL,
  closing_on_hand INTEGER NOT NULL,
  on_order_units INTEGER NOT NULL,
  stockout_flag INTEGER NOT NULL,
  avg_demand_7d REAL NOT NULL,
  days_of_cover REAL NOT NULL,
  oldest_stock_age_days INTEGER NOT NULL,
  slow_moving_units INTEGER NOT NULL,
  aged_units INTEGER NOT NULL,
  stock_age_class TEXT NOT NULL,
  PRIMARY KEY (snapshot_id),
  FOREIGN KEY (sku) REFERENCES Product(sku)
);

CREATE TABLE PriceDecision (
  decision_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  decision_date TEXT NOT NULL,
  decided_at TEXT NOT NULL,
  trigger TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT NOT NULL,
  cost_id TEXT NOT NULL,
  unit_cost REAL NOT NULL,
  price_before REAL NOT NULL,
  on_hand_units INTEGER NOT NULL,
  avg_daily_demand_7d REAL NOT NULL,
  days_of_cover REAL NOT NULL,
  competitor_obs_id TEXT,
  competitor_price REAL,
  competitor_obs_age_days REAL,
  effective_floor REAL NOT NULL,
  price_ceiling REAL NOT NULL,
  gradient_ref_price REAL NOT NULL,
  gradient_ceiling REAL NOT NULL,
  min_margin_pct REAL NOT NULL,
  candidate_base_price REAL NOT NULL,
  base_price REAL NOT NULL,
  promo_discount_amt REAL NOT NULL,
  net_price REAL NOT NULL,
  margin_pct REAL NOT NULL,
  guardrail_flags TEXT,
  reason_code TEXT NOT NULL,
  outcome TEXT NOT NULL,
  PRIMARY KEY (decision_id),
  FOREIGN KEY (sku) REFERENCES Product(sku),
  FOREIGN KEY (cost_id) REFERENCES CostRecord(cost_id),
  FOREIGN KEY (competitor_obs_id) REFERENCES CompetitorObservation(obs_id)
);

CREATE TABLE PriceHistory (
  price_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  price_date TEXT NOT NULL,
  base_price REAL NOT NULL,
  promo_discount_amt REAL NOT NULL,
  net_price REAL NOT NULL,
  applied_promo_ids TEXT,
  price_event TEXT NOT NULL,
  change_reason_code TEXT,
  decision_id TEXT,
  PRIMARY KEY (price_id),
  FOREIGN KEY (sku) REFERENCES Product(sku),
  FOREIGN KEY (decision_id) REFERENCES PriceDecision(decision_id)
);

CREATE TABLE ProductBundle (
  bundle_id TEXT NOT NULL,
  primary_sku TEXT NOT NULL,
  secondary_sku TEXT NOT NULL,
  bundle_discount_pct REAL NOT NULL,
  primary_unit_price REAL NOT NULL,
  secondary_unit_price REAL NOT NULL,
  individual_total_price REAL NOT NULL,
  bundle_price REAL NOT NULL,
  combined_cost REAL NOT NULL,
  bundle_margin_pct REAL NOT NULL,
  required_margin_pct REAL NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT NOT NULL,
  bundle_status TEXT NOT NULL,
  rejection_reason TEXT,
  created_at TEXT NOT NULL,
  primary_avg_demand_30d REAL NOT NULL,
  primary_demand_threshold REAL NOT NULL,
  primary_sellable_units INTEGER NOT NULL,
  secondary_sellable_units INTEGER NOT NULL,
  max_bundle_units INTEGER NOT NULL,
  secondary_oldest_age_days INTEGER NOT NULL,
  secondary_stock_age_class TEXT NOT NULL,
  secondary_slow_units INTEGER NOT NULL,
  secondary_aged_units INTEGER NOT NULL,
  PRIMARY KEY (bundle_id),
  FOREIGN KEY (primary_sku) REFERENCES Product(sku),
  FOREIGN KEY (secondary_sku) REFERENCES Product(sku)
);

CREATE TABLE Orders (
  order_id TEXT NOT NULL,
  order_date TEXT NOT NULL,
  sku TEXT NOT NULL,
  price_id TEXT NOT NULL,
  decision_id TEXT,
  channel TEXT NOT NULL,
  customer_segment TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit_base_price REAL NOT NULL,
  unit_net_price REAL NOT NULL,
  unit_cost REAL NOT NULL,
  line_total REAL NOT NULL,
  order_status TEXT NOT NULL,
  bundle_order_id TEXT,
  PRIMARY KEY (order_id),
  FOREIGN KEY (sku) REFERENCES Product(sku),
  FOREIGN KEY (price_id) REFERENCES PriceHistory(price_id),
  FOREIGN KEY (decision_id) REFERENCES PriceDecision(decision_id),
  FOREIGN KEY (bundle_order_id) REFERENCES BundleOrder(bundle_order_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE BundleOrder (
  bundle_order_id TEXT NOT NULL,
  bundle_id TEXT NOT NULL,
  order_id TEXT NOT NULL,
  secondary_order_id TEXT NOT NULL,
  order_date TEXT NOT NULL,
  channel TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  bundle_selling_price REAL NOT NULL,
  total_revenue REAL NOT NULL,
  total_cost REAL NOT NULL,
  gross_profit REAL NOT NULL,
  aged_units_cleared INTEGER NOT NULL,
  PRIMARY KEY (bundle_order_id),
  FOREIGN KEY (bundle_id) REFERENCES ProductBundle(bundle_id),
  FOREIGN KEY (order_id) REFERENCES Orders(order_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (secondary_order_id) REFERENCES Orders(order_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE DecisionPromotion (
  decision_id TEXT NOT NULL,
  promo_id TEXT NOT NULL,
  evaluation_status TEXT NOT NULL,
  rejection_reason TEXT,
  apply_sequence INTEGER,
  discount_amt REAL NOT NULL,
  PRIMARY KEY (decision_id, promo_id),
  FOREIGN KEY (decision_id) REFERENCES PriceDecision(decision_id),
  FOREIGN KEY (promo_id) REFERENCES Promotion(promo_id)
);
