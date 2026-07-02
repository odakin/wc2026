#!/usr/bin/env python3
"""決勝トーナメントの「勝者→次ラウンドの対戦カード」を results.yaml から決定論的に伝播する。

決勝T の fixtures.yaml の label はブラケットスロット表記で始まる:
  R16  "M73勝者 × M75勝者"
  QF   "M89勝者 × M90勝者"
  SF   "M97勝者 × M98勝者"
  3位  "M101敗者 × M102敗者"
  決勝 "M101勝者 × M102勝者"
各スロット "M<no>勝者"/"M<no>敗者" は results.yaml に記録された Match<no> の勝者/敗者で
一意に決まる。 本 script は results からそれを解決して fixtures.yaml の label を実チーム名に
書き換える (= 純粋に決定論的、 判断ゼロ)。

⚠️ チェーンしない設計: 各ラウンドは「**前ラウンドの results**」だけから解決する。 例えば QF の
   "M89勝者" は results[89] (= R16 の結果) の winner を引く。 fixtures→fixtures の連鎖は無いので、
   結果が記録されるたびに 1 段ずつ確実に埋まる (= 早期 partial も per-side で埋まる)。

ブラケット構造の SoT = 本 script の BRACKET_SLOTS 定数 (= FIFA 公式の固定トーナメント表):
  fixtures.yaml の label は「slot が構造の正本を兼ねる」旧設計だったが、 伝播が label を実チーム名で
  上書きした瞬間に構造情報が消え、 **後から results を訂正しても label に反映されない** 焼き込み事故が
  起きた (= 2026-07-02 M82 誤記録 [セネガル勝ち] 時代の伝播が M94 に セネガル を焼き込み、 その後の
  ベルギー 3-2 訂正が届かなかった)。 現設計は毎回 BRACKET_SLOTS ⊕ results から全 knockout label を
  **再導出**して現 label と比較する = results の訂正・取り消しが自動で label に伝わる (自己修復)。
  feeder 結果が未記録/未解決に戻れば label も slot 表記に戻る (= M76 早すぎ記録 revert と同じ挙動を自動化)。

勝者の確定 (= 決勝T 固有の難所):
  決勝T は延長・PK があり score (hg/ag) だけでは勝者が出ない。 results の knockout entry には
  `winner:` フィールド (チーム名) を付ける。 解決順:
    1. `winner` があればそれ (= PK 戦・明示)。 winner は home/away のどちらかに一致必須。
    2. 無ければ hg/ag の大きい方。
    3. 引き分け (hg==ag) で winner 無し → **未解決** (= PK の勝者未記録)。 slot を維持し ⚠ で surface。

冪等: 同じ results に対し何度走らせても同じ fixtures になる (= label は常に BRACKET_SLOTS ⊕ results の
   純関数として再導出され、 一致していれば no-op)。 未解決の feeder は slot のまま残る (= 早すぎる埋めをしない)。

整形保持: PyYAML の dump は flow-style inline dict とコメントを壊すため、 該当行を
   **surgical text 置換** する (= `label: "<old>"` → `label: "<new>"` のみ、 他は touch しない)。

usage:
  python3 scripts/propagate-knockout.py            # dry-run (変更点を表示するだけ)
  python3 scripts/propagate-knockout.py --apply     # fixtures.yaml を書き換える
  python3 scripts/propagate-knockout.py --selftest  # ロジックの自己検証
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "data" / "fixtures.yaml"
RESULTS = ROOT / "data" / "results.yaml"

SLOT_RE = re.compile(r"^M(\d+)(勝者|敗者)$")
SEP = " × "  # label のチーム区切り (全角 × の前後 space)

# ブラケット構造の SoT (FIFA 2026 公式トーナメント表、 大会中不変)。
# R32 (M73-88) はグループ順位から決まる別機構なのでここに含めない (= label を touch しない)。
# 検証: 伝播前の fixtures.yaml (commit c64c516) の label と一致することを確認済み。
BRACKET_SLOTS = {
    # R16
    89: "M74勝者 × M77勝者",
    90: "M73勝者 × M75勝者",
    91: "M76勝者 × M78勝者",
    92: "M79勝者 × M80勝者",
    93: "M83勝者 × M84勝者",
    94: "M81勝者 × M82勝者",
    95: "M86勝者 × M88勝者",
    96: "M85勝者 × M87勝者",
    # QF
    97: "M89勝者 × M90勝者",
    98: "M93勝者 × M94勝者",
    99: "M91勝者 × M92勝者",
    100: "M95勝者 × M96勝者",
    # SF / 3位 / 決勝
    101: "M97勝者 × M98勝者",
    102: "M99勝者 × M100勝者",
    103: "M101敗者 × M102敗者",
    104: "M101勝者 × M102勝者",
}


def winner_loser(r):
    """result dict r から (winner, loser) を返す。 確定不能なら (None, None)。"""
    home, away = r.get("home"), r.get("away")
    w = r.get("winner")
    if w:
        if w == home:
            return home, away
        if w == away:
            return away, home
        return None, None  # winner が参加者に一致しない = データ誤り
    hg, ag = r.get("hg"), r.get("ag")
    if hg is None or ag is None:
        return None, None
    if hg > ag:
        return home, away
    if ag > hg:
        return away, home
    return None, None  # 引き分けで winner 未記録 (= PK 勝者未記録)


def resolve_side(side, ridx):
    """label の片側 (= "M73勝者" / "M73敗者" / 実チーム名) を解決する。
    解決できなければ元の文字列をそのまま返す (= slot 維持)。"""
    m = SLOT_RE.match(side.strip())
    if not m:
        return side  # 既に実チーム名 / 非 slot 表記
    no, kind = int(m.group(1)), m.group(2)
    r = ridx.get(no)
    if not r:
        return side  # feeder 未実施
    w, l = winner_loser(r)
    team = w if kind == "勝者" else l
    return team if team else side  # 未解決 (PK 勝者未記録等) は slot 維持


def new_label(label, ridx):
    """label 全体を解決した新 label を返す (= 各 side を独立に解決)。"""
    parts = label.split(SEP)
    if len(parts) != 2:
        return label  # 想定外フォーマットは touch しない
    a = resolve_side(parts[0], ridx)
    b = resolve_side(parts[1], ridx)
    return f"{a}{SEP}{b}"


def unresolved_feeder_warnings(ridx):
    """BRACKET_SLOTS が参照する feeder のうち、 結果はあるのに勝者が確定できないものを警告列挙
    (= PK 勝者未記録 / winner がチーム名不一致のデータ誤り)。"""
    warns = []
    feeders = set()
    for slots in BRACKET_SLOTS.values():
        for side in slots.split(SEP):
            mm = SLOT_RE.match(side.strip())
            if mm:
                feeders.add(int(mm.group(1)))
    for no in sorted(feeders):
        r = ridx.get(no)
        if not r:
            continue
        w, _ = winner_loser(r)
        if w:
            continue
        score = f"{r.get('home')} {r.get('hg')}-{r.get('ag')} {r.get('away')}"
        if r.get("winner"):
            warns.append(f"Match {no} ({score}) の winner: \"{r.get('winner')}\" が home/away の"
                         f"どちらとも一致しない (= データ誤り) → results.yaml を修正して再実行")
        elif r.get("hg") is not None and r.get("hg") == r.get("ag"):
            warns.append(f"Match {no} ({score}) は引き分けだが winner 未記録 "
                         f"→ PK 勝者を winner: に追記して再実行")
    return warns


def compute_changes(fmatches, ridx):
    """(no, old_label, new_label) の変更リストを返す。

    label の現在値でなく BRACKET_SLOTS (構造の SoT) から毎回**再導出**して比較する。
    = 新規解決だけでなく、 誤伝播の訂正 (results 訂正後の焼き込み残留) や、
    feeder 結果が取り消された時の slot 復帰も同じ 1 本の経路で扱う。"""
    changes = []
    for m in fmatches:
        slots = BRACKET_SLOTS.get(m.get("no"))
        if slots is None:
            continue
        old = str(m.get("label", ""))
        new = new_label(slots, ridx)
        if new != old:
            changes.append((m["no"], old, new))
    return changes


def apply_changes(text, changes):
    """fixtures.yaml の text に対し、 該当 no の行の label を surgical 置換した text を返す。"""
    lines = text.splitlines(keepends=True)
    applied, missed = [], []
    for no, old, new in changes:
        no_re = re.compile(rf'"no":\s*{no}(?!\d)')
        needle = f'label: "{old}"'
        repl = f'label: "{new}"'
        for i, ln in enumerate(lines):
            if no_re.search(ln) and needle in ln:
                lines[i] = ln.replace(needle, repl)
                applied.append((no, old, new))
                break
        else:
            missed.append((no, old, new))
    return "".join(lines), applied, missed


def load_ridx():
    data = yaml.safe_load(RESULTS.read_text()) or {}
    return {r["no"]: r for r in (data.get("matches") or []) if "no" in r}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="fixtures.yaml を書き換える (既定は dry-run)")
    ap.add_argument("--selftest", action="store_true", help="ロジックの自己検証")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        sys.exit(0)

    fdata = yaml.safe_load(FIXTURES.read_text()) or {}
    fmatches = fdata.get("matches") or []
    ridx = load_ridx()

    changes = compute_changes(fmatches, ridx)
    warns = unresolved_feeder_warnings(ridx)

    for w in warns:
        print(f"⚠ {w}", file=sys.stderr)

    if not changes:
        print("✅ 伝播対象なし (= 未解決 slot または既に解決済み)。")
        sys.exit(0)

    for no, old, new in changes:
        print(f"M{no}: {old}  →  {new}")

    if not args.apply:
        print(f"\n[dry-run] {len(changes)} 件。 書き換えるには --apply を付ける。", file=sys.stderr)
        sys.exit(0)

    text = FIXTURES.read_text()
    new_text, applied, missed = apply_changes(text, changes)
    if missed:
        for no, old, new in missed:
            print(f"❌ M{no} の行が見つからず未適用: label: \"{old}\"", file=sys.stderr)
        print("中止 (= fixtures.yaml は変更しない)。", file=sys.stderr)
        sys.exit(1)
    FIXTURES.write_text(new_text)
    print(f"\n✅ {len(applied)} 件の label を fixtures.yaml に適用。 standings/build を再生成して公開する。")
    sys.exit(0)


def _selftest():
    # winner_loser
    assert winner_loser({"home": "A", "away": "B", "hg": 1, "ag": 1, "winner": "A"}) == ("A", "B")
    assert winner_loser({"home": "A", "away": "B", "hg": 1, "ag": 1, "winner": "B"}) == ("B", "A")
    assert winner_loser({"home": "A", "away": "B", "hg": 2, "ag": 0}) == ("A", "B")
    assert winner_loser({"home": "A", "away": "B", "hg": 0, "ag": 3}) == ("B", "A")
    assert winner_loser({"home": "A", "away": "B", "hg": 1, "ag": 1}) == (None, None)  # 引分・winner無
    assert winner_loser({"home": "A", "away": "B", "hg": 1, "ag": 1, "winner": "Z"}) == (None, None)  # 不一致
    # resolve_side
    ridx = {73: {"home": "南ア", "away": "カナダ", "hg": 2, "ag": 1},
            75: {"home": "蘭", "away": "モロッコ", "hg": 1, "ag": 1, "winner": "モロッコ"},
            78: {"home": "コートジ", "away": "ノル", "hg": 0, "ag": 0}}  # PK 勝者未記録
    assert resolve_side("M73勝者", ridx) == "南ア"
    assert resolve_side("M73敗者", ridx) == "カナダ"
    assert resolve_side("M75勝者", ridx) == "モロッコ"
    assert resolve_side("M75敗者", ridx) == "蘭"
    assert resolve_side("M78勝者", ridx) == "M78勝者"  # PK 未解決 → slot 維持
    assert resolve_side("M99勝者", ridx) == "M99勝者"  # feeder 未実施
    assert resolve_side("ブラジル", ridx) == "ブラジル"  # 実チーム名は不変
    # new_label
    assert new_label("M73勝者 × M75勝者", ridx) == "南ア × モロッコ"  # 両解決
    assert new_label("M73勝者 × M78勝者", ridx) == "南ア × M78勝者"  # partial (片側 PK 未)
    assert new_label("M101勝者 × M102勝者", ridx) == "M101勝者 × M102勝者"  # 両未実施
    assert new_label("南ア × モロッコ", ridx) == "南ア × モロッコ"  # 冪等 (再適用で不変)
    # compute_changes (BRACKET_SLOTS からの再導出: 新規解決 / 焼き込み訂正 / slot 復帰 / 対象外不変)
    ridx2 = dict(ridx)
    ridx2[81] = {"home": "米", "away": "ボスニア", "hg": 2, "ag": 0}
    ridx2[82] = {"home": "ベルギー", "away": "セネガル", "hg": 3, "ag": 2, "winner": "ベルギー"}
    fm = [{"no": 90, "stage": "r16", "label": "M73勝者 × M75勝者"},   # 新規解決
          {"no": 94, "stage": "r16", "label": "米 × セネガル"},        # 焼き込み残留 (= M94 事故 regression)
          {"no": 91, "stage": "r16", "label": "ブラジル × 日本"},      # feeder 未確定に戻った → slot 復帰
          {"no": 89, "stage": "r16", "label": "M74勝者 × M77勝者"},   # feeder 未実施 → 不変
          {"no": 73, "stage": "r32", "label": "南ア × カナダ"},        # BRACKET_SLOTS 対象外 → 不変
          {"no": 5, "stage": "group", "label": "X × Y"}]              # group → 不変
    ch = compute_changes(fm, ridx2)
    assert ch == [(90, "M73勝者 × M75勝者", "南ア × モロッコ"),
                  (94, "米 × セネガル", "米 × ベルギー"),
                  (91, "ブラジル × 日本", "M76勝者 × M78勝者")], ch
    # 冪等: 再導出結果と一致する label は変更なし
    fm_ok = [{"no": 90, "stage": "r16", "label": "南ア × モロッコ"},
             {"no": 94, "stage": "r16", "label": "米 × ベルギー"}]
    assert compute_changes(fm_ok, ridx2) == [], compute_changes(fm_ok, ridx2)
    # apply_changes (surgical 置換 + 整形/コメント保持 + no 境界)
    text = ('matches:\n'
            '  # comment line\n'
            '  - {"no": 9, stage: r16, label: "M73勝者 × M75勝者", venue: "X"}\n'
            '  - {"no": 90, stage: r16, label: "M73勝者 × M75勝者", venue: "Y"}\n')
    out, applied, missed = apply_changes(text, [(90, "M73勝者 × M75勝者", "南ア × モロッコ")])
    assert not missed, missed
    assert '"no": 9, stage: r16, label: "M73勝者 × M75勝者"' in out  # no=9 は不変 (境界)
    assert '"no": 90, stage: r16, label: "南ア × モロッコ", venue: "Y"' in out  # no=90 のみ置換
    assert "# comment line" in out  # コメント保持
    # feeder 警告 (PK 勝者未記録 / winner チーム名不一致)
    warns = unresolved_feeder_warnings(ridx)
    assert len(warns) == 1 and "Match 78" in warns[0] and "winner 未記録" in warns[0], warns
    ridx3 = dict(ridx)
    ridx3[77] = {"home": "A", "away": "B", "hg": 1, "ag": 0, "winner": "Z"}  # 不一致
    warns = unresolved_feeder_warnings(ridx3)
    assert len(warns) == 2 and any("Match 77" in w and "一致しない" in w for w in warns), warns
    # BRACKET_SLOTS 整合性 (全 slot が M73-102 の勝者/敗者を参照、 各 feeder は高々 2 slot に登場)
    from collections import Counter
    refs = Counter()
    for slots in BRACKET_SLOTS.values():
        a, b = slots.split(SEP)
        for side in (a, b):
            mm = SLOT_RE.match(side)
            assert mm, slots
            refs[int(mm.group(1))] += 1
    assert set(refs) == set(range(73, 103)), sorted(refs)  # M73-102 が漏れなく参照される
    assert all(refs[n] == (2 if n in (101, 102) else 1) for n in refs), refs  # SF のみ勝者+敗者で 2 回
    print("✅ propagate-knockout selftest OK "
          "(winner判定 / side解決 / partial / 再導出=新規+訂正+復帰 / 冪等 / surgical置換 / no境界 / feeder警告 / bracket整合)")


if __name__ == "__main__":
    main()
