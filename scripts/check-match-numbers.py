#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""results.yaml の no (FIFA公式試合番号) を検算するゲート。

目的: results ↔ fixtures の突合を「チーム名一致」でなく no (join key) で堅牢化したので、
両者の no が食い違っていないことを機械的に保証する。finding があれば exit 1。

検査軸:
  (1) 全 result に no がある (= 付け忘れ検出)。
  (2) result の no が一意 (= 重複番号検出)。
  (3) result と fixtures の両方に存在する対戦カード (= group + {home,away}) で no が一致。
      ここが本丸: fixtures は 2026-06-25 に I組(41/42)・E組(55/56) の番号スワップを訂正済。
      以後どちらかを編集して再びズレたら、ここで落とす。
  (4) fixtures の group-stage no が一意。

突合キー = (group, frozenset{両チーム名})。グループ内で各カードは 1 回のみなので一意。
チーム名表記は results/fixtures で統一されている前提 (・/中黒や空白は正規化して比較)。

使い方: python3 scripts/check-match-numbers.py [--selftest]
"""
import sys
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results.yaml"
FIXTURES = ROOT / "data" / "fixtures.yaml"


def _norm(s: str) -> str:
    return re.sub(r"[\s・·]", "", str(s))


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def check(results_doc, fixtures_doc):
    findings = []
    rmatches = results_doc["matches"]

    # (1) 全 result に no
    missing = [m for m in rmatches if m.get("no") is None]
    for m in missing:
        findings.append(f"[no欠落] {m.get('group')} {m.get('home')}×{m.get('away')}")

    # (2) result の no 一意
    seen = {}
    for m in rmatches:
        n = m.get("no")
        if n is None:
            continue
        if n in seen:
            findings.append(f"[no重複] M{n}: {seen[n]} と {m.get('home')}×{m.get('away')}")
        seen[n] = f"{m.get('home')}×{m.get('away')}"

    # fixtures の group-stage を (group,{teams}) -> no に
    fmap = {}
    for m in fixtures_doc["matches"]:
        if m.get("stage") != "group":
            continue
        lab = m["label"]
        parts = re.split(r"[×x✕]", lab)
        if len(parts) != 2:
            continue
        key = (m["group"], frozenset({_norm(parts[0]), _norm(parts[1])}))
        # (4) fixtures no 一意
        if key in fmap and fmap[key] != m["no"]:
            findings.append(f"[fixtures重複カード] {lab}")
        fmap[key] = m["no"]

    fno_seen = {}
    for m in fixtures_doc["matches"]:
        if m.get("stage") != "group":
            continue
        n = m["no"]
        if n in fno_seen:
            findings.append(f"[fixtures no重複] M{n}: {fno_seen[n]} と {m['label']}")
        fno_seen[n] = m["label"]

    # (3) overlap で no 一致
    overlap = 0
    for m in rmatches:
        key = (m["group"], frozenset({_norm(m["home"]), _norm(m["away"])}))
        if key in fmap:
            overlap += 1
            if m.get("no") != fmap[key]:
                findings.append(
                    f"[no不一致] {m['group']} {m['home']}×{m['away']}: "
                    f"results=M{m.get('no')} / fixtures=M{fmap[key]}"
                )
    return findings, overlap


def _selftest():
    good_r = {"matches": [
        {"no": 1, "group": "A", "home": "X", "away": "Y", "hg": 1, "ag": 0},
        {"no": 42, "group": "I", "home": "フランス", "away": "イラク", "hg": 3, "ag": 0},
    ]}
    good_f = {"matches": [
        {"no": 1, "stage": "group", "group": "A", "label": "X × Y"},
        {"no": 42, "stage": "group", "group": "I", "label": "フランス × イラク"},
    ]}
    f, ov = check(good_r, good_f)
    assert not f, f"selftest clean failed: {f}"
    assert ov == 2, ov
    # no不一致を仕込む
    bad_f = {"matches": [
        {"no": 1, "stage": "group", "group": "A", "label": "X × Y"},
        {"no": 41, "stage": "group", "group": "I", "label": "フランス × イラク"},
    ]}
    f, ov = check(good_r, bad_f)
    assert any("no不一致" in x for x in f), f"selftest mismatch failed: {f}"
    # no欠落
    miss_r = {"matches": [{"group": "A", "home": "X", "away": "Y", "hg": 1, "ag": 0}]}
    f, _ = check(miss_r, good_f)
    assert any("no欠落" in x for x in f), f"selftest missing failed: {f}"
    print("selftest ✅ (clean/mismatch/missing 全検出)")


def main():
    if "--selftest" in sys.argv:
        _selftest()
        return 0
    findings, overlap = check(_load(RESULTS), _load(FIXTURES))
    if findings:
        print(f"❌ match-number 検算 NG ({len(findings)} 件):")
        for x in findings:
            print("  -", x)
        return 1
    n = len(_load(RESULTS)["matches"])
    print(f"✅ match-number 検算 OK: results {n}件すべて no 付与・一意、 fixtures と overlap {overlap}件で no 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
