# -*- coding: utf-8 -*-
"""ヘックス・アリーナ（オートバトル）メイン画面

3D表示は Panda3D、文字やボタンなどの画面上の部品は pygame で描いて 3D の上に重ねています。
"""
import math
import os
import queue
import sys
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from panda3d.core import loadPrcFileData

import data
from data import (UNITS, TRAITS, COST_COLORS, SHOP_ODDS, MAX_LEVEL, BENCH_SIZE, SHOP_SIZE, VERSION,
                  GAME_TITLE, ARCH_NAME, compute_traits, base_stats, ability_desc, ability_value, trait_desc,
                  sell_value, pve_board, unit_info, resource_path)
from combat import MOVE_TIME, CombatSim
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
SCOUT = (200, 170, 255)
TIER_COLORS = [(62, 66, 82), (176, 118, 70), (170, 182, 198), (240, 200, 70)]
STAR_COLORS = {1: (200, 200, 210), 2: (220, 225, 235), 3: (255, 210, 60)}
PANEL_A = PANEL + (228,)


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


def draw_text_shadow(surf, s, pos, size=16, color=TEXT, anchor="topleft"):
    """3Dの上に出す文字（黒いふち付き）"""
    sh = text_surf(s, size, (0, 0, 0))
    r = sh.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
        surf.blit(sh, r.move(dx, dy))
    surf.blit(text_surf(s, size, color), r)
    return r


def lighten(c, k=25):
    return tuple(min(255, v + k) for v in c[:3]) + tuple(c[3:])


def get_clipboard():
    try:
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        s = r.clipboard_get()
        r.destroy()
        return s
    except Exception:
        return ""


# ---------------- 入力（Panda3Dの入力を pygame 風のイベントに変換） ----------------
class Ev:
    def __init__(self, type, **kw):
        self.type = type
        self.pos = kw.get("pos", (0, 0))
        self.button = kw.get("button", 0)
        self.key = kw.get("key", 0)
        self.mod = kw.get("mod", 0)
        self.text = kw.get("text", "")


KEYMAP = {"escape": pygame.K_ESCAPE, "space": pygame.K_SPACE, "backspace": pygame.K_BACKSPACE,
          "enter": pygame.K_RETURN, "home": pygame.K_HOME}

APP = None


def mouse_pos():
    return APP.mouse if APP else (0, 0)


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
        if self.active and int(time.monotonic() * 2) % 2 == 0:
            w = text_surf(self.text, 22, TEXT).get_width() if self.text else 0
            x = self.rect.x + 14 + w
            pygame.draw.line(surf, TEXT, (x, self.rect.y + 10), (x, self.rect.bottom - 10), 2)


def draw_panel(surf, rect, color=PANEL_A, radius=10):
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
    pygame.draw.rect(surf, (12, 14, 20, 245), rect, border_radius=8)
    pygame.draw.rect(surf, (100, 110, 140), rect, 2, border_radius=8)
    yy = y + pad
    for t, s, c in lines:
        draw_text(surf, t, (x + pad, yy), s, c)
        yy += s + 8


def shade_screen(surf, alpha=170):
    sh = pygame.Surface((W, H), pygame.SRCALPHA)
    sh.fill((0, 0, 0, alpha))
    surf.blit(sh, (0, 0))


# ---------------- 画面の配置 ----------------
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


def fmt_num(v):
    return f"{v:g}" if isinstance(v, float) else str(v)


def unit_tooltip(uid, star, cu=None):
    info = unit_info(uid)
    lines = [(f"{info['name']}  {'★' * star}", 20, STAR_COLORS[star])]
    bs = base_stats(uid, star)
    if uid in UNITS:
        lines.append((f"{info['cost']}コスト ／ {ARCH_NAME.get(info['arch'], '')} ／ " + "・".join(info["traits"]), 15, SUB))
    else:
        lines.append(("モンスター", 15, SUB))
    if cu is not None:
        lines.append((f"HP {int(cu.hp)}/{int(cu.maxhp)}   マナ {int(cu.mana)}/{int(cu.maxmana)}", 15, TEXT))
        lines.append((f"攻撃力 {int(cu.atk)}  攻速 {cu.as_base:.2f}  射程 {cu.range}  防御 {int(cu.armor)}/{int(cu.mr)}", 15, TEXT))
    else:
        lines.append((f"HP {int(bs['hp'])}  攻撃力 {int(bs['atk'])}  攻速 {bs['as']:.2f}  射程 {bs['rng']}", 15, TEXT))
        lines.append((f"物理防御 {int(bs['armor'])}  魔法防御 {int(bs['mr'])}  マナ {int(bs['mana'])}", 15, TEXT))
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
        self.new_events = []

    def update(self, dt):
        self.elapsed += dt
        n = 0
        while not self.sim.done and self.sim.t < self.elapsed and n < 300:
            for e in self.sim.step():
                self.fx.append([self.sim.t, e])
                self.new_events.append(e)
            n += 1
        self.fx = [f for f in self.fx if self.sim.t - f[0] < 0.9]

    def disp(self, r, c):
        return (7 - r, 6 - c) if self.flip else (r, c)

    def pos3(self, u):
        """(x, y, 跳ねる高さ)"""
        from world3d import cell_world
        a = cell_world(*self.disp(u.pr, u.pc))
        b = cell_world(*self.disp(u.r, u.c))
        f = 1.0 if u.mt < 0 else min(1.0, (self.sim.t - u.mt) / MOVE_TIME)
        hop = 0.25 * math.sin(f * math.pi) if f < 1.0 else 0.0
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, hop)

    @property
    def my_side(self):
        return "b" if self.flip else "a"


# ---------------- 画面：タイトル ----------------
class TitleScene:
    text_input = True

    def __init__(self, app, msg=""):
        self.app = app
        self.msg = msg
        app.restore_data()
        self.name = TextBox((490, 250, 300, 46), app.player_name, 10, "名前を入力")
        self.buttons = [
            Button((490, 320, 300, 52), "ひとりで遊ぶ（AI 7人と対戦）", self.solo),
            Button((490, 382, 300, 52), "部屋を作る（ホスト）", self.host),
            Button((490, 444, 300, 52), "部屋に入る", self.join),
            Button((490, 506, 300, 52), "遊び方", lambda: app.go(HelpScene(app))),
            Button((490, 568, 300, 52), "終了", self.quit),
            Button((1010, 640, 250, 40), "最新データを読み込む", self.reload, size=16),
        ]
        self.showcase = self._pick_showcase()

    def _pick_showcase(self):
        seen, out = set(), []
        for uid, u in sorted(UNITS.items(), key=lambda x: (-x[1]["cost"], x[0])):
            if u["look"] not in seen:
                seen.add(u["look"])
                out.append(uid)
        return out[:7]

    def reload(self):
        self.app.fetch_remote()

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
        self.app.quit()

    def handle(self, e):
        self.name.handle(e)
        for b in self.buttons:
            if b.handle(e):
                return

    def update(self, dt):
        if self.app.remote_changed:
            self.app.remote_changed = False
            self.app.restore_data()
            self.showcase = self._pick_showcase()

    def sync3d(self, w):
        from world3d import cell_world
        w.auto_orbit = True
        w.begin_sync()
        for i, uid in enumerate(self.showcase):
            x, y = cell_world(5, i)
            a = w.actor(("show", i), uid, UNITS[uid], 2 if i == 3 else 1, OWN)
            a.place(x, y, 0)
        for i, (cid, r, c) in enumerate((("c5", 1, 3), ("c4", 2, 1), ("c3", 2, 5), ("c1", 2, 3))):
            if cid in data.CREEPS:
                x, y = cell_world(r, c)
                a = w.actor(("showc", i), cid, data.CREEPS[cid], 1, ENEMY, True)
                a.place(x, y, 180)
        w.end_sync()

    def draw(self, s):
        draw_panel(s, pygame.Rect(440, 80, 400, 560), (16, 18, 26, 215), 16)
        draw_text_shadow(s, GAME_TITLE, (640, 130), 56, GOLD, "center")
        draw_text(s, f"8人のオートバトル ／ ユニット{len(UNITS)}種・シナジー{len(TRAITS)}種", (640, 190), 16, SUB, "center")
        draw_text(s, "あなたの名前", (490, 226), 16, SUB)
        self.name.draw(s)
        m = mouse_pos()
        for b in self.buttons:
            b.draw(s, m)
        if self.msg:
            draw_text_shadow(s, self.msg, (640, 660), 18, RED, "center")
        info = f"データ：{data.DATA_SOURCE}　{data.CURRENT.get('data_version', '')}"
        draw_text_shadow(s, info, (1260, 692), 14, SUB, "bottomright")
        if self.app.fetching:
            draw_text_shadow(s, "GitHubから最新データを取得中…", (1260, 632), 14, ACCENT, "bottomright")
        y = 6
        errs = data.LOAD_ERRORS[-3:]
        if data.REMOTE_ERROR and not self.app.fetching:
            errs = [data.REMOTE_ERROR] + errs
        for er in errs:
            draw_text_shadow(s, er, (1270, y), 14, RED, "topright")
            y += 20
        draw_text_shadow(s, f"ver {VERSION}", (1270, 714), 13, SUB, "bottomright")


class HelpScene:
    text_input = False
    LINES = [
        "【目的】8人で戦い、最後の1人まで生き残れば優勝です。",
        "1. 画面下のショップのカードをクリックしてユニットを買います。",
        "2. 買ったユニットはベンチ（盤面の手前の9マス）に入ります。ドラッグして盤面の手前半分に並べます。",
        "3. 盤面に置ける数は「レベル」と同じです。経験値を買う（Fキー）とレベルが上がります。",
        "4. 同じユニットを3体集めると★2、★2を3体で★3に自動で強化されます。",
        "5. 左の一覧は「シナジー」。同じ特性のユニットを揃えるとボーナスが付きます。",
        "6. 戦闘は自動です。負けると体力が減り、0になると脱落します。",
        "7. ゴールドは10ごとに利子+1（最大+5）。連勝・連敗でもボーナスがもらえます。",
        "8. 売却：ユニットをショップ欄へドラッグ、またはマウスを合わせてEキー。",
        "",
        "【キー】 D＝リロール(2G)  F＝経験値購入(4G)  E＝売却  Space＝準備OK  Esc＝メニュー",
        "【カメラ】 右ドラッグ＝回す　ホイール＝寄る・引く　Home＝元に戻す",
        "【対戦】ホストが「部屋を作る」→表示された部屋コードを伝える→他の人は「部屋に入る」で入力。",
        "　　　 空いた席はAIが入ります。途中で切断した人の席もAIが引き継ぎます。",
    ]

    def __init__(self, app):
        self.app = app
        self.back = Button((540, 640, 200, 50), "戻る", lambda: app.go(TitleScene(app)))

    def handle(self, e):
        self.back.handle(e)
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.app.go(TitleScene(self.app))

    def update(self, dt):
        pass

    def draw(self, s):
        s.fill(BG + (225,))
        draw_text(s, "遊び方", (640, 50), 36, GOLD, "center")
        y = 105
        for ln in self.LINES:
            draw_text(s, ln, (110, y), 19, TEXT)
            y += 36
        self.back.draw(s, mouse_pos())


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
                # ホストのユニットデータを配る（全員が同じ数値で戦闘を再生するため）
                self.server.send(cid, {"t": "welcome", "data": data.CURRENT, "src": data.DATA_SOURCE})
                changed = True
            elif t == "_disconnect":
                if cid in self.names:
                    del self.names[cid]
                    changed = True
        if changed:
            self.server.broadcast({"t": "lobby", "players": self.lobby_list()})

    def draw(self, s):
        s.fill(BG + (215,))
        draw_text(s, "部屋を作りました", (640, 50), 34, GOLD, "center")
        if self.error:
            draw_text(s, self.error, (640, 620), 18, RED, "center")
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
                "　 Radmin VPN などの無料VPNツールを全員で使うのが簡単です（説明書参照）。",
                f"※ 使うデータ：{data.DATA_SOURCE}（参加者にも自動で配られます）"]
        for tp in tips:
            draw_text(s, tp, (100, y), 15, SUB)
            y += 24
        draw_panel(s, pygame.Rect(760, 100, 440, 510))
        draw_text(s, "参加者（最大8人・空きはAI）", (780, 115), 18, TEXT)
        for i, nm in enumerate(self.lobby_list()):
            draw_text(s, f"{i + 1}. {nm}", (790, 160 + i * 44), 22, TEXT)
        for i in range(len(self.lobby_list()), 8):
            draw_text(s, f"{i + 1}. （AI）", (790, 160 + i * 44), 22, SUB)
        m = mouse_pos()
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
        s.fill(BG + (215,))
        draw_text(s, "部屋に入る", (640, 150), 36, GOLD, "center")
        draw_text(s, "ホストから聞いた部屋コードを入力してください（Ctrl+Vで貼り付け可）", (640, 250), 18, TEXT, "center")
        self.code.draw(s)
        m = mouse_pos()
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
        self.data_note = ""
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
            if t == "welcome":
                if msg.get("data"):
                    try:
                        data.apply(msg["data"], "ホストのデータ")
                        self.data_note = f"ホストのデータを受け取りました（{msg['data'].get('data_version', '')}）"
                    except (ValueError, KeyError, TypeError) as ex:
                        self.error = f"ホストのデータを読み込めませんでした：{ex}"
                        self.client.close()
            elif t == "lobby":
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
        s.fill(BG + (215,))
        draw_text(s, "部屋に入りました", (640, 80), 34, GOLD, "center")
        draw_text(s, "ホストがゲームを開始するのを待っています…", (640, 130), 20, TEXT, "center")
        draw_panel(s, pygame.Rect(420, 170, 440, 420))
        for i, nm in enumerate(self.players):
            draw_text(s, f"{i + 1}. {nm}", (450, 195 + i * 44), 22, TEXT)
        if self.error:
            draw_text(s, self.error, (640, 600), 18, RED, "center")
        elif self.data_note:
            draw_text(s, self.data_note, (640, 600), 15, SUB, "center")
        self.back.draw(s, mouse_pos())


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
        self.shown = []          # [(actor, 種類, uid, star, 戦闘中ユニット)] 画面に出ているユニット
        self.menu_buttons = [Button((490, 300, 300, 52), "ゲームに戻る", self.close_menu),
                             Button((490, 368, 300, 52), "タイトルへ戻る（退出）", self.to_title)]
        self.dead_buttons = [Button((440, 400, 190, 52), "観戦を続ける", self.dismiss_dead),
                             Button((650, 400, 190, 52), "タイトルへ", self.to_title)]
        self.end_buttons = [Button((540, 620, 200, 52), "タイトルへ", self.to_title)]
        self.err_buttons = [Button((540, 400, 200, 52), "タイトルへ", self.to_title)]
        app.world.auto_orbit = False
        app.world.reset_camera()

    def leave(self):
        self.session.close()
        self.app.world.clear_units()
        self.app.world.clear_fx()
        self.app.world.highlight()
        self.app.world.reset_camera()

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
                self.app.world.clear_fx()
        else:
            self.view = None
        if self.view:
            self.view.update(dt)

    # ---------- 位置の判定 ----------
    def ground(self, pos):
        return self.app.world.ground_at(self.app.to_ndc(pos))

    def cell_at(self, pos):
        return self.app.world.cell_at(self.ground(pos))

    def bench_at(self, pos):
        return self.app.world.bench_at(self.ground(pos))

    def shown_board(self):
        st = self.st
        if self.scout is not None:
            return st["players"][self.scout]["board"]
        return st["me"]["board"]

    def nearest_shown(self, pos, kinds=None, rad=34):
        """マウスに一番近いユニット（画面上の距離で判定）"""
        best, bd = None, rad
        for item in self.shown:
            a, kind = item[0], item[1]
            if kinds and kind[0] not in kinds:
                continue
            p = self.app.to_px(self.app.world.project((a.x, a.y, a.model.height * 0.5 + a.lift)))
            if p is None:
                continue
            d = math.hypot(pos[0] - p[0], pos[1] - p[1])
            if d < bd:
                bd, best = d, item
        return best

    def unit_at(self, pos):
        """自分のユニット（ドラッグ可能なもの）"""
        st = self.st
        planning = st["phase"] == "planning" and self.scout is None
        item = self.nearest_shown(pos, ("bench", "board") if planning else ("bench",))
        if item:
            kind = item[1]
            if kind[0] == "bench":
                return ["bench", kind[1]], st["me"]["bench"][kind[1]]
            return ["board", kind[1], kind[2]], st["me"]["board"][kind[1]][kind[2]]
        i = self.bench_at(pos)
        if i is not None and st["me"]["bench"][i]:
            return ["bench", i], st["me"]["bench"][i]
        if planning:
            cell = self.cell_at(pos)
            if cell and cell[0] >= 4:
                u = st["me"]["board"][cell[0] - 4][cell[1]]
                if u:
                    return ["board", cell[0] - 4, cell[1]], u
        return None, None

    def drop_target(self, pos):
        if SHOP_AREA.collidepoint(pos):
            return ["sell"]
        i = self.bench_at(pos)
        if i is not None:
            return ["bench", i]
        cell = self.cell_at(pos)
        if cell and cell[0] >= 4:
            return ["board", cell[0] - 4, cell[1]]
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
            elif e.key == pygame.K_HOME:
                self.app.world.reset_camera()
            elif not me["alive"]:
                return
            elif e.key == pygame.K_d:
                self.act({"t": "reroll"})
            elif e.key == pygame.K_f:
                self.act({"t": "xp"})
            elif e.key == pygame.K_SPACE:
                self.act({"t": "ready"})
            elif e.key == pygame.K_e:
                loc, u = self.unit_at(mouse_pos())
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

    # ---------- 3D表示の同期 ----------
    def sync3d(self, w):
        from world3d import cell_world, bench_world
        self.shown = []
        st = self.st
        w.begin_sync()
        if not st:
            w.end_sync()
            return
        me = st["me"]
        mouse = mouse_pos()
        # ベンチ
        for i in range(BENCH_SIZE):
            u = me["bench"][i]
            if not u or (self.drag and self.drag["loc"] == ["bench", i]):
                continue
            a = w.actor(("bench", i), u[0], unit_info(u[0]), u[1], OWN)
            x, y = bench_world(i)
            a.place(x, y, 0)
            self.shown.append((a, ("bench", i), u[0], u[1], None))
        if self.view and self.scout is None:
            self._sync_combat(w)
        else:
            board = self.shown_board()
            team = OWN if self.scout is None else SCOUT
            for r in range(4):
                for c in range(7):
                    u = board[r][c]
                    if not u or (self.scout is None and self.drag and self.drag["loc"] == ["board", r, c]):
                        continue
                    a = w.actor(("board", r, c, self.scout), u[0], unit_info(u[0]), u[1], team)
                    x, y = cell_world(4 + r, c)
                    a.place(x, y, 0)
                    self.shown.append((a, ("board", r, c), u[0], u[1], None))
            if self.scout is None and st["phase"] == "planning" and st["pve"]:
                for i, (uid, star, r, c) in enumerate(pve_board(st["round"])):
                    if uid not in data.CREEPS:
                        continue
                    a = w.actor(("pve", i, st["round"]), uid, data.CREEPS[uid], star, ENEMY, True)
                    x, y = cell_world(3 - r, 6 - c)
                    a.place(x, y, 180)
                    a.set_dim(True)
                    self.shown.append((a, ("pve", i), uid, star, None))
        # ドラッグ中のユニット
        hl_cells, hl_bench = (), ()
        if self.drag:
            u = self.drag["u"]
            g = self.ground(mouse)
            if g is not None:
                a = w.actor(("drag",), u[0], unit_info(u[0]), u[1], OWN)
                a.place(g[0], g[1], 0, lift=0.5)
            cell = self.cell_at(mouse)
            if cell and cell[0] >= 4:
                hl_cells = (cell,)
            b = self.bench_at(mouse)
            if b is not None:
                hl_bench = (b,)
        w.highlight(hl_cells, hl_bench)
        w.end_sync()

    def _sync_combat(self, w):
        v = self.view
        now = w.now
        acts = {}
        for u in v.sim.units:
            info = unit_info(u.uid)
            mine = u.side == v.my_side
            a = w.actor(("cb", v.cid, u.idx), u.uid, info, u.star, OWN if mine else ENEMY, u.uid not in UNITS)
            acts[u.idx] = a
            x, y, hop = v.pos3(u)
            tg = u.target
            if tg is not None and tg.alive:
                tx, ty, _ = v.pos3(tg)
                want = math.degrees(math.atan2(-(tx - x), ty - y))
            else:
                want = 0.0 if mine else 180.0
            dh = (want - a.heading + 540) % 360 - 180
            a.place(x, y, a.heading + dh * 0.25, hop=hop)
            if not u.alive:
                if a.dead_t is None:
                    a.dead_t = now
            elif a.dead_t is not None:
                a.revive()
            a.set_shield(u.alive and v.sim.shield_total(u) > 1)
            if u.alive:
                self.shown.append((a, ("cb", u.idx), u.uid, u.star, u))

        def chest(a):
            return (a.x, a.y, a.model.height * 0.55)

        for e in v.new_events:
            kind = e[0]
            if kind == "atk":
                a, b = acts.get(e[1]), acts.get(e[2])
                if a is None or b is None:
                    continue
                a.t_attack = now
                if e[3]:
                    col = (255, 240, 170)
                    info = UNITS.get(v.sim.units[e[1]].uid)
                    if info and info["arch"] == "caster":
                        col = (150, 190, 255)
                    w.fx_projectile(chest(a), chest(b), col)
            elif kind == "dmg":
                b = acts.get(e[1])
                if b is not None:
                    b.t_hit = now
                    if e[3] in ("phys", "magic") and e[2] > 0:
                        w.fx_burst(chest(b), (255, 170, 110) if e[3] == "phys" else (130, 170, 255), n=3, dur=0.35)
            elif kind == "heal":
                b = acts.get(e[1])
                if b is not None and e[2] >= 20:
                    w.fx_burst((b.x, b.y, 0.3), (120, 240, 140), n=4, dur=0.6, up=1.6, spread=0.3)
            elif kind == "cast":
                a = acts.get(e[1])
                if a is None:
                    continue
                a.t_cast = now
                typ = e[2]
                col = {"heal": (120, 240, 140), "aura_heal": (120, 240, 140), "shield": (230, 230, 255),
                       "taunt": (255, 200, 120), "frenzy": (255, 120, 80), "buff_team": (255, 220, 100),
                       "meteor": (255, 110, 60), "blast": (255, 140, 70), "quake": (220, 180, 110),
                       "chain": (140, 200, 255), "stun": (200, 160, 255)}.get(typ, (120, 200, 255))
                w.fx_ring((a.x, a.y), col, size=2.2 if typ in ("aura_heal", "buff_team", "quake", "taunt") else 1.4)
                tg = v.sim.units[e[1]].target
                if typ in ("meteor", "blast") and tg is not None and tg.idx in acts:
                    t = acts[tg.idx]
                    w.fx_ring((t.x, t.y), col, size=3.5 if typ == "meteor" else 2.2, dur=0.6)
                    w.fx_burst((t.x, t.y, 0.4), col, n=10, dur=0.6, up=1.5, spread=1.2)
                elif typ in ("strike", "stun", "snipe", "drain", "leap", "chain") and tg is not None and tg.idx in acts:
                    w.fx_projectile(chest(a), chest(acts[tg.idx]), col, dur=0.2, r=0.18)
                elif typ in ("shield", "taunt"):
                    w.fx_bubble((a.x, a.y, 0.6), col)
            elif kind == "die":
                a = acts.get(e[1])
                if a is not None:
                    a.dead_t = now
                    w.fx_burst(chest(a), (200, 200, 220), n=8, dur=0.6)
            elif kind == "revive":
                a = acts.get(e[1])
                if a is not None:
                    a.revive()
                    w.fx_burst(chest(a), (220, 200, 255), n=10, dur=0.8, up=1.5)
        v.new_events = []

    # ---------- 描画 ----------
    def draw(self, s):
        st = self.st
        if not st:
            s.fill(BG + (200,))
            draw_text(s, "ホストからの情報を待っています…", (640, 360), 24, TEXT, "center")
            if self.session.error:
                self.draw_overlay(s, self.session.error, "", self.err_buttons)
            return
        mouse = mouse_pos()
        w = self.app.world
        tips = None
        me = st["me"]

        # 上部バー
        draw_panel(s, pygame.Rect(0, 0, W, 40), PANEL_A, 0)
        kind = "モンスター戦" if st["pve"] else "対人戦"
        draw_text(s, f"ラウンド {st['round']}  ・ {kind}", (12, 20), 18, TEXT, "midleft")
        ph = {"planning": "準備フェーズ", "combat": "戦闘フェーズ", "end": "ゲーム終了"}[st["phase"]]
        tcol = RED if st["timer"] < 6 and st["phase"] == "planning" else TEXT
        draw_text(s, f"{ph}  残り {int(math.ceil(st['timer']))} 秒", (640, 20), 20, tcol, "center")
        odds = SHOP_ODDS[me["level"]]
        x = 1270
        for ci in range(5, 0, -1):
            r = draw_text(s, f"{fmt_num(odds[ci - 1])}%", (x, 20), 15, COST_COLORS[ci], "midright")
            x = r.left - 10
        draw_text(s, "出現率", (x, 20), 14, SUB, "midright")
        if self.view:
            opp = self.view.setup["b" if self.view.my_side == "a" else "a"]["name"]
            draw_text(s, f"VS {opp}", (330, 20), 18, ENEMY, "midleft")

        planning = st["phase"] == "planning"
        # ユニットの頭上（★・HP・マナ）
        for a, kind_, uid, star, cu in self.shown:
            p = self.app.to_px(w.project(a.head_pos()))
            if p is None:
                continue
            x, y = p
            if cu is not None:
                bw = 46
                bx, by = int(x - bw / 2), int(y - 4)
                mine = cu.side == self.view.my_side
                pygame.draw.rect(s, (20, 10, 10, 230), (bx - 1, by - 1, bw + 2, 7))
                pygame.draw.rect(s, GREEN if mine else RED, (bx, by, int(bw * max(0, min(1, cu.hp / cu.maxhp))), 5))
                if cu.maxmana:
                    pygame.draw.rect(s, (15, 18, 34, 230), (bx - 1, by + 6, bw + 2, 4))
                    pygame.draw.rect(s, (90, 150, 255), (bx, by + 6, int(bw * max(0, min(1, cu.mana / cu.maxmana))), 3))
                draw_text_shadow(s, "★" * star, (x, by - 9), 11, STAR_COLORS[star], "center")
                if cu.stun_until > self.view.sim.t:
                    draw_text_shadow(s, "スタン", (x, by - 24), 12, GOLD, "center")
            else:
                draw_text_shadow(s, "★" * star, (x, y - 2), 12, STAR_COLORS[star], "center")
        if self.view and self.scout is None:
            self.draw_fx(s, self.view)
            v = self.view
            if v.sim.done:
                won = v.sim.winner == v.my_side
                txt = "勝利！" if won else ("引き分け" if v.sim.winner == "draw" else "敗北…")
                draw_text_shadow(s, txt, (640, 250), 60, GOLD if won else RED, "center")
        else:
            if self.scout is not None:
                draw_text_shadow(s, f"{st['players'][self.scout]['name']} の盤面を見ています（右の一覧をもう一度クリックで戻る）",
                                 (640, 60), 17, SCOUT, "center")
            elif planning and st["pve"]:
                draw_text_shadow(s, "次の相手：モンスター", (640, 60), 17, SUB, "center")
            elif planning:
                draw_text_shadow(s, "相手の陣地（戦闘開始時に対戦相手が決まります）", (640, 60), 16, SUB, "center")
            if planning and self.scout is None:
                cnt = sum(1 for row in me["board"] for u in row if u)
                col = GOLD if cnt < me["level"] else SUB
                draw_text_shadow(s, f"盤面 {cnt} / {me['level']} 体", (640, 584), 15, col, "midbottom")
        if not self.drag:
            item = self.nearest_shown(mouse, rad=30)
            if item:
                tips = unit_tooltip(item[2], item[3], item[4])

        # シナジー一覧
        uids = [u[0] for row in self.shown_board() for u in row if u]
        if self.view and self.scout is None:
            side = self.view.my_side
            uids = [x[0] for x in self.view.setup[side]["units"]]
        traits = compute_traits(uids)
        draw_text_shadow(s, "シナジー", (TRAIT_X + 4, TRAIT_Y - 2), 14, SUB)
        y = TRAIT_Y + 20
        for name, cnt, tier in traits[:17]:
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
            pygame.draw.rect(s, PANEL_A, rr, border_radius=6)
            pygame.draw.rect(s, tc, (TRAIT_X, y, 34, TRAIT_H - 3), border_radius=6)
            draw_text(s, str(cnt), (TRAIT_X + 17, y + (TRAIT_H - 3) // 2), 16, (20, 20, 20) if tier else TEXT, "center")
            draw_text(s, name, (TRAIT_X + 42, y + (TRAIT_H - 3) // 2), 16, TEXT if tier else SUB, "midleft")
            ths = " ・ ".join(str(x) for x in th)
            draw_text(s, ths, (TRAIT_X + 205, y + (TRAIT_H - 3) // 2), 13, SUB, "midright")
            if rr.collidepoint(mouse):
                tips = trait_tooltip(name, cnt, set(uids))
            y += TRAIT_H
        if not traits:
            draw_text_shadow(s, "ユニットを盤面に置くと表示", (TRAIT_X + 4, y), 14, SUB)

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
            col = PANEL2 + (235,) if enabled else (32, 34, 42, 235)
            if enabled and rect.collidepoint(mouse):
                col = lighten(col, 30)
            pygame.draw.rect(s, col, rect, border_radius=8)
            draw_text(s, label, rect.center, 17, TEXT if enabled else SUB, "center")

        # ショップ
        if self.drag:
            pygame.draw.rect(s, (90, 40, 40, 235), SHOP_AREA, border_radius=10)
            u = self.drag["u"]
            draw_text(s, f"ここに置くと売却（+{sell_value(u[0], u[1])}G）", SHOP_AREA.center, 24, TEXT, "center")
        else:
            for i in range(SHOP_SIZE):
                rc = card_rect(i)
                uid = me["shop"][i]
                if not uid or uid not in UNITS:
                    pygame.draw.rect(s, (24, 26, 34, 200), rc, border_radius=8)
                    continue
                info = UNITS[uid]
                cc = COST_COLORS[info["cost"]]
                can = me["gold"] >= info["cost"]
                bg = tuple(int(v * 0.30) for v in cc)
                if rc.collidepoint(mouse) and can:
                    bg = lighten(bg, 25)
                pygame.draw.rect(s, bg + (240,), rc, border_radius=8)
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
        for i in range(8):
            p = st["players"][i]
            rc = player_rect(i)
            bg = PANEL_A
            if self.scout == i:
                bg = (60, 50, 90, 235)
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
                ratio = max(0, min(1, p["hp"] / max(1, data.START_HP)))
                pygame.draw.rect(s, hpc, (rc.x + 10, rc.y + 34, int(150 * ratio), 12), border_radius=4)
                draw_text(s, str(p["hp"]), (rc.right - 10, rc.y + 40), 15, TEXT, "midright")
            else:
                draw_text(s, f"脱落 {p['placement']}位", (rc.x + 10, rc.y + 32), 15, SUB)
            if rc.collidepoint(mouse) and i != me["pid"]:
                tips = [(f"{p['name']}", 18, TEXT), ("クリックで盤面を見る", 14, SUB)]

        # 右下：固定・準備OK
        lcol = (90, 70, 30, 235) if me["locked"] else PANEL2 + (235,)
        if BTN_LOCK.collidepoint(mouse):
            lcol = lighten(lcol, 25)
        pygame.draw.rect(s, lcol, BTN_LOCK, border_radius=8)
        draw_text(s, "ショップ固定中" if me["locked"] else "ショップを固定", BTN_LOCK.center, 17, TEXT, "center")
        if planning:
            rcol = (40, 110, 70, 240) if me["ready"] else (50, 70, 110, 240)
            if BTN_READY.collidepoint(mouse):
                rcol = lighten(rcol, 25)
            pygame.draw.rect(s, rcol, BTN_READY, border_radius=8)
            draw_text(s, "準備OK（待機中）" if me["ready"] else "準備OK [Space]", BTN_READY.center, 19, TEXT, "center")
        else:
            pygame.draw.rect(s, (30, 32, 40, 235), BTN_READY, border_radius=8)
            draw_text(s, "戦闘中…", BTN_READY.center, 18, SUB, "center")

        # ログ
        y = 555
        for ln in st.get("log", [])[-2:]:
            draw_text_shadow(s, ln, (1270, y), 12, SUB, "topright")
            y += 16

        if self.drag:
            tips = None

        # トースト
        if self.toast_t > 0 and self.toast:
            t = text_surf(self.toast, 22, TEXT)
            rc = t.get_rect(center=(640, 92)).inflate(30, 14)
            pygame.draw.rect(s, (10, 12, 18, 240), rc, border_radius=10)
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
        w = self.app.world
        acts = {k[2]: a for k, a in w.actors.items() if k[0] == "cb" and k[1] == v.cid}

        def head(i, up=0.0):
            a = acts.get(i)
            if a is None:
                return None
            return self.app.to_px(w.project((a.x, a.y, a.model.height + 0.3 + up)))

        for ft, e in v.fx:
            age = t - ft
            kind = e[0]
            if kind == "dmg" and age < 0.7:
                p = head(e[1])
                if p:
                    col = {"phys": (255, 150, 120), "magic": (140, 180, 255)}.get(e[3], TEXT)
                    draw_text_shadow(s, str(e[2]), (p[0] + 14, p[1] - 10 - age * 40), 15, col, "center")
            elif kind == "heal" and age < 0.7:
                p = head(e[1])
                if p:
                    draw_text_shadow(s, "+" + str(e[2]), (p[0] - 14, p[1] - 10 - age * 40), 14, GREEN, "center")
            elif kind == "miss" and age < 0.5:
                p = head(e[1])
                if p:
                    draw_text_shadow(s, "回避", (p[0], p[1] - 14 - age * 30), 13, SUB, "center")
            elif kind == "cast" and age < 0.5:
                p = self.app.to_px(w.project((acts[e[1]].x, acts[e[1]].y, 0))) if e[1] in acts else None
                info = UNITS.get(units[e[1]].uid)
                if p and info:
                    draw_text_shadow(s, info["ability_name"], (p[0], p[1] + 14), 14, (150, 210, 255), "center")
            elif kind == "revive" and age < 0.8:
                p = head(e[1])
                if p:
                    draw_text_shadow(s, "復活！", (p[0], p[1] - 20), 16, (220, 200, 255), "center")

    def draw_overlay(self, s, title, sub, buttons):
        shade_screen(s, 170)
        draw_panel(s, pygame.Rect(400, 200, 480, 300), PANEL + (250,))
        draw_text(s, title, (640, 250), 30, GOLD, "center")
        if sub:
            draw_text(s, sub, (640, 300), 18, SUB, "center")
        m = mouse_pos()
        for b in buttons:
            b.draw(s, m)

    def draw_ranking(self, s):
        shade_screen(s, 180)
        draw_panel(s, pygame.Rect(390, 90, 500, 600), PANEL + (250,))
        draw_text(s, "最終結果", (640, 130), 34, GOLD, "center")
        ps = sorted(self.st["players"], key=lambda p: p["placement"] or 99)
        for i, p in enumerate(ps):
            col = GOLD if p["placement"] == 1 else (ACCENT if p["pid"] == self.st["me"]["pid"] else TEXT)
            draw_text(s, f"{p['placement']}位", (450, 180 + i * 52), 26, col)
            draw_text(s, p["name"], (540, 184 + i * 52), 22, col)
        m = mouse_pos()
        for b in self.end_buttons:
            b.draw(s, m)


# ---------------- アプリ本体 ----------------
def configure_panda(offscreen=False):
    lines = [f"window-title {GAME_TITLE}  ver {VERSION}", f"win-size {W} {H}", "sync-video 1",
             "framebuffer-multisample 1", "multisamples 4", "audio-library-name null",
             "textures-power-2 none", "notify-level error", "default-directnotify-level error",
             "load-display pandagl"]
    if getattr(sys, "frozen", False):
        lines.append(f"plugin-path {os.path.join(sys._MEIPASS, 'panda3d')}")
        lines.append(f"plugin-path {sys._MEIPASS}")
    if offscreen:
        lines.append("window-type offscreen")
    loadPrcFileData("", "\n".join(lines))


class App:
    def __init__(self, base):
        global APP
        APP = self
        from panda3d.core import CardMaker, KeyboardButton, Texture, TransparencyAttrib
        import world3d
        self.base = base
        self.world = world3d.World(base)
        self.surf = pygame.Surface((W, H), pygame.SRCALPHA)
        self.tex = Texture("ui")
        self.tex.setup2dTexture(W, H, Texture.T_unsigned_byte, Texture.F_rgba8)
        self.tex.setMinfilter(Texture.FT_linear)
        self.tex.setMagfilter(Texture.FT_linear)
        cm = CardMaker("ui")
        cm.setFrame(-1, 1, -1, 1)
        card = base.render2d.attachNewNode(cm.generate())
        card.setTexture(self.tex)
        card.setTransparency(TransparencyAttrib.MAlpha)
        self.ctrl_btn = KeyboardButton.control()
        self.mouse = (W // 2, H // 2)
        self.events = []
        self.rdrag = None
        self.player_name = "プレイヤー"
        self.remote_data = None
        self.remote_changed = False
        self.fetching = False
        self.scene = None
        if base.buttonThrowers:  # 画面なし（自動テスト）のときは無い
            bt = base.buttonThrowers[0].node()
            bt.setButtonDownEvent("btn_down")
            bt.setButtonUpEvent("btn_up")
            bt.setKeystrokeEvent("keystroke")
        base.accept("btn_down", self.on_down)
        base.accept("btn_up", self.on_up)
        base.accept("keystroke", self.on_key)
        base.exitFunc = self.on_exit
        self.fetch_remote()
        self.go(TitleScene(self))
        base.taskMgr.add(self.loop, "hexarena-loop")

    # ----- データ -----
    def fetch_remote(self):
        if self.fetching:
            return
        self.fetching = True

        def run():
            d = data.fetch_remote()
            if d is not None:
                self.remote_data = d
            self.fetching = False
            self.remote_changed = True
        threading.Thread(target=run, daemon=True).start()

    def restore_data(self):
        """タイトルに戻ったら自分のデータに戻す（ホストのデータを受け取っていた場合など）"""
        data.load_preferred(self.remote_data)

    # ----- 画面 -----
    def go(self, scene):
        if self.scene is not None and hasattr(self.scene, "leave"):
            try:
                self.scene.leave()
            except Exception:
                pass
        self.scene = scene

    def quit(self):
        self.base.userExit()

    def on_exit(self):
        if self.scene is not None and hasattr(self.scene, "leave"):
            try:
                self.scene.leave()
            except Exception:
                pass

    # ----- 座標 -----
    def to_ndc(self, pos):
        return (pos[0] / W * 2 - 1, 1 - pos[1] / H * 2)

    def to_px(self, ndc):
        if ndc is None:
            return None
        return ((ndc[0] + 1) / 2 * W, (1 - ndc[1]) / 2 * H)

    # ----- 入力 -----
    def ctrl(self):
        mw = self.base.mouseWatcherNode
        return mw is not None and mw.isButtonDown(self.ctrl_btn)

    def on_down(self, name):
        if name == "mouse1":
            self.events.append(Ev(pygame.MOUSEBUTTONDOWN, pos=self.mouse, button=1))
        elif name == "mouse3":
            self.rdrag = self.mouse
        elif name in ("wheel_up", "wheel_down"):
            if isinstance(self.scene, GameScene):
                self.world.zoom(0.92 if name == "wheel_up" else 1.08)
        else:
            key = KEYMAP.get(name)
            if key is None and len(name) == 1 and "a" <= name <= "z":
                key = ord(name)
            if key is not None:
                self.events.append(Ev(pygame.KEYDOWN, key=key, mod=pygame.KMOD_CTRL if self.ctrl() else 0))

    def on_up(self, name):
        if name == "mouse1":
            self.events.append(Ev(pygame.MOUSEBUTTONUP, pos=self.mouse, button=1))
        elif name == "mouse3":
            self.rdrag = None

    def on_key(self, ch):
        if ch and ord(ch[0]) >= 32 and ch != "\x7f" and not self.ctrl():
            self.events.append(Ev(pygame.TEXTINPUT, text=ch))

    def poll_mouse(self):
        mw = self.base.mouseWatcherNode
        if mw is not None and mw.hasMouse():
            m = mw.getMouse()
            self.mouse = (int((m.x + 1) / 2 * W), int((1 - m.y) / 2 * H))
        if self.rdrag is not None and isinstance(self.scene, GameScene):
            dx = self.mouse[0] - self.rdrag[0]
            dy = self.mouse[1] - self.rdrag[1]
            if dx or dy:
                self.world.rotate_camera(dx, dy)
            self.rdrag = self.mouse

    # ----- 毎フレーム -----
    def step(self, dt):
        self.poll_mouse()
        evs, self.events = self.events, []
        for e in evs:
            self.scene.handle(e)
        scene = self.scene
        scene.update(dt)
        if self.scene is scene:
            if hasattr(scene, "sync3d"):
                scene.sync3d(self.world)
            else:
                self.world.begin_sync()
                self.world.end_sync()
        self.world.update(dt)
        self.surf.fill((0, 0, 0, 0))
        self.scene.draw(self.surf)
        self.tex.setRamImage(pygame.image.tobytes(self.surf, "BGRA", True))

    def loop(self, task):
        from panda3d.core import ClockObject
        dt = min(0.1, ClockObject.getGlobalClock().getDt())
        try:
            self.step(dt)
        except Exception:
            import traceback
            if sys.stderr:
                traceback.print_exc()
            log_error(traceback.format_exc())
            self.go(TitleScene(self, "エラーが起きたのでタイトルに戻りました（hexarena_error.log を確認）"))
        return task.cont


def log_error(text):
    try:
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base_dir, "hexarena_error.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S]\n") + text + "\n")
    except OSError:
        pass


def create_app(offscreen=False):
    configure_panda(offscreen)
    pygame.font.init()
    from direct.showbase.ShowBase import ShowBase
    base = ShowBase()
    return App(base)


def smoke_test(path):
    """起動確認用：画面を出さずに数十フレーム動かし、画像を保存して終了する（exeの自動チェック用）"""
    from panda3d.core import Filename
    app = create_app(offscreen=True)
    for _ in range(30):
        app.base.taskMgr.step()
    app.go(GameScene(app, HostSession(Game(["テスト"]))))
    for _ in range(60):
        app.base.taskMgr.step()
    ok = app.base.win.saveScreenshot(Filename.fromOsSpecific(path))
    with open(path + ".txt", "w", encoding="utf-8") as f:  # 画面なしのexeでは print が使えないのでファイルに書く
        f.write(("SMOKE_OK" if ok else "SMOKE_FAIL") + f" {data.DATA_SOURCE} units={len(UNITS)}\n")
    os._exit(0 if ok else 1)


def main():
    if os.environ.get("HEXARENA_SMOKETEST"):
        smoke_test(os.environ["HEXARENA_SMOKETEST"])
    app = create_app()
    app.base.run()


if __name__ == "__main__":
    main()
