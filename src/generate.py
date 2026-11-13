#!/usr/bin/env python
"""Synthetic pricing & promotion simulation data generator (deterministic, parameterised scale).

Usage:  python generate.py --skus 5000 --days 180 --promos 2000 --seed 20261022 --out ../data_full
Starter and full datasets use this same code; only the scale arguments differ.
"""
import argparse, datetime as dt, hashlib, json, math, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import (COMP_REASONS, ENTITIES, ORDER, GLOBAL_RULES, CATEGORIES, COMPETITORS, STACK_REASONS, ddl,
                    dictionary_json, dictionary_md)
import bundles as B

START = dt.date(2026, 4, 26)
MAX_STACK = GLOBAL_RULES["max_promos_stacked"]
MAX_TOTAL = GLOBAL_RULES["max_total_discount_pct_of_base"]
STALE_DAYS = GLOBAL_RULES["competitor_staleness_threshold_days"]
STEP = GLOBAL_RULES["max_step_change_pct_per_decision"]

# name, price_lo, price_hi, list_margin(lo,hi), min_margin(lo,hi), elasticity(lo,hi), demand_mult, nouns
CAT = [
    ("Electronics", 30, 600, (.30, .45), (.10, .18), (.9, 1.8), .5, ["Headphones", "Speaker", "Monitor", "Charger"]),
    ("Home & Kitchen", 8, 150, (.35, .55), (.12, .22), (1.0, 2.0), .9, ["Blender", "Cookware Set", "Lamp", "Organizer"]),
    ("Grocery", 1.5, 20, (.20, .35), (.06, .12), (1.2, 2.5), 2.5, ["Olive Oil", "Coffee Beans", "Granola", "Pasta Pack"]),
    ("Apparel", 10, 120, (.40, .60), (.15, .25), (1.2, 2.2), .8, ["Jacket", "T-Shirt", "Sneakers", "Backpack"]),
    ("Beauty", 4, 60, (.45, .65), (.18, .28), (1.0, 2.0), 1.1, ["Serum", "Moisturizer", "Shampoo", "Lip Balm"]),
    ("Sports", 10, 250, (.35, .50), (.12, .22), (1.0, 1.9), .7, ["Yoga Mat", "Dumbbells", "Water Bottle", "Tennis Racket"]),
    ("Toys", 5, 70, (.35, .55), (.12, .22), (1.1, 2.1), 1.0, ["Puzzle", "Building Set", "Plush", "Board Game"]),
    ("Office", 2, 80, (.35, .55), (.12, .22), (0.8, 1.6), 1.2, ["Notebook", "Desk Chair", "Pen Set", "Stapler"]),
]
CAT_P = [.15, .18, .15, .14, .10, .10, .08, .10]
ADJ = ["Aurora", "Nimbus", "Terra", "Vertex", "Solace", "Ember", "Quartz", "Zephyr", "Orbit", "Willow"]
BRANDS = [f"Brand-{i:02d}" for i in range(1, 41)]
SEG_P = [.6, .15, .25]
CH_P = [.5, .3, .2]


def ceil_cent(x):
    return math.ceil(x * 100 - 1e-9) / 100


def dstr(d):
    return d.isoformat()


def dts(hours):
    base = np.datetime64("2026-04-26T00:00:00", "s")
    return np.datetime_as_string(base + (np.asarray(hours) * 3600).astype("timedelta64[s]"), unit="s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skus", type=int, default=5000)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--promos", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261022)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sql", action="store_true", help="also emit seed.sql (INSERT statements)")
    a = ap.parse_args()
    S, D, P = a.skus, a.days, a.promos
    rng = np.random.default_rng(a.seed)
    out = os.path.abspath(a.out)
    gt_dir = os.path.join(out, "ground_truth")
    os.makedirs(gt_dir, exist_ok=True)
    dates = [START + dt.timedelta(i) for i in range(D)]
    as_of = dates[-1]
    W = math.ceil(D / 7)
    sku_ids = np.array([f"SKU-{i + 1:06d}" for i in range(S)])

    # ------------------------------------------------------------------ Product
    cat_i = rng.choice(len(CAT), S, p=CAT_P)
    lo = np.array([c[1] for c in CAT])[cat_i]; hi = np.array([c[2] for c in CAT])[cat_i]
    raw = np.exp(rng.uniform(np.log(lo), np.log(hi)))
    list_price = np.where(raw >= 5, np.floor(raw) + 0.99, np.round(raw, 2))
    lm = rng.uniform(np.array([c[3][0] for c in CAT])[cat_i], np.array([c[3][1] for c in CAT])[cat_i])
    cost0 = np.round(list_price * (1 - lm), 2)
    minm = np.round(rng.uniform(np.array([c[4][0] for c in CAT])[cat_i], np.array([c[4][1] for c in CAT])[cat_i]), 2)
    elast = rng.uniform(np.array([c[5][0] for c in CAT])[cat_i], np.array([c[5][1] for c in CAT])[cat_i])
    base_mean = np.clip(np.exp(rng.normal(0.0, 0.9, S)) * np.array([c[6] for c in CAT])[cat_i], 0.05, 40)
    absfl = np.round(cost0 * 1.05, 2)
    ceil_ = np.round(list_price * 1.30, 2)
    lead = rng.integers(5, 22, S)
    brand_i = rng.integers(0, len(BRANDS), S); brand = np.array(BRANDS)[brand_i]
    nouns = [CAT[c][7][rng.integers(0, 4)] for c in cat_i]
    names = [f"{ADJ[rng.integers(0, 10)]} {n} {rng.integers(100, 999)}" for n in nouns]
    last_day = np.full(S, D, dtype=int)
    disc_mask = rng.random(S) < 0.02
    last_day[disc_mask] = rng.integers(min(20, D - 2), D - 1, disc_mask.sum())  # last active day index
    active = np.arange(D)[:, None] <= np.where(disc_mask, last_day, D)[None, :]
    launch = [dstr(START - dt.timedelta(int(x))) for x in rng.integers(30, 900, S)]
    prod = pd.DataFrame(dict(
        sku=sku_ids, product_name=names, category=[CAT[c][0] for c in cat_i], brand=brand, uom="EA", currency="USD",
        launch_date=launch,
        status=np.where(disc_mask, "DISCONTINUED", "ACTIVE"),
        discontinued_date=[dstr(START + dt.timedelta(int(x) + 1)) if m else "" for x, m in zip(last_day, disc_mask)],
        list_price=list_price, price_floor_abs=absfl, price_ceiling=ceil_, min_margin_pct=minm, lead_time_days=lead))

    # ------------------------------------------ 5-year annual history & price gradient
    G_TOL = GLOBAL_RULES["gradient_ceiling_tolerance"]; G_BAND = GLOBAL_RULES["gradient_recovery_band"]
    ANCHOR = dt.date(2025, 7, 1)
    cat_mean = np.array([.020, .030, .040, .035, .030, .025, .025, .030])[cat_i]  # per CAT order
    brand_eff = rng.normal(0, 0.008, len(BRANDS))[brand_i]
    yoy_true = np.clip(cat_mean[None, :] + brand_eff[None, :] + rng.normal(0, 0.015, (5, S)), -0.05, 0.15)
    t0 = (START - ANCHOR).days / 365.25
    g_geo = np.prod(1 + yoy_true, axis=0) ** 0.2 - 1
    ref_p = np.zeros((6, S))  # index 0 = 2020 base ... 5 = 2025
    ref_p[5] = list_price / ((1 + g_geo) ** t0 * np.exp(np.clip(rng.normal(0, 0.01, S), -0.025, 0.025)))
    cost_yoy = yoy_true - 0.004 + rng.normal(0, 0.006, (5, S))
    ref_c = np.zeros((6, S)); ref_c[5] = cost0 / (1 + (np.prod(1 + cost_yoy, axis=0) ** 0.2 - 1)) ** t0
    for i in range(5, 0, -1):
        ref_p[i - 1] = ref_p[i] / (1 + yoy_true[i - 1]); ref_c[i - 1] = ref_c[i] / (1 + cost_yoy[i - 1])
    ref_p = np.maximum(np.round(ref_p, 2), 0.01); ref_c = np.maximum(np.round(ref_c, 2), 0.01)
    ah = []
    for i in range(1, 6):
        ah.append(pd.DataFrame(dict(
            aph_id=[f"APH-{k}-{2020 + i}" for k in sku_ids], sku=sku_ids, year=2020 + i, ref_price=ref_p[i], prev_year_price=ref_p[i - 1],
            yoy_price_pct=np.round(ref_p[i] / ref_p[i - 1] - 1, 6), ref_cost=ref_c[i], prev_year_cost=ref_c[i - 1],
            yoy_cost_pct=np.round(ref_c[i] / ref_c[i - 1] - 1, 6))))
    ah_df = pd.concat(ah, ignore_index=True).sort_values(["sku", "year"], kind="stable").reset_index(drop=True)
    yoy_p = np.round(ref_p[1:] / ref_p[:-1] - 1, 6)
    g_avg = np.round(yoy_p.mean(0), 6); g_cagr = np.round((ref_p[5] / ref_p[0]) ** 0.2 - 1, 6)
    g_max = np.round(yoy_p.max(0), 6); g_min = np.round(yoy_p.min(0), 6); g_sd = np.round(yoy_p.std(0, ddof=1), 6)
    c_cagr = np.round((ref_c[5] / ref_c[0]) ** 0.2 - 1, 6)
    g_cap = np.round(ref_p[5] * (1 + g_max + G_TOL), 2)
    grad_df = pd.DataFrame(dict(
        sku=sku_ids, basis_start_year=2021, basis_end_year=2025, years_of_history=5, avg_yoy_price_pct=g_avg, price_cagr_5y=g_cagr,
        max_yoy_price_pct=g_max, min_yoy_price_pct=g_min, yoy_price_stdev=g_sd, cost_cagr_5y=c_cagr, last_ref_price=ref_p[5],
        gradient_ceiling=g_cap))
    tyrs = np.array([(x - ANCHOR).days / 365.25 for x in dates])
    gexp = np.round(ref_p[5][None, :] * (1 + g_cagr[None, :]) ** tyrs[:, None], 2)  # (D,S) expected gradient price

    # --------------------------------------------------------------- CostRecord
    months = []
    for d in dates:
        ym = (d.year, d.month)
        if ym not in months:
            months.append(ym)
    M = len(months)
    midx = np.array([months.index((d.year, d.month)) for d in dates])
    costs = np.zeros((M, S)); creason = np.empty((M, S), dtype=object)
    costs[0] = cost0; creason[0] = "INITIAL"
    for m in range(1, M):
        chg = rng.random(S) < 0.30
        pct = np.clip(rng.normal(c_cagr / (12 * 0.30), 0.03, S), -0.08, 0.12)  # drift follows cost gradient
        newc = np.round(costs[m - 1] * (1 + pct * chg), 2)
        up = rng.choice(["SUPPLIER_INCREASE", "FX_ADJUSTMENT", "FREIGHT_SURCHARGE"], S)
        dn = rng.choice(["NEGOTIATED_REDUCTION", "FX_ADJUSTMENT", "VOLUME_REBATE"], S)
        costs[m] = newc
        creason[m] = np.where(newc == costs[m - 1], "NO_CHANGE", np.where(newc > costs[m - 1], up, dn))
    cost_ids = [[f"COST-{sku_ids[s]}-{y}-{mo:02d}" for s in range(S)] for (y, mo) in months]
    cr = []
    for m, (y, mo) in enumerate(months):
        first = dt.date(y, mo, 1)
        last = (dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(1))
        prev = costs[m - 1] if m else None
        cr.append(pd.DataFrame(dict(
            cost_id=cost_ids[m], sku=sku_ids, cost_month=f"{y}-{mo:02d}", effective_from=dstr(first), effective_to=dstr(last),
            unit_cost=costs[m], prev_unit_cost=prev if m else np.nan,
            cost_change_pct=np.round(costs[m] / prev - 1, 6) if m else np.nan, cost_change_reason=creason[m])))
    cost_df = pd.concat(cr, ignore_index=True).sort_values(["sku", "cost_month"], kind="stable").reset_index(drop=True)
    day_cost = costs[midx]  # (D,S)
    cost_changed = np.zeros((D, S), dtype=bool)
    for d in range(D):
        if dates[d].day == 1 and midx[d] > 0:
            cost_changed[d] = costs[midx[d]] != costs[midx[d] - 1]

    # ---------------------------------------------- market reference & competitor observations
    mr = list_price[None, :] * np.exp(np.cumsum(rng.normal(0, 0.004, (D, S)), axis=0))
    first_c = rng.integers(0, 4, S); second_c = (first_c + rng.integers(1, 4, S)) % 4
    bias = rng.uniform(0.93, 1.07, (2, S))
    parts = []
    for k in range(2):
        n = int(D / 4) + 3
        steps = rng.integers(4, 8, (S, n))
        t = rng.random(S)[:, None] * 5 + np.cumsum(steps, axis=1) - 4
        hrs = np.round(t * 24).astype(int)
        out_flag = rng.random(S) < 0.12
        o_start = rng.integers(5, max(6, D - 15), S); o_len = rng.integers(12, 36, S)
        in_out = out_flag[:, None] & (hrs / 24 >= o_start[:, None]) & (hrs / 24 < (o_start + o_len)[:, None])
        lag = np.where(rng.random((S, n)) < 0.04, rng.integers(30, 100, (S, n)), rng.integers(1, 13, (S, n)))
        day = np.clip(hrs // 24, 0, D - 1)
        sidx = np.repeat(np.arange(S)[:, None], n, axis=1)
        price = np.round(mr[day, sidx] * bias[k][:, None] * np.exp(rng.normal(0, 0.02, (S, n)))
                         * np.where(rng.random((S, n)) < 0.05, 0.90, 1.0), 2)
        ins = rng.random((S, n)) < 0.92
        srcv = rng.choice(["SCRAPE_FEED", "PARTNER_API", "MANUAL_CHECK"], (S, n), p=[.6, .3, .1])
        ok = (hrs >= 0) & (hrs < D * 24) & ~in_out & (hrs + lag < D * 24)
        parts.append(pd.DataFrame(dict(
            sku_i=sidx[ok], comp=np.where(k == 0, first_c, second_c)[sidx[ok]], slot=k, obs_h=hrs[ok], lag=lag[ok],
            price=price[ok], in_stock=ins[ok].astype(int), source=srcv[ok])))
    ob = pd.concat(parts, ignore_index=True)
    ob["cap_h"] = ob.obs_h + ob.lag
    ob = ob.sort_values(["cap_h", "sku_i", "slot"], kind="stable").reset_index(drop=True)
    obs_df = pd.DataFrame(dict(
        obs_id=[f"COBS-2026-{i + 1:06d}" for i in range(len(ob))], sku=sku_ids[ob.sku_i.values],
        competitor_id=np.array(COMPETITORS)[ob.comp.values], observed_at=dts(ob.obs_h.values).astype(str),
        captured_at=dts(ob.cap_h.values).astype(str), competitor_price=ob.price.values, in_stock=ob.in_stock.values,
        source=ob.source.values, source_lag_hours=ob.lag.astype(float).values))
    obs_df["observed_at"] = obs_df.observed_at.str.replace("T", " "); obs_df["captured_at"] = obs_df.captured_at.str.replace("T", " ")
    obs_ids = obs_df.obs_id.values
    o_price = ob.price.values; o_in = ob.in_stock.values; o_h = ob.obs_h.values
    avail = np.maximum(np.ceil((ob.cap_h.values - 6) / 24).astype(int), 0)
    last_obs = []
    for k in range(2):
        mat = np.full((D, S), -1, dtype=np.int64)
        sel = (ob.slot.values == k) & (avail < D)
        np.maximum.at(mat, (avail[sel], ob.sku_i.values[sel]), np.nonzero(sel)[0])
        last_obs.append(np.maximum.accumulate(mat, axis=0))

    # --------------------------------------------------------------------- Promotions
    future = rng.random(P) < 0.08
    sw = np.where(future, W + rng.integers(0, 8, P), rng.integers(0, W, P))
    dw = rng.choice([1, 2, 3, 4], P, p=[.30, .35, .20, .15])
    order_ = np.argsort(sw, kind="stable"); sw = sw[order_]; dw = dw[order_]
    ptype = rng.choice(["PCT_OFF", "FIXED_OFF", "COUPON"], P, p=[.5, .2, .3])
    pgrp = np.empty(P, dtype=object)
    for i in range(P):
        pgrp[i] = {"PCT_OFF": rng.choice(["SEASONAL", "CLEARANCE", "BRAND", "LOYALTY"]),
                   "FIXED_OFF": rng.choice(["CLEARANCE", "BRAND"]), "COUPON": "COUPON"}[ptype[i]]
    ppct = np.where(ptype != "FIXED_OFF", rng.choice([.05, .08, .10, .15, .20, .25, .30], P), 0.0)
    pamt = np.where(ptype == "FIXED_OFF", np.round(rng.uniform(1, 8, P) * 2) / 2, 0.0)
    cancelled = rng.random(P) < 0.06
    pcat = rng.integers(0, len(CAT), P)
    start_d = [START + dt.timedelta(int(7 * w)) for w in sw]
    end_d = [s + dt.timedelta(int(7 * x) - 1) for s, x in zip(start_d, dw)]
    created = [s - dt.timedelta(int(x)) for s, x in zip(start_d, rng.integers(14, 46, P))]
    created = [min(c, as_of - dt.timedelta(int(x))) for c, x in zip(created, rng.integers(0, 10, P))]
    sched = [max(s - dt.timedelta(int(x)), c) for s, x, c in zip(start_d, rng.integers(2, 11, P), created)]
    canc_off = rng.integers(0, 2, P)
    cancel_d = [min(sc + dt.timedelta(int(o)), s - dt.timedelta(1)) for sc, o, s in zip(sched, canc_off, start_d)]
    promo_ids = [f"PROMO-2026-{i + 1:06d}" for i in range(P)]
    ev_rows = []; status = []
    for i in range(P):
        seq = [(None, "DRAFT", created[i])]
        if sched[i] <= as_of:
            seq.append(("DRAFT", "SCHEDULED", sched[i]))
            if cancelled[i]:
                if cancel_d[i] <= as_of:
                    seq.append(("SCHEDULED", "CANCELLED", cancel_d[i]))
            else:
                if start_d[i] <= as_of:
                    seq.append(("SCHEDULED", "ACTIVE", start_d[i]))
                    if end_d[i] + dt.timedelta(1) <= as_of:
                        seq.append(("ACTIVE", "ENDED", end_d[i] + dt.timedelta(1)))
        seq = [e for e in seq if e[2] <= as_of]
        for j, (fs, ts, ed) in enumerate(seq):
            ev_rows.append((f"PEVT-{promo_ids[i]}-{j + 1:02d}", promo_ids[i], j + 1, dstr(ed), fs, ts))
        status.append(seq[-1][1])
    SEASON = ["Spring", "Summer", "Back-to-School", "Autumn", "Flash", "Weekend", "Clearance", "Member"]
    promo_df = pd.DataFrame(dict(
        promo_id=promo_ids, promo_name=[f"{SEASON[rng.integers(0, 8)]} {CAT[c][0]} Deal {i + 1}" for i, c in enumerate(pcat)],
        promo_type=ptype, stack_group=pgrp, discount_pct=np.where(ppct > 0, ppct, np.nan), discount_amt=np.where(pamt > 0, pamt, np.nan),
        coupon_code=[f"CPN{i + 1:06d}" if t == "COUPON" else "" for i, t in enumerate(ptype)], scope_category=[CAT[c][0] for c in pcat],
        start_date=[dstr(x) for x in start_d], end_date=[dstr(x) for x in end_d], created_date=[dstr(x) for x in created], status=status))
    promo_event_df = pd.DataFrame(ev_rows, columns=["event_id", "promo_id", "event_seq", "event_date", "from_status", "to_status"])
    cat_skus = [np.nonzero(cat_i == c)[0] for c in range(len(CAT))]
    n_target = 0.5 * S * W / (max(P, 1) * 2.4)
    promo_skus = []; pp_rows = []
    for i in range(P):
        pool = cat_skus[pcat[i]]
        n = min(max(3, int(round(n_target * rng.uniform(0.5, 1.5)))), len(pool))
        mem = np.sort(rng.choice(pool, n, replace=False)) if n else np.array([], dtype=int)
        promo_skus.append(mem)
        pp_rows.append(pd.DataFrame(dict(promo_id=promo_ids[i], sku=sku_ids[mem], added_date=dstr(created[i]))))
    promo_prod_df = pd.concat(pp_rows, ignore_index=True)
    r_stock = np.zeros(P); r_excl = np.zeros(P, dtype=bool); r_marg = np.zeros(P)
    rule_rows = []
    for i in range(P):
        u = rng.random(3); got = False
        if u[0] < .35:
            r_stock[i] = rng.choice([5, 10, 20]); got = True
            rule_rows.append((promo_ids[i], "MIN_STOCK_UNITS", r_stock[i]))
        if u[1] < .12:
            r_excl[i] = True; got = True; rule_rows.append((promo_ids[i], "EXCLUSIVE", 1.0))
        if u[2] < .30:
            r_marg[i] = rng.choice([.20, .25, .30, .35]); got = True; rule_rows.append((promo_ids[i], "MIN_MARGIN_PCT", r_marg[i]))
        if not got:
            r_stock[i] = 5; rule_rows.append((promo_ids[i], "MIN_STOCK_UNITS", 5.0))
    promo_rule_df = pd.DataFrame(rule_rows, columns=["promo_id", "rule_type", "rule_value"])
    promo_rule_df.insert(0, "rule_id", [f"PRULE-2026-{i + 1:06d}" for i in range(len(promo_rule_df))])
    sd = np.array([x.toordinal() for x in start_d]); ed_ = np.array([x.toordinal() for x in end_d])
    excl_pairs = set()
    for i in range(P):
        if ptype[i] == "COUPON" and not cancelled[i] and rng.random() < 0.4:
            cand = np.nonzero((sd <= ed_[i]) & (ed_ >= sd[i]) & (np.arange(P) != i) & (pgrp != "COUPON") & ~cancelled)[0]
            if len(cand):
                j = int(rng.choice(cand)); excl_pairs.add((min(i, j), max(i, j)))
    excl_pairs = sorted(excl_pairs)
    promo_excl_df = pd.DataFrame([(promo_ids[i], promo_ids[j], "CONFLICTING_COUPON") for i, j in excl_pairs],
                                 columns=["promo_id_a", "promo_id_b", "exclusion_reason"])
    partner = {}
    for i, j in excl_pairs:
        partner.setdefault(i, set()).add(j); partner.setdefault(j, set()).add(i)
    partner = {k: frozenset(v) for k, v in partner.items()}
    grp_l = list(pgrp)

    # ------------------------------------------------------------------- simulation
    dow = np.array([1.0, 0.95, 0.95, 1.0, 1.1, 1.25, 1.15])
    season = np.array([1 + 0.15 * math.sin(2 * math.pi * i / 90) for i in range(D)])
    on_hand = np.round(base_mean * rng.uniform(10, 60, S)).astype(int)
    ob_mask = rng.random(S) < 0.10
    on_hand[ob_mask] = np.round(base_mean[ob_mask] * rng.uniform(80, 150, ob_mask.sum())).astype(int)
    rop = np.maximum(2, np.ceil(base_mean * (lead + 10))).astype(int)
    qty = np.maximum(6, np.ceil(base_mean * rng.uniform(25, 55, S))).astype(int)
    disrupt = rng.random(S) < 0.06
    pend = np.zeros((D + 90, S), dtype=int); pend_total = np.zeros(S, dtype=int)
    hist7 = np.tile(base_mean, (7, 1)); hptr = 0
    base = list_price.copy(); disc = np.zeros(S); net = list_price.copy()
    gov = np.zeros(S, dtype=np.int64); last_dec_cost = cost0.copy()
    shp = (D, S)
    r_base = np.zeros(shp); r_disc = np.zeros(shp); r_net = np.zeros(shp); r_ev = np.zeros(shp, dtype=np.int8)
    r_reason = np.empty(shp, dtype=object); r_gov = np.zeros(shp, dtype=np.int64)
    r_open = np.zeros(shp, dtype=np.int64); r_recv = np.zeros(shp, dtype=np.int64); r_dem = np.zeros(shp, dtype=np.int64)
    r_sold = np.zeros(shp, dtype=np.int64); r_close = np.zeros(shp, dtype=np.int64); r_onord = np.zeros(shp, dtype=np.int64)
    EVN = ["CARRY_FORWARD", "DECISION_CHANGE", "PROMO_CHANGE", "DECISION_HOLD", "MANUAL_CHANGE"]
    dec_rows = []; dp_rows = []; dec_promo_str = [""]; gt_dec = []; gt_anom = []
    MAN_REASONS = ["MANUAL_OVERRIDE", "PRICE_MATCH_STORE", "ERROR_CORRECTION"]
    week_cache = (-1, None)

    def week_map(w):
        nonlocal week_cache
        if week_cache[0] == w:
            return week_cache[1]
        mp = {}
        for p in np.nonzero((sw <= w) & (w < sw + dw) & ~cancelled)[0]:
            for s_ in promo_skus[p]:
                mp.setdefault(int(s_), []).append(int(p))
        week_cache = (w, mp)
        return mp

    def eval_promos(b, plist, oh, c, F):
        """Apply documented rules in documented order. Returns (rows, cur, applied_list)."""
        applied = []; rows = []; cur = b; used = set(); excl_app = False
        ordered = sorted(plist, key=lambda p: (-(ppct[p] if ppct[p] > 0 else pamt[p] / b), p))
        for p in ordered:
            reason = None; tent = cur
            if r_stock[p] and oh < r_stock[p]:
                reason = "MIN_STOCK"
            elif (r_excl[p] and applied) or excl_app:
                reason = "EXCLUSIVE_WITH_OTHER"
            elif grp_l[p] in used:
                reason = "SAME_GROUP"
            elif any(q in partner.get(p, ()) for q in applied):
                reason = "CONFLICT_PAIR"
            elif len(applied) >= MAX_STACK:
                reason = "MAX_STACK"
            else:
                tent = round(cur * (1 - ppct[p]), 2) if ppct[p] > 0 else round(cur - pamt[p], 2)
                if (b - tent) / b > MAX_TOTAL + 1e-12:
                    reason = "MAX_TOTAL_DISCOUNT"
                elif tent < F - 1e-9:
                    reason = "FLOOR_GUARDRAIL"
                elif r_marg[p] and (tent - c) / tent < r_marg[p] - 1e-12:
                    reason = "MARGIN_GUARDRAIL"
            if reason:
                rows.append([p, "REJECTED", reason, None, 0.0])
            else:
                rows.append([p, "APPLIED", None, len(applied) + 1, round(cur - tent, 2)])
                applied.append(p); used.add(grp_l[p]); excl_app = excl_app or bool(r_excl[p]); cur = tent
        return rows, cur, applied

    def core(ref, has_stale, p0, cover, a7, gx):
        if cover < 5 and a7 > 0.2:
            return p0 * 1.04, "LOW_STOCK_MARKUP"
        if ref is not None:
            if p0 > ref * 1.03:
                return ref * 0.995, "COMP_MATCH_DOWN"
            if p0 < ref * 0.93:
                return min(ref * 0.96, p0 * 1.06), "COMP_RAISE"
            if p0 < gx * (1 - G_BAND) and min(gx, ref) > p0 * 1.01:
                return min(gx, ref), "GRADIENT_RECOVERY"
            return p0, "HOLD_IN_COMP_BAND"
        if cover > 75:
            return p0 * 0.95, "OVERSTOCK_MARKDOWN"
        if has_stale:
            return p0, "HOLD_STALE_COMPETITOR"
        if p0 < gx * (1 - G_BAND):
            return gx, "GRADIENT_RECOVERY"
        return p0, "HOLD_NO_SIGNAL"

    def finalize(target, reason, p0, F, C, c, lc, gcap):
        Ce = max(min(C, gcap), F)
        flags = []
        if reason.startswith("HOLD") and abs(c - lc) > 1e-9:
            target = p0 * (1 + 0.6 * (c / lc - 1)); reason = "COST_PASS_THROUGH"
        t = min(max(target, p0 * (1 - STEP)), p0 * (1 + STEP))
        if abs(t - target) > 1e-9:
            flags.append("STEP_LIMITED")
        if t < F:
            t = F; flags.append("FLOOR_CLAMPED")
        elif t > Ce:
            t = Ce; flags.append("GRADIENT_CAPPED" if Ce < C - 1e-9 else "CEILING_CLAMPED")
        b = round(t, 2)
        if reason.startswith("HOLD") and abs(b - p0) > 0.004:
            reason = "FLOOR_REPAIR" if "FLOOR_CLAMPED" in flags else "CEILING_REPAIR"
        return b, reason, flags, round(target, 2)

    def decide(d, s, trig, avg7):
        nonlocal_dec = len(dec_rows) + 1
        c = float(day_cost[d, s]); m = float(minm[s]); p0 = float(base[s])
        F = max(float(absfl[s]), ceil_cent(c / (1 - m))); C = max(float(ceil_[s]), F)
        gcap = float(g_cap[s]); gx = float(gexp[d, s]); Ce = max(min(C, gcap), F)
        oh = int(on_hand[s]); a7 = float(avg7[s]); cover = min(oh / max(a7, 0.05), 999.0)
        fresh = None; stale = None
        for k in range(2):
            pos = last_obs[k][d, s]
            if pos >= 0 and o_in[pos]:
                age = (d * 24 + 6 - o_h[pos]) / 24
                cand = (float(o_price[pos]), int(pos), age)
                if age <= STALE_DAYS:
                    if fresh is None or cand[0] < fresh[0]:
                        fresh = cand
                elif stale is None or age < stale[2]:
                    stale = cand
        considered = fresh or stale
        lowstock = cover < 5 and a7 > 0.2
        tgt, reason = core(fresh[0] if fresh else None, stale is not None, p0, cover, a7, gx)
        b, reason, flags, cand_price = finalize(tgt, reason, p0, F, C, c, float(last_dec_cost[s]), gcap)
        plist = week_map(d // 7).get(s, [])
        rows, cur, applied = eval_promos(b, plist, oh, c, F)
        net_c = round(cur, 2); margin = round((net_c - c) / net_c, 4)
        clean = dict(base=b, net=net_c, applied=list(applied), reason=reason, margin=margin)
        r = rng.random(5)
        issue = None
        if stale is not None and fresh is None and not lowstock and r[0] < 0.20:
            issue = "STALE_OBSERVATION_AS_CURRENT"
        else:
            stack_c = [x for x in rows if x[1] == "REJECTED" and x[2] in STACK_REASONS]
            marg_c = [x for x in rows if x[1] == "REJECTED" and x[2] == "MARGIN_GUARDRAIL"]
            if stack_c and r[1] < 0.06:
                issue = "PROMO_STACK_VIOLATION"
            elif marg_c and r[2] < 0.06:
                issue = "MARGIN_BEFORE_DISCOUNT"
            elif r[3] < 0.004:
                issue = "PRICE_BELOW_FLOOR"
            elif r[4] < 0.003:
                issue = "PRICE_ABOVE_GRADIENT_CEILING"
        rec_margin = None
        if issue == "STALE_OBSERVATION_AS_CURRENT":
            tgt2, reason2 = core(stale[0], True, p0, cover, a7, gx)
            b2, reason2, flags2, cand2 = finalize(tgt2, reason2, p0, F, C, c, float(last_dec_cost[s]), gcap)
            if reason2 in COMP_REASONS and not (reason2 == clean["reason"] and b2 == clean["base"]):
                b, reason, flags, cand_price = b2, reason2, flags2, cand2
                rows, cur, applied = eval_promos(b, plist, oh, c, F)
            else:
                issue = None  # no observable effect; keep the clean decision, do not label
        elif issue in ("PROMO_STACK_VIOLATION", "MARGIN_BEFORE_DISCOUNT"):
            pool = stack_c if issue == "PROMO_STACK_VIOLATION" else marg_c
            row = pool[0]; p = row[0]
            tent = round(cur * (1 - ppct[p]), 2) if ppct[p] > 0 else round(cur - pamt[p], 2)
            ok = tent >= F - 1e-9
            if issue == "PROMO_STACK_VIOLATION":
                ok = ok and not (r_marg[p] and (tent - c) / tent < r_marg[p] - 1e-12)
            else:  # margin anomaly must not also be a (separately labelled) stacking violation
                ok = ok and len(applied) < MAX_STACK and grp_l[p] not in {grp_l[q] for q in applied}                     and not (r_excl[p] or any(r_excl[q] for q in applied))                     and not any(q in partner.get(p, ()) for q in applied) and (b - tent) / b <= MAX_TOTAL + 1e-12
            if ok:
                row[1] = "APPLIED"; row[2] = None; row[3] = len(applied) + 1; row[4] = round(cur - tent, 2)
                applied.append(p); cur = tent
                if issue == "MARGIN_BEFORE_DISCOUNT":
                    rec_margin = round((b - c) / b, 4)
            else:
                issue = None
        elif issue == "PRICE_BELOW_FLOOR":
            b = round(F * rng.uniform(0.82, 0.97), 2); flags = []
            rows, cur, applied = eval_promos(b, plist, oh, c, F)
        elif issue == "PRICE_ABOVE_GRADIENT_CEILING":
            b = round(Ce * rng.uniform(1.04, 1.12), 2); flags = []
            rows, cur, applied = eval_promos(b, plist, oh, c, F)
        net_f = round(cur, 2); dsc = round(b - net_f, 2)
        margin_rec = rec_margin if rec_margin is not None else round((net_f - c) / net_f, 4)
        dnum = nonlocal_dec; dec_id = f"DEC-2026-{dnum:06d}"
        nxt = ((d // 7) + 1) * 7
        vto = min(nxt - 1, D - 1)
        changed = abs(b - p0) > 0.004
        dec_rows.append([dec_id, sku_ids[s], dstr(dates[d]), f"{dates[d]} 06:00:00", trig, dstr(dates[d]), dstr(dates[vto]),
                         cost_ids[midx[d]][s], c, p0, oh, round(a7, 3), round(cover, 1),
                         obs_ids[considered[1]] if considered else "", considered[0] if considered else np.nan,
                         round(considered[2], 2) if considered else np.nan, F, C, gx, gcap, m, cand_price, b, dsc, net_f, margin_rec,
                         "|".join(flags), reason, "PRICE_CHANGED" if changed else "PRICE_HELD"])
        for row in rows:
            dp_rows.append([dec_id, promo_ids[row[0]], row[1], row[2], row[3], row[4]])
        dec_promo_str.append("|".join(promo_ids[p] for p in applied))
        gt_dec.append([dec_id, clean["base"], clean["net"], "|".join(promo_ids[p] for p in clean["applied"]),
                       clean["margin"], clean["reason"], issue or ""])
        if issue:
            desc = {
                "PRICE_BELOW_FLOOR": (f"net_price {net_f} below effective_floor {F}", "net_price >= effective_floor", "decision.net_price < recomputed floor"),
                "PROMO_STACK_VIOLATION": ("applied promotion set violates stacking rules (see rules_config.json / PromotionRule)", "rejected promo not applied", "replay of stacking rules over APPLIED DecisionPromotion rows"),
                "STALE_OBSERVATION_AS_CURRENT": (f"competitor observation age {round(considered[2], 2) if considered else None}d > {STALE_DAYS}d used as current", "HOLD_STALE_COMPETITOR / ignore stale", "competitor_obs_age_days > 7 and reason_code in competitor-driven reasons"),
                "PRICE_ABOVE_GRADIENT_CEILING": (f"base_price {b} above applied ceiling {Ce} (gradient ceiling {gcap})", "base_price <= max(min(price_ceiling, gradient_ceiling), effective_floor)", "decision.base_price > max(min(price_ceiling, gradient_ceiling), effective_floor)"),
                "MARGIN_BEFORE_DISCOUNT": ("margin_pct computed on base_price before promo discount; guardrail bypassed", "margin on net price", "recorded margin_pct != (net-cost)/net"),
            }[issue]
            exp = {"PRICE_BELOW_FLOOR": clean["net"], "PROMO_STACK_VIOLATION": clean["net"], "STALE_OBSERVATION_AS_CURRENT": clean["base"],
                   "PRICE_ABOVE_GRADIENT_CEILING": clean["base"], "MARGIN_BEFORE_DISCOUNT": clean["margin"]}[issue]
            obsv = {"PRICE_BELOW_FLOOR": net_f, "PROMO_STACK_VIOLATION": net_f, "STALE_OBSERVATION_AS_CURRENT": b, "PRICE_ABOVE_GRADIENT_CEILING": b, "MARGIN_BEFORE_DISCOUNT": margin_rec}[issue]
            gt_anom.append([issue, "PriceDecision", dec_id, sku_ids[s], dec_id, desc[0], desc[2], exp, obsv])
        prev_net = float(net[s]); prev_disc = float(disc[s])
        if changed:
            ev, rsn = 1, reason
        elif abs(net_f - prev_net) > 0.004:
            ev = 2; rsn = "PROMO_APPLIED" if prev_disc == 0 else ("PROMO_ENDED" if dsc == 0 else "PROMO_CHANGED")
        else:
            ev, rsn = 3, None
        base[s] = b; disc[s] = dsc; net[s] = net_f; gov[s] = dnum; last_dec_cost[s] = c
        return ev, rsn

    # ------------------------------------------------ FIFO stock lots + inventory-clearance bundles (separate RNG stream)
    BR = GLOBAL_RULES
    ATT = 0.25; REFD = 0.10; INJECT_P = 0.08  # simulation parameters (internal, not exported)
    rng_b = np.random.default_rng([a.seed, 7])
    age_open = np.where(ob_mask, rng_b.integers(70, 201, S), rng_b.integers(1, 76, S)).astype(np.int64)
    lot_q = np.zeros((D + 1, S), dtype=np.int64); lot_q[0] = on_hand
    lot_cum = np.zeros((D + 1, S), dtype=np.int64); lot_cum[0] = on_hand
    cso = np.zeros(S, dtype=np.int64); cso_hist = np.zeros((D, S), dtype=np.int64)
    la = np.where(disc_mask, last_day, D - 1)  # last active day index
    r_reg = np.zeros(shp, dtype=np.int64)
    bundles = []; accepted = []; bundle_sales = []; pair_end = {}
    CHN = ["WEB", "STORE", "MARKETPLACE"]; SEGN = ["CONSUMER", "BUSINESS", "LOYALTY_MEMBER"]

    def review_bundles(d, act):
        vf = d + 1
        if vf > D - 1 or d < BR["bundle_review_min_history_days"]:
            return
        oldest, slow_u, aged_u, tot_u = B.stock_age(lot_q, lot_cum, age_open, d, cso, BR)
        dem30 = r_dem[max(0, d - 30):d].mean(axis=0)
        thr = B.category_thresholds(dem30, cat_i, act, len(CAT), BR["bundle_high_demand_percentile"])
        high = act & (dem30 >= thr[cat_i]) & (dem30 >= BR["bundle_min_daily_demand"])
        sell = np.floor(on_hand * (1 - BR["bundle_stock_reserve_pct"]) + 1e-9).astype(np.int64)
        cls = B.classify_age_vec(oldest, tot_u, BR)
        sec = act & np.isin(cls, BR["bundle_eligible_secondary_classes"]) & ((slow_u + aged_u) >= BR["bundle_min_secondary_aged_units"])
        sec_idx = np.nonzero(sec)[0]
        order_ = sec_idx[np.lexsort((sec_idx, -aged_u[sec_idx], -oldest[sec_idx]))]
        K = max(5, math.ceil(BR["bundle_review_cap_pct_of_skus"] * S))
        prim = {}
        for c in range(len(CAT)):
            ix = np.nonzero(high & (cat_i == c))[0]
            prim[CAT[c][0]] = ix[np.lexsort((ix, -dem30[ix]))]
        use = {}
        for s_ in order_[:K]:
            s_ = int(s_); best = None
            for pc in B.primary_categories_for(CAT[cat_i[s_]][0], BR):
                for p_ in prim.get(pc, []):
                    p_ = int(p_)
                    if p_ == s_ or use.get(p_, 0) >= BR["bundle_max_per_primary_per_review"] or not B.price_ratio_ok(float(base[p_]), float(base[s_]), BR):
                        continue
                    if best is None or dem30[p_] > dem30[best]:
                        best = p_
                    break
            if best is None:
                continue
            p_ = best; use[p_] = use.get(p_, 0) + 1
            pp = round(float(base[p_]), 2); ps = round(float(base[s_]), 2)
            disc_ = B.pick_discount(int(oldest[s_]), BR)
            price = B.bundle_price(pp, ps, disc_)
            cp = float(day_cost[vf, p_]); cs_ = float(day_cost[vf, s_])
            cc = round(cp + cs_, 2)
            marg = B.bundle_margin(price, cc); req = B.required_margin(float(minm[p_]), float(minm[s_]))
            fsum = B.effective_floor(float(absfl[p_]), cp, float(minm[p_])) + B.effective_floor(float(absfl[s_]), cs_, float(minm[s_]))
            key = frozenset((p_, s_))
            reason = B.evaluate_bundle(component_discontinued=min(int(la[p_]), int(la[s_])) < vf, sell_primary=int(sell[p_]), sell_secondary=int(sell[s_]),
                                       duplicate_active=pair_end.get(key, -1) >= vf, price=price, floor_sum=fsum, margin=marg, req_margin=req, rules=BR)
            injected = False
            if reason is None and rng_b.random() < INJECT_P:
                # labelled anomaly: an over-deep discount pushes the margin below the requirement but the bundle is still approved
                target = cc / (1 - req)
                if target - fsum > 0.03:
                    px = round(fsum + 0.5 * (target - fsum), 2); dx = round(1 - px / (pp + ps), 4)
                    prx = B.bundle_price(pp, ps, dx); mx_ = B.bundle_margin(prx, cc)
                    if prx >= fsum and mx_ < req - 0.0005:
                        injected = True; disc_, price, marg = dx, prx, mx_
            vt = max(vf, min(vf + BR["bundle_validity_days"] - 1, D - 1, int(la[p_]), int(la[s_])))
            mx = B.max_bundle_units(int(sell[p_]), int(sell[s_]))
            bid = f"BNDL-2026-{len(bundles) + 1:06d}"
            bundles.append(dict(
                bundle_id=bid, primary_sku=sku_ids[p_], secondary_sku=sku_ids[s_], bundle_discount_pct=disc_, primary_unit_price=pp,
                secondary_unit_price=ps, individual_total_price=round(pp + ps, 2), bundle_price=price, combined_cost=cc,
                bundle_margin_pct=round(marg, 4), required_margin_pct=req, valid_from=dstr(dates[vf]), valid_to=dstr(dates[vt]),
                rejection_reason=reason or "", created_at=f"{dates[d]} 06:00:00", primary_avg_demand_30d=round(float(dem30[p_]), 3),
                primary_demand_threshold=round(float(thr[cat_i[p_]]), 3), primary_sellable_units=int(sell[p_]),
                secondary_sellable_units=int(sell[s_]), max_bundle_units=mx, secondary_oldest_age_days=int(oldest[s_]),
                secondary_stock_age_class=str(cls[s_]), secondary_slow_units=int(slow_u[s_]), secondary_aged_units=int(aged_u[s_])))
            if reason is None:
                pair_end[key] = vt
                accepted.append(dict(bi=len(bundles) - 1, p=p_, s=s_, vf=vf, vt=vt, left=mx, d30=float(dem30[p_]), disc=disc_, price=price,
                                     alloc=B.allocate_price(price, pp, ps)))
            if injected:
                gt_anom.append(["BUNDLE_BELOW_MARGIN", "ProductBundle", bid, sku_ids[p_], "",
                                f"discount {disc_} pushed bundle margin to {round(marg, 4)} < required {req}; bundle still approved",
                                "accepted bundle with (bundle_price - combined_cost)/bundle_price < max(min_margin_pct of both components)",
                                req, round(marg, 4)])

    def run_bundle_sales(d):
        bd = np.zeros(S, dtype=np.int64)
        for b in accepted:
            if b["vf"] > d or b["vt"] < d or b["left"] <= 0:
                continue
            p_, s_ = b["p"], b["s"]
            lam = ATT * b["d30"] * (b["disc"] / REFD) * dow[(START + dt.timedelta(d)).weekday()] * season[d] * rng_b.gamma(4.0, 0.25)
            want = int(rng_b.poisson(min(lam, 1e4)))
            ch = int(rng_b.choice(3, p=CH_P)); sg = int(rng_b.choice(3, p=SEG_P))
            q = int(min(want, on_hand[p_], on_hand[s_], b["left"]))
            if q <= 0:
                continue
            aged = B.aged_overlap(lot_q[:d + 2, s_], B.lot_ages(d, age_open[s_]), int(cso[s_]), q, BR)
            on_hand[p_] -= q; on_hand[s_] -= q; cso[p_] += q; cso[s_] += q; bd[p_] += q; bd[s_] += q; b["left"] -= q
            bundle_sales.append(dict(bi=b["bi"], d=d, q=q, channel=CHN[ch], segment=SEGN[sg], aged=aged))
        return bd

    for d in range(D):
        act = active[d]
        arr = pend[d].copy(); r_open[d] = on_hand; on_hand += arr; pend_total -= arr; r_recv[d] = arr
        lot_q[d + 1] = arr; lot_cum[d + 1] = lot_cum[d] + arr
        avg7 = hist7.mean(axis=0)
        r_ev[d] = 0; r_reason[d] = None
        dec_today = np.nonzero(act & ((d % 7 == 0) | cost_changed[d]))[0]
        decided = np.zeros(S, dtype=bool)
        for s in dec_today:
            trig = "COST_CHANGE" if cost_changed[d, s] else "WEEKLY_REVIEW"
            ev, rsn = decide(d, int(s), trig, avg7)
            r_ev[d, s] = ev; r_reason[d, s] = rsn; decided[s] = True
        if d > 0:
            man = np.nonzero(act & ~decided & (disc == 0) & (rng.random(S) < 0.003))[0]
            for s in man:
                c = float(day_cost[d, s]); F = max(float(absfl[s]), ceil_cent(c / (1 - float(minm[s])))); C = max(min(float(ceil_[s]), float(g_cap[s])), F)
                nb = round(min(max(float(base[s]) * rng.uniform(0.93, 1.07), F), C), 2)
                if abs(nb - base[s]) < 0.005:
                    continue
                rs = MAN_REASONS[rng.integers(0, 3)]; noreason = rng.random() < 0.4
                base[s] = nb; net[s] = nb; r_ev[d, s] = 4
                r_reason[d, s] = None if noreason else rs
                if noreason:
                    gt_anom.append(["PRICE_CHANGE_WITHOUT_REASON", "PriceHistory", f"PRC-{sku_ids[s]}-{dates[d]:%Y%m%d}", sku_ids[s], "",
                                    f"manual base price change to {nb} recorded without change_reason_code", "price change event with null change_reason_code",
                                    "non-null reason", ""])
        if d % 7 == 0:
            review_bundles(d, act)
        r_base[d] = base; r_disc[d] = disc; r_net[d] = net; r_gov[d] = gov
        promo_on = (disc > 0)
        lam = (base_mean * dow[(START + dt.timedelta(d)).weekday()] * season[d]
               * (net / mr[d]) ** (-elast) * np.where(promo_on, 1.15, 1.0) * rng.gamma(4.0, 0.25, S))
        dem = np.where(act, rng.poisson(np.clip(lam, 0, 1e4)), 0)
        sold = np.minimum(on_hand, dem); on_hand -= sold; cso += sold; r_reg[d] = sold
        bdem = run_bundle_sales(d)  # bundle take-up: extra demand for BOTH components, served from the same stock
        dem = dem + bdem; sold = sold + bdem; cso_hist[d] = cso
        hist7[hptr % 7] = dem; hptr += 1
        pos_ = on_hand + pend_total
        trg = np.nonzero(act & (pos_ <= rop))[0]
        if len(trg):
            delay = np.where(disrupt[trg] & (rng.random(len(trg)) < 0.3), rng.integers(10, 36, len(trg)), 0)
            arr_day = d + lead[trg] + delay
            np.add.at(pend, (arr_day, trg), qty[trg]); pend_total[trg] += qty[trg]
        r_dem[d] = dem; r_sold[d] = sold; r_close[d] = on_hand; r_onord[d] = pend_total

    # ------------------------------------------------------------- tables from matrices
    sI, dI = np.nonzero(active.T)  # ordered by sku then date
    dstrs = np.array([dstr(x) for x in dates]); dcompact = np.array([f"{x:%Y%m%d}" for x in dates])
    sk = sku_ids[sI]
    gov_f = r_gov[dI, sI]
    dec_arr = np.array([""] + [f"DEC-2026-{i:06d}" for i in range(1, len(dec_rows) + 1)], dtype=object)
    promo_arr = np.array(dec_promo_str, dtype=object)
    ev_f = r_ev[dI, sI]
    rs_f = r_reason[dI, sI]
    ph = pd.DataFrame(dict(
        price_id=np.char.add(np.char.add(np.char.add("PRC-", sk), "-"), dcompact[dI]), sku=sk, price_date=dstrs[dI],
        base_price=r_base[dI, sI], promo_discount_amt=r_disc[dI, sI], net_price=r_net[dI, sI],
        applied_promo_ids=np.where(r_ev[dI, sI] == 4, "", promo_arr[gov_f]),
        price_event=np.array(EVN)[ev_f], change_reason_code=np.where(rs_f == None, "", rs_f),  # noqa: E711
        decision_id=dec_arr[gov_f]))
    ph["base_price"] = ph.base_price.round(2); ph["net_price"] = ph.net_price.round(2); ph["promo_discount_amt"] = ph.promo_discount_amt.round(2)
    # trailing 7d demand mean (min periods 1)
    cs = np.cumsum(r_dem, axis=0)
    prevcs = np.vstack([np.zeros((7, S)), cs[:-7]])[:D] if D > 7 else np.zeros((D, S))
    cnt = np.minimum(np.arange(D) + 1, 7)[:, None]
    avg7_m = (cs - prevcs) / cnt
    cover_m = np.minimum(r_close / np.maximum(avg7_m, 0.05), 999.0)
    r_old = np.zeros(shp, dtype=np.int64); r_slow = np.zeros(shp, dtype=np.int64); r_aged = np.zeros(shp, dtype=np.int64)
    for d_ in range(D):
        o_, sl_, ag_, _t = B.stock_age(lot_q, lot_cum, age_open, d_, cso_hist[d_], BR)
        r_old[d_] = o_; r_slow[d_] = sl_; r_aged[d_] = ag_
    assert (lot_cum[1:] - cso_hist == r_close).all(), "FIFO lots do not reconcile to closing stock"
    cls_m = B.classify_age_vec(r_old, r_close, BR)
    inv = pd.DataFrame(dict(
        snapshot_id=np.char.add(np.char.add(np.char.add("INV-", sk), "-"), dcompact[dI]), sku=sk, snapshot_date=dstrs[dI],
        opening_on_hand=r_open[dI, sI], units_received=r_recv[dI, sI], demand_units=r_dem[dI, sI], units_sold=r_sold[dI, sI],
        lost_sales_units=r_dem[dI, sI] - r_sold[dI, sI], closing_on_hand=r_close[dI, sI], on_order_units=r_onord[dI, sI],
        stockout_flag=(r_close[dI, sI] == 0).astype(int), avg_demand_7d=np.round(avg7_m[dI, sI], 3), days_of_cover=np.round(cover_m[dI, sI], 1),
        oldest_stock_age_days=r_old[dI, sI], slow_moving_units=r_slow[dI, sI], aged_units=r_aged[dI, sI], stock_age_class=cls_m[dI, sI]))
    # orders (date, sku) order
    dO, sO = np.nonzero(r_reg > 0)
    cnts = rng.multinomial(r_reg[dO, sO], CH_P)
    rowi, chi = np.nonzero(cnts > 0)
    q = cnts[rowi, chi]; d2 = dO[rowi]; s2 = sO[rowi]
    n_o = len(q)
    orders = pd.DataFrame(dict(
        order_id="", order_date=dstrs[d2], sku=sku_ids[s2],
        price_id=np.char.add(np.char.add(np.char.add("PRC-", sku_ids[s2]), "-"), dcompact[d2]),
        decision_id=dec_arr[r_gov[d2, s2]], channel=np.array(["WEB", "STORE", "MARKETPLACE"])[chi],
        customer_segment=np.array(["CONSUMER", "BUSINESS", "LOYALTY_MEMBER"])[rng.choice(3, n_o, p=SEG_P)], quantity=q,
        unit_base_price=np.round(r_base[d2, s2], 2), unit_net_price=np.round(r_net[d2, s2], 2), unit_cost=day_cost[d2, s2],
        line_total=np.round(q * np.round(r_net[d2, s2], 2), 2), order_status="FULFILLED", bundle_order_id="", _bo=-1, _role=""))
    if bundle_sales:
        acc_by_bi = {b["bi"]: b for b in accepted}; bl = []
        for k, bs in enumerate(bundle_sales):
            ab = acc_by_bi[bs["bi"]]; d_ = bs["d"]
            for role, sx, al in (("P", ab["p"], ab["alloc"][0]), ("S", ab["s"], ab["alloc"][1])):
                bl.append(dict(order_id="", order_date=dstrs[d_], sku=sku_ids[sx], price_id=f"PRC-{sku_ids[sx]}-{dcompact[d_]}",
                               decision_id=dec_arr[r_gov[d_, sx]], channel=bs["channel"], customer_segment=bs["segment"], quantity=bs["q"],
                               unit_base_price=round(float(r_base[d_, sx]), 2), unit_net_price=al, unit_cost=float(day_cost[d_, sx]),
                               line_total=round(bs["q"] * al, 2), order_status="FULFILLED", bundle_order_id=f"BORD-2026-{k + 1:06d}", _bo=k, _role=role))
        orders = pd.concat([orders, pd.DataFrame(bl)], ignore_index=True)
    orders["_isb"] = (orders._bo >= 0).astype(int)
    orders = orders.sort_values(["order_date", "sku", "_isb", "_bo"], kind="stable").reset_index(drop=True)
    orders["order_id"] = [f"ORD-2026-{i + 1:06d}" for i in range(len(orders))]
    oid = {(int(b_), r_): o_ for b_, r_, o_ in zip(orders._bo, orders._role, orders.order_id) if b_ >= 0}
    orders["bundle_order_id"] = orders.bundle_order_id.replace("", np.nan)
    bo_rows = []
    for k, bs in enumerate(bundle_sales):
        bb = bundles[bs["bi"]]; ab = acc_by_bi[bs["bi"]]; d_ = bs["d"]
        rev = round(bs["q"] * bb["bundle_price"], 2); cst = round(bs["q"] * float(day_cost[d_, ab["p"]] + day_cost[d_, ab["s"]]), 2)
        bo_rows.append(dict(bundle_order_id=f"BORD-2026-{k + 1:06d}", bundle_id=bb["bundle_id"], order_id=oid[(k, "P")], secondary_order_id=oid[(k, "S")],
                            order_date=dstrs[d_], channel=bs["channel"], quantity=bs["q"], bundle_selling_price=bb["bundle_price"], total_revenue=rev,
                            total_cost=cst, gross_profit=round(rev - cst, 2), aged_units_cleared=bs["aged"]))
    bo_df = pd.DataFrame(bo_rows, columns=[x["name"] for x in ENTITIES["BundleOrder"]["fields"]])
    pb_df = pd.DataFrame(bundles, columns=[x["name"] for x in ENTITIES["ProductBundle"]["fields"] if x["name"] != "bundle_status"])
    asof_s = dstr(as_of)
    pb_df.insert(list(x["name"] for x in ENTITIES["ProductBundle"]["fields"]).index("bundle_status"), "bundle_status",
                 [B.bundle_status(r_ or None, vf_, vt_, asof_s) for r_, vf_, vt_ in zip(pb_df.rejection_reason, pb_df.valid_from, pb_df.valid_to)])
    # stock lots
    cso_end = cso_hist[la, np.arange(S)]; lots = []
    for j in range(D + 1):
        sel = np.nonzero((lot_q[j] > 0) & ((j == 0) | ((j - 1) <= la)))[0]
        if not len(sel):
            continue
        rd = [dstr(START - dt.timedelta(int(age_open[x]))) for x in sel] if j == 0 else [dstrs[j - 1]] * len(sel)
        rem = np.clip(lot_cum[j, sel] - cso_end[sel], 0, lot_q[j, sel])
        lots.append(pd.DataFrame(dict(
            lot_id=[f"LOT-{sku_ids[x]}-{r.replace('-', '')}" for x, r in zip(sel, rd)], sku=sku_ids[sel], received_date=rd, received_units=lot_q[j, sel],
            source="OPENING_BALANCE" if j == 0 else "REPLENISHMENT", unit_cost=costs[0][sel] if j == 0 else day_cost[j - 1, sel],
            remaining_units=rem, lot_status=np.where(rem > 0, "OPEN", "DEPLETED"))))
    lot_df = pd.concat(lots, ignore_index=True).sort_values(["sku", "received_date"], kind="stable").reset_index(drop=True)
    dec_cols = [x["name"] for x in ENTITIES["PriceDecision"]["fields"]]
    dec_df = pd.DataFrame(dec_rows, columns=dec_cols)
    dp_df = pd.DataFrame(dp_rows, columns=["decision_id", "promo_id", "evaluation_status", "rejection_reason", "apply_sequence", "discount_amt"])
    dp_df["apply_sequence"] = dp_df.apply_sequence.astype("Int64")

    tables = {"Product": prod, "AnnualPriceHistory": ah_df, "PriceGradient": grad_df, "CostRecord": cost_df, "PriceHistory": ph, "CompetitorObservation": obs_df, "InventorySnapshot": inv,
              "Promotion": promo_df, "PromotionRule": promo_rule_df, "PromotionProduct": promo_prod_df,
              "PromotionExclusion": promo_excl_df, "PromotionEvent": promo_event_df, "Orders": orders, "PriceDecision": dec_df,
              "DecisionPromotion": dp_df,
              "InventoryLot": lot_df, "ProductBundle": pb_df, "BundleOrder": bo_df}
    for name, df in tables.items():
        cols = [x["name"] for x in ENTITIES[name]["fields"]]
        df[cols].to_csv(os.path.join(out, ENTITIES[name]["file"]), index=False)

    # ----------------------------------------------------------------- ground truth
    ga = pd.DataFrame(gt_anom, columns=["issue_type", "entity", "record_id", "sku", "decision_id", "description", "detection_rule",
                                         "expected_value", "observed_value"])
    ga.insert(0, "anomaly_id", [f"GT-{i + 1:06d}" for i in range(len(ga))])
    ga.to_csv(os.path.join(gt_dir, "ground_truth_anomalies.csv"), index=False)
    ga.to_json(os.path.join(gt_dir, "ground_truth_anomalies.json"), orient="records", indent=1)
    gd = pd.DataFrame(gt_dec, columns=["decision_id", "expected_base_price", "expected_net_price", "expected_applied_promos",
                                        "expected_margin_pct", "expected_reason_code", "issue_type"])
    gd.to_csv(os.path.join(gt_dir, "ground_truth_decisions.csv"), index=False)

    # ----------------------------------------------------------------- docs / SQL
    with open(os.path.join(out, "data_dictionary.md"), "w", encoding="utf-8") as fh:
        fh.write(dictionary_md())
    with open(os.path.join(out, "data_dictionary.json"), "w", encoding="utf-8") as fh:
        fh.write(dictionary_json())
    with open(os.path.join(out, "schema.sql"), "w", encoding="utf-8") as fh:
        fh.write(ddl())
    with open(os.path.join(out, "rules_config.json"), "w", encoding="utf-8") as fh:
        json.dump(GLOBAL_RULES, fh, indent=2)
    cmd = f"python generate.py --skus {S} --days {D} --promos {P} --seed {a.seed} --out <OUT_DIR>" + (" --sql" if a.sql else "")
    with open(os.path.join(out, "generator_command.txt"), "w") as fh:
        fh.write(cmd + "\n")
    if a.sql:
        import sqlite3
        con = sqlite3.connect(":memory:")
        con.executescript(ddl())
        for name in ORDER:
            cols = [x["name"] for x in ENTITIES[name]["fields"]]
            df = tables[name][cols].astype(object).where(tables[name][cols].notna(), None)
            con.executemany(f'INSERT INTO {ENTITIES[name]["table"]} VALUES ({",".join("?" * len(cols))})', df.values.tolist())
        con.commit()
        with open(os.path.join(out, "seed.sql"), "w", encoding="utf-8") as fh:
            fh.write(ddl() + "\n")
            for line in con.iterdump():
                if line.startswith("INSERT"):
                    fh.write(line + "\n")
    counts = {n: int(len(df)) for n, df in tables.items()}
    counts.update(ground_truth_anomalies=len(ga), ground_truth_decisions=len(gd))
    manifest = dict(
        generator="generate.py", seed=a.seed, scale=dict(skus=S, days=D, promos=P), window=[dstr(dates[0]), dstr(dates[-1])],
        generated_with=dict(python=sys.version.split()[0], numpy=np.__version__, pandas=pd.__version__),
        external_data=[], provenance="Fully synthetic. No external or public datasets used; no personal data. Schema inspired by generic retail pricing domain models.",
        row_counts=counts)
    files = {}
    for root, _, fs in os.walk(out):
        for fn in sorted(fs):
            if fn in ("source_manifest.json",) or fn.startswith("validation") or fn in ("metrics.json",):
                continue
            pth = os.path.join(root, fn)
            h = hashlib.sha256()
            with open(pth, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            files[os.path.relpath(pth, out).replace("\\", "/")] = h.hexdigest()
    manifest["sha256"] = dict(sorted(files.items()))
    with open(os.path.join(out, "source_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()
