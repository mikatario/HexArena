# -*- coding: utf-8 -*-
"""ヘックス・アリーナ（オートバトル）メイン画面"""
import math
import os
import queue
import sys
import threading

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from data import (UNITS, CREEPS, TRAITS, TRAIT_ORDER, COST_COLORS, SHOP_ODDS, MAX_LEVEL, BENCH_SIZE,
                  SHOP_SIZE, VERSION, GAME_TITLE, ARCH_NAME, compute_traits, base_stats, ability_desc,
                  ability_value, trait_desc, sell_value, pve_board, unit_info)
from combat import CombatSim, MOVE_TIME
from game import Game
import net

W, H = 1280, 720
BG = (16, 18, 26)
PANEL = (28, 32, 44)
PANEL2 = (40, 46, 62)
TEXT = (232, 234, 242)
SUB = (150, 156, 175)
ACCENT = (90, 170, 255)
GOLD = (245, 200, 70)
RED = (230, 80, 80)
GREEN = (90, 205, 120)
OWN = (80, 190, 255)
ENEMY = (240, 90, 90)
TIER_COLORS = [(62, 66, 82), (176, 118, 70), (170, 182, 198), (240, 200, 70)]
STAR_COLORS = {1: (200, 200, 210), 2: (220, 225, 235), 3: (255, 210, 60)}


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ---------------- 文字描画 ----------------
_fonts = {}
_texts = {}


def font(size):
    f = _fonts.get(size)
    if f is None:
        path = resource_path(os.path.join("assets", "NotoSansJP-Regular.otf"))
        if os.path.exists(path):
            f = pygame.font.Font(path, size)
        else:
            f = pygame.font.SysFont("yugothicui,yugothic,meiryo,msgothic,notosanscjkjp", size)
        _fonts[size] = f
    return f


def text_surf(s, size, color):
    key = (s, size, color)
    t = _texts.get(key)
    if t is None:
        if len(_texts) > 4000:
            _texts.clear()
        t = font(size).render(str(s), True, color)
        _texts[key] = t
    return t


def draw_text(surf, s, pos, size=16, color=TEXT, anchor="topleft"):
    t = text_surf(s, size, color)
    r = t.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    surf.blit(t, r)
    return r


def lighten(c, k=25):
    return tuple(min(255, v + k) for v in c)


def get_clipboard():
    try:
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        s = r.clipboard_get()
        r.destroy()
        return s
    except Exception:
        pass
    try:
        return pygame.scrap.get_text() or ""
    except Exception:
        return ""


# ---------------- 部品 ----------------
class Button:
    def __init__(self, rect, label, cb, size=20, color=PANEL2, enabled=True):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.cb = cb
        self.size = size
        self.color = color
        self.enabled = enabled

    def draw(self, surf, mouse):
        hov = self.enabled and self.rect.collidepoint(mouse)
        col = self.color if self.enabled else (34, 36, 44)
        if hov:
            col = lighten(col, 30)
        pygame.draw.rect(surf, col, self.rect, border_radius=8)
        pygame.draw.rect(surf, (90, 100, 125) if self.enabled else (50, 52, 60), self.rect, 2, border_radius=8)
        draw_text(surf, self.label, self.rect.center, self.size, TEXT if self.enabled else SUB, "center")

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.enabled and self.rect.collidepoint(e.pos):
            self.cb()
            return True
        return False


class TextBox:
    def __init__(self, rect, text="", maxlen=16, placeholder=""):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.maxlen = maxlen
        self.active = False
        self.placeholder = placeholder

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.active = self.rect.collidepoint(e.pos)
            if self.active:
                pygame.key.set_text_input_rect(self.rect)
        elif self.active and e.type == pygame.TEXTINPUT:
            self.text = (self.text + e.text)[:self.maxlen]
        elif self.active and e.type == pygame.KEYDOWN:
            if e.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif e.key == pygame.K_v and (e.mod & pygame.KMOD_CTRL):
                self.text = (self.text + get_clipboard().strip())[:self.maxlen]

    def draw(self, surf):
        pygame.draw.rect(surf, (22, 25, 34), self.rect, border_radius=6)
        pygame.draw.rect(surf, ACCENT if self.active else (80, 88, 110), self.rect, 2, border_radius=6)
        if self.text:
            draw_text(surf, self.text, (self.rect.x + 12, self.rect.centery), 22, TEXT, "midleft")
        else:
            draw_text(surf, self.placeholder, (self.rect.x + 12, self.rect.centery), 18, SUB, "midleft")
        if self.active and (pygame.time.get_ticks() // 500) % 2 == 0:
            w = text_surf(self.text, 22, TEXT).get_width() if self.text else 0
            x = self.rect.x + 14 + w
            pygame.draw.line(surf, TEXT, (x, self.rect.y + 10), (x, self.rect.bottom - 10), 2)


def draw_panel(surf, rect, color=PANEL, radius=10):
    pygame.draw.rect(surf, color, rect, border_radius=radius)


def draw_tooltip(surf, lines, pos):
    if not lines:
        return
    pad = 10
    w = max(text_surf(t, s, c).get_width() for t, s, c in lines) + pad * 2
    h = sum(s + 8 for t, s, c in lines) + pad * 2
    x, y = pos[0] + 18, pos[1] + 18
    if x + w > W - 4:
        x = pos[0] - w - 12
    if y + h > H - 4:
        y = H - h - 4
    rect = pygame.Rect(x, y, w, h)
    pygame.draw.rect(surf, (12, 14, 20), rect, border_radius=8)
    pygame.draw.rect(surf, (100, 110, 140), rect, 2, border_radius=8)
    yy = y + pad
    for t, s, c in lines:
        draw_text(surf, t, (x + pad, yy), s, c)
        yy += s + 8


# ---------------- 盤面の座標 ----------------
R = 36
SQ3 = math.sqrt(3)
BX0 = 640 - SQ3 * R * 3.25
BY0 = 50 + R


def cell_center(r, c):
    return (BX0 + SQ3 * R * (c + 0.5 * (r & 1)), BY0 + 1.5 * R * r)


HEX_POLY = {}
for _r in range(8):
    for _c in range(7):
        _cx, _cy = cell_center(_r, _c)
        HEX_POLY[(_r, _c)] = [(_cx + (R - 2) * math.cos(math.radians(a)), _cy + (R - 2) * math.sin(math.radians(a)))
                              for a in (-90, -30, 30, 90, 150, 210)]


def cell_at(pos):
    best, bd = None, R * 0.95
    for (r, c) in HEX_POLY:
        cx, cy = cell_center(r, c)
        d = math.hypot(pos[0] - cx, pos[1] - cy)
        if d < bd:
            bd, best = d, (r, c)
    return best


BENCH_X0, BENCH_Y, SLOT, SLOT_GAP = 346, 512, 60, 6


def bench_rect(i):
    return pygame.Rect(BENCH_X0 + i * (SLOT + SLOT_GAP), BENCH_Y, SLOT, SLOT)


def card_rect(i):
    return pygame.Rect(430 + i * 124, 598, 118, 114)


SHOP_AREA = pygame.Rect(426, 588, 624, 130)
BTN_XP = pygame.Rect(232, 628, 188, 40)
BTN_ROLL = pygame.Rect(232, 674, 188, 40)
BTN_LOCK = pygame.Rect(1066, 598, 208, 44)
BTN_READY = pygame.Rect(1066, 650, 208, 60)
TRAIT_X, TRAIT_Y, TRAIT_H = 8, 48, 29


def player_rect(i):
    return pygame.Rect(1066, 48 + i * 62, 208, 58)


def draw_token(surf, x, y, uid, star, border, hp=None, mana=None, dim=False, rad=22):
    info = unit_info(uid)
    cost = info.get("cost", 0)
    col = COST_COLORS.get(cost, COST_COLORS[0])
    if dim:
        col = tuple(int(v * 0.5) for v in col)
        border = tuple(int(v * 0.5) for v in border)
    dark = tuple(int(v * 0.45) for v in col)
    x, y = int(x), int(y)
    pygame.draw.circle(surf, dark, (x, y), rad)
    pygame.draw.circle(surf, col, (x, y), rad, 3)
    pygame.draw.circle(surf, border, (x, y), rad + 3, 2)
    draw_text(surf, info["name"][:2], (x, y), 15, SUB if dim else TEXT, "center")
    draw_text(surf, "★" * star, (x, y - rad - 7), 12, STAR_COLORS[star], "center")
    if hp is not None:
        bw = rad * 2 + 4
        bx = x - bw // 2
        by = y + rad + 4
        pygame.draw.rect(surf, (40, 20, 20), (bx, by, bw, 5))
        pygame.draw.rect(surf, GREEN if border == OWN else RED, (bx, by, int(bw * max(0, min(1, hp))), 5))
        if mana is not None:
            pygame.draw.rect(surf, (20, 24, 40), (bx, by + 6, bw, 3))
            pygame.draw.rect(surf, (90, 150, 255), (bx, by + 6, int(bw * max(0, min(1, mana))), 3))


def unit_tooltip(uid, star, cu=None):
    info = unit_info(uid)
    lines = [(f"{info['name']}  {'★' * star}", 20, STAR_COLORS[star])]
    bs = base_stats(uid, star)
    if uid in UNITS:
        lines.append((f"{info['cost']}コスト ／ {ARCH_NAME[info['arch']]} ／ " + "・".join(info["traits"]), 15, SUB))
    else:
        lines.append(("モンスター", 15, SUB))
    if cu is not None:
        lines.append((f"HP {int(cu.hp)}/{int(cu.maxhp)}   マナ {int(cu.mana)}/{int(cu.maxmana)}", 15, TEXT))
        lines.append((f"攻撃力 {int(cu.atk)}  攻速 {cu.as_base:.2f}  射程 {cu.range}  防御 {int(cu.armor)}/{int(cu.mr)}", 15, TEXT))
    else:
        lines.append((f"HP {int(bs['hp'])}  攻撃力 {int(bs['atk'])}  攻速 {bs['as']:.2f}  射程 {bs['rng']}", 15, TEXT))
        lines.append((f"物理防御 {bs['armor']}  魔法防御 {bs['mr']}  マナ {bs['mana']}", 15, TEXT))
    if uid in UNITS:
        ab = info["ability"]
        lines.append((f"スキル：{info['ability_name']}", 16, ACCENT))
        lines.append((ability_desc(ab, ability_value(ab, info["cost"], star)), 15, TEXT))
    return lines


def trait_tooltip(name, count, owned_uids):
    t = TRAITS[name]
    lines = [(f"{name}（{t['kind']}）  {count}体", 20, GOLD)]
    for i, th in enumerate(t["thresholds"]):
        col = TEXT if count >= th else SUB
        lines.append((f"({th}) {trait_desc(name, i)}", 15, col))
    names = []
    for u in t["members"]:
        names.append(UNITS[u]["name"] + ("●" if u in owned_uids else ""))
    lines.append(("ユニット：" + "・".join(names), 14, SUB))
    return lines


# ---------------- セッション ----------------
class HostSession:
    """ひとり用・ホスト用。ゲーム本体を自分のPCで動かす"""

    def __init__(self, game, server=None, cid_to_pid=None):
        self.game = game
        self.server = server
        self.map = cid_to_pid or {}
        self.bt = 0.0
        self.error = None

    def update(self, dt):
        dirty = set()
        if self.server:
            while True:
                try:
                    cid, msg = self.server.inbox.get_nowait()
                except queue.Empty:
                    break
                pid = self.map.get(cid)
                if pid is None:
                    continue
                t = msg.get("t")
                if t == "act":
                    self.game.action(pid, msg.get("a", {}))
                    dirty.add(cid)
                elif t == "_disconnect":
                    p = self.game.players[pid]
                    if not p.is_ai:
                        p.is_ai = True
                        p.name += "(AI)"
                        self.game.add_log(f"{p.name} が切断しました（以後AIが操作）")
                    self.map.pop(cid, None)
        self.game.tick(dt)
        if self.server:
            self.bt += dt
            targets = list(self.map.keys()) if self.bt >= 0.15 else list(dirty)
            if self.bt >= 0.15:
                self.bt = 0.0
            for cid in targets:
                if cid in self.map:
                    self.server.send(cid, {"t": "state", "s": self.game.state_for(self.map[cid])})

    def state(self):
        return self.game.state_for(0)

    def act(self, a):
        self.game.action(0, a)

    def close(self):
        if self.server:
            self.server.close()


class RemoteSession:
    """参加者用。ホストから届いた状態を表示し、操作を送る"""

    def __init__(self, client, first_state=None):
        self.client = client
        self.st = first_state
        self.error = None

    def update(self, dt):
        while True:
            try:
                msg = self.client.inbox.get_nowait()
            except queue.Empty:
                break
            t = msg.get("t")
            if t == "state":
                self.st = msg["s"]
            elif t == "_disconnect":
                self.error = "ホストとの接続が切れました"
            elif t == "error":
                self.error = msg.get("text", "エラー")
        if self.st:
            self.st["timer"] = max(0.0, self.st["timer"] - dt)

    def state(self):
        return self.st

    def act(self, a):
        self.client.send({"t": "act", "a": a})

    def close(self):
        self.client.close()


class CombatView:
    """戦闘の再生（ホストと同じ計算を手元でも行って表示）"""

    def __init__(self, setup, flip):
        self.setup = setup
        self.sim = CombatSim(setup)
        self.cid = setup["cid"]
        self.flip = flip
        self.elapsed = 0.0
        self.fx = []

    def update(self, dt):
        self.elapsed += dt
        n = 0
        while not self.sim.done and self.sim.t < self.elapsed and n < 300:
            for e in self.sim.step():
                self.fx.append([self.sim.t, e])
            n += 1
        self.fx = [f for f in self.fx if self.sim.t - f[0] < 0.9]

    def disp(self, r, c):
        return (7 - r, 6 - c) if self.flip else (r, c)

    def pos(self, u):
        a = cell_center(*self.disp(u.pr, u.pc))
        b = cell_center(*self.disp(u.r, u.c))
        f = 1.0 if u.mt < 0 else min(1.0, (self.sim.t - u.mt) / MOVE_TIME)
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)

    @property
    def my_side(self):
        return "b" if self.flip else "a"


# ---------------- 画面：タイトル ----------------
class TitleScene:
    text_input = True

    def __init__(self, app, msg=""):
        self.app = app
        self.msg = msg
        self.name = TextBox((490, 250, 300, 46), app.player_name, 10, "名前を入力")
        self.buttons = [
            Button((490, 320, 300, 52), "ひとりで遊ぶ（AI 7人と対戦）", self.solo),
            Button((490, 382, 300, 52), "部屋を作る（ホスト）", self.host),
            Button((490, 444, 300, 52), "部屋に入る", self.join),
            Button((490, 506, 300, 52), "遊び方", lambda: app.go(HelpScene(app))),
            Button((490, 568, 300, 52), "終了", self.quit),
        ]

    def save_name(self):
        self.app.player_name = self.name.text.strip() or "プレイヤー"

    def solo(self):
        self.save_name()
        self.app.go(GameScene(self.app, HostSession(Game([self.app.player_name]))))

    def host(self):
        self.save_name()
        self.app.go(HostLobbyScene(self.app))

    def join(self):
        self.save_name()
        self.app.go(JoinScene(self.app))

    def quit(self):
        self.app.running = False

    def handle(self, e):
        self.name.handle(e)
        for b in self.buttons:
            if b.handle(e):
                return

    def update(self, dt):
        pass

    def draw(self, s):
        s.fill(BG)
        for i in range(12):
            x = 120 + i * 95
            pygame.draw.polygon(s, (26, 30, 42), [(x + 30 * math.cos(math.radians(a)), 120 + 30 * math.sin(math.radians(a)))
                                                    for a in range(-90, 270, 60)], 2)
        draw_text(s, GAME_TITLE, (640, 130), 56, GOLD, "center")
        draw_text(s, "8人のオートバトル ／ ユニット60種・シナジー36種", (640, 190), 18, SUB, "center")
        draw_text(s, "あなたの名前", (490, 226), 16, SUB)
        self.name.draw(s)
        m = pygame.mouse.get_pos()
        for b in self.buttons:
            b.draw(s, m)
        if self.msg:
            draw_text(s, self.msg, (640, 650), 18, RED, "center")
        draw_text(s, f"ver {VERSION}", (1270, 710), 14, SUB, "bottomright")


class HelpScene:
    text_input = False
    LINES = [
        "【目的】8人で戦い、最後の1人まで生き残れば優勝です。",
        "1. 画面下のショップのカードをクリックしてユニットを買います。",
        "2. 買ったユニットはベンチ（盤面の下の9マス）に入ります。ドラッグして盤面の下半分に並べます。",
        "3. 盤面に置ける数は「レベル」と同じです。経験値を買う（Fキー）とレベルが上がります。",
        "4. 同じユニットを3体集めると★2、★2を3体で★3に自動で強化されます。",
        "5. 左の一覧は「シナジー」。同じ特性のユニットを揃えるとボーナスが付きます。",
        "6. 戦闘は自動です。負けると体力が減り、0になると脱落します。",
        "7. ゴールドは10ごとに利子+1（最大+5）。連勝・連敗でもボーナスがもらえます。",
        "8. 売却：ユニットをショップ欄へドラッグ、またはマウスを合わせてEキー。",
        "",
        "【キー】 D＝リロール(2G)  F＝経験値購入(4G)  E＝売却  Space＝準備OK  Esc＝メニュー",
        "【対戦】ホストが「部屋を作る」→表示された部屋コードを伝える→他の人は「部屋に入る」で入力。",
        "　　　 空いた席はAIが入ります。途中で切断した人の席もAIが引き継ぎます。",
    ]

    def __init__(self, app):
        self.app = app
        self.back = Button((540, 630, 200, 50), "戻る", lambda: app.go(TitleScene(app)))

    def handle(self, e):
        self.back.handle(e)
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.app.go(TitleScene(self.app))

    def update(self, dt):
        pass

    def draw(self, s):
        s.fill(BG)
        draw_text(s, "遊び方", (640, 60), 36, GOLD, "center")
        y = 120
        for ln in self.LINES:
            draw_text(s, ln, (120, y), 19, TEXT)
            y += 36
        self.back.draw(s, pygame.mouse.get_pos())


# ---------------- 画面：ホストの待機部屋 ----------------
class HostLobbyScene:
    text_input = False

    def __init__(self, app):
        self.app = app
        self.error = ""
        self.names = {}  # cid -> name
        self.pub = None
        self.pub_state = "取得中…"
        self.server = None
        try:
            self.server = net.Server(net.PORT)
        except OSError as ex:
            self.error = f"部屋を作れませんでした（ポート{net.PORT}が使用中の可能性）: {ex}"
        self.lan = net.local_ips()[:3]
        threading.Thread(target=self._fetch_pub, daemon=True).start()
        self.buttons = [Button((440, 640, 190, 52), "ゲーム開始", self.start, color=(40, 90, 60)),
                        Button((650, 640, 190, 52), "戻る", self.back)]

    def _fetch_pub(self):
        ip = net.public_ip()
        self.pub = ip
        self.pub_state = "" if ip else "取得できませんでした"

    def back(self):
        if self.server:
            self.server.close()
        self.app.go(TitleScene(self.app))

    def start(self):
        if not self.server:
            return
        self.server.accepting = False
        cids = sorted(self.names.keys())
        names = [self.app.player_name] + [self.names[c] for c in cids]
        mapping = {c: i + 1 for i, c in enumerate(cids)}
        for c in list(self.server.conns.keys()):
            if c not in mapping:
                self.server.kick(c)
        game = Game(names)
        for c, pid in mapping.items():
            self.server.send(c, {"t": "start", "pid": pid})
        self.app.go(GameScene(self.app, HostSession(game, self.server, mapping)))

    def lobby_list(self):
        return [self.app.player_name + "（ホスト）"] + [self.names[c] for c in sorted(self.names)]

    def handle(self, e):
        for b in self.buttons:
            if b.handle(e):
                return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.back()

    def update(self, dt):
        if not self.server:
            return
        changed = False
        while True:
            try:
                cid, msg = self.server.inbox.get_nowait()
            except queue.Empty:
                break
            t = msg.get("t")
            if t == "hello":
                if msg.get("ver") != VERSION:
                    self.server.send(cid, {"t": "error", "text": f"バージョンが違います（ホスト: {VERSION}）"})
                    continue
                nm = str(msg.get("name", "ゲスト"))[:10] or "ゲスト"
                self.names[cid] = nm
                self.server.send(cid, {"t": "welcome"})
                changed = True
            elif t == "_disconnect":
                if cid in self.names:
                    del self.names[cid]
                    changed = True
        if changed:
            self.server.broadcast({"t": "lobby", "players": self.lobby_list()})

    def draw(self, s):
        s.fill(BG)
        draw_text(s, "部屋を作りました", (640, 50), 34, GOLD, "center")
        if self.error:
            draw_text(s, self.error, (640, 110), 18, RED, "center")
        draw_panel(s, pygame.Rect(80, 100, 640, 510))
        draw_text(s, "参加する人に、下の「部屋コード」を伝えてください", (100, 115), 18, TEXT)
        y = 155
        draw_text(s, "■ ネット越しで遊ぶ用（ポート開放が必要）", (100, y), 17, ACCENT)
        y += 30
        if self.pub:
            draw_text(s, net.encode_room(self.pub, net.PORT), (120, y), 34, TEXT)
            draw_text(s, f"（{self.pub}:{net.PORT}）", (430, y + 12), 15, SUB)
        else:
            draw_text(s, self.pub_state, (120, y + 6), 20, SUB)
        y += 64
        draw_text(s, "■ 同じWi-Fi・社内LAN・VPNツールで遊ぶ用", (100, y), 17, ACCENT)
        y += 30
        for ip in self.lan:
            draw_text(s, net.encode_room(ip, net.PORT), (120, y), 30, TEXT)
            draw_text(s, f"（{ip}:{net.PORT}）", (430, y + 10), 15, SUB)
            y += 44
        y += 10
        tips = ["※ 初回はWindowsの警告が出たら「アクセスを許可する」を押してください。",
                f"※ ネット越しはルーターでTCP {net.PORT}番を開放するか、",
                "　 Radmin VPN などの無料VPNツールを全員で使うのが簡単です（説明書参照）。"]
        for tp in tips:
            draw_text(s, tp, (100, y), 15, SUB)
            y += 24
        draw_panel(s, pygame.Rect(760, 100, 440, 510))
        draw_text(s, "参加者（最大8人・空きはAI）", (780, 115), 18, TEXT)
        for i, nm in enumerate(self.lobby_list()):
            draw_text(s, f"{i + 1}. {nm}", (790, 160 + i * 44), 22, TEXT)
        for i in range(len(self.lobby_list()), 8):
            draw_text(s, f"{i + 1}. （AI）", (790, 160 + i * 44), 22, SUB)
        m = pygame.mouse.get_pos()
        for b in self.buttons:
            b.draw(s, m)


# ---------------- 画面：部屋に入る ----------------
class JoinScene:
    text_input = True

    def __init__(self, app):
        self.app = app
        self.code = TextBox((390, 300, 500, 56), "", 30, "例）K7Q2M-9XA3B  または 192.168.0.10")
        self.code.active = True
        self.status = ""
        self.busy = False
        self.result = None
        self.buttons = [Button((440, 400, 190, 52), "入る", self.connect, color=(40, 90, 60)),
                        Button((650, 400, 190, 52), "戻る", lambda: app.go(TitleScene(app)))]

    def connect(self):
        if self.busy:
            return
        try:
            host, port = net.parse_address(self.code.text)
        except (ValueError, IndexError):
            self.status = "部屋コードが正しくありません（0とO、1とIは使われません）"
            return
        self.busy = True
        self.status = "接続中…"

        def run():
            try:
                c = net.Client(host, port)
                c.send({"t": "hello", "name": self.app.player_name, "ver": VERSION})
                self.result = ("ok", c)
            except OSError:
                self.result = ("ng", None)
        threading.Thread(target=run, daemon=True).start()

    def handle(self, e):
        self.code.handle(e)
        for b in self.buttons:
            if b.handle(e):
                return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
            self.connect()

    def update(self, dt):
        if self.result:
            kind, c = self.result
            self.result = None
            self.busy = False
            if kind == "ok":
                self.app.go(ClientLobbyScene(self.app, c))
            else:
                self.status = "接続できませんでした（コード・ホストの起動・ポート開放を確認）"

    def draw(self, s):
        s.fill(BG)
        draw_text(s, "部屋に入る", (640, 150), 36, GOLD, "center")
        draw_text(s, "ホストから聞いた部屋コードを入力してください（Ctrl+Vで貼り付け可）", (640, 250), 18, TEXT, "center")
        self.code.draw(s)
        m = pygame.mouse.get_pos()
        for b in self.buttons:
            b.draw(s, m)
        if self.status:
            draw_text(s, self.status, (640, 490), 18, SUB, "center")


class ClientLobbyScene:
    text_input = False

    def __init__(self, app, client):
        self.app = app
        self.client = client
        self.players = []
        self.error = ""
        self.back = Button((540, 620, 200, 52), "戻る", self.leave_to_title)

    def leave_to_title(self):
        self.client.close()
        self.app.go(TitleScene(self.app))

    def handle(self, e):
        self.back.handle(e)

    def update(self, dt):
        while True:
            try:
                msg = self.client.inbox.get_nowait()
            except queue.Empty:
                break
            t = msg.get("t")
            if t == "lobby":
                self.players = msg.get("players", [])
            elif t == "start":
                self.app.go(GameScene(self.app, RemoteSession(self.client)))
                return
            elif t == "state":
                self.app.go(GameScene(self.app, RemoteSession(self.client, msg["s"])))
                return
            elif t == "error":
                self.error = msg.get("text", "エラー")
            elif t == "_disconnect":
                if not self.error:
                    self.error = "ホストとの接続が切れました"

    def draw(self, s):
        s.fill(BG)
        draw_text(s, "部屋に入りました", (640, 80), 34, GOLD, "center")
        draw_text(s, "ホストがゲームを開始するのを待っています…", (640, 130), 20, TEXT, "center")
        draw_panel(s, pygame.Rect(420, 170, 440, 420))
        for i, nm in enumerate(self.players):
            draw_text(s, f"{i + 1}. {nm}", (450, 195 + i * 44), 22, TEXT)
        if self.error:
            draw_text(s, self.error, (640, 600), 18, RED, "center")
        self.back.draw(s, pygame.mouse.get_pos())


# ---------------- 画面：ゲーム本編 ----------------
class GameScene:
    text_input = False

    def __init__(self, app, session):
        self.app = app
        self.session = session
        self.st = None
        self.view = None
        self.drag = None
        self.scout = None
        self.toast = ""
        self.toast_t = 0.0
        self.toast_seq = -1
        self.last_result = None
        self.menu = False
        self.dead_dismissed = False
        self.hover = None
        self.menu_buttons = [Button((490, 300, 300, 52), "ゲームに戻る", self.close_menu),
                             Button((490, 368, 300, 52), "タイトルへ戻る（退出）", self.to_title)]
        self.dead_buttons = [Button((440, 400, 190, 52), "観戦を続ける", self.dismiss_dead),
                             Button((650, 400, 190, 52), "タイトルへ", self.to_title)]
        self.end_buttons = [Button((540, 620, 200, 52), "タイトルへ", self.to_title)]
        self.err_buttons = [Button((540, 400, 200, 52), "タイトルへ", self.to_title)]

    def leave(self):
        self.session.close()

    def to_title(self):
        self.app.go(TitleScene(self.app))

    def close_menu(self):
        self.menu = False

    def dismiss_dead(self):
        self.dead_dismissed = True

    def show_toast(self, text, sec=2.5):
        self.toast = text
        self.toast_t = sec

    def act(self, a):
        self.session.act(a)

    # ---------- 更新 ----------
    def update(self, dt):
        self.session.update(dt)
        st = self.session.state()
        self.st = st
        self.toast_t -= dt
        if not st:
            return
        me = st["me"]
        if me["toast_seq"] != self.toast_seq:
            if self.toast_seq != -1 and me["toast"]:
                self.show_toast(me["toast"])
            self.toast_seq = me["toast_seq"]
        key = (st["round"], me["result"])
        if me["result"] and key != self.last_result and st["phase"] == "planning":
            if self.last_result is not None:
                self.show_toast(me["result"], 4.0)
            self.last_result = key
        cb = st.get("combat")
        if st["phase"] == "combat" and cb:
            if self.view is None or self.view.cid != cb["setup"]["cid"]:
                self.view = CombatView(cb["setup"], cb["side"] == "b")
        else:
            self.view = None
        if self.view:
            self.view.update(dt)

    # ---------- 位置の判定 ----------
    def shown_board(self):
        st = self.st
        if self.scout is not None:
            return st["players"][self.scout]["board"]
        return st["me"]["board"]

    def unit_at(self, pos):
        """自分のユニット（ドラッグ可能なもの）"""
        st = self.st
        for i in range(BENCH_SIZE):
            if bench_rect(i).collidepoint(pos) and st["me"]["bench"][i]:
                return ["bench", i], st["me"]["bench"][i]
        if st["phase"] == "planning" and self.scout is None:
            cell = cell_at(pos)
            if cell and cell[0] >= 4:
                u = st["me"]["board"][cell[0] - 4][cell[1]]
                if u:
                    return ["board", cell[0] - 4, cell[1]], u
        return None, None

    def drop_target(self, pos):
        for i in range(BENCH_SIZE):
            if bench_rect(i).collidepoint(pos):
                return ["bench", i]
        cell = cell_at(pos)
        if cell and cell[0] >= 4:
            return ["board", cell[0] - 4, cell[1]]
        if SHOP_AREA.collidepoint(pos):
            return ["sell"]
        return None

    # ---------- 入力 ----------
    def overlay_buttons(self):
        st = self.st
        if self.session.error:
            return self.err_buttons
        if self.menu:
            return self.menu_buttons
        if st and st["phase"] == "end":
            return self.end_buttons
        if st and not st["me"]["alive"] and not self.dead_dismissed:
            return self.dead_buttons
        return None

    def handle(self, e):
        ob = self.overlay_buttons()
        if ob is not None:
            for b in ob:
                if b.handle(e):
                    return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and self.menu:
                self.menu = False
            return
        st = self.st
        if not st:
            return
        me = st["me"]
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.menu = True
            elif not me["alive"]:
                return
            elif e.key == pygame.K_d:
                self.act({"t": "reroll"})
            elif e.key == pygame.K_f:
                self.act({"t": "xp"})
            elif e.key == pygame.K_SPACE:
                self.act({"t": "ready"})
            elif e.key == pygame.K_e:
                loc, u = self.unit_at(pygame.mouse.get_pos())
                if loc:
                    self.act({"t": "sell", "loc": loc})
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            pos = e.pos
            for i in range(8):
                if player_rect(i).collidepoint(pos):
                    self.scout = None if (i == me["pid"] or self.scout == i) else i
                    return
            if not me["alive"]:
                return
            if BTN_XP.collidepoint(pos):
                self.act({"t": "xp"})
                return
            if BTN_ROLL.collidepoint(pos):
                self.act({"t": "reroll"})
                return
            if BTN_LOCK.collidepoint(pos):
                self.act({"t": "lock"})
                return
            if BTN_READY.collidepoint(pos):
                self.act({"t": "ready"})
                return
            for i in range(SHOP_SIZE):
                if card_rect(i).collidepoint(pos) and me["shop"][i]:
                    self.act({"t": "buy", "slot": i})
                    return
            loc, u = self.unit_at(pos)
            if loc:
                self.drag = {"loc": loc, "u": u}
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag:
            tgt = self.drop_target(e.pos)
            src = self.drag["loc"]
            self.drag = None
            if tgt is None or tgt == src:
                return
            if tgt[0] == "sell":
                self.act({"t": "sell", "loc": src})
            else:
                self.act({"t": "move", "src": src, "dst": tgt})

    # ---------- 描画 ----------
    def draw(self, s):
        s.fill(BG)
        st = self.st
        if not st:
            draw_text(s, "ホストからの情報を待っています…", (640, 360), 24, TEXT, "center")
            if self.session.error:
                self.draw_overlay(s, self.session.error, "", self.err_buttons)
            return
        mouse = pygame.mouse.get_pos()
        self.hover = None
        tips = None
        me = st["me"]

        # 上部バー
        draw_panel(s, pygame.Rect(0, 0, W, 40), PANEL, 0)
        kind = "モンスター戦" if st["pve"] else "対人戦"
        draw_text(s, f"ラウンド {st['round']}  ・ {kind}", (12, 20), 18, TEXT, "midleft")
        ph = {"planning": "準備フェーズ", "combat": "戦闘フェーズ", "end": "ゲーム終了"}[st["phase"]]
        tcol = RED if st["timer"] < 6 and st["phase"] == "planning" else TEXT
        draw_text(s, f"{ph}  残り {int(math.ceil(st['timer']))} 秒", (640, 20), 20, tcol, "center")
        odds = SHOP_ODDS[me["level"]]
        x = 1270
        for ci in range(5, 0, -1):
            r = draw_text(s, f"{odds[ci - 1]}%", (x, 20), 15, COST_COLORS[ci], "midright")
            x = r.left - 10
        draw_text(s, "出現率", (x, 20), 14, SUB, "midright")
        if self.view:
            opp = self.view.setup["b" if self.view.my_side == "a" else "a"]["name"]
            draw_text(s, f"VS {opp}", (330, 20), 18, ENEMY, "midleft")

        # 盤面
        planning = st["phase"] == "planning"
        for (r, c), poly in HEX_POLY.items():
            own_half = r >= 4
            col = (44, 52, 72) if own_half else (36, 38, 50)
            if self.drag and own_half and cell_at(mouse) == (r, c):
                col = (70, 90, 130)
            pygame.draw.polygon(s, col, poly)
            pygame.draw.polygon(s, (60, 68, 90), poly, 1)
        if self.view and self.scout is None:
            v = self.view
            for u in v.sim.units:
                if not u.alive:
                    continue
                x, y = v.pos(u)
                mine = u.side == v.my_side
                draw_token(s, x, y, u.uid, u.star, OWN if mine else ENEMY, u.hp / u.maxhp,
                           (u.mana / u.maxmana) if u.maxmana else None)
                if u.shields and v.sim.shield_total(u) > 1:
                    pygame.draw.circle(s, (220, 220, 240), (int(x), int(y)), 27, 2)
                if u.stun_until > v.sim.t:
                    draw_text(s, "スタン", (x, y - 34), 12, GOLD, "center")
                if math.hypot(mouse[0] - x, mouse[1] - y) < 24:
                    tips = unit_tooltip(u.uid, u.star, u)
            self.draw_fx(s, v)
            if v.sim.done:
                won = v.sim.winner == v.my_side
                txt = "勝利！" if won else ("引き分け" if v.sim.winner == "draw" else "敗北…")
                draw_text(s, txt, (640, 280), 54, GOLD if won else RED, "center")
        else:
            board = self.shown_board()
            border = OWN if self.scout is None else (200, 170, 255)
            for r in range(4):
                for c in range(7):
                    u = board[r][c]
                    if not u:
                        continue
                    if self.drag and self.drag["loc"] == ["board", r, c]:
                        continue
                    x, y = cell_center(4 + r, c)
                    draw_token(s, x, y, u[0], u[1], border)
                    if math.hypot(mouse[0] - x, mouse[1] - y) < 24:
                        tips = unit_tooltip(u[0], u[1])
            if self.scout is not None:
                draw_text(s, f"{st['players'][self.scout]['name']} の盤面を見ています（右の一覧をもう一度クリックで戻る）",
                          (640, 140), 17, (200, 170, 255), "center")
            elif planning and st["pve"]:
                for uid, star, r, c in pve_board(st["round"]):
                    x, y = cell_center(3 - r, 6 - c)
                    draw_token(s, x, y, uid, star, ENEMY, dim=True)
                    if math.hypot(mouse[0] - x, mouse[1] - y) < 24:
                        tips = unit_tooltip(uid, star)
                draw_text(s, "次の相手：モンスター", (640, 140), 17, SUB, "center")
            elif planning:
                draw_text(s, "相手の陣地（戦闘開始時に対戦相手が決まります）", (640, 140), 16, SUB, "center")
            if planning and self.scout is None:
                cnt = sum(1 for row in me["board"] for u in row if u)
                col = GOLD if cnt < me["level"] else SUB
                draw_text(s, f"盤面 {cnt} / {me['level']} 体", (640, 505), 15, col, "midbottom")

        # ベンチ
        for i in range(BENCH_SIZE):
            rc = bench_rect(i)
            hov = self.drag and rc.collidepoint(mouse)
            pygame.draw.rect(s, (60, 72, 100) if hov else PANEL, rc, border_radius=8)
            u = me["bench"][i]
            if u and not (self.drag and self.drag["loc"] == ["bench", i]):
                draw_token(s, rc.centerx, rc.centery + 4, u[0], u[1], OWN)
                if rc.collidepoint(mouse):
                    tips = unit_tooltip(u[0], u[1])

        # シナジー一覧
        uids = [u[0] for row in self.shown_board() for u in row if u]
        if self.view and self.scout is None:
            side = self.view.my_side
            uids = [x[0] for x in self.view.setup[side]["units"]]
        traits = compute_traits(uids)
        draw_text(s, "シナジー", (TRAIT_X + 4, TRAIT_Y - 2), 14, SUB)
        y = TRAIT_Y + 20
        for name, cnt, tier in traits[:18]:
            th = TRAITS[name]["thresholds"]
            if tier == 0:
                tc = TIER_COLORS[0]
            elif tier == len(th):
                tc = TIER_COLORS[3]
            elif tier == 1:
                tc = TIER_COLORS[1]
            else:
                tc = TIER_COLORS[2]
            rr = pygame.Rect(TRAIT_X, y, 212, TRAIT_H - 3)
            pygame.draw.rect(s, PANEL, rr, border_radius=6)
            pygame.draw.rect(s, tc, (TRAIT_X, y, 34, TRAIT_H - 3), border_radius=6)
            draw_text(s, str(cnt), (TRAIT_X + 17, y + (TRAIT_H - 3) // 2), 16, (20, 20, 20) if tier else TEXT, "center")
            draw_text(s, name, (TRAIT_X + 42, y + (TRAIT_H - 3) // 2), 16, TEXT if tier else SUB, "midleft")
            ths = " ・ ".join(str(x) for x in th)
            draw_text(s, ths, (TRAIT_X + 205, y + (TRAIT_H - 3) // 2), 13, SUB, "midright")
            if rr.collidepoint(mouse):
                tips = trait_tooltip(name, cnt, set(uids))
            y += TRAIT_H
        if not traits:
            draw_text(s, "ユニットを盤面に置くと表示", (TRAIT_X + 4, y), 14, SUB)

        # 所持金・レベル
        draw_panel(s, pygame.Rect(8, 592, 216, 122))
        draw_text(s, f"{me['gold']} G", (20, 600), 34, GOLD)
        draw_text(s, f"レベル {me['level']}", (20, 648), 18, TEXT)
        if me["level"] < MAX_LEVEL:
            need = max(1, me["xp_need"])
            pygame.draw.rect(s, (30, 34, 50), (20, 676, 190, 10), border_radius=4)
            pygame.draw.rect(s, ACCENT, (20, 676, int(190 * me["xp"] / need), 10), border_radius=4)
            draw_text(s, f"経験値 {me['xp']}/{need}", (210, 652), 14, SUB, "topright")
        sk = me["streak"]
        if abs(sk) >= 2:
            draw_text(s, f"{abs(sk)}連勝中" if sk > 0 else f"{abs(sk)}連敗中", (20, 692), 14,
                      GREEN if sk > 0 else RED)
        draw_text(s, f"体力 {me['hp']}", (210, 692), 14, TEXT, "topright")

        # ボタン
        for rect, label, enabled in ((BTN_XP, "経験値を買う 4G [F]", me["gold"] >= 4 and me["level"] < MAX_LEVEL),
                                     (BTN_ROLL, "リロール 2G [D]", me["gold"] >= 2)):
            col = PANEL2 if enabled else (32, 34, 42)
            if enabled and rect.collidepoint(mouse):
                col = lighten(col, 30)
            pygame.draw.rect(s, col, rect, border_radius=8)
            draw_text(s, label, rect.center, 17, TEXT if enabled else SUB, "center")

        # ショップ
        if self.drag:
            pygame.draw.rect(s, (70, 40, 40), SHOP_AREA, border_radius=10)
            u = self.drag["u"]
            draw_text(s, f"ここに置くと売却（+{sell_value(u[0], u[1])}G）", SHOP_AREA.center, 24, TEXT, "center")
        else:
            for i in range(SHOP_SIZE):
                rc = card_rect(i)
                uid = me["shop"][i]
                if not uid:
                    pygame.draw.rect(s, (24, 26, 34), rc, border_radius=8)
                    continue
                info = UNITS[uid]
                cc = COST_COLORS[info["cost"]]
                can = me["gold"] >= info["cost"]
                bg = tuple(int(v * 0.30) for v in cc)
                if rc.collidepoint(mouse) and can:
                    bg = lighten(bg, 25)
                pygame.draw.rect(s, bg, rc, border_radius=8)
                pygame.draw.rect(s, cc if can else (70, 70, 80), rc, 2, border_radius=8)
                draw_text(s, info["name"], (rc.x + 8, rc.y + 6), 18, TEXT if can else SUB)
                draw_text(s, f"{info['cost']}G", (rc.right - 8, rc.y + 8), 15, GOLD, "topright")
                for k, t in enumerate(info["traits"]):
                    draw_text(s, t, (rc.x + 8, rc.y + 36 + k * 20), 14, SUB)
                owned = sum(1 for row in me["board"] for u in row if u and u[0] == uid) + \
                    sum(1 for u in me["bench"] if u and u[0] == uid)
                if owned:
                    draw_text(s, f"所持{owned}", (rc.right - 8, rc.bottom - 6), 13, GREEN, "bottomright")
                if rc.collidepoint(mouse):
                    tips = unit_tooltip(uid, 1)

        # 右：プレイヤー一覧
        opp_pid = None
        if self.view:
            opp_pid = self.view.setup["b" if self.view.my_side == "a" else "a"]["pid"]
        order = list(range(8))
        for i in order:
            p = st["players"][i]
            rc = player_rect(i)
            bg = PANEL
            if self.scout == i:
                bg = (60, 50, 90)
            pygame.draw.rect(s, bg, rc, border_radius=8)
            if i == me["pid"]:
                pygame.draw.rect(s, ACCENT, rc, 2, border_radius=8)
            elif i == opp_pid:
                pygame.draw.rect(s, ENEMY, rc, 2, border_radius=8)
            ncol = TEXT if p["alive"] else SUB
            draw_text(s, p["name"], (rc.x + 10, rc.y + 5), 16, ncol)
            if p["alive"]:
                draw_text(s, f"Lv{p['level']}", (rc.right - 10, rc.y + 6), 14, SUB, "topright")
                pygame.draw.rect(s, (40, 22, 22), (rc.x + 10, rc.y + 34, 150, 12), border_radius=4)
                hpc = GREEN if p["hp"] > 50 else (GOLD if p["hp"] > 25 else RED)
                pygame.draw.rect(s, hpc, (rc.x + 10, rc.y + 34, int(150 * max(0, p["hp"]) / 100), 12), border_radius=4)
                draw_text(s, str(p["hp"]), (rc.right - 10, rc.y + 40), 15, TEXT, "midright")
            else:
                draw_text(s, f"脱落 {p['placement']}位", (rc.x + 10, rc.y + 32), 15, SUB)
            if rc.collidepoint(mouse) and i != me["pid"]:
                tips = [(f"{p['name']}", 18, TEXT), ("クリックで盤面を見る", 14, SUB)]

        # 右下：固定・準備OK
        lcol = (90, 70, 30) if me["locked"] else PANEL2
        if BTN_LOCK.collidepoint(mouse):
            lcol = lighten(lcol, 25)
        pygame.draw.rect(s, lcol, BTN_LOCK, border_radius=8)
        draw_text(s, "ショップ固定中" if me["locked"] else "ショップを固定", BTN_LOCK.center, 17, TEXT, "center")
        if planning:
            rcol = (40, 110, 70) if me["ready"] else (50, 70, 110)
            if BTN_READY.collidepoint(mouse):
                rcol = lighten(rcol, 25)
            pygame.draw.rect(s, rcol, BTN_READY, border_radius=8)
            draw_text(s, "準備OK（待機中）" if me["ready"] else "準備OK [Space]", BTN_READY.center, 19, TEXT, "center")
        else:
            pygame.draw.rect(s, (30, 32, 40), BTN_READY, border_radius=8)
            draw_text(s, "戦闘中…", BTN_READY.center, 18, SUB, "center")

        # ログ
        y = 555
        for ln in st.get("log", [])[-2:]:
            draw_text(s, ln, (1270, y), 12, SUB, "topright")
            y += 16

        # ドラッグ中
        if self.drag:
            u = self.drag["u"]
            draw_token(s, mouse[0], mouse[1], u[0], u[1], OWN)
            tips = None

        # トースト
        if self.toast_t > 0 and self.toast:
            t = text_surf(self.toast, 22, TEXT)
            rc = t.get_rect(center=(640, 72)).inflate(30, 14)
            pygame.draw.rect(s, (10, 12, 18), rc, border_radius=10)
            pygame.draw.rect(s, GOLD, rc, 2, border_radius=10)
            s.blit(t, t.get_rect(center=rc.center))

        if tips and self.overlay_buttons() is None:
            draw_tooltip(s, tips, mouse)

        # オーバーレイ
        if self.session.error:
            self.draw_overlay(s, self.session.error, "", self.err_buttons)
        elif self.menu:
            self.draw_overlay(s, "メニュー", "", self.menu_buttons)
        elif st["phase"] == "end":
            self.draw_ranking(s)
        elif not me["alive"] and not self.dead_dismissed:
            self.draw_overlay(s, f"あなたは {me['placement']}位 でした", "おつかれさまでした", self.dead_buttons)

    def draw_fx(self, s, v):
        t = v.sim.t
        units = v.sim.units
        for ft, e in v.fx:
            age = t - ft
            kind = e[0]
            if kind == "atk" and age < 0.12:
                a = v.pos(units[e[1]])
                b = v.pos(units[e[2]])
                if e[3]:
                    k = min(1.0, age / 0.12)
                    px = a[0] + (b[0] - a[0]) * k
                    py = a[1] + (b[1] - a[1]) * k
                    pygame.draw.circle(s, (255, 240, 180), (int(px), int(py)), 4)
                else:
                    pygame.draw.line(s, (255, 255, 255), a, b, 2)
            elif kind == "dmg" and age < 0.7:
                x, y = v.pos(units[e[1]])
                col = {"phys": (255, 150, 120), "magic": (140, 180, 255)}.get(e[3], TEXT)
                draw_text(s, str(e[2]), (x + 10, y - 26 - age * 40), 14, col, "center")
            elif kind == "heal" and age < 0.7:
                x, y = v.pos(units[e[1]])
                draw_text(s, "+" + str(e[2]), (x - 10, y - 26 - age * 40), 14, GREEN, "center")
            elif kind == "miss" and age < 0.5:
                x, y = v.pos(units[e[1]])
                draw_text(s, "回避", (x, y - 30 - age * 30), 13, SUB, "center")
            elif kind == "cast" and age < 0.45:
                x, y = v.pos(units[e[1]])
                rad = int(24 + age * 90)
                pygame.draw.circle(s, (120, 200, 255), (int(x), int(y)), rad, 3)
                if age < 0.35:
                    info = UNITS.get(units[e[1]].uid)
                    if info:
                        draw_text(s, info["ability_name"], (x, y + 38), 13, (150, 210, 255), "center")
            elif kind == "revive" and age < 0.8:
                x, y = v.pos(units[e[1]])
                draw_text(s, "復活！", (x, y - 40), 15, (220, 200, 255), "center")

    def draw_overlay(self, s, title, sub, buttons):
        sh = pygame.Surface((W, H), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 170))
        s.blit(sh, (0, 0))
        draw_panel(s, pygame.Rect(400, 200, 480, 300))
        draw_text(s, title, (640, 250), 30, GOLD, "center")
        if sub:
            draw_text(s, sub, (640, 300), 18, SUB, "center")
        m = pygame.mouse.get_pos()
        for b in buttons:
            b.draw(s, m)

    def draw_ranking(self, s):
        sh = pygame.Surface((W, H), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 180))
        s.blit(sh, (0, 0))
        draw_panel(s, pygame.Rect(390, 90, 500, 600))
        draw_text(s, "最終結果", (640, 130), 34, GOLD, "center")
        ps = sorted(self.st["players"], key=lambda p: p["placement"] or 99)
        for i, p in enumerate(ps):
            col = GOLD if p["placement"] == 1 else (ACCENT if p["pid"] == self.st["me"]["pid"] else TEXT)
            draw_text(s, f"{p['placement']}位", (450, 180 + i * 52), 26, col)
            draw_text(s, p["name"], (540, 184 + i * 52), 22, col)
        m = pygame.mouse.get_pos()
        for b in self.end_buttons:
            b.draw(s, m)


# ---------------- アプリ本体 ----------------
class App:
    def __init__(self, screen):
        self.screen = screen
        self.scene = None
        self.player_name = "プレイヤー"
        self.running = True
        self.go(TitleScene(self))

    def go(self, scene):
        if self.scene is not None and hasattr(self.scene, "leave"):
            try:
                self.scene.leave()
            except Exception:
                pass
        self.scene = scene
        if getattr(scene, "text_input", False):
            pygame.key.start_text_input()
        else:
            pygame.key.stop_text_input()

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = min(0.1, clock.tick(60) / 1000.0)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                else:
                    self.scene.handle(e)
            self.scene.update(dt)
            self.scene.draw(self.screen)
            pygame.display.flip()
        if hasattr(self.scene, "leave"):
            try:
                self.scene.leave()
            except Exception:
                pass


def main():
    pygame.init()
    pygame.display.set_caption(f"{GAME_TITLE}  ver {VERSION}")
    try:
        screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
    except pygame.error:
        screen = pygame.display.set_mode((W, H))
    App(screen).run()
    pygame.quit()


if __name__ == "__main__":
    main()
