#!/usr/bin/env python3
"""wc2026 静的サイト generator (日英 2 言語)。

data/results.yaml (結果 SoT) + data/articles.yaml (FIFA レポート link、 SoT は日本語 URL) から
日本語 (docs/{index,standings,links}.html) と英語 (docs/en/...) の 3 ページずつを生成。
英語ページの FIFA リンクは fifa_localize() が日本語 URL から決定論変換する (/ja/→/en/、
記事は語尾 -ja 除去)。 例外は ref の url_en で上書き可。 共通の明るいテーマ + ナビ + 日英トグル。
stdlib + PyYAML のみ。

  python3 build.py

順位は FIFA 2026 大会規定 (直接対決 → 全試合得失差 → 全試合総得点 → フェアプレー点 →
FIFA ランク、 抽選廃止) で決定論算出。 head-to-head は同点サブグループ内で再帰計算。
"""
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent
# 順位アルゴリズム (compute / rank_group / tiebreak) の正本 = scripts/standings.py。
# build.py は再実装せず import する (= single source、 grid・順位表・公開ページが必ず一致)。
sys.path.insert(0, str(ROOT / "scripts"))
from standings import compute, rank_group, _h2h_stats  # noqa: E402

DATA = ROOT / "data"
DOCS = ROOT / "docs"
GROUP_ORDER = list("ABCDEFGHIJKL")
CIRC = {1: "①", 2: "②", 3: "③", 4: "④"}
JP_GROUP = "F"
LANGS = ("ja", "en")

# 列見出し用の短縮名 (table-layout:fixed で収める)
SHORT_JA = {
    "南アフリカ": "南ア", "ボスニア・ヘルツェゴビナ": "ボスニア", "アメリカ合衆国": "米国",
    "オーストラリア": "豪州", "コートジボワール": "コートジ", "ニュージーランド": "NZ",
    "サウジアラビア": "サウジ", "カーボベルデ": "CV", "アルゼンチン": "アルゼン",
    "オーストリア": "オースト", "アルジェリア": "アルジェ", "ウズベキスタン": "ウズベク",
    "コンゴ民主共和国": "コンゴ", "スコットランド": "スコット", "イングランド": "英国",
    "スウェーデン": "スウェ", "チュニジア": "チュニ", "ウルグアイ": "ウルグ",
    "ノルウェー": "ノルウェ", "ポルトガル": "ポルト", "コロンビア": "コロン",
    "クロアチア": "クロア", "エクアドル": "エクア", "キュラソー": "キュラ", "パラグアイ": "パラグ",
}
SHORT_EN = {
    "メキシコ": "Mexico", "南アフリカ": "S.Africa", "韓国": "Korea", "チェコ": "Czechia",
    "カナダ": "Canada", "スイス": "Switz.", "ボスニア・ヘルツェゴビナ": "Bosnia", "カタール": "Qatar",
    "ブラジル": "Brazil", "モロッコ": "Morocco", "スコットランド": "Scotland", "ハイチ": "Haiti",
    "アメリカ合衆国": "USA", "オーストラリア": "Australia", "パラグアイ": "Paraguay", "トルコ": "Türkiye",
    "ドイツ": "Germany", "コートジボワール": "C.d'Ivoire", "エクアドル": "Ecuador", "キュラソー": "Curaçao",
    "日本": "Japan", "オランダ": "Netherl.", "スウェーデン": "Sweden", "チュニジア": "Tunisia",
    "ベルギー": "Belgium", "イラン": "Iran", "ニュージーランド": "N.Zealand", "エジプト": "Egypt",
    "スペイン": "Spain", "ウルグアイ": "Uruguay", "サウジアラビア": "S.Arabia", "カーボベルデ": "C.Verde",
    "フランス": "France", "ノルウェー": "Norway", "セネガル": "Senegal", "イラク": "Iraq",
    "アルゼンチン": "Argentina", "オーストリア": "Austria", "ヨルダン": "Jordan", "アルジェリア": "Algeria",
    "ポルトガル": "Portugal", "コロンビア": "Colombia", "ウズベキスタン": "Uzbek.", "コンゴ民主共和国": "DR Congo",
    "クロアチア": "Croatia", "パナマ": "Panama", "ガーナ": "Ghana", "イングランド": "England",
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


def short(t, lang):
    return SHORT_EN.get(t, t) if lang == "en" else SHORT_JA.get(t, t)


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


# ============ i18n strings ============
STR = {
    "ja": {
        "html_lang": "ja", "brand": "2026 W杯 観戦表", "other_lang": "English", "other_code": "en",
        "nav": {"index.html": "クロス表", "standings.html": "順位表", "links.html": "記事リンク"},
        "site_title": "2026 W杯 観戦表",
        "sub": "並びは暫定順位（FIFA 2026 規定）。 as_of {as_of} JST · 非公式",
        "idx_head": "グループ別クロス表",
        "idx_intro": ("各行＝そのチームの対戦結果。 セルは<b>行チームから見たスコア</b>（自分-相手）を勝=緑/分=灰/負=赤で色分け。"
                      " クリックで FIFA 日本語マッチレポート。 W杯は中立地開催でホーム/アウェイの優位が基本無いため、同じ試合を両チームの視点で表示。"),
        "lg_adv": "突破圏", "lg_3rd": "3位", "lg_out": "敗退圏",
        "lg_wdl": "行チーム視点 → FIFAレポート", "lg_self": "自チーム ／ 空欄 = 未対戦",
        "corner": "自＼相手",
        "std_head": "グループステージ順位表",
        "cols": ["順", "チーム", "試", "勝", "分", "敗", "得", "失", "差", "点"],
        "note_title": "同点で得失差・総得点まで並んだ箇所の確定根拠",
        "note_src": "出典",
        "links_head": "試合別 FIFA マッチレポート",
        "links_intro": "消化済み全試合の FIFA 公式マッチレポート（日本語）。 一部は日本語記事版が未配信のため FIFA 公式ハイライト動画で代替。",
        "md": "第{md}節", "report": "レポート", "matchcentre": "マッチセンター", "video": "ハイライト", "pt": "pt",
        "grp": "{g}組", "jp_badge": "🇯🇵 日本",
        "foot": ("結果は FIFA 公式・各紙を 2 ソース以上で確認したもの。 順位 tiebreak = <b>FIFA 2026 規定</b>"
                 "（直接対決〔勝点→得失差→総得点〕→ 全試合得失差 → 全試合総得点 → フェアプレー点 → FIFA ランキング、 抽選は廃止）。"
                 " 本サイトは個人運営の非公式ファンページで、 FIFA とは無関係です。"),
        "tb": {"h2h": "直接対決", "fp": "フェアプレーポイント", "rank": "FIFA ランキング",
               "undecided": "（未決着 = フェアプレー/FIFAランクのデータ待ち）",
               "tmpl": "{i}位 {a} / {j}位 {b}: {basis} で確定"},
    },
    "en": {
        "html_lang": "en", "brand": "2026 World Cup Tables", "other_lang": "日本語", "other_code": "ja",
        "nav": {"index.html": "Cross-table", "standings.html": "Standings", "links.html": "Reports"},
        "site_title": "2026 World Cup Tables",
        "sub": "Ordered by current standings (FIFA 2026 rules). As of {as_of} JST · unofficial",
        "idx_head": "Group Cross-Tables",
        "idx_intro": ("Each row is a team's results. Cells show the <b>score from the row team's view</b> (for-against), "
                      "coloured win=green / draw=grey / loss=red. Click to open the FIFA match report. World Cup matches are "
                      "at neutral venues with no real home advantage, so each match is shown from both teams' perspectives."),
        "lg_adv": "Advance", "lg_3rd": "3rd", "lg_out": "Out",
        "lg_wdl": "row team's view → FIFA report", "lg_self": "same team / blank = not played",
        "corner": "Team＼Opp",
        "std_head": "Group Standings",
        "cols": ["#", "Team", "MP", "W", "D", "L", "GF", "GA", "GD", "Pts"],
        "note_title": "How teams level on points / GD / goals were separated",
        "note_src": "Source",
        "links_head": "FIFA Match Reports",
        "links_intro": ("FIFA official match reports (English) for every completed match. A few link to the official FIFA "
                        "highlights video where an article was not available."),
        "md": "MD{md}", "report": "Report", "matchcentre": "Match Centre", "video": "Highlights", "pt": "pt",
        "grp": "Group {g}", "jp_badge": "🇯🇵 Japan",
        "foot": ("Results cross-checked against FIFA and major outlets (2+ sources). Tiebreak = <b>FIFA 2026 rules</b> "
                 "(head-to-head [points → GD → goals] → overall GD → overall goals → fair-play points → FIFA Ranking; "
                 "drawing of lots abolished). This is an unofficial personal fan page, not affiliated with FIFA."),
        "tb": {"h2h": "head-to-head", "fp": "fair-play points", "rank": "FIFA Ranking",
               "undecided": "(undecided — awaiting fair-play / FIFA-ranking data)",
               "tmpl": "#{i} {a} / #{j} {b}: decided by {basis}"},
    },
}


# ============ ranking ============
# compute / _h2h_stats / rank_group は scripts/standings.py から import (= 正本 1 つ)。
# 以下 tie_basis は bilingual の「表示」層のみ (アルゴリズムは上記 import を使う)。
def tie_basis(g, rows, matches, conduct, fifa_rank, lang):
    L = STR[lang]["tb"]
    notes = []
    for i in range(1, len(rows)):
        (a, sa, _), (b, sb, tied_b) = rows[i - 1], rows[i]
        if (sa["Pts"], sa["GF"] - sa["GA"], sa["GF"]) != (sb["Pts"], sb["GF"] - sb["GA"], sb["GF"]):
            continue
        h = _h2h_stats(g, {a, b}, matches)
        if (h[a]["Pts"], h[a]["GF"] - h[a]["GA"], h[a]["GF"]) != \
           (h[b]["Pts"], h[b]["GF"] - h[b]["GA"], h[b]["GF"]):
            basis = L["h2h"]
        elif a in conduct and b in conduct and conduct[a] != conduct[b]:
            basis = f'{L["fp"]} ({short(a, lang)} {conduct[a]:+d} / {short(b, lang)} {conduct[b]:+d})'
        elif a in fifa_rank and b in fifa_rank:
            basis = L["rank"]
        else:
            basis = L["undecided"] if tied_b else L["h2h"]
        notes.append(L["tmpl"].format(i=i, j=i + 1, a=short(a, lang), b=short(b, lang), basis=basis))
    return notes


def fifa_localize(url, lang):
    """FIFA の URL を lang 言語版に変換する。

    SoT (articles.yaml) は日本語 URL を持つ前提。 en ページ用に決定論変換する:
      - 記事 URL  /ja/.../articles/<slug>-ja  →  /en/.../articles/<slug>   (語尾 -ja を除去)
      - match-centre /ja/match-centre/.../<数値ID>  →  /en/match-centre/.../<数値ID>
    en の記事 slug は「日本語と同一語順 + 言語接尾辞を落とす」 が FIFA の規則 (語順
    highlights-match-report / match-report-highlights は試合ごとに揺れるが ja/en で一致、
    -en は付かない)。 = slug 推測ではない。 fifa.com 以外・変換不能・ja はそのまま返す。
    例外で規則が破れる試合は ref に明示 url_en を置けば derive せず尊重する。"""
    if "fifa.com" not in url or lang == "ja":
        return url
    out = url.replace("/ja/", "/en/", 1)
    if "/articles/" in out:
        base = out.rstrip("/")
        if base.endswith("-ja"):
            out = base[:-3]
    return out


def url_lookup(arts):
    def finder(g, home, away, lang="ja"):
        for a in arts["matches"]:
            if a["group"] != g:
                continue
            if home in a["title"] and away in a["title"]:
                fr = next((r for r in a["refs"] if r.get("source") == "FIFA公式"), a["refs"][0])
                # 明示 url_en があれば derive せず尊重 (推測 slug 禁止の escape hatch)
                if lang == "en" and fr.get("url_en"):
                    u = fr["url_en"]
                else:
                    u = fifa_localize(fr["url"], lang)
                return u, ("match-centre" in fr["url"])
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
.topbar .inner{max-width:1140px;margin:0 auto;padding:12px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.brand{font-weight:800;font-size:15px;letter-spacing:-.01em;display:flex;align-items:center;gap:8px}
.brand .ball{font-size:18px}
nav.tabs{display:flex;gap:6px;margin-left:auto}
nav.tabs a{color:var(--muted);text-decoration:none;font-size:13px;font-weight:600;padding:6px 13px;border-radius:999px;border:1px solid transparent}
nav.tabs a:hover{background:var(--panel);border-color:var(--line)}
nav.tabs a.on{background:var(--accent-soft);color:var(--accent-ink);border-color:transparent}
a.lang{color:var(--muted);text-decoration:none;font-size:12px;font-weight:700;border:1px solid var(--line);
  border-radius:999px;padding:6px 12px;background:var(--panel)}
a.lang:hover{color:var(--accent-ink);border-color:var(--accent-soft)}
header.top{margin:30px 0 26px}
h1{font-size:25px;line-height:1.24;letter-spacing:-.015em;margin:0 0 9px;font-weight:800}
.sub{color:var(--muted);font-size:14px;margin:0;max-width:72ch}
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
table.s{border-collapse:separate;border-spacing:0;width:100%;font-size:12.5px}
table.s th,table.s td{padding:7px 4px;text-align:center;border-bottom:1px solid var(--line-soft);white-space:nowrap}
table.s thead th{color:var(--muted);font-weight:600;font-size:11px;border-bottom:1px solid var(--line)}
table.s td.team,table.s th.team{text-align:left;font-weight:600}
table.s td.pts{font-weight:800}
table.s tbody tr:last-child td{border-bottom:none}
.matchrow{display:flex;align-items:center;gap:10px;padding:9px 2px;border-bottom:1px solid var(--line-soft);font-size:13px}
.matchrow:last-child{border-bottom:none}
.matchrow .md{color:var(--muted);font-size:11px;min-width:42px}
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


def shell(lang, active_file, head_html, body_html, as_of):
    L = STR[lang]
    tabs = "".join(
        '<a href="{}"{}>{}</a>'.format(f, ' class="on"' if f == active_file else '', esc(label))
        for f, label in L["nav"].items())
    other = ("en/" + active_file) if lang == "ja" else ("../" + active_file)
    return f"""<!DOCTYPE html>
<html lang="{L['html_lang']}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(head_html)} | {esc(L['site_title'])}</title>
<meta name="description" content="2026 FIFA World Cup group stage: cross-tables, standings, and FIFA match-report links (unofficial fan page).">
<!-- generated by build.py from data/. do not edit docs/ directly. -->
<style>{CSS}</style></head>
<body>
<div class="topbar"><div class="inner">
<span class="brand"><span class="ball">⚽️</span>{esc(L['brand'])}</span>
<nav class="tabs">{tabs}</nav>
<a class="lang" href="{other}">{esc(L['other_lang'])}</a>
</div></div>
<div class="wrap">
<header class="top"><h1>{esc(head_html)}</h1>
<p class="sub">{esc(L['sub']).format(as_of=esc(as_of))}</p></header>
{body_html}
<p class="foot">{L['foot']}</p>
</div></body></html>"""


def grid_card(g, teams, stats, grid, lang):
    L = STR[lang]
    h2 = (f'<h2><span class="tag">{esc(L["grp"]).format(g=g)}</span>'
          + (f'<span class="jp">{esc(L["jp_badge"])}</span>' if g == JP_GROUP else '') + '</h2>')
    head = (f'<tr><th class="corner">{esc(L["corner"])}</th>'
            + "".join(f'<th><span class="rank {_zone(i+1)}">{CIRC[i+1]}</span>'
                      f'<span class="flag">{flag(t)}</span>{esc(short(t, lang))}</th>'
                      for i, t in enumerate(teams)) + "</tr>")
    rows = []
    for i, h in enumerate(teams):
        tds = [f'<th class="rowh"><span class="rank {_zone(i+1)}">{CIRC[i+1]}</span>'
               f'<span class="flag">{flag(h)}</span>{esc(short(h, lang))}'
               f'<span class="pts">{stats[h]["Pts"]}{esc(L["pt"])}</span></th>']
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


def standings_card(g, rows, lang):
    L = STR[lang]
    h2 = (f'<h2><span class="tag">{esc(L["grp"]).format(g=g)}</span>'
          + (f'<span class="jp">{esc(L["jp_badge"])}</span>' if g == JP_GROUP else '') + '</h2>')
    c = L["cols"]
    head = ('<tr>' + f'<th>{esc(c[0])}</th><th class="team">{esc(c[1])}</th>'
            + "".join(f'<th>{esc(x)}</th>' for x in c[2:]) + '</tr>')
    trs = []
    for i, (t, s, tied) in enumerate(rows, 1):
        gd = s["GF"] - s["GA"]
        mark = "※" if tied else ""
        trs.append(
            f'<tr><td><span class="rank {_zone(i)}">{CIRC[i]}</span>{mark}</td>'
            f'<td class="team"><span class="flag">{flag(t)}</span>{esc(short(t, lang))}</td>'
            f'<td>{s["P"]}</td><td>{s["W"]}</td><td>{s["D"]}</td><td>{s["L"]}</td>'
            f'<td>{s["GF"]}</td><td>{s["GA"]}</td><td>{gd:+d}</td><td class="pts">{s["Pts"]}</td></tr>')
    return (f'<div class="card pad">{h2}<table class="s"><thead>{head}</thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def links_card(g, matches, find_url, lang):
    L = STR[lang]
    h2 = (f'<h2><span class="tag">{esc(L["grp"]).format(g=g)}</span>'
          + (f'<span class="jp">{esc(L["jp_badge"])}</span>' if g == JP_GROUP else '') + '</h2>')
    res = sorted((m for m in matches if m["group"] == g),
                 key=lambda x: (x["md"], str(x.get("date", ""))))
    rows = []
    for m in res:
        h, a = m["home"], m["away"]
        url, mc = find_url(g, h, a, lang)
        if url and "/watch/" in url:
            label, icon = L["video"], "▶"
        elif mc:
            label, icon = L["matchcentre"], "📄"
        else:
            label, icon = L["report"], "📄"
        vs = (f'<span class="flag">{flag(h)}</span>{esc(short(h, lang))}'
              f'<span class="sc">{m["hg"]}-{m["ag"]}</span>{esc(short(a, lang))}<span class="flag">{flag(a)}</span>')
        rep = (f'<a class="rep" href="{esc(url)}" target="_blank" rel="noopener">{icon} {esc(label)}</a>'
               if url else '<span style="color:var(--muted);font-size:11px">—</span>')
        rows.append(f'<div class="matchrow"><span class="md">{esc(L["md"]).format(md=m["md"])}</span>'
                    f'<span class="vs">{vs}</span>{rep}</div>')
    return f'<div class="card pad">{h2}{"".join(rows)}</div>'


def build_lang(lang, matches, table, find_url, conduct, fifa_rank, source, as_of, outdir):
    L = STR[lang]
    grid_cards, stand_cards, link_cards, notes = [], [], [], []
    rmap = {}
    for m in matches:
        rmap[(m["group"], m["home"], m["away"])] = (m["hg"], m["ag"])
        rmap[(m["group"], m["away"], m["home"])] = (m["ag"], m["hg"])
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
                    u, _mc = find_url(g, r, c, lang)
                    grid[r][c] = ("played", f"{rg}-{cg}", u,
                                  "win" if rg > cg else ("draw" if rg == cg else "loss"))
                else:
                    grid[r][c] = ("empty", None, None, None)
        grid_cards.append(grid_card(g, teams, stats, grid, lang))
        stand_cards.append(standings_card(g, rows, lang))
        link_cards.append(links_card(g, matches, find_url, lang))
        for n in tie_basis(g, rows, matches, conduct, fifa_rank, lang):
            notes.append(f'{L["grp"].format(g=g)} — {n}')

    outdir.mkdir(parents=True, exist_ok=True)
    # index (cross-table)
    legend = (
        '<div class="legend">'
        f'<span class="chip"><span class="dot" style="background:var(--adv)"></span><b>①②</b> {esc(L["lg_adv"])}</span>'
        f'<span class="chip"><span class="dot" style="background:var(--mid)"></span><b>③</b> {esc(L["lg_3rd"])}</span>'
        f'<span class="chip"><span class="dot" style="background:var(--out)"></span><b>④</b> {esc(L["lg_out"])}</span>'
        '<span class="chip"><b style="color:var(--win-ink)">'
        + ("勝" if lang == "ja" else "W") + '</b> <b style="color:var(--draw-ink)">'
        + ("分" if lang == "ja" else "D") + '</b> <b style="color:var(--loss-ink)">'
        + ("負" if lang == "ja" else "L") + f'</b> {esc(L["lg_wdl"])}</span>'
        f'<span class="chip"><b>▦</b> {esc(L["lg_self"])}</span></div>')
    idx_body = (f'<p class="sub" style="margin:6px 0 0">{L["idx_intro"]}</p>{legend}'
                f'<div class="grid" style="margin-top:22px">{"".join(grid_cards)}</div>')
    (outdir / "index.html").write_text(shell(lang, "index.html", L["idx_head"], idx_body, as_of))
    # standings
    note_html = ""
    if notes:
        items = "".join(f"<li>⚖️ {esc(n)}</li>" for n in notes)
        src = f'<p class="notesrc">{esc(L["note_src"])}: {esc(source)}</p>' if source else ""
        note_html = f'<div class="notes"><b>{esc(L["note_title"])}</b><ul>{items}</ul>{src}</div>'
    std_body = f'<div class="grid" style="margin-top:6px">{"".join(stand_cards)}</div>{note_html}'
    (outdir / "standings.html").write_text(shell(lang, "standings.html", L["std_head"], std_body, as_of))
    # links
    links_body = (f'<p class="sub" style="margin:6px 0 18px">{esc(L["links_intro"])}</p>'
                  f'<div class="grid">{"".join(link_cards)}</div>')
    (outdir / "links.html").write_text(shell(lang, "links.html", L["links_head"], links_body, as_of))


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

    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("")
    build_lang("ja", matches, table, find_url, conduct, fifa_rank, source, as_of, DOCS)
    build_lang("en", matches, table, find_url, conduct, fifa_rank, source, as_of, DOCS / "en")
    print(f"built docs/ (ja) + docs/en/ (en): index+standings+links  "
          f"({sum(1 for g in GROUP_ORDER if g in table)} groups, {len(matches)} matches)")


if __name__ == "__main__":
    main()
