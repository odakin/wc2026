#!/usr/bin/env python3
"""articles.yaml から「試合ごとの良記事・リンク集」の閲覧ビューを生成する派生ビュー。

articles.yaml = 試合に紐づく記事 / ブログ / 掲示板リンクの SoT (生事実)。
ここから articles.md (リポ閲覧用の生成物) を決定論的に出力する (= 二重管理しない)。
results.yaml (結果 DB) とは疎結合: 各 match.key の (group, md) が results.yaml に
あるかを軽く照合する (lag 時は warn のみで block しない)。

usage:
  python3 scripts/articles.py                       # 全試合のリンク集を表示
  python3 scripts/articles.py --write                # articles.md を生成 (リポ閲覧用)
  python3 scripts/articles.py --match F-md2-JPN-TUN  # 特定試合のみ
"""
import argparse
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
ARTICLES = ROOT / "data" / "articles.yaml"   # SoT は data/ 配下 (build.py と共有)
RESULTS = ROOT / "data" / "results.yaml"

# 表示順 (yaml 上の並びに依らず常にこの順でセクション化)
CAT_ORDER = ["報道・公式", "分析・展望", "海外の反応", "掲示板・まとめ"]
CAT_EMOJI = {"報道・公式": "📰", "分析・展望": "📊", "海外の反応": "🌍", "掲示板・まとめ": "💬"}


def load(path):
    return yaml.safe_load(path.read_text()) or {}


def results_keys():
    """results.yaml の (group, md) 集合 (整合チェック用)。無ければ空集合。"""
    return {(m.get("group"), m.get("md")) for m in results_matches()}


def results_matches():
    """results.yaml の match dict 一覧 (整合チェック用)。無ければ空リスト。"""
    if not RESULTS.exists():
        return []
    return load(RESULTS).get("matches", []) or []


def _covered(m, arts_matches):
    """results の試合 m を覆う articles ブロックがあるか判定する。

    同 group・同 md ∧ 両チーム名が記事 title に含まれる ∧ 有効な url を持つ ref が
    1 つ以上ある、 で「リンクあり」とみなす。 (group, md) だけだと同一節の複数試合を
    区別できないため、 チーム名 (results.yaml と articles.yaml で統一表記) で照合する。"""
    home, away = m.get("home", ""), m.get("away", "")
    if not (home and away):
        return False
    for a in arts_matches:
        if a.get("group") != m.get("group") or a.get("md") != m.get("md"):
            continue
        title = a.get("title", "") or ""
        if home in title and away in title:
            if any(r.get("url") for r in (a.get("refs") or [])):
                return True
    return False


def validate(matches, rkeys, rmatches):
    warns = []
    seen_urls = {}
    for mt in matches:
        key = mt.get("key", "?")
        if rkeys and (mt.get("group"), mt.get("md")) not in rkeys:
            warns.append(f"[{key}] results.yaml に (group={mt.get('group')}, md={mt.get('md')}) が無い")
        for r in mt.get("refs", []):
            for f in ("cat", "title", "url", "source"):
                if not r.get(f):
                    warns.append(f"[{key}] ref に '{f}' が無い: {r.get('title') or r.get('url')}")
            if r.get("cat") not in CAT_ORDER:
                warns.append(f"[{key}] 未知の cat: {r.get('cat')!r} ({r.get('title')})")
            u = r.get("url")
            if u:
                if u in seen_urls:
                    warns.append(f"URL 重複: {u} ({seen_urls[u]} と {key})")
                else:
                    seen_urls[u] = key
    # 逆方向: results に記録済みなのに articles に対応リンクが無い試合 (= リンク取りこぼし検知)
    for m in rmatches:
        if not _covered(m, matches):
            warns.append(
                f"記事リンク欠落: {m.get('group')}組 第{m.get('md')}節 "
                f"{m.get('home')} {m.get('hg')}-{m.get('ag')} {m.get('away')} "
                f"({m.get('date')}) — articles.yaml に対応ブロック/有効リンクが無い")
    return warns


def fmt_match(mt):
    out = []
    head = f"### {mt.get('title', mt.get('key', '?'))}"
    sub = []
    if mt.get("group"):
        sub.append(f"{mt['group']}組")
    if mt.get("md"):
        sub.append(f"第{mt['md']}節")
    if mt.get("date"):
        sub.append(str(mt["date"]))
    if sub:
        head += f"（{' / '.join(sub)}）"
    out.append(head)
    refs = mt.get("refs", [])
    for cat in CAT_ORDER:
        crefs = [r for r in refs if r.get("cat") == cat]
        if not crefs:
            continue
        out.append("")
        out.append(f"**{CAT_EMOJI.get(cat, '')} {cat}**")
        out.append("")
        for r in crefs:
            line = f"- [{r['title']}]({r['url']})"
            tail = [x for x in (r.get("source"), r.get("note")) if x]
            if tail:
                line += " — " + " / ".join(tail)
            out.append(line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="articles.md を生成")
    ap.add_argument("--match", help="特定試合のみ (例: F-md2-JPN-TUN)")
    ap.add_argument("--check", action="store_true",
                    help="検証のみ実行。 finding (記事リンク欠落・欄欠落・重複等) があれば exit 1")
    args = ap.parse_args()

    data = load(ARTICLES)
    meta = data.get("meta", {})
    matches = data.get("matches", [])
    rkeys = results_keys()
    rmatches = results_matches()

    warns = validate(matches, rkeys, rmatches)
    for w in warns:
        print(f"⚠ {w}", file=sys.stderr)

    if args.check:
        # AUTO_UPDATE.md / CI 用の gate: finding を出して非ゼロ終了 (記録済みなのにリンク無い試合を見逃さない)
        if warns:
            print(f"\n❌ {len(warns)} 件の finding (上記)。 articles.yaml を直して再実行。", file=sys.stderr)
            sys.exit(1)
        print(f"✅ 記事リンク検証 OK (results {len(rmatches)} 試合すべてにリンクあり)。")
        sys.exit(0)

    sel = [m for m in matches if (not args.match or m.get("key") == args.match)]
    n_refs = sum(len(m.get("refs", [])) for m in sel)
    print(f"2026 FIFA World Cup — 試合ごとの良記事・リンク集\n"
          f"試合数: {len(sel)} / リンク数: {n_refs}\n")
    print("\n\n".join(fmt_match(m) for m in sel))

    if args.write and not args.match:
        total = sum(len(m.get("refs", [])) for m in matches)
        md = ("<!-- ⚠ 生成物: scripts/articles.py が articles.yaml から生成。直接編集しない。\n"
              "     articles.yaml を更新したら `python3 scripts/articles.py --write` で再生成。 -->\n\n"
              "# 2026 FIFA World Cup — 試合ごとの良記事・リンク集\n\n"
              f"- 試合数: {len(matches)} / リンク数: {total}\n")
        if meta.get("note"):
            md += f"- {meta['note']}\n"
        md += "\n" + "\n\n".join(fmt_match(m) for m in matches) + "\n"
        (ROOT / "articles.md").write_text(md)
        print(f"\nwrote {ROOT / 'articles.md'}", file=sys.stderr)


if __name__ == "__main__":
    main()
