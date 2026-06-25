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


def _resolve_token(tok, finals, resolved):
    """スロット票 1 つを {team} か {label_ja,label_en} に解決する。"""
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
    return {"label_ja": tok, "label_en": tok}


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

    ko = sorted((f for f in fixtures if f.get("stage") in STAGE_TITLE), key=lambda x: x["no"])
    resolved = {}   # no -> {home, away, winner_team, loser_team}
    built = {}      # no -> match dict（出力用）
    for f in ko:
        parts = [p.strip() for p in re.split(r"[×x✕]", f["label"])]
        home = _resolve_token(parts[0], finals, resolved) if len(parts) == 2 else {"label_ja": f["label"], "label_en": f["label"]}
        away = _resolve_token(parts[1], finals, resolved) if len(parts) == 2 else {"label_ja": "", "label_en": ""}

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
    # 各 KO 試合の 2 feeder（M<x>勝者 × M<y>勝者）から木を作り、 決勝から DFS して
    # R32（葉）の縦順を決める。 上位ラウンドの順は配下葉位置の平均で導く。
    feeders = {}
    for f in ko:
        ws = [int(mm.group(1)) for p in re.split(r"[×x✕]", f["label"])
              for mm in [_WINNER.match(p.strip())] if mm]
        if len(ws) == 2:
            feeders[f["no"]] = ws
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
