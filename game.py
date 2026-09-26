# -*- coding: utf-8 -*-
"""ゲーム進行（ホスト側で動く本体。ひとり用もホスト扱い）"""
import random
import data
from data import (UNITS, UNIT_IDS_BY_COST, POOL_SIZE, SHOP_ODDS, XP_TO_NEXT, MAX_LEVEL, BENCH_SIZE,
                  SHOP_SIZE, BOARD_ROWS, BOARD_COLS, ROW_PREF, COL_PREF, AI_NAMES,
                  TRAITS, compute_traits, sell_value, is_pve_round, pve_board, pve_reward, stage_damage)
from combat import CombatSim
import ai

NUM_PLAYERS = 8


class Player:
    def __init__(self, pid, name, is_ai):
        self.pid = pid
        self.name = name
        self.is_ai = is_ai
        self.hp = data.START_HP
        self.gold = 0
        self.level = 1
        self.xp = 0
        self.board = [[None] * BOARD_COLS for _ in range(BOARD_ROWS)]
        self.bench = [None] * BENCH_SIZE
        self.shop = [None] * SHOP_SIZE
        self.locked = False
        self.ready = False
        self.alive = True
        self.placement = 0
        self.win_streak = 0
        self.loss_streak = 0
        self.last_opp = None
        self.toast = ""
        self.toast_seq = 0
        self.last_result = ""

    def say(self, text):
        self.toast = text
        self.toast_seq += 1


class Game:
    def __init__(self, human_names, seed=None, planning_time=30.0):
        self.rng = random.Random(seed)
        self.planning_time = planning_time
        self.players = []
        for n in human_names[:NUM_PLAYERS]:
            self.players.append(Player(len(self.players), n, False))
        i = 0
        while len(self.players) < NUM_PLAYERS:
            self.players.append(Player(len(self.players), AI_NAMES[i], True))
            i += 1
        self.pool = {uid: POOL_SIZE[u["cost"]] for uid, u in UNITS.items()}
        self.round = 0
        self.phase = "planning"
        self.timer = 0.0
        self.combats = {}
        self.pending = []
        self.log = []
        self.cid = 0
        for p in self.players:
            uid = self.draw_unit_of_cost(1)
            if uid:
                self.pool[uid] -= 1
                p.bench[0] = [uid, 1]
        self.start_round()

    # ---------- ユーティリティ ----------
    def add_log(self, s):
        self.log.append(s)
        if len(self.log) > 30:
            self.log = self.log[-30:]

    def iter_units(self, p):
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                if p.board[r][c]:
                    yield ("board", r, c), p.board[r][c]
        for i in range(BENCH_SIZE):
            if p.bench[i]:
                yield ("bench", i), p.bench[i]

    def board_count(self, p):
        return sum(1 for r in p.board for u in r if u)

    def board_units(self, p):
        return [[u[0], u[1], r, c] for r in range(BOARD_ROWS) for c in range(BOARD_COLS)
                if (u := p.board[r][c])]

    def owned_counts(self, p):
        cnt = {}
        for loc, u in self.iter_units(p):
            cnt[u[0]] = cnt.get(u[0], 0) + 3 ** (u[1] - 1)
        return cnt

    @staticmethod
    def valid_loc(loc):
        try:
            if loc[0] == "bench":
                return 0 <= int(loc[1]) < BENCH_SIZE
            if loc[0] == "board":
                return 0 <= int(loc[1]) < BOARD_ROWS and 0 <= int(loc[2]) < BOARD_COLS
        except (TypeError, ValueError, IndexError):
            return False
        return False

    def get_at(self, p, loc):
        if loc[0] == "bench":
            return p.bench[int(loc[1])]
        return p.board[int(loc[1])][int(loc[2])]

    def set_at(self, p, loc, v):
        if loc[0] == "bench":
            p.bench[int(loc[1])] = v
        else:
            p.board[int(loc[1])][int(loc[2])] = v

    def pref_cell(self, p, uid):
        rows = ROW_PREF[UNITS[uid]["arch"]]
        for r in rows:
            for c in COL_PREF:
                if p.board[r][c] is None:
                    return (r, c)
        return None

    # ---------- ショップ ----------
    def draw_unit_of_cost(self, cost):
        cands = [(uid, self.pool[uid]) for uid in UNIT_IDS_BY_COST[cost] if self.pool[uid] > 0]
        total = sum(w for _, w in cands)
        if total <= 0:
            return None
        x = self.rng.random() * total
        for uid, w in cands:
            x -= w
            if x < 0:
                return uid
        return cands[-1][0]

    def roll_shop(self, p):
        odds = SHOP_ODDS[p.level]
        for i in range(SHOP_SIZE):
            uid = None
            for _ in range(6):
                x = self.rng.random() * 100
                cost, acc = 1, 0
                for ci, o in enumerate(odds):
                    acc += o
                    if x < acc:
                        cost = ci + 1
                        break
                uid = self.draw_unit_of_cost(cost)
                if uid:
                    break
            p.shop[i] = uid

    def add_xp(self, p, amt):
        p.xp += amt
        while p.level < MAX_LEVEL and p.xp >= XP_TO_NEXT[p.level]:
            p.xp -= XP_TO_NEXT[p.level]
            p.level += 1
        if p.level >= MAX_LEVEL:
            p.xp = 0

    def buy(self, p, slot):
        if not (0 <= slot < SHOP_SIZE):
            return False
        uid = p.shop[slot]
        if uid is None:
            return False
        cost = UNITS[uid]["cost"]
        if p.gold < cost:
            p.say("ゴールドが足りません")
            return False
        if self.pool[uid] <= 0:
            p.say("そのユニットは売り切れです")
            p.shop[slot] = None
            return False
        free = next((i for i in range(BENCH_SIZE) if p.bench[i] is None), None)
        if free is None:
            locs = [loc for loc, u in self.iter_units(p) if u[0] == uid and u[1] == 1]
            if len(locs) < 2:
                p.say("ベンチがいっぱいです（売却して空けてください）")
                return False
            p.gold -= cost
            self.pool[uid] -= 1
            p.shop[slot] = None
            locs.sort(key=lambda l: 0 if l[0] == "board" else 1)
            self.set_at(p, locs[1], None)
            self.set_at(p, locs[0], [uid, 2])
            self.try_combine(p, uid)
            return True
        p.gold -= cost
        self.pool[uid] -= 1
        p.shop[slot] = None
        p.bench[free] = [uid, 1]
        self.try_combine(p, uid)
        return True

    def try_combine(self, p, uid):
        for star in (1, 2):
            locs = [loc for loc, u in self.iter_units(p) if u[0] == uid and u[1] == star]
            if len(locs) >= 3:
                locs.sort(key=lambda l: 0 if l[0] == "board" else 1)
                keep = locs[0]
                self.set_at(p, locs[1], None)
                self.set_at(p, locs[2], None)
                self.set_at(p, keep, [uid, star + 1])
                if not p.is_ai:
                    p.say(f"{UNITS[uid]['name']} が ★{star + 1} に強化！")

    def sell(self, p, loc):
        if not self.valid_loc(loc):
            return
        if self.phase != "planning" and loc[0] == "board":
            p.say("戦闘中は盤面のユニットを売れません")
            return
        u = self.get_at(p, loc)
        if not u:
            return
        p.gold += sell_value(u[0], u[1])
        self.pool[u[0]] += 3 ** (u[1] - 1)
        self.set_at(p, loc, None)

    def move(self, p, src, dst):
        if not (self.valid_loc(src) and self.valid_loc(dst)):
            return
        if self.phase != "planning" and (src[0] == "board" or dst[0] == "board"):
            p.say("戦闘中は盤面を動かせません")
            return
        u = self.get_at(p, src)
        if u is None:
            return
        v = self.get_at(p, dst)
        if src[0] == "bench" and dst[0] == "board" and v is None and self.board_count(p) >= p.level:
            p.say(f"盤面に置けるのはレベルと同じ {p.level}体 までです")
            return
        self.set_at(p, src, v)
        self.set_at(p, dst, u)

    def reroll(self, p):
        if p.gold < 2:
            p.say("ゴールドが足りません")
            return False
        p.gold -= 2
        self.roll_shop(p)
        return True

    def buy_xp(self, p):
        if p.level >= MAX_LEVEL:
            return False
        if p.gold < 4:
            p.say("ゴールドが足りません")
            return False
        p.gold -= 4
        self.add_xp(p, 4)
        return True

    def action(self, pid, a):
        if not (0 <= pid < len(self.players)):
            return
        p = self.players[pid]
        if not p.alive or self.phase == "end" or not isinstance(a, dict):
            return
        t = a.get("t")
        try:
            if t == "buy":
                self.buy(p, int(a["slot"]))
            elif t == "sell":
                self.sell(p, a["loc"])
            elif t == "move":
                self.move(p, a["src"], a["dst"])
            elif t == "reroll":
                self.reroll(p)
            elif t == "xp":
                self.buy_xp(p)
            elif t == "lock":
                p.locked = not p.locked
            elif t == "ready":
                if self.phase == "planning":
                    p.ready = not p.ready
        except (KeyError, ValueError, IndexError, TypeError):
            pass

    # ---------- ラウンド進行 ----------
    def income(self, p):
        base = {1: 2, 2: 3, 3: 4}.get(self.round, 5)
        interest = min(5, p.gold // 10)
        s = max(p.win_streak, p.loss_streak)
        sb = 0 if s < 2 else 1 if s < 4 else 2 if s < 5 else 3
        p.gold += base + interest + sb

    def start_round(self):
        self.round += 1
        self.phase = "planning"
        self.timer = self.planning_time if self.round > 1 else min(self.planning_time, 20.0)
        self.combats = {}
        for p in self.players:
            if not p.alive:
                continue
            self.income(p)
            if self.round > 1:
                self.add_xp(p, 2)
            if p.locked:
                p.locked = False
            else:
                self.roll_shop(p)
            p.ready = False
        for p in self.players:
            if p.alive and p.is_ai:
                ai.take_turn(self, p)
        kind = "モンスター戦" if is_pve_round(self.round) else "対人戦"
        self.add_log(f"ラウンド{self.round}（{kind}）開始")

    def autofill(self, p):
        while self.board_count(p) < p.level:
            idx = next((i for i in range(BENCH_SIZE) if p.bench[i]), None)
            if idx is None:
                break
            cell = self.pref_cell(p, p.bench[idx][0])
            if cell is None:
                break
            p.board[cell[0]][cell[1]] = p.bench[idx]
            p.bench[idx] = None

    def make_setup(self, pa, b_pid, b_name, b_units):
        self.cid += 1
        return {"cid": self.cid, "seed": self.rng.randrange(1 << 30),
                "a": {"pid": pa.pid, "name": pa.name, "units": self.board_units(pa)},
                "b": {"pid": b_pid, "name": b_name, "units": b_units}}

    def start_combat(self):
        self.phase = "combat"
        self.combats = {}
        self.pending = []
        alive = [p for p in self.players if p.alive]
        for p in alive:
            self.autofill(p)
            p.ready = False
        maxdur = 0.0
        entries = []
        if is_pve_round(self.round):
            for p in alive:
                entries.append(("pve", p, None, self.make_setup(p, -1, "モンスター", pve_board(self.round))))
        else:
            order = alive[:]
            pairs = []
            for _ in range(12):
                self.rng.shuffle(order)
                pairs = list(zip(order[0::2], order[1::2]))
                if not any(a.last_opp == b.pid or b.last_opp == a.pid for a, b in pairs):
                    break
            for a, b in pairs:
                entries.append(("pvp", a, b, self.make_setup(a, b.pid, b.name, self.board_units(b))))
            if len(order) % 2 == 1:
                a = order[-1]
                g = self.rng.choice([q for q in alive if q is not a])
                entries.append(("ghost", a, g, self.make_setup(a, g.pid, g.name + "（分身）", self.board_units(g))))
        for kind, a, b, setup in entries:
            res = CombatSim(setup).run_all()
            maxdur = max(maxdur, res["duration"])
            self.pending.append((kind, a, b, res, setup))
            self.combats[a.pid] = {"setup": setup, "side": "a"}
            if kind == "pvp":
                self.combats[b.pid] = {"setup": setup, "side": "b"}
        self.timer = min(maxdur + 3.5, 45.0)

    def _lose(self, p, surv, opp_name, dmg_base):
        d = dmg_base + sum(star for uid, star in surv)
        p.hp -= d
        p.loss_streak += 1
        p.win_streak = 0
        p.last_result = f"{opp_name}に敗北… -{d}HP"

    def _win(self, p, opp_name):
        p.gold += 1
        p.win_streak += 1
        p.loss_streak = 0
        p.last_result = f"{opp_name}に勝利！ +1G"

    def end_combat(self):
        base = stage_damage(self.round)
        for kind, a, b, res, setup in self.pending:
            w = res["winner"]
            if kind == "pve":
                if w == "a":
                    g = pve_reward(self.round)
                    a.gold += g
                    a.last_result = f"モンスターに勝利！ +{g}G"
                else:
                    d = 1 + len(res["survivors"]["b"])
                    a.hp -= d
                    a.last_result = f"モンスターに敗北… -{d}HP"
            else:
                bname = setup["b"]["name"]
                real_b = kind == "pvp"
                if w == "a":
                    self._win(a, bname)
                    if real_b:
                        self._lose(b, res["survivors"]["a"], a.name, base)
                elif w == "b":
                    self._lose(a, res["survivors"]["b"], bname, base)
                    if real_b:
                        self._win(b, a.name)
                else:
                    for p in ([a, b] if real_b else [a]):
                        d = base + 1
                        p.hp -= d
                        p.last_result = f"引き分け… -{d}HP"
                a.last_opp = b.pid
                if real_b:
                    b.last_opp = a.pid
            # 盗賊ボーナス
            for p, key in ((a, "a"), (b, "b")):
                if p is None or (key == "b" and kind != "pvp"):
                    continue
                for t, cnt, tier in compute_traits([u[0] for u in setup[key]["units"]]):
                    if t == "盗賊" and tier > 0:
                        p.gold += TRAITS["盗賊"]["stats"]["gold"][tier - 1]
        dead = [p for p in self.players if p.alive and p.hp <= 0]
        dead.sort(key=lambda p: p.hp)
        alive_count = sum(1 for p in self.players if p.alive)
        for p in dead:
            p.placement = alive_count
            alive_count -= 1
            p.alive = False
            p.hp = 0
            for loc, u in list(self.iter_units(p)):
                self.pool[u[0]] += 3 ** (u[1] - 1)
                self.set_at(p, loc, None)
            self.add_log(f"{p.name} が脱落（{p.placement}位）")
        remaining = [p for p in self.players if p.alive]
        if len(remaining) <= 1:
            if remaining:
                remaining[0].placement = 1
                self.add_log(f"{remaining[0].name} の優勝！")
            self.phase = "end"
            self.combats = {}
            return
        self.start_round()

    def tick(self, dt):
        if self.phase == "end":
            return
        self.timer -= dt
        if self.phase == "planning":
            humans = [p for p in self.players if p.alive and not p.is_ai]
            if self.timer <= 0 or all(p.ready for p in humans):
                self.start_combat()
        elif self.phase == "combat":
            if self.timer <= 0:
                self.end_combat()

    # ---------- 送信用の状態 ----------
    def state_for(self, pid):
        p = self.players[pid]
        return {
            "phase": self.phase, "round": self.round, "timer": round(max(0.0, self.timer), 2),
            "pve": is_pve_round(self.round),
            "me": {"pid": pid, "gold": p.gold, "level": p.level, "xp": p.xp,
                   "xp_need": XP_TO_NEXT.get(p.level, 0), "hp": p.hp, "bench": p.bench,
                   "board": p.board, "shop": p.shop, "locked": p.locked, "ready": p.ready,
                   "streak": p.win_streak if p.win_streak else -p.loss_streak,
                   "alive": p.alive, "placement": p.placement, "toast": p.toast,
                   "toast_seq": p.toast_seq, "result": p.last_result},
            "players": [{"pid": q.pid, "name": q.name, "hp": q.hp, "level": q.level, "alive": q.alive,
                         "placement": q.placement, "ai": q.is_ai, "board": q.board}
                        for q in self.players],
            "combat": self.combats.get(pid) if self.phase == "combat" else None,
            "log": self.log[-6:],
        }
