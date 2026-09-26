# -*- coding: utf-8 -*-
"""ゲームデータ

ユニット・スキル・シナジー・モンスター・経済の数値は unit_data.json に入っています。
編集サイト（editor/index.html）で編集して、unit_data.json を差し替えてください。

読み込む順番（先に見つかったものを使う）:
  1. exe（または main.py）と同じフォルダに置いた unit_data.json …… 自分だけ試したいとき用
  2. GitHubにある最新の unit_data.json（REMOTE_URL）…… チームで共有する正式データ
  3. exeに同梱された unit_data.json …… ネットにつながらないとき用
対戦では、ホストのデータが参加者全員に配られるので数値のズレは起きません。
"""
import hashlib
import json
import os
import sys
import urllib.request

VERSION = "2.0.0"
GAME_TITLE = "ヘックス・アリーナ"
REMOTE_URL = "https://raw.githubusercontent.com/mikatario/HexArena/main/unit_data.json"
DATA_FILE = "unit_data.json"

BOARD_ROWS, BOARD_COLS = 4, 7
BENCH_SIZE = 9
SHOP_SIZE = 5
MAX_LEVEL = 10
COST_COLORS = {1: (150, 150, 160), 2: (60, 175, 95), 3: (60, 130, 230), 4: (175, 85, 225), 5: (240, 185, 40), 0: (150, 95, 70)}

# 新しくユニットを作るときの目安（編集サイトの「タイプ」初期値）
ARCH = {
    "tank":     {"hp": 720, "atk": 45, "as": 0.60, "armor": 40, "mr": 35, "rng": 1},
    "bruiser":  {"hp": 640, "atk": 55, "as": 0.70, "armor": 30, "mr": 30, "rng": 1},
    "assassin": {"hp": 540, "atk": 62, "as": 0.80, "armor": 22, "mr": 22, "rng": 1},
    "lancer":   {"hp": 600, "atk": 55, "as": 0.70, "armor": 25, "mr": 25, "rng": 2},
    "sniper":   {"hp": 500, "atk": 55, "as": 0.75, "armor": 15, "mr": 15, "rng": 4},
    "caster":   {"hp": 500, "atk": 38, "as": 0.65, "armor": 15, "mr": 20, "rng": 3},
}
ARCH_NAME = {"tank": "タンク", "bruiser": "近接", "assassin": "暗殺", "lancer": "中距離",
             "sniper": "遠距離", "caster": "魔法"}
# AIが盤面に置くときの行の好み（0=前列）
ROW_PREF = {"tank": [0, 1, 2, 3], "bruiser": [0, 1, 2, 3], "assassin": [3, 2, 1, 0],
            "lancer": [1, 0, 2, 3], "sniper": [3, 2, 1, 0], "caster": [3, 2, 1, 0]}
COL_PREF = [3, 2, 4, 1, 5, 0, 6]

# 見た目（3Dモデル）の種類
LOOKS = {"knight": "騎士", "warrior": "戦士", "lancer": "槍使い", "archer": "弓使い", "mage": "魔法使い",
         "assassin": "忍び", "beast": "獣人", "dragonkin": "竜人", "robot": "機械兵", "ghost": "亡霊",
         "slime": "スライム", "goblin": "ゴブリン", "wolf": "オオカミ", "golem": "ゴーレム", "dragon": "ドラゴン"}

# スキルの効果の種類（動きはプログラム側で決まっていて、威力・マナ・秒数を編集できる）
SKILL_TYPES = {
    "strike": "単体に魔法ダメージ",
    "stun": "単体に魔法ダメージ＋スタン",
    "snipe": "最も遠い敵に物理ダメージ",
    "leap": "HP最小の敵へ跳んで魔法ダメージ",
    "heal": "HP割合最小の味方を回復",
    "aura_heal": "味方全員を回復",
    "shield": "自分にシールド",
    "taunt": "シールド＋周囲の敵を挑発",
    "frenzy": "攻撃速度アップ（%）",
    "multishot": "ランダムな敵3体に物理ダメージ",
    "drain": "魔法ダメージ＋与えた60%回復",
    "blast": "対象と周囲1マスに魔法ダメージ",
    "chain": "敵4体に連鎖する魔法ダメージ",
    "quake": "周囲1マスに魔法ダメージ＋スタン",
    "buff_team": "味方全員の攻撃力・スキル威力アップ（%）",
    "meteor": "対象の周囲2マスに魔法ダメージ",
}
PCT_TYPES = {"frenzy", "buff_team"}

# ---------- 読み込んだデータが入る入れ物（中身だけ入れ替えるので import 先でもそのまま使える） ----------
START_HP = 100
STAR_MULT = [1.0, 1.8, 3.24]
POOL_SIZE = {}
SHOP_ODDS = {}
XP_TO_NEXT = {}
ABILITIES = {}
UNITS = {}
UNIT_IDS_BY_COST = {c: [] for c in range(1, 6)}
TRAITS = {}
TRAIT_ORDER = {}
CREEPS = {}
CURRENT = {}          # いま使っているデータ（そのまま参加者に送る）
DATA_SOURCE = ""      # 画面表示用：どこから読んだか
LOAD_ERRORS = []      # 読み込めなかった理由
REMOTE_ERROR = ""     # GitHubから取得できなかった理由


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _num(v, name):
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} が数字ではありません（{v!r}）")


def validate(d):
    """おかしなデータなら ValueError（日本語の理由つき）"""
    if not isinstance(d, dict):
        raise ValueError("データの形式が正しくありません")
    for key in ("settings", "skills", "traits", "units", "creeps"):
        if key not in d:
            raise ValueError(f"「{key}」がありません")
    skills = {s.get("id") for s in d["skills"]}
    for s in d["skills"]:
        if s.get("type") not in SKILL_TYPES:
            raise ValueError(f"スキル「{s.get('name')}」の効果の種類「{s.get('type')}」は使えません")
        _num(s.get("mana"), f"スキル「{s.get('name')}」のマナ")
        _num(s.get("power"), f"スキル「{s.get('name')}」の威力")
    traits = {t.get("name"): t for t in d["traits"]}
    ids = set()
    for u in d["units"]:
        nm = u.get("name")
        if u.get("id") in ids:
            raise ValueError(f"ユニットID「{u.get('id')}」が重複しています")
        ids.add(u.get("id"))
        if int(u.get("cost", 0)) not in (1, 2, 3, 4, 5):
            raise ValueError(f"ユニット「{nm}」のコストは1〜5にしてください")
        if u.get("element") not in traits or traits[u["element"]].get("kind") != "属性":
            raise ValueError(f"ユニット「{nm}」の属性「{u.get('element')}」がシナジー表（属性）にありません")
        if not u.get("classes"):
            raise ValueError(f"ユニット「{nm}」に職業がありません")
        for c in u["classes"]:
            if c not in traits or traits[c].get("kind") != "職業":
                raise ValueError(f"ユニット「{nm}」の職業「{c}」がシナジー表（職業）にありません")
        if u.get("skill") not in skills:
            raise ValueError(f"ユニット「{nm}」のスキル「{u.get('skill')}」がスキル表にありません")
        if u.get("type") not in ARCH:
            raise ValueError(f"ユニット「{nm}」のタイプ「{u.get('type')}」は使えません")
        for k in ("hp", "atk", "as", "armor", "mr", "rng"):
            _num(u.get(k), f"ユニット「{nm}」の{k}")
        if float(u["as"]) <= 0 or float(u["hp"]) <= 0 or int(float(u["rng"])) < 1:
            raise ValueError(f"ユニット「{nm}」のHP・攻撃速度・射程は1以上（攻速は0より大）にしてください")
    for c in range(1, 6):
        if not any(int(u["cost"]) == c for u in d["units"]):
            raise ValueError(f"{c}コストのユニットが1体もいません（各コスト最低1体必要）")
    for c in ("c1", "c2", "c3", "c4", "c5"):
        if not any(x.get("id") == c for x in d["creeps"]):
            raise ValueError(f"モンスター「{c}」がありません（c1〜c5は必須）")
    st = d["settings"]
    for lv in range(1, MAX_LEVEL + 1):
        odds = st["shop_odds"].get(str(lv))
        if not odds or len(odds) != 5 or sum(odds) <= 0:
            raise ValueError(f"レベル{lv}のショップ出現率が正しくありません")
    for lv in range(1, MAX_LEVEL):
        _num(st["xp_to_next"].get(str(lv)), f"レベル{lv}の必要経験値")
    if len(st.get("star_mult", [])) != 3:
        raise ValueError("★倍率は3つ（★1・★2・★3）必要です")


def apply(d, source=""):
    """データを検査してから、ゲーム全体に反映する"""
    global START_HP, DATA_SOURCE
    validate(d)
    st = d["settings"]
    START_HP = int(st.get("start_hp", 100))
    STAR_MULT[:] = [float(x) for x in st["star_mult"]]
    POOL_SIZE.clear()
    POOL_SIZE.update({int(k): int(v) for k, v in st["pool_size"].items()})
    for c in range(1, 6):
        POOL_SIZE.setdefault(c, 10)
    SHOP_ODDS.clear()
    SHOP_ODDS.update({int(k): [float(x) for x in v] for k, v in st["shop_odds"].items()})
    XP_TO_NEXT.clear()
    XP_TO_NEXT.update({int(k): int(v) for k, v in st["xp_to_next"].items()})

    ABILITIES.clear()
    for s in d["skills"]:
        ABILITIES[s["id"]] = {"name": s.get("name", s["id"]), "type": s["type"], "mana": float(s["mana"]),
                              "base": float(s["power"]), "dur": float(s.get("dur") or 0)}

    UNITS.clear()
    for c in UNIT_IDS_BY_COST:
        UNIT_IDS_BY_COST[c].clear()
    for u in d["units"]:
        uid = u["id"]
        el = u["element"]
        sk = ABILITIES[u["skill"]]
        UNITS[uid] = {"id": uid, "name": u["name"], "cost": int(u["cost"]), "traits": [el] + list(u["classes"]),
                      "arch": u["type"], "ability": u["skill"],
                      "ability_name": u.get("skill_name") or (el + "の" + sk["name"]),
                      "look": u.get("look") or "warrior",
                      "stats": {"hp": float(u["hp"]), "atk": float(u["atk"]), "as": float(u["as"]),
                                "armor": float(u["armor"]), "mr": float(u["mr"]), "rng": int(float(u["rng"]))}}
        UNIT_IDS_BY_COST[int(u["cost"])].append(uid)

    TRAITS.clear()
    TRAIT_ORDER.clear()
    for i, t in enumerate(d["traits"]):
        n = t["name"]
        members = [x for x in UNITS if n in UNITS[x]["traits"]]
        th = [int(x) for x in (t.get("thresholds") or []) if str(x).strip() != ""]
        if not th:
            th = auto_thresholds(len(members))
        TRAITS[n] = {"name": n, "kind": t["kind"], "scope": t["scope"],
                     "stats": {k: [float(x) for x in v] for k, v in t["stats"].items()},
                     "desc": t.get("desc", ""), "thresholds": sorted(th), "members": members}
        TRAIT_ORDER[n] = i

    CREEPS.clear()
    for c in d["creeps"]:
        CREEPS[c["id"]] = {"name": c["name"], "hp": float(c["hp"]), "atk": float(c["atk"]), "as": float(c["as"]),
                           "armor": float(c["armor"]), "mr": float(c["mr"]), "rng": int(float(c["rng"])),
                           "look": c.get("look") or "slime"}
    CURRENT.clear()
    CURRENT.update(d)
    DATA_SOURCE = source


def auto_thresholds(cnt):
    if cnt >= 6:
        return [2, 4, 6]
    if cnt >= 4:
        return [2, 4]
    if cnt == 3:
        return [2, 3]
    return [max(1, cnt)]


def data_hash(d=None):
    s = json.dumps(d if d is not None else CURRENT, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]


def _read_file(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def local_override_path():
    """exe（または main.py）の隣に置いた unit_data.json"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), DATA_FILE)
    return None  # ソースから動かすときは同梱ファイル＝隣のファイルなので不要


def load_bundled():
    d = _read_file(resource_path(DATA_FILE))
    apply(d, "同梱データ")
    return d


def fetch_remote(timeout=4.0):
    """GitHubの最新データを取得（失敗したら None）"""
    global REMOTE_ERROR
    REMOTE_ERROR = ""
    try:
        req = urllib.request.Request(REMOTE_URL, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8-sig"))
    except Exception as ex:  # ネット切断・まだGitHubに置いていない など
        REMOTE_ERROR = f"GitHubの最新データを取得できませんでした（{type(ex).__name__}）"
        return None


def load_preferred(remote=None):
    """優先順位どおりに読み込む。remote に取得済みデータを渡せる"""
    LOAD_ERRORS.clear()
    p = local_override_path()
    if p and os.path.exists(p):
        try:
            apply(_read_file(p), "exeの隣の unit_data.json")
            return
        except (ValueError, KeyError, TypeError, OSError) as ex:
            LOAD_ERRORS.append(f"exeの隣の unit_data.json に問題があります：{ex}")
    if remote is not None:
        try:
            apply(remote, "GitHubの最新データ")
            return
        except (ValueError, KeyError, TypeError) as ex:
            LOAD_ERRORS.append(f"GitHubのデータに問題があります：{ex}")
    load_bundled()


# ---------------- 計算 ----------------
def ability_value(ab, cost, star):
    a = ABILITIES[ab]
    base = a["base"]
    if a["type"] in PCT_TYPES:
        return base * (1 + 0.1 * (cost - 1)) * [1.0, 1.4, 2.0][star - 1]
    m = [1.0, 1.5, 2.5][star - 1]
    if cost == 5 and star == 3:
        m = 4.0
    return base * (1 + 0.4 * (cost - 1)) * m


def ability_desc(ab, v):
    v = int(round(v))
    a = ABILITIES[ab]
    ds = f"{a.get('dur') or 0:g}"
    return {
        "strike": f"対象に{v}の魔法ダメージ",
        "stun": f"対象に{v}の魔法ダメージ＋{ds}秒スタン",
        "snipe": f"最も遠い敵に{v}＋攻撃力×1.5の物理ダメージ",
        "leap": f"最もHPの低い敵へ跳び、{v}の魔法ダメージ",
        "heal": f"HP割合が最も低い味方を{v}回復",
        "aura_heal": f"味方全員を{v}回復",
        "shield": f"自身に{v}のシールド（4秒）",
        "taunt": f"自身に{v}のシールド＋周囲2マスの敵を2秒挑発",
        "frenzy": f"4秒間 攻撃速度 +{v}%",
        "multishot": f"ランダムな敵3体に{v}＋攻撃力×0.8の物理ダメージ",
        "drain": f"対象に{v}の魔法ダメージ、与えた量の60%を回復",
        "blast": f"対象と周囲1マスの敵に{v}の魔法ダメージ",
        "chain": f"敵4体に連鎖する{v}の魔法ダメージ（徐々に減少）",
        "quake": f"周囲1マスの敵に{v}の魔法ダメージ＋{ds}秒スタン",
        "buff_team": f"5秒間 味方全員の攻撃力 +{v}%・スキル威力 +{v}",
        "meteor": f"対象の周囲2マスの敵に{v}の魔法ダメージ",
    }[a["type"]]


def trait_desc(name, tier_index):
    """tier_index: 0始まり"""
    t = TRAITS[name]
    vals = {k: f"{v[min(tier_index, len(v) - 1)]:g}" for k, v in t["stats"].items()}
    try:
        return t["desc"].format(**vals)
    except (KeyError, ValueError, IndexError):
        return t["desc"]


def compute_traits(uids):
    """盤面のユニットIDリスト -> [(特性名, 人数, 到達段階)]（同名ユニットは1体と数える）"""
    seen = set()
    counts = {}
    for u in uids:
        if u in UNITS and u not in seen:
            seen.add(u)
            for t in UNITS[u]["traits"]:
                if t in TRAITS:
                    counts[t] = counts.get(t, 0) + 1
    res = []
    for t, c in counts.items():
        tier = sum(1 for x in TRAITS[t]["thresholds"] if c >= x)
        res.append((t, c, tier))
    res.sort(key=lambda x: (-x[2], -x[1], TRAIT_ORDER[x[0]]))
    return res


def sell_value(uid, star):
    cost = UNITS[uid]["cost"]
    if star == 1:
        return cost
    return cost * (3 ** (star - 1)) - (1 if cost > 1 else 0)


# ---------------- モンスター（PvE） ----------------
def is_pve_round(r):
    return r <= 3 or r % 7 == 0


def pve_board(r):
    if r == 1:
        return [["c1", 1, 0, 2], ["c1", 1, 0, 4]]
    if r == 2:
        return [["c1", 1, 0, 2], ["c1", 1, 0, 4], ["c2", 1, 1, 3]]
    if r == 3:
        return [["c2", 1, 0, 2], ["c2", 1, 0, 4], ["c3", 1, 1, 3]]
    k = r // 7
    if k == 1:
        return [["c3", 1, 0, 1], ["c3", 1, 0, 3], ["c3", 1, 0, 5], ["c4", 1, 1, 3]]
    if k == 2:
        return [["c4", 1, 0, 2], ["c4", 1, 0, 4], ["c3", 2, 1, 1], ["c3", 2, 1, 5]]
    if k == 3:
        return [["c4", 2, 0, 3], ["c3", 2, 0, 1], ["c3", 2, 0, 5], ["c5", 1, 1, 3]]
    return [["c4", 2, 0, 2], ["c4", 2, 0, 4], ["c3", 3, 0, 0], ["c3", 3, 0, 6], ["c5", 2, 1, 3]]


def pve_reward(r):
    return 3 + r // 7


def stage_damage(r):
    return [0, 2, 3, 5, 8, 10, 13, 17][min(7, (r + 1) // 5)]


def unit_info(uid):
    return UNITS.get(uid) or CREEPS.get(uid)


def base_stats(uid, star):
    sm = STAR_MULT[star - 1]
    if uid in UNITS:
        u = UNITS[uid]
        s = u["stats"]
        return {"hp": s["hp"] * sm, "atk": s["atk"] * sm, "as": s["as"], "armor": s["armor"], "mr": s["mr"],
                "rng": s["rng"], "mana": ABILITIES[u["ability"]]["mana"]}
    cr = CREEPS[uid]
    return {"hp": cr["hp"] * sm, "atk": cr["atk"] * sm, "as": cr["as"], "armor": cr["armor"],
            "mr": cr["mr"], "rng": cr["rng"], "mana": 0}


AI_NAMES = ["AI・アカネ", "AI・バルド", "AI・シズク", "AI・ゲンブ", "AI・ミコト", "AI・ロウ", "AI・ハルカ", "AI・ソラ"]

# 起動時はまず同梱データで動けるようにしておく（最新データは main.py が裏で取得して差し替える）
load_bundled()
