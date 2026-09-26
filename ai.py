# -*- coding: utf-8 -*-
"""AIプレイヤーの思考"""
import data
from data import UNITS, MAX_LEVEL, BENCH_SIZE, BOARD_ROWS, BOARD_COLS, ROW_PREF, COL_PREF, sell_value


def target_level(r, p):
    if r < 5:
        lv = 3
    elif r < 9:
        lv = 5
    elif r < 13:
        lv = 6
    elif r < 17:
        lv = 7
    elif r < 23:
        lv = 8
    else:
        lv = 9
    if p.hp < 40:
        lv += 1
    return min(MAX_LEVEL, lv)


def reserve_for(g, p):
    if g.round <= 4 or p.hp <= 30:
        return 0
    if g.round <= 10:
        return 20
    return 50 if p.level < 8 else 30


def unit_value(uid, star):
    return UNITS[uid]["cost"] * (3 ** (star - 1))


def trait_counts(g, p):
    seen = set()
    cnt = {}
    for loc, u in g.iter_units(p):
        if u[0] not in seen:
            seen.add(u[0])
            for t in UNITS[u[0]]["traits"]:
                cnt[t] = cnt.get(t, 0) + 1
    return cnt


def shop_score(g, p, uid):
    owned = g.owned_counts(p)
    tc = trait_counts(g, p)
    s = 0.0
    if uid in owned:
        s += 4.0 if owned[uid] < 9 else -10.0
    s += sum(min(tc.get(t, 0), 4) for t in UNITS[uid]["traits"]) * 0.8
    s += UNITS[uid]["cost"] * 0.4
    total = sum(1 for _ in g.iter_units(p))
    if total < p.level + 2:
        s += 2.0
    s += g.rng.random() * 0.5
    return s


def buy_pass(g, p, reserve):
    bought = False
    order = sorted(range(len(p.shop)), key=lambda i: -shop_score(g, p, p.shop[i]) if p.shop[i] else 99)
    for i in order:
        uid = p.shop[i]
        if uid is None:
            continue
        cost = UNITS[uid]["cost"]
        sc = shop_score(g, p, uid)
        if sc < 2.5 or p.gold - cost < reserve:
            continue
        if g.buy(p, i):
            bought = True
    return bought


def maybe_use_skill(g, p):
    """コントローラーのスキル：決めたラウンドを過ぎ、払えるなら使う（体力が減ってきたら回復役は早めに）"""
    if p.ctrl_used or p.controller is None:
        return
    c = data.CONTROLLERS.get(p.controller)
    if c is None or g.skill_block_reason(p):
        return
    if c["type"] == "heal":
        if p.hp <= 55:
            g.use_skill(p)
        return
    if c["cost_type"] == "hp" and p.hp - c["cost"] < 30:
        return
    if g.round >= p.ai_skill_round:
        g.use_skill(p)


def take_turn(g, p):
    maybe_use_skill(g, p)
    reserve = reserve_for(g, p)
    tl = target_level(g.round, p)
    while p.level < tl and p.gold - 4 >= reserve and p.level < MAX_LEVEL:
        g.buy_xp(p)
    rolls = 0
    while True:
        buy_pass(g, p, reserve)
        if rolls < 8 and (p.level >= 7 or p.hp <= 40) and p.gold - 2 >= reserve and p.gold >= 2:
            g.reroll(p)
            rolls += 1
            continue
        break
    arrange(g, p)


def arrange(g, p):
    units = [u for loc, u in g.iter_units(p)]
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            p.board[r][c] = None
    p.bench = [None] * BENCH_SIZE
    # 盤面に出すユニットを選ぶ（強さ＋シナジー）
    chosen = []
    rest = units[:]
    while rest and len(chosen) < g.board_limit(p):
        tc = {}
        seen = set()
        for u in chosen:
            if u[0] not in seen:
                seen.add(u[0])
                for t in UNITS[u[0]]["traits"]:
                    tc[t] = tc.get(t, 0) + 1

        def val(u):
            dup = any(c[0] == u[0] for c in chosen)
            syn = 0 if dup else sum(tc.get(t, 0) for t in UNITS[u[0]]["traits"])
            return unit_value(u[0], u[1]) + syn * 0.8 - (3 if dup else 0)
        best = max(rest, key=val)
        rest.remove(best)
        chosen.append(best)
    for u in chosen:
        cell = g.pref_cell(p, u[0])
        if cell:
            p.board[cell[0]][cell[1]] = u
        else:
            rest.append(u)
    rest.sort(key=lambda u: -unit_value(u[0], u[1]))
    counts = {}
    for u in rest:
        counts[u[0]] = counts.get(u[0], 0) + 1
    keep_max = 7
    kept = []
    for u in rest:
        kept.append(u)
    # ベンチ上限を超える / 多すぎる分は価値の低いものから売る（ペアは残す）
    while len(kept) > keep_max:
        cand = sorted(kept, key=lambda u: (counts.get(u[0], 0) > 1 or any(b[0] == u[0] for row in p.board for b in row if b),
                                           unit_value(u[0], u[1])))
        s = cand[0]
        kept.remove(s)
        p.gold += sell_value(s[0], s[1])
        g.pool[s[0]] += 3 ** (s[1] - 1)
    for i, u in enumerate(kept[:BENCH_SIZE]):
        p.bench[i] = u
