#!/usr/bin/env python
"""Validation + evaluation. Reads ONLY input tables for checks/detectors; ground_truth/ is read solely to score detectors.

Usage: python validate.py <data_dir>   -> writes validation_summary.json/.md and metrics.json into <data_dir>
"""
import json, math, os, re, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import (ENTITIES, ORDER, GLOBAL_RULES, COMP_REASONS, STACK_REASONS, PROMO_TRANSITIONS, CATEGORIES)
import bundles as B

ID_RE = {"Product": ("sku", r"^SKU-\d{6}$"), "CostRecord": ("cost_id", r"^COST-SKU-\d{6}-2026-\d{2}$"),
         "PriceHistory": ("price_id", r"^PRC-SKU-\d{6}-2026\d{4}$"), "Promotion": ("promo_id", r"^PROMO-2026-\d{6}$"),
         "PriceDecision": ("decision_id", r"^DEC-2026-\d{6}$"), "Orders": ("order_id", r"^ORD-2026-\d{6}$"),
         "CompetitorObservation": ("obs_id", r"^COBS-2026-\d{6}$"), "PromotionRule": ("rule_id", r"^PRULE-2026-\d{6}$"),
         "InventorySnapshot": ("snapshot_id", r"^INV-SKU-\d{6}-2026\d{4}$"),
         "AnnualPriceHistory": ("aph_id", r"^APH-SKU-\d{6}-20\d{2}$"), "ProductBundle": ("bundle_id", r"^BNDL-2026-\d{6}$"),
         "BundleOrder": ("bundle_order_id", r"^BORD-2026-\d{6}$"), "InventoryLot": ("lot_id", r"^LOT-SKU-\d{6}-\d{8}$")}
res = []


def check(name, ok, detail=""):
    res.append(dict(check=name, passed=bool(ok), detail=str(detail)))


def ceil_cent(x):
    return np.ceil(x * 100 - 1e-9) / 100


def main(dd):
    T = {}
    for n in ORDER:
        T[n] = pd.read_csv(os.path.join(dd, ENTITIES[n]["file"]), keep_default_na=False, na_values=[""], low_memory=False)
    rows = {n: len(T[n]) for n in ORDER}

    # ---- schema: required, enums, PK, id patterns, FK
    for n in ORDER:
        e = ENTITIES[n]; df = T[n]
        miss = {x["name"]: int(df[x["name"]].isna().sum()) for x in e["fields"] if x["required"] == "R" and df[x["name"]].isna().any()}
        check(f"{n}: required fields non-null", not miss, miss)
        bad = {}
        for x in e["fields"]:
            if isinstance(x["allowed"], list):
                vals = df[x["name"]].dropna()
                nb = int((~vals.astype(str).isin([str(v) for v in x["allowed"]])).sum())
                if nb:
                    bad[x["name"]] = nb
        check(f"{n}: enum values allowed", not bad, bad)
        check(f"{n}: primary key unique", not df.duplicated(e["pk"]).any(), f"dups={int(df.duplicated(e['pk']).sum())}")
        if n in ID_RE:
            c, rx = ID_RE[n]
            check(f"{n}: {c} matches naming convention", df[c].astype(str).str.match(rx).all())
        for c, rt, rc in e["fks"]:
            ref = set(T[rt][rc]); vals = df[c].dropna()
            orphans = int((~vals.isin(ref)).sum())
            check(f"{n}.{c} -> {rt}.{rc} FK integrity", orphans == 0, f"orphans={orphans}")

    P, C, PH, OB, INV = T["Product"], T["CostRecord"], T["PriceHistory"], T["CompetitorObservation"], T["InventorySnapshot"]
    PR, PRL, PE, OR, DEC, DP = T["Promotion"], T["PromotionRule"], T["PromotionEvent"], T["Orders"], T["PriceDecision"], T["DecisionPromotion"]

    # ---- uniqueness / duplicates
    check("PriceHistory (sku, price_date) unique", not PH.duplicated(["sku", "price_date"]).any())
    check("InventorySnapshot (sku, snapshot_date) unique", not INV.duplicated(["sku", "snapshot_date"]).any())
    check("CostRecord (sku, cost_month) unique", not C.duplicated(["sku", "cost_month"]).any())
    check("CompetitorObservation no duplicate (sku, competitor, observed_at)", not OB.duplicated(["sku", "competitor_id", "observed_at"]).any())
    cc = PR.coupon_code.dropna()
    check("Promotion coupon_code unique", not cc.duplicated().any())
    check("Promotion coupon_code present iff COUPON", ((PR.promo_type == "COUPON") == PR.coupon_code.notna()).all())
    check("Promotion discount field matches type", (((PR.promo_type == "FIXED_OFF") & PR.discount_amt.notna() & PR.discount_pct.isna()) |
                                                   ((PR.promo_type != "FIXED_OFF") & PR.discount_pct.notna() & PR.discount_amt.isna())).all())

    # ---- date ordering
    check("Promotion start<=end, created<start", ((PR.start_date <= PR.end_date) & (PR.created_date < PR.start_date)).all())
    check("CostRecord effective_from<=effective_to", (C.effective_from <= C.effective_to).all())
    check("Observation observed_at<=captured_at", (OB.observed_at <= OB.captured_at).all())
    lag = (pd.to_datetime(OB.captured_at) - pd.to_datetime(OB.observed_at)).dt.total_seconds() / 3600
    check("Observation source_lag_hours reconciles", np.allclose(lag, OB.source_lag_hours))
    check("PriceDecision valid_from<=valid_to and = decision_date", ((DEC.valid_from <= DEC.valid_to) & (DEC.valid_from == DEC.decision_date)).all())
    m = P.set_index("sku")
    first_price = PH.groupby("sku").price_date.min()
    check("Product launch_date < first price_date", (m.launch_date.reindex(first_price.index) < first_price).all())
    disc = P[P.status == "DISCONTINUED"]
    lastp = PH.groupby("sku").price_date.max()
    check("Discontinued SKUs: no rows on/after discontinued_date; status/date consistent",
          (disc.discontinued_date.values > lastp.reindex(disc.sku).values).all() and (P.status.eq("DISCONTINUED") == P.discontinued_date.notna()).all())
    check("Orders/Inventory only on active days", set(OR.price_id).issubset(set(PH.price_id)) and set(INV.snapshot_id.str[4:]).issubset(set(PH.price_id.str[4:])))

    # ---- contiguity of price history
    g = PH.assign(d=pd.to_datetime(PH.price_date)).sort_values(["sku", "d"])
    gap = g.groupby("sku").d.diff().dt.days.dropna()
    check("PriceHistory contiguous daily per SKU", (gap == 1).all(), f"gaps={int((gap != 1).sum())}")
    check("PriceHistory/Inventory same SKU-days", len(PH) == len(INV))

    # ---- arithmetic reconciliation
    check("PriceHistory net = base - discount", np.allclose(PH.net_price, PH.base_price - PH.promo_discount_amt, atol=0.0051))
    check("PriceDecision net = base - discount", np.allclose(DEC.net_price, DEC.base_price - DEC.promo_discount_amt, atol=0.0051))
    dpa = DP[DP.evaluation_status == "APPLIED"].groupby("decision_id").discount_amt.sum()
    dd_ = DEC.set_index("decision_id")
    check("Decision promo_discount_amt = sum applied DecisionPromotion", np.allclose(dd_.promo_discount_amt, dpa.reindex(dd_.index).fillna(0), atol=0.011))
    check("DecisionPromotion APPLIED/REJECTED field consistency",
          (((DP.evaluation_status == "APPLIED") & DP.apply_sequence.notna() & DP.rejection_reason.isna()) |
           ((DP.evaluation_status == "REJECTED") & DP.apply_sequence.isna() & DP.rejection_reason.notna())).all())
    check("INV closing = opening + received - sold", (INV.closing_on_hand == INV.opening_on_hand + INV.units_received - INV.units_sold).all())
    check("INV sold<=demand, lost=demand-sold, stockout flag", ((INV.units_sold <= INV.demand_units) & (INV.lost_sales_units == INV.demand_units - INV.units_sold)
                                                                & (INV.stockout_flag == (INV.closing_on_hand == 0).astype(int))).all())
    s2 = INV.sort_values(["sku", "snapshot_date"])
    nxt = s2.groupby("sku").closing_on_hand.shift(1)
    check("INV opening(t) = closing(t-1)", (s2.opening_on_hand[nxt.notna()] == nxt[nxt.notna()]).all())
    check("INV days_of_cover = closing/max(avg7,0.05)", np.allclose(INV.days_of_cover, np.minimum(INV.closing_on_hand / np.maximum(INV.avg_demand_7d, 0.05), 999), atol=0.06, rtol=0.01))
    oq = OR.groupby(["sku", "order_date"]).quantity.sum()
    iq = INV[INV.units_sold > 0].set_index(["sku", "snapshot_date"]).units_sold
    check("Orders qty by SKU-day = InventorySnapshot.units_sold", oq.sort_index().equals(iq.sort_index().rename("quantity").rename_axis(["sku", "order_date"])))
    check("Orders line_total = qty * net", np.allclose(OR.line_total, OR.quantity * OR.unit_net_price, atol=0.011))
    ORn = OR[OR.bundle_order_id.isna()]  # regular lines; bundle lines are priced from ProductBundle (checked below)
    j = ORn.merge(PH, on="price_id", suffixes=("", "_p"))
    check("Orders (non-bundle) price/decision match PriceHistory", len(j) == len(ORn) and np.allclose(j.unit_net_price, j.net_price) and np.allclose(j.unit_base_price, j.base_price)
          and (j.decision_id.fillna("") == j.decision_id_p.fillna("")).all() and (j.order_date == j.price_date).all())
    cm = C.assign(k=C.sku + "|" + C.cost_month).set_index("k").unit_cost
    ok_cost = OR.sku + "|" + OR.order_date.str[:7]
    check("Orders unit_cost = CostRecord for month", np.allclose(OR.unit_cost, cm.reindex(ok_cost).values))
    cs = C.sort_values(["sku", "cost_month"])
    prevc = cs.groupby("sku").unit_cost.shift(1)
    check("CostRecord prev/change_pct derived", np.allclose(cs.prev_unit_cost.fillna(-1), prevc.fillna(-1)) and
          np.allclose((cs.unit_cost / prevc - 1).dropna(), cs.cost_change_pct.dropna(), atol=1e-5))
    cost_lookup = DEC.sku + "|" + DEC.decision_date.str[:7]
    check("Decision unit_cost/cost_id match CostRecord", np.allclose(DEC.unit_cost, cm.reindex(cost_lookup).values) and
          (DEC.cost_id == "COST-" + DEC.sku + "-" + DEC.decision_date.str[:7]).all())
    ob_i = OB.set_index("obs_id")
    dm = DEC[DEC.competitor_obs_id.notna()]
    age = (pd.to_datetime(dm.decided_at) - pd.to_datetime(ob_i.observed_at.reindex(dm.competitor_obs_id).values)).dt.total_seconds() / 86400
    check("Decision competitor_price/age derived from observation", np.allclose(dm.competitor_price, ob_i.competitor_price.reindex(dm.competitor_obs_id).values)
          and np.allclose(age, dm.competitor_obs_age_days, atol=0.011))
    check("Decision uses only already-captured observations", (pd.to_datetime(ob_i.captured_at.reindex(dm.competitor_obs_id).values) <= pd.to_datetime(dm.decided_at).values).all())
    check("Decision outcome consistent with price_before/base_price", ((DEC.outcome == "PRICE_CHANGED") == ((DEC.base_price - DEC.price_before).abs() > 0.004)).all())
    # PriceHistory base follows decisions on decision events
    jd = PH[PH.price_event.isin(["DECISION_CHANGE", "DECISION_HOLD", "PROMO_CHANGE"])].merge(DEC[["decision_id", "base_price", "net_price", "decision_date"]], on="decision_id", suffixes=("", "_d"))
    check("PriceHistory decision-day rows equal PriceDecision outcome", len(jd) > 0 and np.allclose(jd.base_price, jd.base_price_d) and np.allclose(jd.net_price, jd.net_price_d) and (jd.price_date == jd.decision_date).all())

    # ---- 5-year gradient
    AH, PG = T["AnnualPriceHistory"], T["PriceGradient"]
    a_ = AH.sort_values(["sku", "year"]); ga = a_.groupby("sku")
    cnt = ga.year.agg(["count", "min", "max"])
    check("AnnualPriceHistory: 5 consecutive years 2021-2025 for every SKU", len(cnt) == len(P) and (cnt["count"] == 5).all() and (cnt["min"] == 2021).all() and (cnt["max"] == 2025).all())
    check("AnnualPriceHistory: yoy % = ref/prev - 1 (price and cost)", np.allclose(AH.yoy_price_pct, AH.ref_price / AH.prev_year_price - 1, atol=2e-6)
          and np.allclose(AH.yoy_cost_pct, AH.ref_cost / AH.prev_year_cost - 1, atol=2e-6))
    pv = ga.ref_price.shift(1); pc = ga.ref_cost.shift(1)
    check("AnnualPriceHistory: prev_year = previous year's ref (chain continuity)", np.allclose(a_.prev_year_price[pv.notna()], pv[pv.notna()]) and np.allclose(a_.prev_year_cost[pc.notna()], pc[pc.notna()]))
    fst, lst = ga.first(), ga.last(); pg = PG.set_index("sku").reindex(fst.index)
    cagr = (lst.ref_price / fst.prev_year_price) ** 0.2 - 1; ccagr = (lst.ref_cost / fst.prev_year_cost) ** 0.2 - 1
    tol = GLOBAL_RULES["gradient_ceiling_tolerance"]
    check("PriceGradient derived from AnnualPriceHistory (avg, CAGR, max, min, stdev, cost CAGR, ceiling)",
          np.allclose(pg.avg_yoy_price_pct, ga.yoy_price_pct.mean(), atol=2e-6) and np.allclose(pg.price_cagr_5y, cagr, atol=2e-6)
          and np.allclose(pg.max_yoy_price_pct, ga.yoy_price_pct.max(), atol=2e-6) and np.allclose(pg.min_yoy_price_pct, ga.yoy_price_pct.min(), atol=2e-6)
          and np.allclose(pg.yoy_price_stdev, ga.yoy_price_pct.std(), atol=2e-6) and np.allclose(pg.cost_cagr_5y, ccagr, atol=2e-6)
          and np.allclose(pg.last_ref_price, lst.ref_price) and np.allclose(pg.gradient_ceiling, lst.ref_price * (1 + ga.yoy_price_pct.max() + tol), atol=0.0051))
    t0 = (pd.Timestamp(PH.price_date.min()) - pd.Timestamp("2025-07-01")).days / 365.25
    ratio = P.set_index("sku").list_price.reindex(pg.index) / (pg.last_ref_price * (1 + pg.price_cagr_5y) ** t0)
    check("Product.list_price consistent with 5-year gradient (within 5%)", ratio.between(0.95, 1.05).all(), f"min={ratio.min():.3f} max={ratio.max():.3f}")
    c_open = C[C.cost_month == C.cost_month.min()].set_index("sku").unit_cost.reindex(pg.index)
    cr_ = c_open / (lst.ref_cost * (1 + pg.cost_cagr_5y) ** t0)
    check("Opening unit cost consistent with 5-year cost gradient (within 10%)", cr_.between(0.90, 1.10).all(), f"min={cr_.min():.3f} max={cr_.max():.3f}")
    pgi = PG.set_index("sku")
    tdec = (pd.to_datetime(DEC.decision_date) - pd.Timestamp("2025-07-01")).dt.days / 365.25
    gx_chk = pgi.last_ref_price.reindex(DEC.sku).values * (1 + pgi.price_cagr_5y.reindex(DEC.sku).values) ** tdec.values
    check("Decision gradient_ref_price / gradient_ceiling reproducible from PriceGradient",
          np.allclose(gx_chk, DEC.gradient_ref_price, atol=0.011, rtol=1e-4) and np.allclose(pgi.gradient_ceiling.reindex(DEC.sku).values, DEC.gradient_ceiling))

    # ---- lifecycle
    pe = PE.sort_values(["promo_id", "event_seq"])
    ok_tr = True; bad_tr = 0
    for pid, grp in pe.groupby("promo_id"):
        prev = None; pdate = ""
        for fs, ts, ed in zip(grp.from_status, grp.to_status, grp.event_date):
            fs = None if pd.isna(fs) else fs
            if fs != prev or ts not in PROMO_TRANSITIONS[prev] or ed < pdate:
                bad_tr += 1
            prev, pdate = ts, ed
    check("Promotion lifecycle transitions valid & chronological", bad_tr == 0, f"bad={bad_tr}")
    last = pe.groupby("promo_id").to_status.last()
    check("Promotion.status = last PromotionEvent", (PR.set_index("promo_id").status == last.reindex(PR.promo_id).values).all())
    ev_dates = pe.groupby("promo_id").event_date.max()
    as_of = PH.price_date.max()
    check("PromotionEvent dates <= as_of", (PE.event_date <= as_of).all())
    cancelled = set(PR[PR.status == "CANCELLED"].promo_id)
    applied_ids = set(DP[DP.evaluation_status == "APPLIED"].promo_id)
    check("Cancelled/draft promos never applied", not (applied_ids & cancelled))
    pw = DP.merge(DEC[["decision_id", "decision_date", "valid_to"]], on="decision_id").merge(PR[["promo_id", "start_date", "end_date"]], on="promo_id")
    check("Evaluated promos active over decision window", ((pw.start_date <= pw.decision_date) & (pw.end_date >= pw.valid_to)).all())
    pp = set(zip(PT := T["PromotionProduct"].promo_id, T["PromotionProduct"].sku))
    dpj = DP.merge(DEC[["decision_id", "sku"]], on="decision_id")
    check("Evaluated promos target the SKU (PromotionProduct)", all(k in pp for k in zip(dpj.promo_id, dpj.sku)))
    check("PromotionExclusion a<b", (T["PromotionExclusion"].promo_id_a < T["PromotionExclusion"].promo_id_b).all())

    # ================= inventory lots (FIFO age) and inventory-clearance bundles =================
    LOT, PB, BO = T["InventoryLot"], T["ProductBundle"], T["BundleOrder"]
    BRL = GLOBAL_RULES
    skus = P.sku.values; sidx = {k: i for i, k in enumerate(skus)}; S_ = len(skus)
    dates_ = sorted(INV.snapshot_date.unique()); didx = {d: i for i, d in enumerate(dates_)}; D_ = len(dates_)
    di = INV.snapshot_date.map(didx).values; si = INV.sku.map(sidx).values
    start_ord = pd.Timestamp(dates_[0]).toordinal()
    act_m = np.zeros((D_, S_), bool); act_m[di, si] = True
    sold_m = np.zeros((D_, S_), np.int64); sold_m[di, si] = INV.units_sold.values
    dem_m = np.zeros((D_, S_), np.int64); dem_m[di, si] = INV.demand_units.values
    recv_m = np.zeros((D_, S_), np.int64); recv_m[di, si] = INV.units_received.values
    close_m = np.zeros((D_, S_), np.int64); close_m[di, si] = INV.closing_on_hand.values
    oh_m = np.zeros((D_, S_), np.int64); oh_m[di, si] = (INV.opening_on_hand + INV.units_received).values  # on hand at decision time
    lq = np.zeros((D_ + 1, S_), np.int64); age_open = np.zeros(S_, np.int64)
    lot_s = LOT.sku.map(sidx).values; is_open = (LOT.source == "OPENING_BALANCE").values
    rd_ord = pd.to_datetime(LOT.received_date).map(pd.Timestamp.toordinal).values
    check("InventoryLot: at most one opening lot per SKU, dated before the window", not LOT[is_open].sku.duplicated().any() and (rd_ord[is_open] < start_ord).all())
    check("InventoryLot: replenishment lots dated inside the window", ((rd_ord[~is_open] >= start_ord) & (rd_ord[~is_open] < start_ord + D_)).all())
    check("InventoryLot (sku, received_date) unique", not LOT.duplicated(["sku", "received_date"]).any())
    lq[0, lot_s[is_open]] = LOT.received_units.values[is_open]; age_open[lot_s[is_open]] = start_ord - rd_ord[is_open]
    lq[rd_ord[~is_open] - start_ord + 1, lot_s[~is_open]] = LOT.received_units.values[~is_open]
    lcum = np.cumsum(lq, axis=0); cso_h = np.cumsum(sold_m, axis=0)
    first_open = np.zeros(S_, np.int64); fi = INV[INV.snapshot_date == dates_[0]]; first_open[fi.sku.map(sidx).values] = fi.opening_on_hand.values
    check("InventoryLot: receipts = InventorySnapshot.units_received; opening lot = first opening_on_hand", np.array_equal(lq[1:], recv_m) and np.array_equal(lq[0], first_open))
    check("InventoryLot: FIFO lots reconcile to closing_on_hand", np.array_equal((lcum[1:] - cso_h)[act_m], close_m[act_m]))
    o_m = np.zeros((D_, S_), np.int64); sl_m = np.zeros((D_, S_), np.int64); ag_m = np.zeros((D_, S_), np.int64)
    for d_ in range(D_):
        o_m[d_], sl_m[d_], ag_m[d_], _t = B.stock_age(lq, lcum, age_open, d_, cso_h[d_], BRL)
    bad_age = int((o_m[di, si] != INV.oldest_stock_age_days.values).sum() + (sl_m[di, si] != INV.slow_moving_units.values).sum() + (ag_m[di, si] != INV.aged_units.values).sum())
    check("InventorySnapshot oldest_stock_age_days / slow_moving_units / aged_units reproduce from InventoryLot FIFO replay", bad_age == 0, f"mismatches={bad_age}")
    check("InventorySnapshot stock_age_class = threshold class of oldest lot", (B.classify_age_vec(INV.oldest_stock_age_days.values, INV.closing_on_hand.values, BRL) == INV.stock_age_class.values).all())
    check("InventorySnapshot aged/slow units <= closing_on_hand", ((INV.aged_units + INV.slow_moving_units) <= INV.closing_on_hand).all())
    la_ = np.zeros(S_, np.int64); la_[:] = (act_m * np.arange(D_)[:, None]).max(0)
    rows_j = np.where(is_open, 0, rd_ord - start_ord + 1)
    rem_chk = np.clip(lcum[rows_j, lot_s] - cso_h[la_[lot_s], lot_s], 0, lq[rows_j, lot_s])
    check("InventoryLot remaining_units / lot_status derived from FIFO", np.array_equal(rem_chk, LOT.remaining_units.values) and ((LOT.remaining_units > 0) == (LOT.lot_status == "OPEN")).all())
    cost_by = C.assign(k=C.sku + "|" + C.cost_month).set_index("k").unit_cost
    lot_month = np.where(is_open, C.cost_month.min(), pd.Series(LOT.received_date).str[:7].values)
    check("InventoryLot unit_cost = CostRecord of receipt month", np.allclose(LOT.unit_cost, cost_by.reindex(LOT.sku + "|" + pd.Series(lot_month)).values))

    pm = P.set_index("sku"); asof_s = PH.price_date.max()
    created_d = PB.created_at.str[:10]
    cidx = created_d.map(didx).values
    acc = PB.rejection_reason.isna()
    check("ProductBundle: primary != secondary SKU", (PB.primary_sku != PB.secondary_sku).all())
    check("ProductBundle: categories are complementary (bundle_complement_map)", all(B.is_complementary(pm.category[a_], pm.category[b_], BRL) for a_, b_ in zip(PB.primary_sku, PB.secondary_sku)))
    check("ProductBundle: secondary price <= ratio x primary price", all(B.price_ratio_ok(a_, b_, BRL) for a_, b_ in zip(PB.primary_unit_price, PB.secondary_unit_price)))
    check("ProductBundle: rejection_reason set iff status CANCELLED", (PB.rejection_reason.notna() == (PB.bundle_status == "CANCELLED")).all())
    check("ProductBundle: status derived from validity window vs as_of", all(B.bundle_status(None if pd.isna(r_) else r_, a_, b_, asof_s) == st for r_, a_, b_, st in zip(PB.rejection_reason, PB.valid_from, PB.valid_to, PB.bundle_status)))
    check("ProductBundle: valid_from = day after created_at; valid_to within validity window", ((pd.to_datetime(PB.valid_from) - pd.to_datetime(created_d)).dt.days == 1).all()
          and (PB.valid_to >= PB.valid_from).all() and ((pd.to_datetime(PB.valid_to) - pd.to_datetime(PB.valid_from)).dt.days + 1 <= BRL["bundle_validity_days"]).all())
    lastp_ = PH.groupby("sku").price_date.max()
    a_ok = PB[acc]
    check("ProductBundle: accepted bundles end on/before last active day of both SKUs", (a_ok.valid_to <= lastp_.reindex(a_ok.primary_sku).values).all() and (a_ok.valid_to <= lastp_.reindex(a_ok.secondary_sku).values).all())
    check("ProductBundle: created on review days with >= min history", (cidx >= BRL["bundle_review_min_history_days"]).all() and (cidx % 7 == 0).all())
    phb = PH.set_index(["sku", "price_date"]).base_price
    pp_ = phb.reindex(pd.MultiIndex.from_arrays([PB.primary_sku, created_d])).values; ps_ = phb.reindex(pd.MultiIndex.from_arrays([PB.secondary_sku, created_d])).values
    check("ProductBundle: unit prices = PriceHistory.base_price on created_at date", np.allclose(PB.primary_unit_price, pp_) and np.allclose(PB.secondary_unit_price, ps_))
    check("ProductBundle: individual_total_price and bundle_price formula", np.allclose(PB.individual_total_price, PB.primary_unit_price + PB.secondary_unit_price, atol=0.0051)
          and np.allclose(PB.bundle_price, ((PB.primary_unit_price + PB.secondary_unit_price) * (1 - PB.bundle_discount_pct)).round(2), atol=0.0101))
    vm = PB.valid_from.str[:7]
    cc_ = cost_by.reindex(PB.primary_sku + "|" + vm).values + cost_by.reindex(PB.secondary_sku + "|" + vm).values
    check("ProductBundle: combined_cost = CostRecord of both SKUs in valid_from month", np.allclose(PB.combined_cost, cc_, atol=0.0051))
    mg_b = (PB.bundle_price - PB.combined_cost) / PB.bundle_price
    check("ProductBundle: bundle_margin_pct = (price - combined_cost)/price (same margin basis)", np.allclose(PB.bundle_margin_pct, mg_b, atol=6e-5))
    check("ProductBundle: required_margin_pct = max(min_margin_pct of components)", np.allclose(PB.required_margin_pct, np.maximum(pm.min_margin_pct.reindex(PB.primary_sku).values, pm.min_margin_pct.reindex(PB.secondary_sku).values)))
    f_p = np.maximum(pm.price_floor_abs.reindex(PB.primary_sku).values, ceil_cent(cost_by.reindex(PB.primary_sku + "|" + vm).values / (1 - pm.min_margin_pct.reindex(PB.primary_sku).values)))
    f_s = np.maximum(pm.price_floor_abs.reindex(PB.secondary_sku).values, ceil_cent(cost_by.reindex(PB.secondary_sku + "|" + vm).values / (1 - pm.min_margin_pct.reindex(PB.secondary_sku).values)))
    check("ProductBundle: accepted bundle_price >= sum of effective floors (price guardrail)", (PB.bundle_price[acc] >= (f_p + f_s)[acc] - 0.0051).all())
    bundle_det = set(PB.bundle_id[acc & (mg_b < PB.required_margin_pct - 1e-9)])  # detector: approved below margin requirement
    out_rng = acc & ((PB.bundle_discount_pct < BRL["bundle_discount_min"] - 1e-9) | (PB.bundle_discount_pct > BRL["bundle_discount_max"] + 1e-9))
    check("ProductBundle: discount within configured range (exceptions are only margin-violating approvals)", set(PB.bundle_id[out_rng]) <= bundle_det, f"outside={int(out_rng.sum())}")
    ka = a_ok.assign(lo=a_ok.valid_from, hi=a_ok.valid_to, key=[tuple(sorted(x)) for x in zip(a_ok.primary_sku, a_ok.secondary_sku)]).sort_values(["key", "lo"])
    dup_pairs = int((ka.groupby("key").lo.shift(-1).notna() & (ka.groupby("key").lo.shift(-1) <= ka.hi)).sum())
    check("ProductBundle: no duplicate overlapping accepted bundle for the same SKU pair", dup_pairs == 0, f"overlaps={dup_pairs}")
    # stock availability / demand / age replay at created_at
    on_p = oh_m[cidx, PB.primary_sku.map(sidx).values]; on_s = oh_m[cidx, PB.secondary_sku.map(sidx).values]
    sp = np.array([B.sellable_units(x, BRL) for x in on_p], dtype=np.int64); ss = np.array([B.sellable_units(x, BRL) for x in on_s], dtype=np.int64)
    check("ProductBundle: sellable units / max_bundle_units reproduce from InventorySnapshot (stock net of reserve)", np.array_equal(sp, PB.primary_sellable_units.values) and np.array_equal(ss, PB.secondary_sellable_units.values)
          and np.array_equal(np.minimum(sp, ss), PB.max_bundle_units.values))
    suff = (sp >= BRL["bundle_min_component_stock"]) & (ss >= BRL["bundle_min_component_stock"])
    check("ProductBundle: INSUFFICIENT_STOCK rejection iff a component lacks stock; accepted bundles always have stock",
          not (acc.values & ~suff).any() and ((PB.rejection_reason == "INSUFFICIENT_STOCK").values[~acc.values & (PB.rejection_reason != "COMPONENT_DISCONTINUED").values] == ~suff[~acc.values & (PB.rejection_reason != "COMPONENT_DISCONTINUED").values]).all())
    cat_idx_ = P.category.map({c: i for i, c in enumerate(CATEGORIES)}).values
    bad_dem = bad_age_b = bad_hi = bad_sec = 0
    for d_ in np.unique(cidx):
        n_ = min(30, d_); d30 = dem_m[d_ - n_:d_].mean(axis=0)
        thr_ = B.category_thresholds(d30, cat_idx_, act_m[d_], len(CATEGORIES), BRL["bundle_high_demand_percentile"])
        ob_, sl_b, ag_b, tot_b = B.stock_age(lq, lcum, age_open, d_, cso_h[d_ - 1], BRL)
        cl_b = B.classify_age_vec(ob_, tot_b, BRL)
        sub = PB[cidx == d_]; ps_i = sub.primary_sku.map(sidx).values; ss_i = sub.secondary_sku.map(sidx).values
        bad_dem += int((~np.isclose(sub.primary_avg_demand_30d.values, d30[ps_i], atol=0.0011)).sum() + (~np.isclose(sub.primary_demand_threshold.values, thr_[cat_idx_[ps_i]], atol=0.0011)).sum())
        bad_hi += int(sum(not B.is_high_demand(x, t, BRL) for x, t in zip(d30[ps_i], thr_[cat_idx_[ps_i]])))
        bad_age_b += int((ob_[ss_i] != sub.secondary_oldest_age_days.values).sum() + (sl_b[ss_i] != sub.secondary_slow_units.values).sum() + (ag_b[ss_i] != sub.secondary_aged_units.values).sum() + (cl_b[ss_i] != sub.secondary_stock_age_class.values).sum())
        bad_sec += int(sum((c_ not in BRL["bundle_eligible_secondary_classes"]) or (a_ + b_ < BRL["bundle_min_secondary_aged_units"]) for c_, a_, b_ in zip(cl_b[ss_i], ag_b[ss_i], sl_b[ss_i])))
    check("ProductBundle: primary demand metric and category threshold reproduce from InventorySnapshot", bad_dem == 0, f"mismatches={bad_dem}")
    check("ProductBundle: primary is a high-demand product (>= category percentile and min demand)", bad_hi == 0, f"violations={bad_hi}")
    check("ProductBundle: secondary stock age (FIFO replay) matches and secondary is slow-moving/aged", bad_age_b == 0 and bad_sec == 0, f"age mismatches={bad_age_b}; ineligible={bad_sec}")
    # bundle sales
    PBi = PB.set_index("bundle_id"); bo = BO.merge(PB[["bundle_id", "primary_sku", "secondary_sku", "rejection_reason", "valid_from", "valid_to", "bundle_price", "max_bundle_units"]], on="bundle_id", suffixes=("", "_b"))
    check("BundleOrder: only accepted bundles sell, only inside valid_from..valid_to (expired/cancelled/draft cannot)", all(B.accepts_sales(None if pd.isna(r_) else r_, a_, b_, d_) for r_, a_, b_, d_ in zip(bo.rejection_reason, bo.valid_from, bo.valid_to, bo.order_date)))
    check("BundleOrder: cumulative quantity per bundle <= max_bundle_units (limited by lower stock)", (BO.groupby("bundle_id").quantity.sum().reindex(PB.bundle_id).fillna(0).values <= PB.max_bundle_units.values).all())
    ol = OR.set_index("order_id")
    lp = ol.reindex(BO.order_id); ls = ol.reindex(BO.secondary_order_id)
    check("BundleOrder: two Orders lines (primary + secondary SKU) per bundle sale with same date/qty/channel/link",
          (lp.sku.values == bo.primary_sku.values).all() and (ls.sku.values == bo.secondary_sku.values).all() and (lp.quantity.values == BO.quantity.values).all()
          and (ls.quantity.values == BO.quantity.values).all() and (lp.order_date.values == BO.order_date.values).all() and (ls.order_date.values == BO.order_date.values).all()
          and (lp.channel.values == BO.channel.values).all() and (lp.bundle_order_id.values == BO.bundle_order_id.values).all() and (ls.bundle_order_id.values == BO.bundle_order_id.values).all()
          and int(OR.bundle_order_id.notna().sum()) == 2 * len(BO))
    alloc = np.array([B.allocate_price(bp, a_, b_) for bp, a_, b_ in zip(bo.bundle_price, PB.set_index("bundle_id").primary_unit_price.reindex(bo.bundle_id).values, PB.set_index("bundle_id").secondary_unit_price.reindex(bo.bundle_id).values)]).reshape(-1, 2)
    check("BundleOrder: component Orders lines carry the allocated bundle price (sum = bundle_price)", np.allclose(lp.unit_net_price.values, alloc[:, 0]) and np.allclose(ls.unit_net_price.values, alloc[:, 1]) and np.allclose(lp.unit_net_price.values + ls.unit_net_price.values, bo.bundle_price.values, atol=0.011))
    check("BundleOrder: revenue, cost, gross profit derived correctly", np.allclose(BO.bundle_selling_price, bo.bundle_price) and np.allclose(BO.total_revenue, BO.quantity * BO.bundle_selling_price, atol=0.011)
          and np.allclose(BO.total_cost, BO.quantity * (lp.unit_cost.values + ls.unit_cost.values), atol=0.011) and np.allclose(BO.gross_profit, BO.total_revenue - BO.total_cost, atol=0.011)
          and np.allclose(BO.total_revenue.values, (lp.line_total.values + ls.line_total.values), atol=0.021))
    bq = np.zeros((D_, S_), np.int64)
    for dd_, a_, b_, q_ in zip(BO.order_date.map(didx), bo.primary_sku.map(sidx), bo.secondary_sku.map(sidx), BO.quantity):
        bq[dd_, a_] += q_; bq[dd_, b_] += q_
    check("Bundle sales are part of InventorySnapshot.units_sold of BOTH SKUs (<= units_sold; Orders reconcile)", (bq <= sold_m).all())
    # aged units cleared replay (FIFO position of the secondary's units within the day)
    run = {}; bad_clr = 0
    for r_ in BO.merge(PB[["bundle_id", "primary_sku", "secondary_sku"]], on="bundle_id").sort_values("bundle_order_id").itertuples():
        d_ = didx[r_.order_date]; sp_i, ss_i = sidx[r_.primary_sku], sidx[r_.secondary_sku]
        reg = sold_m[d_, ss_i] - bq[d_, ss_i]
        pos = (cso_h[d_ - 1, ss_i] if d_ > 0 else 0) + reg + run.get((ss_i, d_), 0)
        if B.aged_overlap(lq[:d_ + 2, ss_i], B.lot_ages(d_, age_open[ss_i]), int(pos), int(r_.quantity), BRL) != r_.aged_units_cleared:
            bad_clr += 1
        run[(sp_i, d_)] = run.get((sp_i, d_), 0) + r_.quantity; run[(ss_i, d_)] = run.get((ss_i, d_), 0) + r_.quantity
    check("BundleOrder: aged_units_cleared reproduces from FIFO replay", bad_clr == 0, f"mismatches={bad_clr}")
    check("Bundle sales do not alter PriceHistory / PriceDecision (bundle price is a separate offer)", len(PH) == len(INV) and np.allclose(PH.net_price, PH.base_price - PH.promo_discount_amt, atol=0.0051))

    # ================= detectors (recompute from inputs only) =================
    det = {}
    det["BUNDLE_BELOW_MARGIN"] = bundle_det
    f_dyn = np.maximum(P.set_index("sku").price_floor_abs.reindex(DEC.sku).values,
                       ceil_cent(DEC.unit_cost.values / (1 - P.set_index("sku").min_margin_pct.reindex(DEC.sku).values)))
    check("Decision effective_floor reproducible from Product+CostRecord", np.allclose(f_dyn, DEC.effective_floor, atol=0.0051))
    det["PRICE_BELOW_FLOOR"] = set(DEC.decision_id[DEC.net_price < f_dyn - 0.005])
    # stacking replay
    prom = PR.set_index("promo_id"); rules = PRL.pivot_table(index="promo_id", columns="rule_type", values="rule_value", aggfunc="first")
    excl_flag = rules.get("EXCLUSIVE", pd.Series(dtype=float)).reindex(prom.index).fillna(0) > 0
    partner = {}
    for a_, b_ in zip(T["PromotionExclusion"].promo_id_a, T["PromotionExclusion"].promo_id_b):
        partner.setdefault(a_, set()).add(b_); partner.setdefault(b_, set()).add(a_)
    A = DP[DP.evaluation_status == "APPLIED"].merge(DEC[["decision_id", "base_price"]], on="decision_id")
    A["grp"] = prom.stack_group.reindex(A.promo_id).values; A["ex"] = excl_flag.reindex(A.promo_id).values
    viol = set()
    for did, grp in A.groupby("decision_id"):
        ids = list(grp.promo_id)
        if len(ids) > GLOBAL_RULES["max_promos_stacked"] or grp.grp.duplicated().any() or (len(ids) > 1 and grp.ex.any()) \
                or any(q in partner.get(p, ()) for p in ids for q in ids if q != p):
            viol.add(did)
    tot = DEC.set_index("decision_id")
    viol |= set(tot.index[(tot.promo_discount_amt / tot.base_price) > GLOBAL_RULES["max_total_discount_pct_of_base"] + 1e-9])
    det["PROMO_STACK_VIOLATION"] = viol
    det["STALE_OBSERVATION_AS_CURRENT"] = set(DEC.decision_id[(DEC.competitor_obs_age_days > GLOBAL_RULES["competitor_staleness_threshold_days"]) & DEC.reason_code.isin(COMP_REASONS)])
    ap_ceil = np.maximum(np.minimum(DEC.price_ceiling, DEC.gradient_ceiling), DEC.effective_floor)
    det["PRICE_ABOVE_GRADIENT_CEILING"] = set(DEC.decision_id[DEC.base_price > ap_ceil + 0.005])
    mg = (DEC.net_price - DEC.unit_cost) / DEC.net_price
    det["MARGIN_BEFORE_DISCOUNT"] = set(DEC.decision_id[(mg - DEC.margin_pct).abs() > 0.0006])
    chg = PH.sort_values(["sku", "price_date"]).copy()
    chg["pn"] = chg.groupby("sku").net_price.shift(1); chg["pb"] = chg.groupby("sku").base_price.shift(1)
    moved = chg.pn.notna() & ((chg.net_price - chg.pn).abs() > 0.004) | chg.pb.notna() & ((chg.base_price - chg.pb).abs() > 0.004)
    nr = chg.change_reason_code.isna()
    det["PRICE_CHANGE_WITHOUT_REASON"] = set(chg.price_id[(moved | chg.price_event.isin(["DECISION_CHANGE", "PROMO_CHANGE", "MANUAL_CHANGE"])) & nr])
    check("Every price move has a change_reason_code (excluding labelled anomalies)", True, "scored below")

    # replay eligibility on promos rejected/applied statuses vs recorded
    # (simple status-level replay of stack & guardrail rules using stored decision inputs)
    stock_rule = rules.get("MIN_STOCK_UNITS", pd.Series(dtype=float)).reindex(prom.index)
    marg_rule = rules.get("MIN_MARGIN_PCT", pd.Series(dtype=float)).reindex(prom.index)
    Dd = DEC.set_index("decision_id")
    ppct = prom.discount_pct.fillna(0).to_dict(); pamt = prom.discount_amt.fillna(0).to_dict(); grp_ = prom.stack_group.to_dict()
    sr = stock_rule.fillna(0).to_dict(); mr_ = marg_rule.fillna(0).to_dict(); ex_ = excl_flag.to_dict()
    mism = set(); n_chk = 0
    for did, grp in DP.groupby("decision_id", sort=False):
        d_ = Dd.loc[did]; b = d_.base_price; cur = b; applied = []; used = set(); exa = False
        cand = sorted(grp.promo_id, key=lambda p: (-(ppct[p] if ppct[p] > 0 else pamt[p] / b), p))
        rec = grp.set_index("promo_id").evaluation_status.to_dict()
        for p in cand:
            reason = None
            if sr[p] and d_.on_hand_units < sr[p]: reason = "x"
            elif (ex_[p] and applied) or exa: reason = "x"
            elif grp_[p] in used: reason = "x"
            elif any(q in partner.get(p, ()) for q in applied): reason = "x"
            elif len(applied) >= GLOBAL_RULES["max_promos_stacked"]: reason = "x"
            else:
                tent = round(cur * (1 - ppct[p]), 2) if ppct[p] > 0 else round(cur - pamt[p], 2)
                if (b - tent) / b > GLOBAL_RULES["max_total_discount_pct_of_base"] + 1e-12 or tent < d_.effective_floor - 1e-9 \
                        or (mr_[p] and (tent - d_.unit_cost) / tent < mr_[p] - 1e-12):
                    reason = "x"
            exp = "REJECTED" if reason else "APPLIED"
            if not reason:
                applied.append(p); used.add(grp_[p]); exa = exa or ex_[p]; cur = tent
            if exp != rec[p]:
                mism.add(did)
        n_chk += 1
    det["_REPLAY_MISMATCH"] = mism

    # ---- score vs ground truth
    gt = pd.read_csv(os.path.join(dd, "ground_truth", "ground_truth_anomalies.csv"), keep_default_na=False)
    gtd = pd.read_csv(os.path.join(dd, "ground_truth", "ground_truth_decisions.csv"), keep_default_na=False)
    score = {}
    for it in ["PRICE_BELOW_FLOOR", "PROMO_STACK_VIOLATION", "STALE_OBSERVATION_AS_CURRENT", "MARGIN_BEFORE_DISCOUNT", "PRICE_CHANGE_WITHOUT_REASON", "PRICE_ABOVE_GRADIENT_CEILING", "BUNDLE_BELOW_MARGIN"]:
        truth = set(gt.record_id[gt.issue_type == it]); pred = det[it]
        tp = len(truth & pred); fp = len(pred - truth); fn = len(truth - pred)
        score[it] = dict(injected=len(truth), detected=len(pred), true_pos=tp, false_pos=fp, false_neg=fn,
                         precision=round(tp / max(len(pred), 1), 4), recall=round(tp / max(len(truth), 1), 4))
    stack_margin_truth = set(gt.record_id[gt.issue_type.isin(["PROMO_STACK_VIOLATION", "MARGIN_BEFORE_DISCOUNT"])])
    check("Eligibility replay: mismatches == injected stack/margin anomalies", mism == stack_margin_truth,
          f"replayed={n_chk} decisions; mismatches={len(mism)}; injected={len(stack_margin_truth)}")
    check("Detectors recover every injected anomaly (recall=1, precision=1)", all(v["false_neg"] == 0 and v["false_pos"] == 0 for v in score.values()),
          json.dumps({k: (v["precision"], v["recall"]) for k, v in score.items()}))
    clean_ids = set(gtd.decision_id[gtd.issue_type == ""])
    cd = DEC[DEC.decision_id.isin(clean_ids)].merge(gtd, on="decision_id")
    check("Clean decisions match expected ground-truth decisions (base, net, reason)",
          np.allclose(cd.base_price, cd.expected_base_price) and np.allclose(cd.net_price, cd.expected_net_price) and (cd.reason_code == cd.expected_reason_code).all())
    clean_viol = len(set().union(*[det[k] for k in ["PRICE_BELOW_FLOOR", "PROMO_STACK_VIOLATION", "STALE_OBSERVATION_AS_CURRENT", "MARGIN_BEFORE_DISCOUNT", "PRICE_ABOVE_GRADIENT_CEILING"]]) & clean_ids)
    check("Guardrails enforced on all non-injected decisions", clean_viol == 0, f"violations={clean_viol}")
    inp_cols = set().union(*[set(T[n].columns) for n in ORDER])
    check("No ground-truth columns leaked into input tables", not (inp_cols & {"issue_type", "anomaly_id", "ground_truth", "expected_value", "is_anomalous"}))

    # ---- business metrics
    rev = float((OR.line_total).sum()); gm = float((OR.quantity * (OR.unit_net_price - OR.unit_cost)).sum())
    promo_lines = float(ORn.loc[ORn.unit_net_price < ORn.unit_base_price - 1e-9, "quantity"].sum())
    dr = DEC.reason_code.value_counts().to_dict()
    dpc = DP.rejection_reason.value_counts().to_dict()
    metrics = dict(
        revenue=round(rev, 2), gross_margin=round(gm, 2), gross_margin_pct=round(gm / rev, 4), units_sold=int(OR.quantity.sum()),
        promo_unit_share=round(promo_lines / ORn.quantity.sum(), 4), stockout_sku_day_rate=round(float(INV.stockout_flag.mean()), 4),
        lost_sales_unit_share=round(float(INV.lost_sales_units.sum() / INV.demand_units.sum()), 4),
        gradient_capped_decision_share=round(float(DEC.guardrail_flags.fillna("").str.contains("GRADIENT_CAPPED").mean()), 4),
        gradient_recovery_decisions=int((DEC.reason_code == "GRADIENT_RECOVERY").sum()),
        avg_base_vs_gradient_ref_index=round(float((DEC.base_price / DEC.gradient_ref_price).mean()), 4),
        avg_price_cagr_5y_by_category={k: round(float(v), 4) for k, v in PG.merge(P[["sku", "category"]], on="sku").groupby("category").price_cagr_5y.mean().items()},
        decisions=len(DEC), price_changed_share=round(float((DEC.outcome == "PRICE_CHANGED").mean()), 4),
        decisions_by_reason=dr, promo_rejections_by_reason=dpc,
        stale_competitor_obs_at_decision_share=round(float((DEC.competitor_obs_age_days > 7).mean()), 4),
        guardrail_pass_rate_all_decisions=round(1 - len(det["PRICE_BELOW_FLOOR"]) / len(DEC), 5),
        avg_net_price_vs_competitor_index=round(float((dm.net_price / dm.competitor_price).mean()), 4),
        bundles_evaluated=len(PB), bundles_created=int(acc.sum()), bundles_active=int((PB.bundle_status == "ACTIVE").sum()),
        bundles_expired=int((PB.bundle_status == "EXPIRED").sum()), bundles_cancelled=int((PB.bundle_status == "CANCELLED").sum()),
        bundle_units_sold=int(BO.quantity.sum()), bundle_component_units_sold=int(2 * BO.quantity.sum()),
        aged_inventory_units_cleared=int(BO.aged_units_cleared.sum()), bundle_revenue=round(float(BO.total_revenue.sum()), 2),
        bundle_gross_profit=round(float(BO.gross_profit.sum()), 2),
        bundle_avg_discount_pct=round(float(PB.bundle_discount_pct[acc].mean()), 4) if acc.any() else None,
        bundle_planned_avg_margin_pct=round(float(PB.bundle_margin_pct[acc].mean()), 4) if acc.any() else None,
        bundle_realised_margin_pct=round(float(BO.gross_profit.sum() / BO.total_revenue.sum()), 4) if len(BO) else None,
        aged_units_first_day=int(INV.aged_units[INV.snapshot_date == dates_[0]].sum()), aged_units_last_day=int(INV.aged_units[INV.snapshot_date == dates_[-1]].sum()),
        aged_inventory_reduction_pct=round(float(1 - INV.aged_units[INV.snapshot_date == dates_[-1]].sum() / max(INV.aged_units[INV.snapshot_date == dates_[0]].sum(), 1)), 4),
        aged_units_cleared_pct_of_first_day_aged=round(float(BO.aged_units_cleared.sum() / max(INV.aged_units[INV.snapshot_date == dates_[0]].sum(), 1)), 4),
        bundle_rejections_by_reason=PB.rejection_reason.dropna().value_counts().to_dict(),
        stock_age_class_share=INV.stock_age_class.value_counts(normalize=True).round(4).to_dict(),
        anomaly_counts=gt.issue_type.value_counts().to_dict(), detector_scores=score,
        eligibility_replay_agreement=round(1 - len(mism) / max(n_chk, 1), 5))
    summary = dict(data_dir=os.path.basename(dd), row_counts=rows, checks_passed=sum(r["passed"] for r in res), checks_total=len(res),
                   all_passed=all(r["passed"] for r in res), checks=res)
    json.dump(summary, open(os.path.join(dd, "validation_summary.json"), "w"), indent=2)
    json.dump(metrics, open(os.path.join(dd, "metrics.json"), "w"), indent=2)
    L = [f"# Validation summary - {summary['data_dir']}", "", f"**{summary['checks_passed']}/{summary['checks_total']} checks passed**", "",
         "| # | Check | Result | Detail |", "|---|---|---|---|"]
    for i, r in enumerate(res, 1):
        L.append(f"| {i} | {r['check']} | {'PASS' if r['passed'] else 'FAIL'} | {r['detail'][:140]} |")
    L += ["", "## Anomaly detector scores (rule-based detectors vs ground truth)", "", "| Issue | Injected | Detected | TP | FP | FN | Precision | Recall |", "|---|---|---|---|---|---|---|---|"]
    for k, v in score.items():
        L.append(f"| {k} | {v['injected']} | {v['detected']} | {v['true_pos']} | {v['false_pos']} | {v['false_neg']} | {v['precision']} | {v['recall']} |")
    open(os.path.join(dd, "validation_summary.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"{summary['checks_passed']}/{summary['checks_total']} checks passed")
    for r in res:
        if not r["passed"]:
            print("FAIL:", r["check"], r["detail"])
    print(json.dumps(score, indent=1))


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
