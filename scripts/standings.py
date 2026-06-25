#!/usr/bin/env python3
"""results.yaml から各グループの順位表を計算する派生ビュー。

results.yaml = 消化済み試合の生事実 (SoT)。順位はそこから決定論的に算出するので、
順位表を手で二重管理しない (= 結果を追記 → 再実行で順位が更新)。

順位の tiebreak は **FIFA 2026 大会規定** を実装 (2018/2022 と順序が違う = 直接対決が先):
  0 勝点 (これが等しいチーム同士を以下で分ける)
  1 直接対決 (head-to-head) の勝点
  2 直接対決の得失点差
  3 直接対決の総得点
  4 全試合の得失点差
  5 全試合の総得点
  6 フェアプレー (規律) ポイント   ← カード減点。results.yaml meta.tiebreak.conduct
  7 FIFA ランキング               ← results.yaml meta.tiebreak.fifa_ranking
  (※ 2026 で「抽選」は廃止)
head-to-head(1-3) は同点サブグループ内の試合だけで計算し、サブグループが縮むたび再計算する。
6/7 のデータが無く 1-5 で決着しない場合のみ ※ (= 未決着) を付ける。計算可能な範囲では確定。

usage:
  python3 scripts/standings.py            # 全グループの順位表 + 結果を表示
  python3 scripts/standings.py --write     # standings.md も生成 (リポ閲覧用)
  python3 scripts/standings.py --group F   # 特定グループのみ
"""
import argparse
from pathlib import Path
from collections import defaultdict
import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results.yaml"   # SoT は data/ 配下 (build.py と共有)
GROUP_ORDER = list("ABCDEFGHIJKL")


def compute(matches):
    table = defaultdict(lambda: defaultdict(
        lambda: dict(P=0, W=0, D=0, L=0, GF=0, GA=0, Pts=0)))
    for m in matches:
        g = m.get("group")
        if not g:          # knockout 結果 (group 無し・no が鍵) は順位集計の対象外
            continue
        for team, gf, ga in ((m["home"], m["hg"], m["ag"]),
                             (m["away"], m["ag"], m["hg"])):
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
    """サブグループ S 内の対戦だけで集計した {team: {Pts,GF,GA}}。"""
    st = {t: dict(Pts=0, GF=0, GA=0) for t in S}
    for m in matches:
        if m.get("group") != g or m["home"] not in st or m["away"] not in st:
            continue
        for t, gf, ga in ((m["home"], m["hg"], m["ag"]),
                          (m["away"], m["ag"], m["hg"])):
            st[t]["Pts"] += 3 if gf > ga else (1 if gf == ga else 0)
            st[t]["GF"] += gf
            st[t]["GA"] += ga
    return st


def rank_group(g, matches, conduct=None, fifa_rank=None):
    """FIFA 2026 規定でグループ g を順位付け。 returns [(team, overall_stats, tied)]。
    tied=True = 計算可能な criterion (1-7 のうち手元データで埋まる範囲) で決着しなかったチーム。"""
    conduct = conduct or {}
    fifa_rank = fifa_rank or {}
    overall = compute(matches)[g]
    teams = list(overall)

    def gd(d, t):
        return d[t]["GF"] - d[t]["GA"]

    def h2h_block(S):
        """criteria 1-3 (直接対決) を S に適用。 split した sub-run ごとに再帰。
        返り値 = 順序付き sub-run (list[list])。 割れなければ [S]。"""
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
        """criteria 4-7 (全試合GD → 全試合GF → フェアプレー → FIFAランク) を lexicographic に。"""
        crits = (lambda t: gd(overall, t),
                 lambda t: overall[t]["GF"],
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
    """隣接ペアが (勝点, GD, 総得点) 同値なのに順序が付いた箇所を「何で確定したか」で注記。"""
    notes = []
    for i in range(1, len(rows)):
        (a, sa, _), (b, sb, tied_b) = rows[i - 1], rows[i]
        ka = (sa["Pts"], sa["GF"] - sa["GA"], sa["GF"])
        kb = (sb["Pts"], sb["GF"] - sb["GA"], sb["GF"])
        if ka != kb:
            continue
        h = _h2h_stats(g, {a, b}, matches)
        if (h[a]["Pts"], h[a]["GF"] - h[a]["GA"], h[a]["GF"]) != \
           (h[b]["Pts"], h[b]["GF"] - h[b]["GA"], h[b]["GF"]):
            basis = "直接対決"
        elif a in conduct and b in conduct and conduct[a] != conduct[b]:
            basis = f"フェアプレーポイント ({a} {conduct[a]:+d} / {b} {conduct[b]:+d})"
        elif a in fifa_rank and b in fifa_rank:
            basis = "FIFA ランキング"
        elif tied_b:
            basis = "（未決着 = フェアプレー/FIFAランクのデータ待ち）"
        else:
            basis = "直接対決"
        notes.append(f"{i}位 {a} / {i+1}位 {b}: {basis} で確定")
    return notes


def fmt_group(g, matches, conduct, fifa_rank):
    out = [f"### グループ{g}"]
    rows = rank_group(g, matches, conduct, fifa_rank)
    out.append("| 順 | チーム | 試 | 勝 | 分 | 敗 | 得 | 失 | 差 | 点 |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, (t, s, tied) in enumerate(rows, 1):
        gd = s["GF"] - s["GA"]
        mark = "※" if tied else ""
        out.append(f"| {i}{mark} | {t} | {s['P']} | {s['W']} | {s['D']} | {s['L']} | "
                   f"{s['GF']} | {s['GA']} | {gd:+d} | **{s['Pts']}** |")
    for n in tie_basis(g, rows, matches, conduct, fifa_rank):
        out.append(f"- ⚖️ {n}")
    res = [m for m in matches if m.get("group") == g]
    out.append("")
    for m in sorted(res, key=lambda x: (x["md"], str(x.get("date", "")))):
        line = f"- 第{m['md']}節: {m['home']} {m['hg']}-{m['ag']} {m['away']}"
        if m.get("note"):
            line += f" — {m['note']}"
        out.append(line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="standings.md を生成")
    ap.add_argument("--group", help="特定グループのみ (例: F)")
    args = ap.parse_args()

    data = yaml.safe_load(RESULTS.read_text())
    meta = data["meta"]
    matches = data["matches"]
    table = compute(matches)
    tb = meta.get("tiebreak", {}) or {}
    conduct = tb.get("conduct", {}) or {}
    fifa_rank = tb.get("fifa_ranking", {}) or {}

    groups = [args.group.upper()] if args.group else \
        [g for g in GROUP_ORDER if g in table]
    blocks = [fmt_group(g, matches, conduct, fifa_rank) for g in groups]
    body = "\n\n".join(blocks)

    crit_line = ("tiebreak: FIFA2026規定 = 直接対決(勝点→得失差→総得点)→全試合得失差"
                 "→全試合総得点→フェアプレー点→FIFAランク (抽選廃止、※=データ待ちで未決着)")
    print(f"2026 FIFA World Cup グループステージ 順位表\n"
          f"as_of: {meta['as_of']} (JST) / 記録試合数: {len(matches)} / {crit_line}\n")
    print(body)

    if args.write and not args.group:
        src = tb.get("source")
        src_line = f"- フェアプレー点等の出典: {src}\n" if src else ""
        md = (f"<!-- ⚠ 生成物: scripts/standings.py が results.yaml から生成。直接編集しない。\n"
              f"     results.yaml を更新したら `python3 scripts/standings.py --write` で再生成。 -->\n\n"
              f"# 2026 FIFA World Cup — グループステージ順位表\n\n"
              f"- **as_of**: {meta['as_of']} (JST スナップショット)\n"
              f"- **記録試合数**: {len(matches)}\n"
              f"- {meta['note']}\n"
              f"- {crit_line}\n"
              f"{src_line}\n"
              + body + "\n")
        (ROOT / "standings.md").write_text(md)
        print(f"\nwrote {ROOT/'standings.md'}")


if __name__ == "__main__":
    main()
