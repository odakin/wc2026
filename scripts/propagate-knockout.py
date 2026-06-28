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

勝者の確定 (= 決勝T 固有の難所):
  決勝T は延長・PK があり score (hg/ag) だけでは勝者が出ない。 results の knockout entry には
  `winner:` フィールド (チーム名) を付ける。 解決順:
    1. `winner` があればそれ (= PK 戦・明示)。 winner は home/away のどちらかに一致必須。
    2. 無ければ hg/ag の大きい方。
    3. 引き分け (hg==ag) で winner 無し → **未解決** (= PK の勝者未記録)。 slot を維持し ⚠ で surface。

冪等: 同じ results に対し何度走らせても同じ fixtures になる (= 解決済み side は実チーム名なので
   slot regex に当たらず不変)。 未解決の feeder は slot のまま残る (= 早すぎる埋めをしない)。

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

# slot 表記を持つ決勝T stage (r32 は既に実チームなので no-op だが、 一般性のため含める)。
KNOCKOUT_STAGES = {"r32", "r16", "qf", "sf", "third", "final"}
SLOT_RE = re.compile(r"^M(\d+)(勝者|敗者)$")
SEP = " × "  # label のチーム区切り (全角 × の前後 space)


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


def unresolved_pk_warnings(fmatches, ridx):
    """feeder が引き分けなのに winner 未記録の slot を警告として列挙 (= PK 勝者待ち)。"""
    warns = []
    seen = set()
    for m in fmatches:
        if m.get("stage") not in KNOCKOUT_STAGES:
            continue
        for side in str(m.get("label", "")).split(SEP):
            mm = SLOT_RE.match(side.strip())
            if not mm:
                continue
            no = int(mm.group(1))
            if no in seen:
                continue
            r = ridx.get(no)
            if r and r.get("hg") == r.get("ag") and not r.get("winner") and r.get("hg") is not None:
                seen.add(no)
                warns.append(f"Match {no} ({r.get('home')} {r.get('hg')}-{r.get('ag')} {r.get('away')}) "
                             f"は引き分けだが winner 未記録 → PK 勝者を winner: に追記して再実行")
    return warns


def compute_changes(fmatches, ridx):
    """(no, old_label, new_label) の変更リストを返す。"""
    changes = []
    for m in fmatches:
        if m.get("stage") not in KNOCKOUT_STAGES:
            continue
        old = str(m.get("label", ""))
        new = new_label(old, ridx)
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
    warns = unresolved_pk_warnings(fmatches, ridx)

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
    # compute_changes (stage filter + 変更検出)
    fm = [{"no": 90, "stage": "r16", "label": "M73勝者 × M75勝者"},
          {"no": 91, "stage": "r16", "label": "M101勝者 × M102勝者"},
          {"no": 73, "stage": "r32", "label": "南ア × カナダ"},
          {"no": 5, "stage": "group", "label": "X × Y"}]
    ch = compute_changes(fm, ridx)
    assert ch == [(90, "M73勝者 × M75勝者", "南ア × モロッコ")], ch
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
    # unresolved PK 警告
    warns = unresolved_pk_warnings([{"no": 91, "stage": "qf", "label": "M78勝者 × M77勝者"}], ridx)
    assert len(warns) == 1 and "Match 78" in warns[0], warns
    print("✅ propagate-knockout selftest OK "
          "(winner判定 / side解決 / partial / 冪等 / stage filter / surgical置換 / no境界 / PK警告)")


if __name__ == "__main__":
    main()
