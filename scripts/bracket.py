#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""決勝トーナメント（ノックアウト）の bracket 解決器（= データ層、 build.py が描画）。

data/fixtures.yaml の knockout エントリ（stage r32..final / third、 スロット票 label）を読み、
**データが揃った分だけ**実チームに解決して rounds 構造を返す。順位は standings.py を import
（= 単一実装）。将来は calendar の label 更新も同じ解決器を使う想定（手作業の label 書換を消す）。

段階的解決（= 埋まる順に埋まる、 推測で埋めない）:
  - グループ順位スロット (A1/A2/B2 等): その組が全 6 試合消化済なら順位表から実チーム、 未確定はラベル
  - ベスト3位スロット (3位[A/B/C/D/F]): どの3位がどのスロットに入るかは FIFA 公式の組合せ→割当表が
    要る（48チーム特有）→ Phase 2。 今はラベル（候補組の集合を表示）
  - 勝者/敗者スロット (M73勝者 / M101敗者): 当該 no の knockout 結果が results にあれば解決、 無ければラベル

スコアは results.yaml の knockout エントリ由来（group を持たず no が鍵。 PK は pens:[h,a]）。

出力: build_rounds(results_matches, conduct, fifa_rank) -> (rounds, third)
  rounds = [{stage, title_ja, title_en, matches:[match,...]}, ...]   # r32→final の列
  third  = match | None                                              # 3位決定戦（本線外）
  match  = {no, dt, venue, city,
            home: slot, away: slot,
            score: None | {hg, ag, pens?:[h,a]},
            winner: None | "home" | "away"}
  slot   = {team: "スイス"} (解決済) | {label_ja, label_en} (未確定)
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "data" / "fixtures.yaml"
sys.path.insert(0, str(ROOT / "scripts"))
from standings import rank_group  # noqa: E402

GROUPS = list("ABCDEFGHIJKL")
STAGE_ORDER = ["r32", "r16", "qf", "sf", "final"]
STAGE_TITLE = {
    "r32": ("ベスト32", "Round of 32"),
    "r16": ("ベスト16", "Round of 16"),
    "qf": ("準々決勝", "Quarter-finals"),
    "sf": ("準決勝", "Semi-finals"),
    "final": ("決勝", "Final"),
    "third": ("3位決定戦", "Third place"),
}

# FIFA 2026 公式ブラケットの feed 構造（= 各 KO 試合が「どの 2 つの前段試合の勝者から
# 来るか」）。 **結果に依存しない大会の固定構造**。 描画の縦並び（ツリー順）はこの定数から
# 導く。 fixtures の label を feeders の source にすると、 propagate-knockout が R32 結果を
# R16 label に書き込んで実チーム名化した瞬間（"M74勝者 × M77勝者" → "パラグアイ × M77勝者"）
# に feed 関係が失われ、 ツリー順が崩壊して接続線がワープする（= 2026-06-30 の bug）。
# R32（73-88）は木の葉なので含めない。 third(103) は本線外（両 SF 敗者、 _assign は final から
# しか辿らないので使われないが、 意味として記載）。
KO_FEED = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
    97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96),
    101: (97, 98), 102: (99, 100),
    103: (101, 102), 104: (101, 102),
}

_GROUP_POS = re.compile(r"^([A-L])([1-4])$")
_THIRD = re.compile(r"^3位\[([A-L/]+)\]$")
_WINNER = re.compile(r"^M(\d+)勝者$")
_LOSER = re.compile(r"^M(\d+)敗者$")


def _group_finals(results_matches, conduct, fifa_rank):
    """全 6 試合消化した組だけ {1:team, 2:team, 3:team, 4:team} を返す。未確定組は None。"""
    played = {g: 0 for g in GROUPS}
    for m in results_matches:
        g = m.get("group")
        if g in played:
            played[g] += 1
    finals = {}
    for g in GROUPS:
        if played[g] >= 6:
            rows = rank_group(g, results_matches, conduct, fifa_rank)
            finals[g] = {i + 1: t for i, (t, _, _) in enumerate(rows)}
        else:
            finals[g] = None
    return finals


def _resolve_token(tok, finals, resolved, known_teams=None):
    """スロット票 1 つを {team} か {label_ja,label_en} に解決する。

    known_teams: グループ戦に登場した実チーム名の集合。 fixtures.yaml の knockout label
    が事前に実チーム名で書かれているケース（例 R32 「南アフリカ × カナダ」）を team として
    正しく分類するために使う。 渡されない場合はフォールバックで label 扱い（後方互換）。
    """
    m = _GROUP_POS.match(tok)
    if m:
        g, pos = m.group(1), int(m.group(2))
        if finals.get(g):
            return {"team": finals[g][pos]}
        return {"label_ja": f"{g}組{pos}位", "label_en": f"{g}{pos}"}
    m = _THIRD.match(tok)
    if m:
        grps = m.group(1)
        return {"label_ja": f"3位({grps}組)", "label_en": f"3rd ({grps})"}
    m = _WINNER.match(tok)
    if m:
        n = int(m.group(1))
        w = resolved.get(n, {}).get("winner_team")
        if w:
            return {"team": w}
        return {"label_ja": f"M{n} 勝者", "label_en": f"M{n} winner"}
    m = _LOSER.match(tok)
    if m:
        n = int(m.group(1))
        ls = resolved.get(n, {}).get("loser_team")
        if ls:
            return {"team": ls}
        return {"label_ja": f"M{n} 敗者", "label_en": f"M{n} loser"}
    if known_teams and tok in known_teams:
        return {"team": tok}
    return {"label_ja": tok, "label_en": tok}


def _known_teams(fixtures):
    """fixtures のグループ戦に登場した実チーム名の集合を返す。"""
    teams = set()
    for f in fixtures:
        if f.get("stage") != "group":
            continue
        parts = [p.strip() for p in re.split(r"[×x✕]", f.get("label", ""))]
        if len(parts) == 2:
            teams.update(parts)
    return teams


def _winner_side(score):
    """score から勝者の side を返す（PK 込み）。引き分けで PK 無しなら None。"""
    if not score:
        return None
    hg, ag = score.get("hg"), score.get("ag")
    if hg is None or ag is None:
        return None
    if hg != ag:
        return "home" if hg > ag else "away"
    pens = score.get("pens")
    if pens and pens[0] != pens[1]:
        return "home" if pens[0] > pens[1] else "away"
    return None


def build_rounds(results_matches, conduct=None, fifa_rank=None):
    conduct = conduct or {}
    fifa_rank = fifa_rank or {}
    fixtures = yaml.safe_load(FIXTURES.read_text(encoding="utf-8"))["matches"]
    finals = _group_finals(results_matches, conduct, fifa_rank)
    res_by_no = {m["no"]: m for m in results_matches if m.get("no")}
    known = _known_teams(fixtures)

    ko = sorted((f for f in fixtures if f.get("stage") in STAGE_TITLE), key=lambda x: x["no"])
    resolved = {}   # no -> {home, away, winner_team, loser_team}
    built = {}      # no -> match dict（出力用）
    for f in ko:
        parts = [p.strip() for p in re.split(r"[×x✕]", f["label"])]
        home = _resolve_token(parts[0], finals, resolved, known) if len(parts) == 2 else {"label_ja": f["label"], "label_en": f["label"]}
        away = _resolve_token(parts[1], finals, resolved, known) if len(parts) == 2 else {"label_ja": "", "label_en": ""}

        r = res_by_no.get(f["no"])
        score = None
        if r and r.get("hg") is not None and r.get("ag") is not None and f["stage"] != "group":
            score = {"hg": r["hg"], "ag": r["ag"]}
            if r.get("pens"):
                score["pens"] = list(r["pens"])
        win_side = _winner_side(score)
        win_team = los_team = None
        if win_side and home.get("team") and away.get("team"):
            win_team = (home if win_side == "home" else away)["team"]
            los_team = (away if win_side == "home" else home)["team"]
        resolved[f["no"]] = {"winner_team": win_team, "loser_team": los_team}

        built[f["no"]] = {
            "no": f["no"], "stage": f["stage"],
            "dt": f.get("start_jst", ""), "venue": f.get("venue", ""), "city": f.get("city", ""),
            "home": home, "away": away, "score": score,
            "winner": win_side if (win_side and home.get("team") and away.get("team")) else None,
        }

    # --- ブラケット木順（ペアが隣接 → flexbox で次ラウンドがペアの上下中央に揃う）---
    # KO_FEED（結果非依存の固定構造）から木を作り、 決勝から DFS して R32（葉）の縦順を
    # 決める。 上位ラウンドの順は配下葉位置の平均で導く。 ⚠️ feeders を fixtures の label
    # からパースすると、 propagate-knockout が R16 label を実チーム名に解決した瞬間に feed
    # が失われツリー順が崩壊する（= ワープ bug）。 固定構造を source にして結果から切り離す。
    feeders = {no: list(fs) for no, fs in KO_FEED.items() if no in built}
    leafpos, _c = {}, [0]

    def _assign(no):
        fs = feeders.get(no)
        if fs:
            for ff in fs:
                _assign(ff)
        else:
            leafpos[no] = _c[0]
            _c[0] += 1

    for f in ko:
        if f["stage"] == "final":
            _assign(f["no"])

    def _bkey(no):
        fs = feeders.get(no)
        if not fs:
            return leafpos.get(no, 10 ** 6)
        ks = [_bkey(ff) for ff in fs]
        return sum(ks) / len(ks)

    order = {no: _bkey(no) for no in built}

    rounds = []
    for st in STAGE_ORDER:
        ms = sorted((m for m in built.values() if m["stage"] == st),
                    key=lambda x: order.get(x["no"], x["no"]))
        if ms:
            rounds.append({"stage": st, "title_ja": STAGE_TITLE[st][0],
                           "title_en": STAGE_TITLE[st][1], "matches": ms})
    third = next((m for m in built.values() if m["stage"] == "third"), None)
    return rounds, third


def third_place_race(results_matches, conduct=None, fifa_rank=None):
    """各組3位を集め、FIFA ベスト3位ランキング順（点→得失差→総得点→フェアプレー）に並べる。
    上位 8 が決勝T進出、下位 4 が敗退。 返り値の各 row:
      {rank, group, team, P, Pts, GF, GA, GD, final(組が全6試合消化), qualified(上位8), tied_next}
    ⚠️ 組未確定なら 3位チーム自体が変わり得る（final=False=暫定）。 推測の確率は出さない。"""
    conduct = conduct or {}
    fifa_rank = fifa_rank or {}
    played = {g: 0 for g in GROUPS}
    for m in results_matches:
        g = m.get("group")
        if g in played:
            played[g] += 1
    rows = []
    for g in GROUPS:
        gr = rank_group(g, results_matches, conduct, fifa_rank)
        if len(gr) < 3:
            continue
        t, s, _ = gr[2]
        rows.append({"group": g, "team": t, "P": s["P"], "Pts": s["Pts"],
                     "GF": s["GF"], "GA": s["GA"], "GD": s["GF"] - s["GA"],
                     "final": played[g] >= 6})
    rows.sort(key=lambda r: (-r["Pts"], -r["GD"], -r["GF"], -conduct.get(r["team"], 0)))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        r["qualified"] = i < 8
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        r["tied_next"] = bool(nxt and (r["Pts"], r["GD"], r["GF"]) == (nxt["Pts"], nxt["GD"], nxt["GF"])
                              and conduct.get(r["team"], 0) == conduct.get(nxt["team"], 0))
    return rows


def _selftest():
    # group-pos / best-third / winner-of の解決と未解決ラベルを最小確認
    finals = {"A": {1: "X", 2: "Y", 3: "Z", 4: "W"}, "B": None}
    assert _resolve_token("A2", finals, {}) == {"team": "Y"}
    assert _resolve_token("B2", finals, {})["label_en"] == "B2"
    assert _resolve_token("3位[A/B/C]", finals, {})["label_ja"] == "3位(A/B/C組)"
    res = {73: {"winner_team": "X", "loser_team": "Y"}}
    assert _resolve_token("M73勝者", finals, res) == {"team": "X"}
    assert _resolve_token("M73敗者", finals, res) == {"team": "Y"}
    assert _resolve_token("M99勝者", finals, {})["label_en"] == "M99 winner"
    # 実チーム名（fixtures に登場するもの）は known_teams で team として解決される
    assert _resolve_token("カナダ", finals, {}, {"カナダ", "南アフリカ"}) == {"team": "カナダ"}
    # known_teams 未指定 or 未登録は label のまま（後方互換）
    assert _resolve_token("カナダ", finals, {})["label_ja"] == "カナダ"
    assert _resolve_token("謎チーム", finals, {}, {"カナダ"})["label_en"] == "謎チーム"
    assert _winner_side({"hg": 1, "ag": 0}) == "home"
    assert _winner_side({"hg": 1, "ag": 1, "pens": [4, 2]}) == "home"
    assert _winner_side({"hg": 1, "ag": 1}) is None
    print("bracket selftest ✅")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        import json
        rounds, third = build_rounds(
            yaml.safe_load((ROOT / "data" / "results.yaml").read_text())["matches"])
        print(json.dumps({"rounds": [{"stage": r["stage"], "n": len(r["matches"])} for r in rounds],
                          "third": bool(third)}, ensure_ascii=False))
