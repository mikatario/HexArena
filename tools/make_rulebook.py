# -*- coding: utf-8 -*-
"""unit_data.json からルールブック（docs/rulebook.html）を作る（開発用）

  python tools/make_rulebook.py [出力先]
数値やユニット一覧はデータから作るので、データを変えたら作り直せば最新になります。
"""
import html
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import data  # noqa: E402

E = html.escape
COST = {1: "#8a8a99", 2: "#2f9e5d", 3: "#2f6fd0", 4: "#9a4fd0", 5: "#c79212"}
SCOPE = {"self": "その特性のユニット", "team": "味方全員", "enemy": "敵全員"}
KEYS = [("1〜5", "ショップのユニットを買う"), ("D / R", "リロール（2G）"), ("F", "経験値を買う（4G）"),
        ("E", "マウスを乗せた・選んだユニットを売る"), ("Q", "コントローラーのスキル"), ("L", "ショップを固定"),
        ("Ctrl+1〜6", "アイテムを使う"), ("U", "選んだアイテムを使う"), ("Space", "準備OK"),
        ("Tab", "ほかのプレイヤーの盤面を順番に見る"), ("← →", "カメラを回す"), ("↑ ↓ / + −", "カメラを寄る・引く"),
        ("Home / C", "カメラを元に戻す"), ("M", "音をすべて消す／戻す"), ("F11", "全画面の切り替え"),
        ("F1 / H", "キー操作の一覧"), ("Esc", "情報欄を閉じる／メニュー")]


def chip(cost):
    return f'<span class="cost" style="--c:{COST.get(cost, "#888")}">{cost}</span>'


def section(sid, num, title, body):
    return f'<section id="{sid}"><h2><span class="no">{num}</span>{E(title)}</h2>{body}</section>'


def build():
    st = data.CURRENT["settings"]
    dr = data.ITEM_DROPS
    parts = []
    parts.append(section("flow", "01", "ゲームの目的と流れ", f"""
<p class="lead">8人で戦い、<strong>最後の1人まで生き残ったら優勝</strong>です。空いた席にはAIが入ります。ひとりでも、部屋コードでみんなとも遊べます。</p>
<ol class="flow">
<li><b>コントローラー選択</b><span>あなたの分身を8人から1人選ぶ（{int(data.SETTINGS.get('select_time', 25))}秒）</span></li>
<li><b>準備フェーズ</b><span>ユニットを買って盤面に並べる（30秒・初回20秒）</span></li>
<li><b>戦闘フェーズ</b><span>並べたユニットが自動で戦う（最長35秒）</span></li>
<li><b>結果</b><span>負けると体力が減る。体力0で脱落</span></li>
</ol>
<p>準備〜結果をまとめて<strong>1ラウンド</strong>と呼び、くり返します。体力は最初 {data.START_HP} です。</p>
<h3>ラウンドの種類</h3>
<table><tr><th>印</th><th>種類</th><th>いつ</th><th>内容</th></tr>
<tr><td><span class="tag pve">怪</span></td><td>モンスター戦</td><td>ラウンド1〜3、7の倍数のラウンド</td><td>勝つとゴールドとアイテム</td></tr>
<tr><td><span class="tag pvp">対</span></td><td>対人戦</td><td>それ以外</td><td>ほかのプレイヤーの盤面と戦う（奇数のときは誰かの「分身」と）</td></tr></table>
<p class="note">ゲーム画面の上にある帯で、この先のラウンドの予定と「今どこか」が見られます。</p>"""))

    odds = "".join(f"<tr><td>Lv{lv}</td>" + "".join(f"<td class='n'>{v:g}%</td>" for v in data.SHOP_ODDS[lv]) +
                   (f"<td class='n'>{data.XP_TO_NEXT[lv]}</td>" if lv in data.XP_TO_NEXT else "<td class='n'>—</td>") + "</tr>"
                   for lv in range(1, data.MAX_LEVEL + 1))
    parts.append(section("plan", "02", "準備フェーズ", f"""
<h3>ショップ</h3>
<ul><li>画面下の5枚のカードからユニットを買います。<b>コスト＝値段</b>です。</li>
<li><b>リロール（2G）</b>：カードを引き直します。<b>ショップを固定</b>すると次のラウンドも同じカードが残ります。</li>
<li>レベルが上がるほど、高コストのユニットが出やすくなります。</li></ul>
<h3>配置</h3>
<ul><li>買ったユニットはベンチ（手前の9マス）に入ります。ドラッグ（タッチなら押したまま動かす）で盤面の手前半分に置きます。</li>
<li>盤面に置ける数は<b>レベルと同じ</b>です。置かなかった分は戦闘前に自動で置かれます。</li></ul>
<h3>強化とレベル</h3>
<ul><li>同じユニット3体で<b>★2</b>、★2を3体で<b>★3</b>に自動で合体します。★ごとにHP・攻撃力が {'・'.join(f'×{m:g}' for m in data.STAR_MULT)}。</li>
<li>経験値は4Gで4買えます。毎ラウンド2ずつ自動でもたまります。</li></ul>
<div class="scroll"><table class="odds"><tr><th>レベル</th>{''.join(f'<th>{chip(c)}</th>' for c in range(1, 6))}<th>次まで</th></tr>{odds}</table></div>"""))

    parts.append(section("battle", "03", "戦闘", """
<ul><li>戦闘は自動です。ユニットは近くの敵に近づいて攻撃します。<b>射程</b>1なら隣、4なら4マス先まで届きます。</li>
<li>攻撃したり受けたりすると<b>マナ</b>がたまり、満タンでスキルを使います。</li>
<li><b>物理防御</b>は通常攻撃を、<b>魔法防御</b>はスキルなどの魔法ダメージを減らします。</li></ul>
<table><tr><th>結果</th><th>どうなる</th></tr>
<tr><td>勝ち</td><td>+1G</td></tr>
<tr><td>負け</td><td>体力が減る（ステージのダメージ＋生き残った敵の★の合計）</td></tr>
<tr><td>引き分け</td><td>35秒で決着がつかない。両方の体力が少し減る</td></tr></table>"""))

    rows = []
    for kind in ("属性", "職業"):
        for t in (x for x in data.TRAITS.values() if x["kind"] == kind):
            eff = "<br>".join(f"<b>{n}体</b> {E(data.trait_desc(t['name'], i))}" for i, n in enumerate(t["thresholds"]))
            mem = "・".join(E(data.UNITS[u]["name"]) for u in t["members"])
            rows.append(f"<tr><td class='nm'>{E(t['name'])}<small>{kind}</small></td><td>{SCOPE.get(t['scope'], '')}</td>"
                        f"<td>{eff}</td><td class='mem'>{mem}</td></tr>")
    parts.append(section("synergy", "04", "シナジー（属性・職業）", f"""
<p>ユニットは「属性」1つと「職業」1〜2つを持っています。同じ特性のユニットを<b>盤面に</b>そろえると、ボーナスが発動します（同じ名前のユニットは1体と数えます）。</p>
<div class="scroll"><table class="syn"><tr><th>特性</th><th>対象</th><th>効果</th><th>持っているユニット</th></tr>{''.join(rows)}</table></div>"""))

    cards = []
    for cid, c in list(data.CONTROLLERS.items())[:8]:
        cards.append(f"""<div class="card" style="--c:{E(c['color'])}"><div class="ch"><b>{E(c['name'])}</b><small>{E(c['title'])}</small></div>
<div class="sk">{E(c['skill_name'])}</div><p>{E(data.controller_desc(cid))}</p>
<div class="meta"><span>コスト {E(data.controller_cost_text(cid))}</span><span>ラウンド{c['min_round']}から</span></div></div>""")
    parts.append(section("controller", "05", "コントローラー", f"""
<p>ゲーム開始時に1人選ぶ、あなたの分身です。<b>準備フェーズ中に1ゲーム1回だけ</b>スキルを使えます（Qキー、または左下のスキルボタン）。</p>
<div class="cards">{''.join(cards)}</div>"""))

    tot = sum(max(0.0, it["weight"]) for it in data.ITEMS.values()) or 1
    irows = "".join(f"<tr><td><span class='icon' style='--c:{E(it['color'])}'>{E(it['icon'])}</span> {E(it['name'])}</td>"
                    f"<td>{E(data.item_desc(iid))}</td><td class='n'>{it['weight'] / tot * 100:.0f}%</td></tr>"
                    for iid, it in data.ITEMS.items())
    parts.append(section("item", "06", "アイテム", f"""
<p>使うとその場で効果が出る<b>消耗品</b>です。準備フェーズ中に、左の「アイテム」欄から使います（押して詳しく→もう一度押すか「使う」ボタン、またはCtrl+数字）。</p>
<h3>手に入れ方</h3>
<ul><li>モンスター戦に勝つ：{int(dr.get('pve_win', 1))}個（{int(dr.get('pve_bonus_chance', 0))}%でもう1個）</li>
<li>{int(dr.get('streak_every', 3))}連勝・{int(dr.get('streak_every', 3))}連敗するごとに1個</li>
<li>負けたとき {int(dr.get('loss_chance', 0))}% で1個</li>
<li>持てるのは最大 {int(dr.get('max_items', 6))}個。あふれた分は {int(dr.get('full_gold', 2))}G に換わります。</li></ul>
<table><tr><th>アイテム</th><th>効果</th><th>出る確率</th></tr>{irows}</table>"""))

    parts.append(section("gold", "07", "ゴールド（お金）", """
<table><tr><th>もらえるもの</th><th>内容</th></tr>
<tr><td>基本</td><td>ラウンド1は2G、2は3G、3は4G、それ以降は5G</td></tr>
<tr><td>利子</td><td>持っているゴールド10Gごとに+1G（最大+5G）</td></tr>
<tr><td>連勝・連敗</td><td>2〜3連続で+1G、4連続で+2G、5連続以上で+3G</td></tr>
<tr><td>勝利</td><td>対人戦で+1G、モンスター戦はラウンドに応じて多め</td></tr></table>
<p><b>売却</b>：ユニットをショップ欄へドラッグ、Eキー、または情報欄の「売却する」。★1はコストと同じ値段、★2・★3は高く売れます。</p>
<p class="note">コツ：序盤は利子のために貯め、同じユニットを集めて★2を作るのが近道です。</p>"""))

    keys = "".join(f"<tr><td class='key'>{E(k)}</td><td>{E(d)}</td></tr>" for k, d in KEYS)
    parts.append(section("control", "08", "操作方法", f"""
<table><tr><th>やりたいこと</th><th>マウス</th><th>タッチ</th></tr>
<tr><td>選ぶ・詳しく見る</td><td>クリック（左上に情報が出る）</td><td>タップ</td></tr>
<tr><td>買う</td><td>ショップのカードをクリック</td><td>カードをタップ</td></tr>
<tr><td>ユニットを動かす</td><td>ドラッグ</td><td>押したまま動かす</td></tr>
<tr><td>カメラ</td><td>右ドラッグで回す／ホイールで寄る</td><td>右下の ◀ ▶ ＋ － 元 ボタン</td></tr>
<tr><td>設定・全画面・音</td><td colspan="2">画面右上の「メニュー」</td></tr></table>
<h3>キーボードショートカット</h3>
<table class="keys">{keys}</table>"""))

    urows = []
    for uid, u in sorted(data.UNITS.items(), key=lambda x: (x[1]["cost"], x[0])):
        sk = data.ability_desc(u["ability"], data.ability_value(u["ability"], u["cost"], 1))
        s = u["stats"]
        urows.append(f"<tr><td>{chip(u['cost'])} {E(u['name'])}</td><td>{E('・'.join(u['traits']))}</td>"
                     f"<td>{E(data.ARCH_NAME.get(u['arch'], ''))}</td><td class='n'>{s['hp']:g}</td><td class='n'>{s['atk']:g}</td>"
                     f"<td class='n'>{s['rng']}</td><td><b>{E(u['ability_name'])}</b><br><small>{E(sk)}</small></td></tr>")
    parts.append(section("units", "09", f"ユニット一覧（{len(data.UNITS)}種・★1の値）", f"""
<div class="scroll"><table class="units"><tr><th>ユニット</th><th>特性</th><th>タイプ</th><th>HP</th><th>攻撃</th><th>射程</th><th>スキル</th></tr>{''.join(urows)}</table></div>"""))

    toc = "".join(f'<a href="#{sid}">{t}</a>' for sid, t in (("flow", "目的と流れ"), ("plan", "準備"), ("battle", "戦闘"),
                                                              ("synergy", "シナジー"), ("controller", "コントローラー"),
                                                              ("item", "アイテム"), ("gold", "ゴールド"), ("control", "操作"),
                                                              ("units", "ユニット一覧")))
    return TEMPLATE.replace("__TOC__", toc).replace("__BODY__", "".join(parts)).replace(
        "__VER__", E(f"ver {data.VERSION}／データ：{data.CURRENT.get('data_version', '')}"))


TEMPLATE = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>ヘックス・アリーナ ルールブック</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700&family=Dela+Gothic+One&family=JetBrains+Mono:wght@500&display=swap">
<style>
:root{--bg:#eef1f6;--paper:#ffffff;--ink:#1a2030;--sub:#5b6580;--line:#d7dde8;--accent:#9a6b12;--band:#172033;--band-ink:#f1f3f8;--pve:#b4553f;--pvp:#35508a;
--font:"BIZ UDPGothic","Hiragino Kaku Gothic ProN","Yu Gothic UI","Meiryo",sans-serif;--display:"Dela Gothic One","BIZ UDPGothic",sans-serif;--mono:"JetBrains Mono","Consolas",monospace;}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#0f131b;--paper:#171c27;--ink:#e6e9f1;--sub:#99a2b9;--line:#2b3345;--accent:#e8b54d;--band:#0b0f17;}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#0f131b;--paper:#171c27;--ink:#e6e9f1;--sub:#99a2b9;--line:#2b3345;--accent:#e8b54d;--band:#0b0f17;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);font-size:15px;line-height:1.75;padding-inline:16px;padding-block:0 60px}
header.hero{background:var(--band);color:var(--band-ink);margin-inline:-16px;padding:40px 16px 34px}
.hero .in,.wrap{max-width:1040px;margin:0 auto}
.hero h1{font-family:var(--display);font-weight:400;font-size:clamp(28px,5vw,44px);margin:0;letter-spacing:.03em;text-wrap:balance}
.hero p{margin:8px 0 0;color:#b9c1d6}
.hero .ver{font-family:var(--mono);font-size:12px;color:#8d97b1;margin-top:14px}
nav.toc{position:sticky;top:env(safe-area-inset-top,0px);z-index:3;background:var(--bg);border-bottom:1px solid var(--line);margin-inline:-16px;padding:8px 16px;display:flex;gap:6px;flex-wrap:wrap;justify-content:center}
nav.toc a{color:var(--ink);text-decoration:none;font-size:13px;padding:4px 10px;border-radius:99px;border:1px solid var(--line);background:var(--paper)}
nav.toc a:hover{border-color:var(--accent);color:var(--accent)}
section{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:22px 24px;margin-top:18px}
h2{font-size:22px;margin:0 0 12px;display:flex;align-items:baseline;gap:12px;text-wrap:balance}
h2 .no{font-family:var(--mono);color:var(--accent);font-size:15px}
h3{font-size:16px;margin:20px 0 6px}
p,li{max-width:70ch}
.lead{font-size:16px}
.note{color:var(--sub);font-size:13.5px}
ol.flow{list-style:none;padding:0;margin:14px 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:10px;counter-reset:f}
ol.flow li{border:1px solid var(--line);border-radius:10px;padding:10px 12px;counter-increment:f;display:flex;flex-direction:column}
ol.flow li b::before{content:counter(f) ". ";color:var(--accent);font-family:var(--mono)}
ol.flow li span{font-size:13px;color:var(--sub)}
table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{font-size:12.5px;color:var(--sub);letter-spacing:.03em;background:var(--bg)}
td.n{font-family:var(--mono);text-align:right;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}
.cost{display:inline-grid;place-items:center;min-width:22px;height:22px;border-radius:6px;background:var(--c);color:#fff;font-family:var(--mono);font-size:12px;font-weight:600}
.tag{display:inline-grid;place-items:center;width:28px;height:24px;border-radius:6px;color:#fff;font-weight:700}
.tag.pve{background:var(--pve)}.tag.pvp{background:var(--pvp)}
.syn td.nm{font-weight:700;white-space:nowrap}.syn td.nm small{display:block;color:var(--sub);font-weight:400}
.syn td.mem{font-size:12.5px;color:var(--sub);min-width:150px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,230px),1fr));gap:12px;margin-top:12px}
.card{border:1px solid var(--line);border-top:5px solid var(--c);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}
.card .ch b{font-size:17px}.card .ch small{display:block;color:var(--sub);font-size:12px}
.card .sk{color:var(--accent);font-weight:700}
.card p{margin:0;font-size:13.5px}
.card .meta{display:flex;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--sub);margin-top:auto;padding-top:6px}
.icon{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:7px;background:var(--c);color:#fff;font-weight:700;font-size:13px}
.keys td.key{font-family:var(--mono);white-space:nowrap;color:var(--accent);width:150px}
.units td small{color:var(--sub)}
@media (max-width:640px){section{padding:16px}}
</style>
<header class="hero"><div class="in"><h1>ヘックス・アリーナ ルールブック</h1><p>8人で戦う3Dオートバトル。ユニットを集めて並べ、最後の1人を目指そう。</p><div class="ver">__VER__</div></div></header>
<nav class="toc">__TOC__</nav>
<main class="wrap">__BODY__</main>
"""

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "rulebook.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", out)
