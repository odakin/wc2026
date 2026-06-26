#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自動更新ジョブの稼働 heartbeat（死活監視）。

背景: 30 分ごとの自動更新は AUTO_UPDATE.md §7 で「新規が無い回は commit しない（no-op）」
設計のため、commit が途絶えても「試合が無いだけ」か「ジョブが死んだ」かを git から区別できない。
2026-06-26 に実際に区別できず、6/26 の 6 試合（日本戦含む）が丸ごと取りこぼされた
（Claude アカウント切替で iMac の scheduled task 登録が引き継がれず停止していた）。

対策: 自動更新ジョブが **毎回（no-op の回も含めて）** heartbeat を打刻し commit/push する。
これで別マシンからでも「最後にジョブが回ったのはいつか」が git だけで判る。

- `--beat`  : heartbeat.json を今の時刻で更新（results.yaml の as_of / 記録試合数も一緒に刻む）。
              自動更新ジョブが毎回これを呼ぶ（AUTO_UPDATE.md に配線）。
- `--check` : heartbeat.json を読み、最終打刻からの経過を表示。stale 閾値超で exit 1。
              別マシンで「iMac のジョブ動いてる?」を確認するときに使う。
- `--selftest` : 内蔵テスト。

heartbeat.json は public リポに commit される。個人情報・ホスト名は刻まない（試合データと同じく公開情報のみ）。
タイムスタンプは UTC（機械可読）と JST（人間可読）の併記。

使い方:
  python3 scripts/heartbeat.py --beat            # ジョブが毎回打刻
  python3 scripts/heartbeat.py --check            # 死活確認（既定 stale 閾値 75 分）
  python3 scripts/heartbeat.py --check --stale-min 180
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results.yaml"
HEARTBEAT = ROOT / "heartbeat.json"

JST = timezone(timedelta(hours=9))

# 30 分ジョブが 2 回以上連続で落ちたら異常とみなす既定閾値（30*2 + 余裕）。
DEFAULT_STALE_MIN = 75


def _now():
    return datetime.now(timezone.utc)


def _results_summary():
    """results.yaml の as_of と記録試合数を返す（読めなければ None）。"""
    try:
        data = yaml.safe_load(RESULTS.read_text(encoding="utf-8"))
        return {
            "as_of": data.get("meta", {}).get("as_of"),
            "matches_recorded": len(data.get("matches", [])),
        }
    except Exception:
        return {"as_of": None, "matches_recorded": None}


def beat(now=None):
    """heartbeat.json を現在時刻で更新する。"""
    now = now or _now()
    payload = {
        "last_run_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_run_jst": now.astimezone(JST).strftime("%Y-%m-%d %H:%M JST"),
        "interval_min": 30,
        "note": "wc2026 自動更新ジョブの死活 heartbeat。毎回（no-op 含む）打刻され commit される。",
    }
    payload.update(_results_summary())
    HEARTBEAT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def _parse_last_run(payload):
    return datetime.strptime(payload["last_run_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )


def check(stale_min=DEFAULT_STALE_MIN, now=None):
    """(stale: bool, message: str) を返す。"""
    now = now or _now()
    if not HEARTBEAT.exists():
        return True, f"❌ heartbeat.json が無い（一度も打刻されていない）: {HEARTBEAT}"
    payload = json.loads(HEARTBEAT.read_text(encoding="utf-8"))
    last = _parse_last_run(payload)
    age_min = (now - last).total_seconds() / 60.0
    stamp = (
        f"最終打刻 {payload.get('last_run_jst', '?')} / "
        f"as_of {payload.get('as_of', '?')} / {payload.get('matches_recorded', '?')}試合"
    )
    if age_min > stale_min:
        h = age_min / 60.0
        return True, (
            f"🚨 自動更新ジョブが {age_min:.0f}分（{h:.1f}時間）止まっている疑い"
            f"（閾値 {stale_min}分）。{stamp}\n"
            f"   → iMac の scheduled task を確認（list_scheduled_tasks / AUTO_UPDATE.md で再登録）"
        )
    return False, f"✅ 自動更新ジョブは稼働中（{age_min:.0f}分前に打刻）。{stamp}"


def selftest():
    now = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
    # 鮮度内
    fresh = {
        "last_run_utc": (now - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_run_jst": "x",
        "as_of": "2026-06-26",
        "matches_recorded": 60,
    }
    assert _parse_last_run(fresh)
    age = (now - _parse_last_run(fresh)).total_seconds() / 60.0
    assert abs(age - 20) < 0.01, age
    assert age <= DEFAULT_STALE_MIN
    # stale
    stale = dict(fresh)
    stale["last_run_utc"] = (now - timedelta(hours=18)).strftime("%Y-%m-%dT%H:%M:%SZ")
    age2 = (now - _parse_last_run(stale)).total_seconds() / 60.0
    assert age2 > DEFAULT_STALE_MIN
    # beat round-trip（実ファイルは触らず payload 形だけ検証）
    p = {
        "last_run_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_run_jst": now.astimezone(JST).strftime("%Y-%m-%d %H:%M JST"),
    }
    assert _parse_last_run(p) == now
    print("✅ heartbeat selftest OK")


def main():
    ap = argparse.ArgumentParser(description="wc2026 自動更新ジョブの死活 heartbeat")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--beat", action="store_true", help="今の時刻で打刻")
    g.add_argument("--check", action="store_true", help="死活確認（stale で exit 1）")
    g.add_argument("--selftest", action="store_true", help="内蔵テスト")
    ap.add_argument("--stale-min", type=int, default=DEFAULT_STALE_MIN,
                    help=f"stale とみなす経過分（既定 {DEFAULT_STALE_MIN}）")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if args.beat:
        p = beat()
        print(f"打刻: {p['last_run_jst']} / as_of {p['as_of']} / {p['matches_recorded']}試合")
        return
    if args.check:
        stale, msg = check(stale_min=args.stale_min)
        print(msg)
        sys.exit(1 if stale else 0)


if __name__ == "__main__":
    main()
