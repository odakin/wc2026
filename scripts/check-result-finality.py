#!/usr/bin/env python3
"""結果記録の「早すぎ確定」機械ゲート — 試合が物理的に終わり得ない時刻の新規 results 追記を検出する。

背景 (2 回の実事故):
  - M76 (2026-06-30): kickoff+75 分 (= 後半途中) に「0-1」を最終結果として記録 + 同 run で
    M91 に勝者を伝播 → 21 分後に「match in progress 1-1」で revert。
  - M82 (2026-07-02): kickoff+113 分 (= 90 分終了直後、実際は 2-2 で延長突入) に古いライブ
    スコア「0-2」を最終結果として記録 + 同 run で M94 に敗者側を伝播 → 訂正 2 回を経て
    ベルギー 3-2 に確定したが、旧伝播設計では焼き込みが残った。
  根 = intake が「試合終了 (FT)」の確認なしにライブスコアを最終結果として書くこと。
  判断を伴う FT 確認自体は AUTO_UPDATE.md §5 の規律 (= FT 明示の 2 ソース確認) が担い、
  本ゲートは「その時刻に FT はあり得ない」という**物理下限だけを機械強制**する安価な backstop。

検算 (新規追記 entry のみ、 既存 entry の訂正は対象外):
  - 新規 = working tree の results.yaml にあって HEAD の results.yaml に無い "no"。
    (= 訂正は FT 後にしか起きない正当操作なので gate しない。 auto-update flow では
    commit 前に走るため HEAD = 直前の公開状態。)
  - 各新規 entry を fixtures.yaml の同 no の start_jst と突合:
      now < start + 105 分  → 🔴 FAIL (90 分 + HT15 分 = stoppage ゼロでも FT 不可能な窓)
      PK 決着 (hg==ag ∧ winner) なのに now < start + 145 分 → 🔴 FAIL
        (105 + ET 前 break + 延長 30 分 + PK 数分 の下限)
  - FAIL 時 exit 1: 該当 entry を results.yaml から外して次 cycle に回す (FT 確認後に記録)。

⚠️ 限界 (正直 framing): 下限検算なので「+112 分に 90 分決着として記録された実は延長中の試合」
   (= M82 型そのもの) は素通りする。 これは機械では判別不能 — 一次防御は §5 の FT 明示確認、
   最終安全網は propagate-knockout.py の再導出 (= 訂正が bracket に自動追従)。 本ゲートが
   確実に殺すのは M76 型 (= 試合中の記録) の粗い事故。

usage:
  python3 scripts/check-result-finality.py             # 検算 (finding 時 exit 1)
  python3 scripts/check-result-finality.py --selftest  # ロジックの自己検証
"""
import argparse
import datetime
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "data" / "fixtures.yaml"
RESULTS = ROOT / "data" / "results.yaml"

MIN_FT_MIN = 105   # kickoff → FT の物理下限 (90 分 + ハーフタイム 15 分、 stoppage ゼロ想定)
MIN_PK_MIN = 145   # kickoff → PK 決着の物理下限 (105 + ET 前 break + 延長 30 分 + PK 最短)


def _matches(yaml_text):
    data = yaml.safe_load(yaml_text) or {}
    return {m["no"]: m for m in (data.get("matches") or []) if "no" in m}


def find_premature(new_entries, fidx, now):
    """新規 results entries (dict no→entry) を検算し finding 文字列 list を返す。"""
    findings = []
    for no, r in sorted(new_entries.items()):
        f = fidx.get(no)
        if not f or not f.get("start_jst"):
            continue  # no 不一致は check-match-numbers の領分
        start = datetime.datetime.fromisoformat(f["start_jst"])
        elapsed = (now - start).total_seconds() / 60
        is_pk = r.get("hg") is not None and r.get("hg") == r.get("ag") and r.get("winner")
        limit = MIN_PK_MIN if is_pk else MIN_FT_MIN
        kind = "PK 決着" if is_pk else "FT"
        if elapsed < limit:
            findings.append(
                f"Match {no} ({r.get('home')} {r.get('hg')}-{r.get('ag')} {r.get('away')}): "
                f"kickoff+{elapsed:.0f}分 での新規記録は {kind} の物理下限 {limit}分 より早い "
                f"(kickoff {f['start_jst']}) → 試合中のライブスコアを最終結果として記録した疑い。 "
                f"この entry を外し、 FT を 2 ソースで確認してから次 run で記録する")
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        sys.exit(0)

    try:
        head_text = subprocess.run(
            ["git", "-C", str(ROOT), "show", "HEAD:data/results.yaml"],
            capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        print("⚠ HEAD の results.yaml を取得できず (初回 commit?) → gate skip (fail-open)", file=sys.stderr)
        sys.exit(0)

    head = _matches(head_text)
    work = _matches(RESULTS.read_text())
    new_entries = {no: r for no, r in work.items() if no not in head}
    if not new_entries:
        print("✅ 新規 results 追記なし → finality gate 対象なし。")
        sys.exit(0)

    fidx = _matches(FIXTURES.read_text())
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    findings = find_premature(new_entries, fidx, now)
    if findings:
        for w in findings:
            print(f"🔴 {w}", file=sys.stderr)
        print("finality gate FAIL — 早すぎ記録を results.yaml から外して再実行。", file=sys.stderr)
        sys.exit(1)
    print(f"✅ finality gate OK: 新規 {len(new_entries)} 件すべて物理下限より後の記録。")
    sys.exit(0)


def _selftest():
    JST = datetime.timezone(datetime.timedelta(hours=9))
    fidx = {76: {"no": 76, "start_jst": "2026-06-30T02:00:00+09:00"},
            82: {"no": 82, "start_jst": "2026-07-02T05:00:00+09:00"}}

    def at(iso):
        return datetime.datetime.fromisoformat(iso).replace(tzinfo=JST)

    r_dec = {"no": 76, "home": "A", "away": "B", "hg": 0, "ag": 1}
    r_pk = {"no": 82, "home": "C", "away": "D", "hg": 2, "ag": 2, "winner": "C"}

    # M76 実事故 regression: kickoff+75分 の決着記録 → FAIL
    f = find_premature({76: r_dec}, fidx, at("2026-06-30T03:15:00"))
    assert len(f) == 1 and "Match 76" in f[0] and "+75分" in f[0], f
    # 境界: +104 FAIL / +106 PASS
    assert find_premature({76: r_dec}, fidx, at("2026-06-30T03:44:00"))
    assert not find_premature({76: r_dec}, fidx, at("2026-06-30T03:46:00"))
    # PK 決着: +120 FAIL (下限 145) / +150 PASS
    assert find_premature({82: r_pk}, fidx, at("2026-07-02T07:00:00"))
    assert not find_premature({82: r_pk}, fidx, at("2026-07-02T07:30:00"))
    # 引き分け winner 無し (= PK 勝者未記録) は PK 閾値でなく FT 閾値 (未解決は伝播側が警告)
    r_draw = {"no": 82, "home": "C", "away": "D", "hg": 2, "ag": 2}
    assert not find_premature({82: r_draw}, fidx, at("2026-07-02T07:00:00"))
    # fixtures に無い no は skip (check-match-numbers の領分)
    assert not find_premature({999: dict(r_dec, no=999)}, fidx, at("2026-06-30T02:10:00"))
    # 翌日以降の記録 (通常運用) は PASS
    assert not find_premature({76: r_dec, 82: r_pk}, fidx, at("2026-07-03T09:00:00"))
    print("✅ check-result-finality selftest OK "
          "(M76 regression / 境界 105分 / PK 145分 / draw非PK / no不一致skip / 通常記録)")


if __name__ == "__main__":
    main()
