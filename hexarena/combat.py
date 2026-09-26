# -*- coding: utf-8 -*-
"""戦闘シミュレーション（同じ入力なら全PCで同じ結果になる決定的処理）"""
import random
from data import UNITS, TRAITS, ABILITIES, compute_traits, base_stats, ability_value

ROWS, COLS = 8, 7
DT = 1.0 / 30.0
MAX_TIME = 35.0
MOVE_TIME = 0.4

CELLS = [(r, c) for r in range(ROWS) for c in range(COLS)]


def _cube(r, c):
    x = c - (r - (r & 1)) // 2
    return x, -x - r, r


def _dist(a, b):
    ax, ay, az = _cube(*a)
    bx, by, bz = _cube(*b)
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


DIST = {(a, b): _dist(a, b) for a in CELLS for b in CELLS}
_EVEN = [(-1, -1), (-1, 0), (0, -1), (0, 1), (1, -1), (1, 0)]
_ODD = [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0), (1, 1)]


def _nb(r, c):
    out = []
    for dr, dc in (_ODD if r & 1 else _EVEN):
        rr, cc = r + dr, c + dc
        if 0 <= rr < ROWS and 0 <= cc < COLS:
            out.append((rr, cc))
    return out


NEIGH = {cell: _nb(*cell) for cell in CELLS}


class CU:
    """戦闘中のユニット"""
    pass


class CombatSim:
    def __init__(self, setup):
        self.rng = random.Random(setup["seed"])
        self.t = 0.0
        self.units = []
        self.grid = {}
        self.done = False
        self.winner = None
        self.ev = []
        ua = setup["a"]["units"]
        ub = setup["b"]["units"]
        ta = compute_traits([u[0] for u in ua])
        tb = compute_traits([u[0] for u in ub])
        for side, ul, mine, theirs in (("a", ua, ta, tb), ("b", ub, tb, ta)):
            for uid, star, r, c in ul:
                cell = (4 + r, c) if side == "a" else (3 - r, 6 - c)
                if cell in self.grid:
                    continue
                u = self._make(uid, star, side, mine, theirs)
                u.idx = len(self.units)
                u.r, u.c = cell
                u.pr, u.pc = cell
                u.mt = -1.0
                self.units.append(u)
                self.grid[cell] = u
        for u in self.units:
            if u.leap:
                rows = [0, 1] if u.side == "a" else [7, 6]
                cands = [(ri, abs(c - u.c), c) for ri, r in enumerate(rows) for c in range(COLS)
                         if (r, c) not in self.grid]
                if cands:
                    cands.sort()
                    ri, _, c = cands[0]
                    self._relocate(u, (rows[ri], c))

    # ---------- 生成 ----------
    def _make(self, uid, star, side, mine, theirs):
        u = CU()
        u.uid, u.star, u.side = uid, star, side
        b = {}

        def add(stats, tier):
            for k, vals in stats.items():
                b[k] = b.get(k, 0.0) + vals[min(tier, len(vals)) - 1]

        bs = base_stats(uid, star)
        if uid in UNITS:
            info = UNITS[uid]
            for tname, cnt, tier in mine:
                if tier <= 0:
                    continue
                td = TRAITS[tname]
                if td["scope"] == "team" or (td["scope"] == "self" and tname in info["traits"]):
                    add(td["stats"], tier)
            u.ability = info["ability"]
            u.abval = ability_value(info["ability"], info["cost"], star)
        else:
            u.ability = None
            u.abval = 0
        for tname, cnt, tier in theirs:
            if tier > 0 and TRAITS[tname]["scope"] == "enemy":
                add(TRAITS[tname]["stats"], tier)
        g = lambda k: b.get(k, 0.0)
        u.maxhp = (bs["hp"] + g("hp_flat")) * (1 + g("hp_pct") / 100)
        u.hp = u.maxhp
        u.atk = bs["atk"] * (1 + g("atk_pct") / 100)
        u.as_base = bs["as"] * (1 + g("as_pct") / 100)
        u.armor = bs["armor"] + g("armor")
        u.mr = bs["mr"] + g("mr")
        u.range = bs["rng"]
        u.maxmana = bs["mana"]
        u.mana = min(g("mana_start"), u.maxmana * 0.95) if u.maxmana else 0
        u.ap = 100 + g("ap")
        u.crit = min(1.0, 0.25 + g("crit") / 100)
        u.critdmg = 1.4 + g("crit_dmg") / 100
        u.dodge = min(0.6, g("dodge") / 100)
        for k in ("omnivamp", "dmg_amp", "dmg_red", "block", "regen_pct", "regen_flat", "mana_regen",
                  "burn", "chill", "proc", "poison", "splash", "stack_as", "thorns", "armor_pen",
                  "mana_on_hit", "revive"):
            setattr(u, k, g(k))
        u.dmg_red = min(u.dmg_red, 70)
        u.leap = g("leap") > 0
        sh = g("shield_pct") * u.maxhp / 100 + g("shield_flat")
        u.shields = [[sh, 9999.0]] if sh > 0 else []
        u.stun_until = 0.0
        u.chill_until = 0.0
        u.chill_amt = 0.0
        u.burn_until = 0.0
        u.burn_amt = 0.0
        u.poison_until = 0.0
        u.poison_amt = 0.0
        u.taunt_by = None
        u.taunt_until = 0.0
        u.as_buffs = []
        u.atk_buffs = []
        u.ap_buffs = []
        u.stacks = 0
        u.revived = False
        u.alive = True
        u.target = None
        u.atk_cd = 0.3
        u.move_cd = 0.0
        u.cast_lock = 0.0
        return u

    # ---------- 便利関数 ----------
    def shield_total(self, u):
        return sum(s[0] for s in u.shields)

    def eff_as(self, u):
        pct = sum(p for p, e in u.as_buffs) + u.stacks * u.stack_as
        v = u.as_base * (1 + pct / 100)
        if u.chill_until > self.t:
            v *= (1 - u.chill_amt / 100)
        return max(0.2, min(v, 5.0))

    def eff_atk(self, u):
        return u.atk * (1 + sum(p for p, e in u.atk_buffs) / 100)

    def eff_ap(self, u):
        return u.ap + sum(p for p, e in u.ap_buffs)

    def d(self, a, b):
        return DIST[(a.r, a.c), (b.r, b.c)]

    def nearest(self, u, lst):
        best, bd = None, 99
        for e in lst:
            dd = self.d(u, e)
            if dd < bd:
                bd, best = dd, e
        return best

    def _relocate(self, u, cell):
        del self.grid[(u.r, u.c)]
        u.pr, u.pc = u.r, u.c
        u.r, u.c = cell
        u.mt = self.t
        self.grid[cell] = u

    # ---------- メインループ ----------
    def step(self):
        if self.done:
            return []
        self.ev = ev = []
        self.t += DT
        t = self.t
        for u in self.units:
            if not u.alive:
                continue
            if u.as_buffs:
                u.as_buffs = [x for x in u.as_buffs if x[1] > t]
            if u.atk_buffs:
                u.atk_buffs = [x for x in u.atk_buffs if x[1] > t]
            if u.ap_buffs:
                u.ap_buffs = [x for x in u.ap_buffs if x[1] > t]
            if u.shields:
                u.shields = [s for s in u.shields if s[1] > t and s[0] > 0.01]
            if u.regen_pct or u.regen_flat:
                self.heal(u, (u.regen_pct * u.maxhp / 100 + u.regen_flat) * DT, show=False)
            if u.mana_regen and u.maxmana:
                u.mana += u.mana_regen * DT
            if u.burn_until > t:
                self.damage(None, u, u.burn_amt * u.maxhp / 100 * DT, "true", silent=True)
                if not u.alive:
                    continue
            if u.poison_until > t:
                self.damage(None, u, u.poison_amt * DT, "true", silent=True)
                if not u.alive:
                    continue
            if u.stun_until > t:
                continue
            if u.cast_lock > 0:
                u.cast_lock -= DT
                continue
            if u.maxmana > 0 and u.mana >= u.maxmana:
                u.mana = 0.0
                self.cast(u)
                u.cast_lock = 0.3
                continue
            tgt = self.pick_target(u)
            if tgt is None:
                continue
            if self.d(u, tgt) <= u.range:
                u.atk_cd -= DT
                if u.atk_cd <= 0:
                    self.attack(u, tgt)
                    u.atk_cd = max(0.0, u.atk_cd) + 1.0 / self.eff_as(u)
            else:
                u.move_cd -= DT
                if u.move_cd <= 0:
                    self.move_toward(u, tgt)
                    u.move_cd = MOVE_TIME
        alive_a = any(u.alive and u.side == "a" for u in self.units)
        alive_b = any(u.alive and u.side == "b" for u in self.units)
        if not alive_a or not alive_b:
            self.done = True
            self.winner = "a" if alive_a else ("b" if alive_b else "draw")
        elif t >= MAX_TIME:
            self.done = True
            self.winner = "draw"
        return ev

    def run_all(self):
        while not self.done:
            self.step()
        return {"winner": self.winner, "duration": self.t,
                "survivors": {"a": [(u.uid, u.star) for u in self.units if u.alive and u.side == "a"],
                              "b": [(u.uid, u.star) for u in self.units if u.alive and u.side == "b"]}}

    def pick_target(self, u):
        if u.taunt_by is not None and u.taunt_until > self.t and u.taunt_by.alive:
            u.target = u.taunt_by
            return u.target
        tg = u.target
        if tg is not None and tg.alive and self.d(u, tg) <= u.range:
            return tg
        best, bd = None, 99
        for e in self.units:
            if e.alive and e.side != u.side:
                dd = self.d(u, e)
                if dd < bd:
                    bd, best = dd, e
        u.target = best
        return best

    def move_toward(self, u, tgt):
        start = (u.r, u.c)
        tc = (tgt.r, tgt.c)
        cur_d = DIST[start, tc]
        prev = {start: None}
        depth = {start: 0}
        q = [start]
        i = 0
        best, bkey = None, None
        while i < len(q):
            cell = q[i]
            i += 1
            if cell != start:
                dd = DIST[cell, tc]
                key = (0, depth[cell], 0) if dd <= u.range else (1, dd, depth[cell])
                if bkey is None or key < bkey:
                    bkey, best = key, cell
            if depth[cell] >= 10:
                continue
            for n in NEIGH[cell]:
                if n in prev or n in self.grid:
                    continue
                prev[n] = cell
                depth[n] = depth[cell] + 1
                q.append(n)
        if best is None:
            return
        if bkey[0] == 1 and bkey[1] >= cur_d:
            return
        step = best
        while prev[step] != start:
            step = prev[step]
        self._relocate(u, step)

    # ---------- 攻撃・ダメージ ----------
    def attack(self, u, tgt):
        if u.maxmana:
            u.mana += 10 + u.mana_on_hit
        self.ev.append(("atk", u.idx, tgt.idx, u.range > 1))
        if u.stack_as:
            u.stacks = min(8, u.stacks + 1)
        if tgt.dodge > 0 and self.rng.random() < tgt.dodge:
            self.ev.append(("miss", tgt.idx))
            return
        dmg = self.eff_atk(u)
        if self.rng.random() < u.crit:
            dmg *= u.critdmg
        self.damage(u, tgt, dmg, "phys", attack=True)
        if tgt.alive:
            if u.burn:
                tgt.burn_amt = max(tgt.burn_amt if tgt.burn_until > self.t else 0, u.burn)
                tgt.burn_until = self.t + 3.0
            if u.chill:
                tgt.chill_amt = max(tgt.chill_amt if tgt.chill_until > self.t else 0, u.chill)
                tgt.chill_until = self.t + 2.0
            if u.poison:
                tgt.poison_amt = max(tgt.poison_amt if tgt.poison_until > self.t else 0, u.poison)
                tgt.poison_until = self.t + 3.0
        if u.proc and self.rng.random() < 0.25:
            others = [e for e in self.units if e.alive and e.side != u.side and e is not tgt]
            self.damage(u, tgt, u.proc, "magic")
            if others:
                nx = self.nearest(tgt, others)
                self.damage(u, nx, u.proc, "magic")
        if u.splash:
            for n in NEIGH[(tgt.r, tgt.c)]:
                e = self.grid.get(n)
                if e is not None and e.side != u.side and e.alive:
                    self.damage(u, e, dmg * u.splash / 100, "phys")

    def damage(self, src, tgt, amount, kind, attack=False, silent=False):
        if not tgt.alive or amount <= 0:
            return 0.0
        if kind == "phys":
            res = tgt.armor * (1 - (src.armor_pen / 100 if src else 0))
        elif kind == "magic":
            res = tgt.mr
        else:
            res = 0
        mult = 100 / (100 + res) if res >= 0 else 2 - 100 / (100 - res)
        d = amount * mult
        if src is not None:
            d *= 1 + src.dmg_amp / 100
        d *= 1 - tgt.dmg_red / 100
        if attack:
            d = max(0.0, d - tgt.block)
        dealt = d
        for s in tgt.shields:
            if d <= 0:
                break
            a = min(s[0], d)
            s[0] -= a
            d -= a
        tgt.hp -= d
        if tgt.maxmana and not silent:
            tgt.mana += min(15.0, amount * 0.03)
        if src is not None and src.omnivamp and src.alive:
            self.heal(src, dealt * src.omnivamp / 100, show=False)
        if attack and tgt.thorns and src is not None and src.alive:
            self.damage(tgt, src, amount * tgt.thorns / 100, "magic")
        if not silent:
            self.ev.append(("dmg", tgt.idx, int(dealt), kind))
        if tgt.hp <= 0:
            self.kill(tgt)
        return dealt

    def kill(self, u):
        if u.revive > 0 and not u.revived:
            u.revived = True
            u.hp = u.maxhp * u.revive / 100
            u.shields = []
            u.burn_until = u.poison_until = u.stun_until = 0.0
            self.ev.append(("revive", u.idx))
            return
        u.alive = False
        u.hp = 0
        if self.grid.get((u.r, u.c)) is u:
            del self.grid[(u.r, u.c)]
        self.ev.append(("die", u.idx))

    def heal(self, u, amt, show=True):
        if not u.alive or amt <= 0:
            return
        a = min(amt, u.maxhp - u.hp)
        if a <= 0:
            return
        u.hp += a
        if show and a >= 1:
            self.ev.append(("heal", u.idx, int(a)))

    def stun(self, e, dur):
        e.stun_until = max(e.stun_until, self.t + dur)

    # ---------- スキル ----------
    def cast(self, u):
        ab = u.ability
        if ab is None:
            return
        t = self.t
        v = u.abval * self.eff_ap(u) / 100
        self.ev.append(("cast", u.idx, ab))
        enemies = [e for e in self.units if e.alive and e.side != u.side]
        allies = [a for a in self.units if a.alive and a.side == u.side]
        if not enemies:
            return
        tgt = u.target if (u.target is not None and u.target.alive) else self.nearest(u, enemies)
        if ab == "strike":
            self.damage(u, tgt, v, "magic")
        elif ab == "stun":
            self.damage(u, tgt, v, "magic")
            if tgt.alive:
                self.stun(tgt, ABILITIES["stun"]["dur"])
        elif ab == "snipe":
            far, fd = None, -1
            for e in enemies:
                dd = self.d(u, e)
                if dd > fd:
                    fd, far = dd, e
            self.damage(u, far, v + self.eff_atk(u) * 1.5, "phys")
        elif ab == "leap":
            low = min(enemies, key=lambda e: (e.hp, e.idx))
            free = [n for n in NEIGH[(low.r, low.c)] if n not in self.grid]
            if free:
                free.sort(key=lambda n: (DIST[n, (u.r, u.c)], n))
                self._relocate(u, free[0])
            u.target = low
            self.damage(u, low, v, "magic")
        elif ab == "heal":
            a = min(allies, key=lambda x: (x.hp / x.maxhp, x.idx))
            self.heal(a, v)
        elif ab == "aura_heal":
            for a in allies:
                self.heal(a, v)
        elif ab == "shield":
            u.shields.append([v, t + 4.0])
        elif ab == "taunt":
            u.shields.append([v, t + 4.0])
            for e in enemies:
                if self.d(u, e) <= 2:
                    e.taunt_by = u
                    e.taunt_until = t + 2.0
        elif ab == "frenzy":
            u.as_buffs.append((v, t + 4.0))
        elif ab == "multishot":
            k = min(3, len(enemies))
            for e in self.rng.sample(enemies, k):
                self.damage(u, e, v + self.eff_atk(u) * 0.8, "phys")
        elif ab == "drain":
            dd = self.damage(u, tgt, v, "magic")
            self.heal(u, dd * 0.6)
        elif ab == "blast":
            hits = [tgt] + [e for e in enemies if e is not tgt and self.d(tgt, e) <= 1]
            for e in hits:
                self.damage(u, e, v, "magic")
        elif ab == "chain":
            hit = []
            cur = tgt
            for i in range(4):
                self.damage(u, cur, v * (0.85 ** i), "magic")
                hit.append(cur)
                rest = [e for e in enemies if e.alive and e not in hit]
                if not rest:
                    break
                cur = self.nearest(cur, rest)
        elif ab == "quake":
            near = [e for e in enemies if self.d(u, e) <= 1] or [tgt]
            for e in near:
                self.damage(u, e, v, "magic")
                if e.alive:
                    self.stun(e, ABILITIES["quake"]["dur"])
        elif ab == "buff_team":
            for a in allies:
                a.atk_buffs.append((v, t + 5.0))
                a.ap_buffs.append((v, t + 5.0))
        elif ab == "meteor":
            hits = [e for e in enemies if self.d(tgt, e) <= 2]
            for e in hits:
                self.damage(u, e, v, "magic")
