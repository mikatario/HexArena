# -*- coding: utf-8 -*-
"""ゲームデータ（ユニット60種・シナジー36種・経済テーブル）"""

VERSION = "1.0.0"
GAME_TITLE = "ヘックス・アリーナ"

BOARD_ROWS, BOARD_COLS = 4, 7
BENCH_SIZE = 9
SHOP_SIZE = 5
MAX_LEVEL = 10
START_HP = 100
POOL_SIZE = {1: 29, 2: 22, 3: 18, 4: 12, 5: 10}

# レベルごとのショップ出現率（1〜5コスト, %）
SHOP_ODDS = {
    1: [100, 0, 0, 0, 0],
    2: [100, 0, 0, 0, 0],
    3: [75, 25, 0, 0, 0],
    4: [55, 30, 15, 0, 0],
    5: [45, 33, 20, 2, 0],
    6: [30, 40, 25, 5, 0],
    7: [19, 30, 35, 15, 1],
    8: [18, 25, 32, 22, 3],
    9: [10, 20, 25, 35, 10],
    10: [5, 10, 20, 40, 25],
}
XP_TO_NEXT = {1: 2, 2: 2, 3: 6, 4: 10, 5: 20, 6: 36, 7: 48, 8: 72, 9: 84}
STAR_MULT = [1.0, 1.8, 3.24]
COST_COLORS = {1: (150, 150, 160), 2: (60, 175, 95), 3: (60, 130, 230), 4: (175, 85, 225), 5: (240, 185, 40), 0: (150, 95, 70)}

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
ROW_PREF = {"tank": [0, 1, 2, 3], "bruiser": [0, 1, 2, 3], "assassin": [3, 2, 1, 0],
            "lancer": [1, 0, 2, 3], "sniper": [3, 2, 1, 0], "caster": [3, 2, 1, 0]}
COL_PREF = [3, 2, 4, 1, 5, 0, 6]

CLASS_ARCH = {
    "騎士": "tank", "守護者": "tank", "重装兵": "tank", "拳闘士": "tank",
    "戦士": "bruiser", "狂戦士": "bruiser", "決闘者": "bruiser", "君主": "bruiser",
    "槍兵": "lancer", "暗殺者": "assassin", "忍者": "assassin", "盗賊": "assassin",
    "狙撃手": "sniper", "魔術師": "caster", "呪術師": "caster", "聖職者": "caster",
    "吟遊詩人": "caster", "錬金術師": "caster",
}

# ---------------- スキル ----------------
ABILITIES = {
    "strike":    {"name": "一撃",     "mana": 50, "base": 180},
    "stun":      {"name": "封じ",     "mana": 70, "base": 130, "dur": 1.5},
    "snipe":     {"name": "狙い撃ち", "mana": 60, "base": 120},
    "leap":      {"name": "影跳び",   "mana": 50, "base": 160},
    "heal":      {"name": "癒やし",   "mana": 60, "base": 220},
    "aura_heal": {"name": "祝福",     "mana": 80, "base": 90},
    "shield":    {"name": "守りの構え", "mana": 60, "base": 260},
    "taunt":     {"name": "挑発",     "mana": 70, "base": 200},
    "frenzy":    {"name": "連撃",     "mana": 50, "base": 50},
    "multishot": {"name": "乱れ撃ち", "mana": 60, "base": 80},
    "drain":     {"name": "吸収撃",   "mana": 60, "base": 170},
    "blast":     {"name": "爆裂",     "mana": 70, "base": 140},
    "chain":     {"name": "連鎖",     "mana": 70, "base": 150},
    "quake":     {"name": "震撃",     "mana": 80, "base": 110, "dur": 1.0},
    "buff_team": {"name": "鼓舞",     "mana": 80, "base": 25},
    "meteor":    {"name": "大災",     "mana": 90, "base": 220},
}
PCT_ABILITIES = {"frenzy", "buff_team"}


def ability_value(ab, cost, star):
    base = ABILITIES[ab]["base"]
    if ab in PCT_ABILITIES:
        return base * (1 + 0.1 * (cost - 1)) * [1.0, 1.4, 2.0][star - 1]
    m = [1.0, 1.5, 2.5][star - 1]
    if cost == 5 and star == 3:
        m = 4.0
    return base * (1 + 0.4 * (cost - 1)) * m


def ability_desc(ab, v):
    v = int(round(v))
    return {
        "strike": f"対象に{v}の魔法ダメージ",
        "stun": f"対象に{v}の魔法ダメージ＋1.5秒スタン",
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
        "quake": f"周囲1マスの敵に{v}の魔法ダメージ＋1秒スタン",
        "buff_team": f"5秒間 味方全員の攻撃力 +{v}%・スキル威力 +{v}",
        "meteor": f"対象の周囲2マスの敵に{v}の魔法ダメージ",
    }[ab]


# ---------------- シナジー（36種） ----------------
# (名前, 種別, 対象, 効果, 説明)  対象: self=その特性を持つユニット / team=味方全員 / enemy=敵全員
_TRAIT_LIST = [
    # 属性（18）
    ("炎", "属性", "self", {"burn": [1.0, 2.0, 3.5]}, "攻撃した敵を3秒やけど（毎秒 最大HPの{burn}%）"),
    ("氷", "属性", "self", {"chill": [20, 35, 50]}, "攻撃した敵の攻撃速度を2秒間 -{chill}%"),
    ("雷", "属性", "self", {"proc": [60, 120, 220]}, "攻撃時25%で雷撃：敵2体に{proc}の魔法ダメージ"),
    ("森", "属性", "self", {"regen_pct": [1.0, 2.0, 3.5]}, "毎秒 最大HPの{regen_pct}%回復"),
    ("闇", "属性", "self", {"dmg_amp": [15, 30, 50]}, "与えるダメージ +{dmg_amp}%"),
    ("光", "属性", "team", {"omnivamp": [8, 15, 25]}, "味方全員が与ダメージの{omnivamp}%回復"),
    ("鋼", "属性", "self", {"dmg_red": [15, 25, 40]}, "受けるダメージ -{dmg_red}%"),
    ("砂", "属性", "self", {"dodge": [15, 25, 40]}, "{dodge}%の確率で通常攻撃を回避"),
    ("海", "属性", "team", {"mana_regen": [2, 4, 7]}, "味方全員が毎秒マナを{mana_regen}回復"),
    ("獣", "属性", "team", {"atk_pct": [10, 20, 35]}, "味方全員の攻撃力 +{atk_pct}%"),
    ("毒", "属性", "self", {"poison": [20, 40, 70]}, "攻撃した敵に3秒の毒（毎秒{poison}ダメージ）"),
    ("風", "属性", "self", {"as_pct": [20, 40, 70]}, "攻撃速度 +{as_pct}%"),
    ("岩", "属性", "self", {"armor": [30, 60, 100]}, "物理防御 +{armor}"),
    ("桜", "属性", "team", {"hp_flat": [80, 160, 280]}, "味方全員の最大HP +{hp_flat}"),
    ("竜", "属性", "self", {"hp_pct": [25, 50, 80], "mr": [20, 40, 70]}, "最大HP +{hp_pct}%・魔法防御 +{mr}"),
    ("機械", "属性", "self", {"shield_pct": [20, 35, 55]}, "開始時に最大HPの{shield_pct}%のシールド"),
    ("亡霊", "属性", "self", {"revive": [25, 40, 60]}, "一度だけHP{revive}%で復活"),
    ("星", "属性", "self", {"ap": [20, 40, 70]}, "スキル威力 +{ap}"),
    # 職業（18）
    ("戦士", "職業", "self", {"atk_pct": [15, 30, 50]}, "攻撃力 +{atk_pct}%"),
    ("騎士", "職業", "self", {"block": [12, 22, 35]}, "受ける通常攻撃ダメージを{block}軽減"),
    ("狙撃手", "職業", "self", {"crit": [15, 30, 50]}, "会心率 +{crit}%"),
    ("魔術師", "職業", "self", {"ap": [25, 50, 85]}, "スキル威力 +{ap}"),
    ("暗殺者", "職業", "self", {"leap": [1, 1, 1], "crit": [10, 20, 35], "crit_dmg": [20, 40, 70]},
     "開始時に敵の後列へ跳ぶ。会心率 +{crit}%・会心ダメージ +{crit_dmg}%"),
    ("守護者", "職業", "team", {"shield_flat": [100, 200, 350]}, "味方全員が開始時に{shield_flat}のシールド"),
    ("聖職者", "職業", "team", {"regen_flat": [8, 16, 30]}, "味方全員が毎秒{regen_flat}回復"),
    ("狂戦士", "職業", "self", {"splash": [25, 45, 70]}, "通常攻撃が周囲の敵にも{splash}%のダメージ"),
    ("呪術師", "職業", "enemy", {"armor": [-15, -30, -50], "mr": [-15, -30, -50]}, "敵全員の物理・魔法防御 {armor}"),
    ("槍兵", "職業", "self", {"armor_pen": [25, 45, 70]}, "敵の物理防御を{armor_pen}%無視"),
    ("拳闘士", "職業", "self", {"hp_pct": [30, 60, 100]}, "最大HP +{hp_pct}%"),
    ("決闘者", "職業", "self", {"stack_as": [4, 7, 11]}, "攻撃するたび攻撃速度 +{stack_as}%（最大8回）"),
    ("吟遊詩人", "職業", "team", {"mana_start": [15, 30, 50]}, "味方全員の開始時マナ +{mana_start}"),
    ("盗賊", "職業", "self", {"gold": [1, 2, 3], "dodge": [10, 10, 10]}, "戦闘後に{gold}ゴールド獲得・回避 +{dodge}%"),
    ("重装兵", "職業", "self", {"thorns": [15, 30, 50]}, "受けた通常攻撃の{thorns}%を反射"),
    ("忍者", "職業", "self", {"atk_pct": [18, 35, 60], "ap": [18, 35, 60]}, "攻撃力 +{atk_pct}%・スキル威力 +{ap}"),
    ("錬金術師", "職業", "self", {"mana_on_hit": [5, 10, 18]}, "通常攻撃で得るマナ +{mana_on_hit}"),
    ("君主", "職業", "team", {"atk_pct": [5, 10, 18], "ap": [5, 10, 18], "hp_pct": [5, 10, 18]},
     "味方全員の攻撃力・スキル威力・最大HP +{hp_pct}%"),
]

# ---------------- ユニット（60種） ----------------
# (名前, コスト, 属性, [職業], スキル)
_UNIT_LIST = [
    ("ホムラ", 1, "炎", ["戦士"], "strike"),
    ("ユキメ", 1, "氷", ["魔術師"], "stun"),
    ("ライガ", 1, "雷", ["狙撃手"], "snipe"),
    ("モリオ", 1, "森", ["騎士"], "shield"),
    ("カゲロウ", 1, "闇", ["暗殺者"], "leap"),
    ("ヒカリ", 1, "光", ["聖職者"], "heal"),
    ("テツ", 1, "鋼", ["重装兵"], "taunt"),
    ("サジン", 1, "砂", ["盗賊"], "strike"),
    ("ナミ", 1, "海", ["吟遊詩人"], "aura_heal"),
    ("キバ", 1, "獣", ["拳闘士"], "drain"),
    ("ドクロ", 1, "毒", ["呪術師", "錬金術師"], "blast"),
    ("ハヤテ", 1, "風", ["決闘者", "忍者"], "frenzy"),
    ("ガンテツ", 1, "岩", ["守護者"], "shield"),
    ("サクラ", 1, "桜", ["狙撃手", "吟遊詩人"], "multishot"),

    ("エンジ", 2, "炎", ["狂戦士", "戦士"], "drain"),
    ("ツララ", 2, "氷", ["守護者"], "taunt"),
    ("イナズマ", 2, "雷", ["忍者"], "leap"),
    ("コダマ", 2, "森", ["聖職者"], "aura_heal"),
    ("ヨミ", 2, "亡霊", ["呪術師"], "chain"),
    ("ルクス", 2, "光", ["騎士", "槍兵"], "shield"),
    ("ハガネ", 2, "鋼", ["槍兵"], "strike"),
    ("スナオ", 2, "砂", ["暗殺者", "盗賊"], "leap"),
    ("カイリ", 2, "海", ["狙撃手"], "snipe"),
    ("ギア", 2, "機械", ["重装兵"], "taunt"),
    ("ホシミ", 2, "星", ["魔術師"], "blast"),
    ("ウルフ", 2, "獣", ["戦士"], "frenzy"),
    ("ミドリ", 2, "毒", ["錬金術師"], "blast"),

    ("カグラ", 3, "炎", ["魔術師"], "blast"),
    ("フブキ", 3, "氷", ["狙撃手"], "multishot"),
    ("ゴロウ", 3, "雷", ["拳闘士", "重装兵"], "quake"),
    ("ツバキ", 3, "森", ["決闘者"], "frenzy"),
    ("クロウ", 3, "闇", ["忍者"], "leap"),
    ("セラ", 3, "光", ["吟遊詩人"], "buff_team"),
    ("イワオ", 3, "岩", ["騎士"], "quake"),
    ("タツミ", 3, "竜", ["戦士", "拳闘士"], "drain"),
    ("メカノ", 3, "機械", ["錬金術師"], "chain"),
    ("レイス", 3, "亡霊", ["暗殺者"], "leap"),
    ("ミナト", 3, "海", ["呪術師"], "stun"),
    ("シエル", 3, "風", ["狙撃手"], "snipe"),
    ("ソウマ", 3, "桜", ["槍兵"], "strike"),

    ("イグニス", 4, "炎", ["狂戦士", "戦士"], "quake"),
    ("セツナ", 4, "氷", ["魔術師"], "blast"),
    ("イカヅチ", 4, "雷", ["魔術師"], "chain"),
    ("オウカ", 4, "桜", ["聖職者"], "aura_heal"),
    ("ヤミヒメ", 4, "闇", ["呪術師"], "meteor"),
    ("ダイチ", 4, "岩", ["守護者", "重装兵"], "taunt"),
    ("ドラグ", 4, "竜", ["騎士", "拳闘士"], "quake"),
    ("マキナ", 4, "機械", ["狙撃手", "錬金術師"], "multishot"),
    ("カスミ", 4, "亡霊", ["忍者"], "leap"),
    ("シオン", 4, "星", ["決闘者"], "frenzy"),
    ("ジャドク", 4, "毒", ["暗殺者", "盗賊"], "leap"),

    ("テンショウ", 5, "光", ["君主"], "buff_team"),
    ("ワダツミ", 5, "海", ["君主"], "meteor"),
    ("ガリュウ", 5, "竜", ["魔術師", "君主"], "meteor"),
    ("ジンテツ", 5, "鋼", ["守護者"], "taunt"),
    ("ミカボシ", 5, "星", ["狙撃手"], "snipe"),
    ("シャムラ", 5, "砂", ["暗殺者", "決闘者"], "leap"),
    ("コガラシ", 5, "風", ["吟遊詩人"], "chain"),
    ("ヤマタ", 5, "獣", ["狂戦士", "拳闘士"], "quake"),
    ("オボロ", 5, "亡霊", ["聖職者"], "aura_heal"),
]

UNITS = {}
UNIT_IDS_BY_COST = {c: [] for c in range(1, 6)}
for _i, (_n, _c, _o, _cls, _ab) in enumerate(_UNIT_LIST):
    _uid = "u%02d" % (_i + 1)
    UNITS[_uid] = {"id": _uid, "name": _n, "cost": _c, "traits": [_o] + _cls,
                   "arch": CLASS_ARCH[_cls[0]], "ability": _ab,
                   "ability_name": _o + "の" + ABILITIES[_ab]["name"]}
    UNIT_IDS_BY_COST[_c].append(_uid)

TRAITS = {}
TRAIT_ORDER = {}
for _i, (_n, _k, _s, _st, _d) in enumerate(_TRAIT_LIST):
    _members = [u for u in UNITS if _n in UNITS[u]["traits"]]
    _cnt = len(_members)
    if _cnt >= 6:
        _th = [2, 4, 6]
    elif _cnt >= 4:
        _th = [2, 4]
    elif _cnt == 3:
        _th = [2, 3]
    else:
        _th = [max(1, _cnt)]
    TRAITS[_n] = {"name": _n, "kind": _k, "scope": _s, "stats": _st, "desc": _d,
                  "thresholds": _th, "members": _members}
    TRAIT_ORDER[_n] = _i


def trait_desc(name, tier_index):
    """tier_index: 0始まり"""
    t = TRAITS[name]
    vals = {k: v[min(tier_index, len(v) - 1)] for k, v in t["stats"].items()}
    return t["desc"].format(**vals)


def compute_traits(uids):
    """盤面のユニットIDリスト -> [(特性名, 人数, 到達段階)]（同名ユニットは1体と数える）"""
    seen = set()
    counts = {}
    for u in uids:
        if u in UNITS and u not in seen:
            seen.add(u)
            for t in UNITS[u]["traits"]:
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
CREEPS = {
    "c1": {"name": "スライム", "hp": 380, "atk": 28, "as": 0.6, "armor": 10, "mr": 10, "rng": 1},
    "c2": {"name": "ゴブリン", "hp": 480, "atk": 36, "as": 0.7, "armor": 15, "mr": 10, "rng": 1},
    "c3": {"name": "オオカミ", "hp": 620, "atk": 48, "as": 0.85, "armor": 20, "mr": 15, "rng": 1},
    "c4": {"name": "ゴーレム", "hp": 1600, "atk": 70, "as": 0.55, "armor": 60, "mr": 40, "rng": 1},
    "c5": {"name": "ドラゴン", "hp": 3000, "atk": 110, "as": 0.7, "armor": 50, "mr": 50, "rng": 2},
}


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
        a = ARCH[u["arch"]]
        c = u["cost"]
        return {"hp": a["hp"] * (1 + 0.2 * (c - 1)) * sm, "atk": a["atk"] * (1 + 0.15 * (c - 1)) * sm,
                "as": a["as"], "armor": a["armor"], "mr": a["mr"], "rng": a["rng"],
                "mana": ABILITIES[u["ability"]]["mana"]}
    cr = CREEPS[uid]
    return {"hp": cr["hp"] * sm, "atk": cr["atk"] * sm, "as": cr["as"], "armor": cr["armor"],
            "mr": cr["mr"], "rng": cr["rng"], "mana": 0}


AI_NAMES = ["AI・アカネ", "AI・バルド", "AI・シズク", "AI・ゲンブ", "AI・ミコト", "AI・ロウ", "AI・ハルカ", "AI・ソラ"]
