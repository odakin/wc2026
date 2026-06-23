#!/usr/bin/env python3
"""wc2026 静的サイト generator。

data/results.yaml (結果 SoT) + data/articles.yaml (FIFA日本語レポート link) から
docs/{index,standings,links}.html を生成する。 stdlib + PyYAML のみ、 共通の明るい
テーマ + ナビ付き 3 ページ。

  python3 build.py        # docs/ を再生成

順位は FIFA 2026 大会規定 (直接対決 → 全試合得失差 → 全試合総得点 → フェアプレー点 →
FIFA ランク、 抽選廃止) で決定論的に算出。 head-to-head は同点サブグループ内で再帰計算。
"""
from pathlib import Path
from collections import defaultdict
import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
GROUP_ORDER = list("ABCDEFGHIJKL")
CIRC = {1: "①", 2: "②", 3: "③", 4: "④"}
JP_GROUP = "F"

SHORT = {
    "南アフリカ": "南ア", "ボスニア・ヘルツェゴビナ": "ボスニア", "アメリカ合衆国": "米国",
    "オーストラリア": "豪州", "コートジボワール": "コートジ", "ニュージーランド": "NZ",
    "サウジアラビア": "サウジ", "カーボベルデ": "CV", "アルゼンチン": "アルゼン",
    "オーストリア": "オースト", "アルジェリア": "アルジェ", "ウズベキスタン": "ウズベク",
    "コンゴ民主共和国": "コンゴ", "スコットランド": "スコット", "イングランド": "英国",
    "スウェーデン": "スウェ", "チュニジア": "チュニ", "ウルグアイ": "ウルグ",
    "ノルウェー": "ノルウェ", "ポルトガル": "ポルト", "コロンビア": "コロン",
    "クロアチア": "クロア", "エクアドル": "エクア", "キュラソー": "キュラ", "パラグアイ": "パラグ",
}
ISO = {
    "メキシコ": "MX", "南アフリカ": "ZA", "韓国": "KR", "チェコ": "CZ",
    "カナダ": "CA", "スイス": "CH", "ボスニア・ヘルツェゴビナ": "BA", "カタール": "QA",
    "ブラジル": "BR", "モロッコ": "MA", "ハイチ": "HT",
    "アメリカ合衆国": "US", "オーストラリア": "AU", "パラグアイ": "PY", "トルコ": "TR",
    "ドイツ": "DE", "コートジボワール": "CI", "エクアドル": "EC", "キュラソー": "CW",
    "日本": "JP", "オランダ": "NL", "スウェーデン": "SE", "チュニジア": "TN",
    "ベルギー": "BE", "イラン": "IR", "ニュージーランド": "NZ", "エジプト": "EG",
    "スペイン": "ES", "ウルグアイ": "UY", "サウジアラビア": "SA", "カーボベルデ": "CV",
    "フランス": "FR", "ノルウェー": "NO", "セネガル": "SN", "イラク": "IQ",
    "アルゼンチン": "AR", "オーストリア": "AT", "ヨルダン": "JO", "アルジェリア": "DZ",
    "ポルトガル": "PT", "コロンビア": "CO", "ウズベキスタン": "UZ", "コンゴ民主共和国": "CD",
    "クロアチア": "HR", "パナマ": "PA", "ガーナ": "GH",
}
SUBFLAG = {"スコットランド": "gbsct", "イングランド": "gbeng"}


def sh(t):
    return SHORT.get(t, t)


def _zone(rank):
    return "adv" if rank <= 2 else ("mid" if rank == 3 else "out")


def flag(t):
    if t in SUBFLAG:
        return "\U0001F3F4" + "".join(chr(0xE0000 + ord(c)) for c in SUBFLAG[t]) + "\U000E007F"
    cc = ISO.get(t)
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc) if cc else ""


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ============ ranking (FIFA 2026) ============
def compute(matches):
    table = defaultdict(lambda: defaultdict(
        lambda: dict(P=0, W=0, D=0, L=0, GF=0, GA=0, Pts=0)))
    for m in matches:
        g = m["group"]
        for team, gf, ga in ((m["home"], m["hg"], m["ag"]), (m["away"], m["ag"], m["hg"])):
            s = table[g][team]
            s["P"] += 1
            s["GF"] += gf
            s["GA"] += ga
            if gf > ga:
                s["W"] += 1
                s["Pts"] += 3
            elif gf == ga:
                s["D"] += 1
                s["Pts"] += 1
            else:
                s["L"] += 1
    return table


def _h2h_stats(g, S, matches):
    st = {t: dict(Pts=0, GF=0, GA=0) for t in S}
    for m in matches:
        if m["group"] != g or m["home"] not in st or m["away"] not in st:
            continue
        for t, gf, ga in ((m["home"], m["hg"], m["ag"]), (m["away"], m["ag"], m["hg"])):
            st[t]["Pts"] += 3 if gf > ga else (1 if gf == ga else 0)
            st[t]["GF"] += gf
            st[t]["GA"] += ga
    return st


def rank_group(g, matches, conduct=None, fifa_rank=None):
    conduct = conduct or {}
    fifa_rank = fifa_rank or {}
    overall = compute(matches)[g]
    teams = list(overall)

    def gd(d, t):
        return d[t]["GF"] - d[t]["GA"]

    def h2h_block(S):
        if len(S) == 1:
            return [S]
        h = _h2h_stats(g, set(S), matches)
        for crit in (lambda t: h[t]["Pts"], lambda t: gd(h, t), lambda t: h[t]["GF"]):
            vals = {t: crit(t) for t in S}
            if len(set(vals.values())) > 1:
                runs = []
                for v in sorted(set(vals.values()), reverse=True):
                    sub = [t for t in S if vals[t] == v]
                    runs.extend(h2h_block(sub) if len(sub) > 1 else [sub])
                return runs
        return [S]

    def global_phase(S):
        crits = (lambda t: gd(overall, t), lambda t: overall[t]["GF"],
                 lambda t: conduct.get(t),
                 lambda t: (-fifa_rank[t]) if t in fifa_rank else None)

        def go(S, i):
            if len(S) == 1:
                return [(S[0], False)]
            if i >= len(crits):
                return [(t, True) for t in sorted(S)]
            vals = {t: crits[i](t) for t in S}
            if any(v is None for v in vals.values()):
                return go(S, i + 1)
            if len(set(vals.values())) == 1:
                return go(S, i + 1)
            out = []
            for v in sorted(set(vals.values()), reverse=True):
                sub = [t for t in S if vals[t] == v]
                out.extend(go(sub, i + 1) if len(sub) > 1 else [(sub[0], False)])
            return out
        return go(S, 0)

    def resolve(S):
        out = []
        for sub in h2h_block(S):
            out.extend([(sub[0], False)] if len(sub) == 1 else global_phase(sub))
        return out

    ordered = []
    for p in sorted({overall[t]["Pts"] for t in teams}, reverse=True):
        run = [t for t in teams if overall[t]["Pts"] == p]
        ordered.extend([(run[0], False)] if len(run) == 1 else resolve(run))
    return [(t, overall[t], tied) for t, tied in ordered]


def tie_basis(g, rows, matches, conduct, fifa_rank):
    notes = []
    for i in range(1, len(rows)):
        (a, sa, _), (b, sb, tied_b) = rows[i - 1], rows[i]
        if (sa["Pts"], sa["GF"] - sa["GA"], sa["GF"]) != (sb["Pts"], sb["GF"] - sb["GA"], sb["GF"]):
            continue
        h = _h2h_stats(g, {a, b}, matches)
        if (h[a]["Pts"], h[a]["GF"] - h[a]["GA"], h[a]["GF"]) != \
           (h[b]["Pts"], h[b]["GF"] - h[b]["GA"], h[b]["GF"]):
            basis = "直接対決"
        elif a in conduct and b in conduct and conduct[a] != conduct[b]:
            basis = f"フェアプレーポイント ({sh(a)} {conduct[a]:+d} / {sh(b)} {conduct[b]:+d})"
        elif a in fifa_rank and b in fifa_rank:
            basis = "FIFA ランキング"
        else:
            basis = "（未決着 = フェアプレー/FIFAランクのデータ待ち）" if tied_b else "直接対決"
        notes.append(f"{i}位 {sh(a)} / {i+1}位 {sh(b)}: {basis} で確定")
    return notes


def url_lookup(arts):
    def finder(g, home, away):
        for a in arts["matches"]:
            if a["group"] != g:
                continue
            if home in a["title"] and away in a["title"]:
                fr = next((r for r in a["refs"] if r.get("source") == "FIFA公式"), a["refs"][0])
                return fr["url"], ("match-centre" in fr["url"])
        return None, False
    return finder


# ============ shared HTML shell ============
CSS = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
:root{
  --bg:#eef1f6; --panel:#ffffff; --ink:#19212b; --muted:#697585;
  --line:#e7eaf0; --line-soft:#f1f3f7;
  --accent-ink:#0b6f66; --accent-soft:#e4f4f1;
  --adv:#1aa251; --mid:#e08a1e; --out:#a3acb8;
  --win-bg:#e3f5ea; --win-ink:#137a3f; --draw-bg:#eceff4; --draw-ink:#5b6776;
  --loss-bg:#fdeaea; --loss-ink:#c0392b;
  --self:#e9edf3; --self2:#dfe4ec; --empty:#fafbfd; --jp:#e2356b;
  --shadow:0 1px 2px rgba(17,24,39,.05),0 8px 24px rgba(17,24,39,.06);
  --shadow-sm:0 1px 2px rgba(17,24,39,.06);
}
body{margin:0;color:var(--ink);
  background:radial-gradient(1200px 600px at 100% -10%,#e7f3f0 0,transparent 60%),
    radial-gradient(900px 520px at -10% 0,#edeff9 0,transparent 55%),var(--bg);
  background-attachment:fixed;
  font-family:"Hiragino Kaku Gothic ProN","Hiragino Sans",-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;
  line-height:1.6;font-feature-settings:"palt" 1;-webkit-font-smoothing:antialiased}
.wrap{max-width:1140px;margin:0 auto;padding:0 20px 80px}
.topbar{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.82);backdrop-filter:saturate(1.4) blur(10px);
  border-bottom:1px solid var(--line)}
.topbar .inner{max-width:1140px;margin:0 auto;padding:12px 20px;display:flex;align-items:center;
  gap:18px;flex-wrap:wrap}
.brand{font-weight:800;font-size:15px;letter-spacing:-.01em;display:flex;align-items:center;gap:8px}
.brand .ball{font-size:18px}
nav.tabs{display:flex;gap:6px;margin-left:auto}
nav.tabs a{color:var(--muted);text-decoration:none;font-size:13px;font-weight:600;
  padding:6px 13px;border-radius:999px;border:1px solid transparent}
nav.tabs a:hover{background:var(--panel);border-color:var(--line)}
nav.tabs a.on{background:var(--accent-soft);color:var(--accent-ink);border-color:transparent}
header.top{margin:30px 0 26px}
h1{font-size:25px;line-height:1.24;letter-spacing:-.015em;margin:0 0 9px;font-weight:800}
.sub{color:var(--muted);font-size:14px;margin:0;max-width:70ch}
.legend{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}
.chip{display:inline-flex;align-items:center;gap:7px;background:var(--panel);border:1px solid var(--line);
  border-radius:999px;padding:6px 13px;font-size:12px;color:var(--muted);box-shadow:var(--shadow-sm)}
.chip b{color:var(--ink);font-weight:700}
.dot{width:9px;height:9px;border-radius:999px;display:inline-block}
.flag{margin-right:3px;font-size:1.1em;line-height:1}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(370px,1fr));gap:20px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:18px 18px 8px;box-shadow:var(--shadow)}
.card.pad{padding-bottom:18px}
.card h2{font-size:13px;margin:0 0 12px;display:flex;align-items:center;gap:9px;font-weight:600}
.tag{display:inline-flex;align-items:center;justify-content:center;background:var(--accent-soft);
  color:var(--accent-ink);border-radius:9px;font-size:12px;font-weight:800;padding:4px 10px;letter-spacing:.02em}
.jp{color:var(--jp);font-weight:700;font-size:12px}
.rank{display:inline-block;min-width:1.05em;font-weight:800;margin-right:2px;text-align:center}
.rank.adv{color:var(--adv)} .rank.mid{color:var(--mid)} .rank.out{color:var(--out)}
.pts{color:var(--muted);font-weight:500;font-size:10.5px;margin-left:3px}
/* cross-table */
table.x{border-collapse:separate;border-spacing:0;width:100%;font-size:12px;table-layout:fixed}
table.x th,table.x td{padding:8px 2px;text-align:center}
table.x thead th{color:var(--muted);font-weight:600;font-size:10.5px;white-space:nowrap;letter-spacing:-.01em;
  overflow:hidden;text-overflow:ellipsis;border-bottom:1px solid var(--line);padding-bottom:9px}
table.x thead th.corner{width:28%;text-align:right;color:#aeb6c1;font-size:10px;font-weight:500}
table.x tbody th.rowh{text-align:left;color:var(--ink);font-weight:600;font-size:12.5px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;padding-left:2px;border-bottom:1px solid var(--line-soft)}
table.x tbody td{border-bottom:1px solid var(--line-soft)}
table.x tbody tr:last-child th,table.x tbody tr:last-child td{border-bottom:none}
td.self{background:repeating-linear-gradient(135deg,var(--self) 0,var(--self) 5px,var(--self2) 5px,var(--self2) 6px)}
td.empty{background:var(--empty)}
td.played{padding:5px 3px}
td.played a{display:block;border-radius:8px;padding:6px 0;text-decoration:none;font-weight:800;
  font-variant-numeric:tabular-nums;transition:transform .08s ease,box-shadow .14s ease}
td.played a:hover{transform:translateY(-1px)}
td.win a{background:var(--win-bg);color:var(--win-ink)}
td.win a:hover{box-shadow:0 4px 12px rgba(19,122,63,.26)}
td.draw a{background:var(--draw-bg);color:var(--draw-ink)}
td.draw a:hover{box-shadow:0 4px 12px rgba(91,103,118,.22)}
td.loss a{background:var(--loss-bg);color:var(--loss-ink)}
td.loss a:hover{box-shadow:0 4px 12px rgba(192,57,43,.2)}
/* standings */
table.s{border-collapse:separate;border-spacing:0;width:100%;font-size:12.5px}
table.s th,table.s td{padding:7px 4px;text-align:center;border-bottom:1px solid var(--line-soft);white-space:nowrap}
table.s thead th{color:var(--muted);font-weight:600;font-size:11px;border-bottom:1px solid var(--line)}
table.s td.team,table.s th.team{text-align:left;font-weight:600}
table.s td.pts{font-weight:800}
table.s tbody tr:last-child td{border-bottom:none}
.tienote{color:var(--muted);font-size:11.5px;margin:8px 2px 0;display:flex;gap:6px}
/* links */
.matchrow{display:flex;align-items:center;gap:10px;padding:9px 2px;border-bottom:1px solid var(--line-soft);font-size:13px}
.matchrow:last-child{border-bottom:none}
.matchrow .md{color:var(--muted);font-size:11px;min-width:34px}
.matchrow .vs{flex:1;font-weight:600;font-variant-numeric:tabular-nums}
.matchrow .vs .sc{color:var(--accent-ink);font-weight:800;margin:0 4px}
.matchrow a.rep{flex-shrink:0;background:var(--accent-soft);color:var(--accent-ink);text-decoration:none;
  font-size:11.5px;font-weight:700;border-radius:8px;padding:5px 10px;white-space:nowrap}
.matchrow a.rep:hover{box-shadow:0 3px 10px rgba(14,143,132,.25)}
.notes{margin-top:30px;background:var(--panel);border:1px solid var(--line);border-radius:18px;
  padding:18px 22px;font-size:13.5px;box-shadow:var(--shadow)}
.notes b{color:var(--ink)}
.notes ul{margin:11px 0 4px;padding-left:20px;color:var(--ink)}
.notes li{margin:5px 0}
.notesrc{color:var(--muted);font-size:11.5px;margin:9px 0 0}
.foot{color:var(--muted);font-size:12.5px;margin-top:26px;line-height:1.75}
.foot b{color:var(--ink)} .foot a{color:var(--accent-ink)}
"""

PAGES = [("index.html", "クロス表"), ("standings.html", "順位表"), ("links.html", "記事リンク")]


def shell(active_file, title, head_html, body_html, as_of):
    tabs = "".join(
        '<a href="{}"{}>{}</a>'.format(f, ' class="on"' if f == active_file else '', esc(label))
        for f, label in PAGES)
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | 2026 W杯 観戦表</title>
<meta name="description" content="2026 FIFA ワールドカップのグループステージ結果・順位・FIFA日本語マッチレポートをまとめた非公式の観戦用ページ。">
<!-- ⚠ 生成物: build.py が data/ から生成。docs/ は直接編集しない。 -->
<style>{CSS}</style></head>
<body>
<div class="topbar"><div class="inner">
<span class="brand"><span class="ball">⚽️</span>2026 W杯 観戦表</span>
<nav class="tabs">{tabs}</nav>
</div></div>
<div class="wrap">
<header class="top"><h1>{head_html}</h1>
<p class="sub">並びは暫定順位（FIFA 2026 規定）。 as_of {esc(as_of)} JST · 非公式</p></header>
{body_html}
<p class="foot">結果は FIFA 公式・各紙を 2 ソース以上で確認したもの。 順位 tiebreak = <b>FIFA 2026 規定</b>
（直接対決〔勝点→得失差→総得点〕→ 全試合得失差 → 全試合総得点 → フェアプレー点 → FIFA ランキング、 抽選は廃止）。
本サイトは個人運営の非公式ファンページで、 FIFA とは無関係です。</p>
</div></body></html>"""


# ============ page builders ============
def page_index(groups_grid, as_of):
    legend = (
        '<div class="legend">'
        '<span class="chip"><span class="dot" style="background:var(--adv)"></span><b>①②</b> 突破圏</span>'
        '<span class="chip"><span class="dot" style="background:var(--mid)"></span><b>③</b> 3位</span>'
        '<span class="chip"><span class="dot" style="background:var(--out)"></span><b>④</b> 敗退圏</span>'
        '<span class="chip"><b style="color:var(--win-ink)">勝</b> <b style="color:var(--draw-ink)">分</b> '
        '<b style="color:var(--loss-ink)">負</b> 行チーム視点 → FIFAレポート</span>'
        '<span class="chip"><b>▦</b> 自チーム ／ 空欄 = 未対戦</span></div>')
    intro = ('各行＝そのチームの対戦結果。 セルは<b>行チームから見たスコア</b>（自分-相手）を勝=緑/分=灰/負=赤で色分け。 '
             'クリックで FIFA 日本語マッチレポート。 W杯は中立地開催でホーム/アウェイの優位が基本無いため、同じ試合を両チームの視点で表示。')
    head = "グループ別クロス表"
    body = f'<p class="sub" style="margin:6px 0 0">{intro}</p>{legend}<div class="grid" style="margin-top:22px">{groups_grid}</div>'
    return head, body


def grid_card(g, teams, stats, grid):
    is_jp = g == JP_GROUP
    h2 = (f'<h2><span class="tag">{g}組</span>'
          + ('<span class="jp">🇯🇵 日本</span>' if is_jp else '') + '</h2>')
    head = ('<tr><th class="corner">自＼相手</th>'
            + "".join(f'<th><span class="rank {_zone(i+1)}">{CIRC[i+1]}</span>'
                      f'<span class="flag">{flag(t)}</span>{esc(sh(t))}</th>'
                      for i, t in enumerate(teams)) + "</tr>")
    rows = []
    for i, h in enumerate(teams):
        tds = [f'<th class="rowh"><span class="rank {_zone(i+1)}">{CIRC[i+1]}</span>'
               f'<span class="flag">{flag(h)}</span>{esc(sh(h))}'
               f'<span class="pts">{stats[h]["Pts"]}pt</span></th>']
        for a in teams:
            kind, score, url, res = grid[h][a]
            if kind == "self":
                tds.append('<td class="self"></td>')
            elif kind == "played":
                tds.append(f'<td class="played {res}"><a href="{esc(url)}" target="_blank" '
                           f'rel="noopener">{esc(score)}</a></td>' if url
                           else f'<td class="played {res}">{esc(score)}</td>')
            else:
                tds.append('<td class="empty"></td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<div class="card">{h2}<table class="x"><thead>{head}</thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def page_standings(cards, notes, as_of, source):
    note_html = ""
    if notes:
        items = "".join(f"<li>⚖️ {esc(n)}</li>" for n in notes)
        src = f'<p class="notesrc">出典: {esc(source)}</p>' if source else ""
        note_html = ('<div class="notes"><b>同点で得失差・総得点まで並んだ箇所の確定根拠</b>'
                     f'<ul>{items}</ul>{src}</div>')
    head = "グループステージ順位表"
    body = f'<div class="grid" style="margin-top:6px">{cards}</div>{note_html}'
    return head, body


def standings_card(g, rows):
    is_jp = g == JP_GROUP
    h2 = (f'<h2><span class="tag">{g}組</span>'
          + ('<span class="jp">🇯🇵 日本</span>' if is_jp else '') + '</h2>')
    head = ('<tr><th>順</th><th class="team">チーム</th><th>試</th><th>勝</th><th>分</th>'
            '<th>敗</th><th>得</th><th>失</th><th>差</th><th>点</th></tr>')
    trs = []
    for i, (t, s, tied) in enumerate(rows, 1):
        gd = s["GF"] - s["GA"]
        mark = "※" if tied else ""
        trs.append(
            f'<tr><td><span class="rank {_zone(i)}">{CIRC[i]}</span>{mark}</td>'
            f'<td class="team"><span class="flag">{flag(t)}</span>{esc(sh(t))}</td>'
            f'<td>{s["P"]}</td><td>{s["W"]}</td><td>{s["D"]}</td><td>{s["L"]}</td>'
            f'<td>{s["GF"]}</td><td>{s["GA"]}</td><td>{gd:+d}</td><td class="pts">{s["Pts"]}</td></tr>')
    return (f'<div class="card pad">{h2}<table class="s"><thead>{head}</thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def page_links(cards, as_of):
    head = "試合別 FIFA 日本語レポート"
    intro = '消化済み全試合の FIFA 公式マッチレポート（日本語）。 一部は日本語記事版が未配信のため公式マッチセンターで代替。'
    body = f'<p class="sub" style="margin:6px 0 18px">{intro}</p><div class="grid">{cards}</div>'
    return head, body


def links_card(g, matches, find_url):
    is_jp = g == JP_GROUP
    h2 = (f'<h2><span class="tag">{g}組</span>'
          + ('<span class="jp">🇯🇵 日本</span>' if is_jp else '') + '</h2>')
    res = sorted((m for m in matches if m["group"] == g),
                 key=lambda x: (x["md"], str(x.get("date", ""))))
    rows = []
    for m in res:
        h, a = m["home"], m["away"]
        url, mc = find_url(g, h, a)
        label = "マッチセンター" if mc else "レポート"
        vs = (f'<span class="flag">{flag(h)}</span>{esc(sh(h))}'
              f'<span class="sc">{m["hg"]}-{m["ag"]}</span>{esc(sh(a))}<span class="flag">{flag(a)}</span>')
        rep = (f'<a class="rep" href="{esc(url)}" target="_blank" rel="noopener">📄 {label}</a>'
               if url else '<span style="color:var(--muted);font-size:11px">—</span>')
        rows.append(f'<div class="matchrow"><span class="md">第{m["md"]}節</span>'
                    f'<span class="vs">{vs}</span>{rep}</div>')
    return f'<div class="card pad">{h2}{"".join(rows)}</div>'


def main():
    res = yaml.safe_load((DATA / "results.yaml").read_text())
    arts = yaml.safe_load((DATA / "articles.yaml").read_text())
    meta = res["meta"]
    as_of = meta.get("as_of", "")
    matches = res["matches"]
    tb = meta.get("tiebreak", {}) or {}
    conduct = tb.get("conduct", {}) or {}
    fifa_rank = tb.get("fifa_ranking", {}) or {}
    source = tb.get("source", "")
    table = compute(matches)
    find_url = url_lookup(arts)
    rmap = {}
    for m in matches:
        rmap[(m["group"], m["home"], m["away"])] = (m["hg"], m["ag"])
        rmap[(m["group"], m["away"], m["home"])] = (m["ag"], m["hg"])

    grid_cards, stand_cards, link_cards, notes = [], [], [], []
    for g in GROUP_ORDER:
        if g not in table:
            continue
        rows = rank_group(g, matches, conduct, fifa_rank)
        teams = [t for t, _, _ in rows]
        stats = {t: s for t, s, _ in rows}
        grid = {}
        for r in teams:
            grid[r] = {}
            for c in teams:
                if r == c:
                    grid[r][c] = ("self", None, None, None)
                elif (g, r, c) in rmap:
                    rg, cg = rmap[(g, r, c)]
                    u, _mc = find_url(g, r, c)
                    res_kind = "win" if rg > cg else ("draw" if rg == cg else "loss")
                    grid[r][c] = ("played", f"{rg}-{cg}", u, res_kind)
                else:
                    grid[r][c] = ("empty", None, None, None)
        grid_cards.append(grid_card(g, teams, stats, grid))
        stand_cards.append(standings_card(g, rows))
        link_cards.append(links_card(g, matches, find_url))
        for n in tie_basis(g, rows, matches, conduct, fifa_rank):
            notes.append(f"{g}組 — {n}")

    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("")
    h, b = page_index("".join(grid_cards), as_of)
    (DOCS / "index.html").write_text(shell("index.html", h, h, b, as_of))
    h, b = page_standings("".join(stand_cards), notes, as_of, source)
    (DOCS / "standings.html").write_text(shell("standings.html", h, h, b, as_of))
    h, b = page_links("".join(link_cards), as_of)
    (DOCS / "links.html").write_text(shell("links.html", h, h, b, as_of))
    print(f"built docs/: index + standings + links  ({len(grid_cards)} groups, {len(matches)} matches)")


if __name__ == "__main__":
    main()
