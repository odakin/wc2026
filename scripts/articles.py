#!/usr/bin/env python3
"""articles.yaml から「試合ごとの良記事・リンク集」の閲覧ビューを生成する派生ビュー。

articles.yaml = 試合に紐づく記事 / ブログ / 掲示板リンクの SoT (生事実)。
ここから articles.md (リポ閲覧用の生成物) を決定論的に出力する (= 二重管理しない)。
results.yaml (結果 DB) とは疎結合: 各 match.key の (group, md) が results.yaml に
あるかを軽く照合する (lag 時は warn のみで block しない)。

スコアと記事リンクの分離 (2026-06-28): スコアが確定したら記事リンクの有無に関わらず
results.yaml に記録され、 順位表・公開サイトは即反映される (standings.py は results.yaml
のみ駆動)。 記事リンクは「配信待ち」として後続 run で backfill する。 そのため --check は
finding を 2 段階に分ける:
  🔴 blocking (exit 1) = 本物のデータ不整合 (ref 欄欠落・未知 cat・URL 重複・
     実在しない結果を指す記事ブロック) のみ。
  ⏳ pending (公開は決して止めない) = スコア記録済みだがリンク未着の試合。
     リンク欠落は blocking にしない: ゲートはグローバルなので、 1 本の未着リンクで止めると
     他の確定スコアまで公開が止まってしまう (= 直そうとしている問題の再発)。 代わりに
     ジョブは毎回の run でこの配信待ちリストを再探索 (backfill) する。 取りこぼし防止は
     「ハードに止める」 でなく 「毎回再探索 ＋ 毎回 surface」 で担保する。 PENDING_GRACE_DAYS
     を過ぎても未着のものは ⚠ で目立たせる (= 日本語記事が出ない試合かも → 動画②へ
     フォールバック検討の合図) が、 それでも公開は止めない。

usage:
  python3 scripts/articles.py                       # 全試合のリンク集を表示
  python3 scripts/articles.py --write                # articles.md を生成 (リポ閲覧用)
  python3 scripts/articles.py --check                # ゲート (blocking で exit 1、 pending は surface)
  python3 scripts/articles.py --match F-md2-JPN-TUN  # 特定試合のみ
  python3 scripts/articles.py --selftest             # pending/blocking 分割ロジックの自己検証
"""
import argparse
import datetime
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
ARTICLES = ROOT / "data" / "articles.yaml"   # SoT は data/ 配下 (build.py と共有)
RESULTS = ROOT / "data" / "results.yaml"

# 表示順 (yaml 上の並びに依らず常にこの順でセクション化)
CAT_ORDER = ["報道・公式", "分析・展望", "海外の反応", "掲示板・まとめ"]
CAT_EMOJI = {"報道・公式": "📰", "分析・展望": "📊", "海外の反応": "🌍", "掲示板・まとめ": "💬"}

# 記事リンク未着は常に「⏳ 配信待ち」(公開は止めない)。 この日数を過ぎても未着なら
# ⚠ で目立たせる (= 日本語記事が出ない試合かも → 動画②へフォールバック検討の合図) が、
# それでも blocking には昇格させない (グローバルゲートで全公開を止めないため)。
# FIFA は試合終了後ふつう数時間〜1 日で日本語レポートを配信するので、 2 日が「長すぎ」の目安。
PENDING_GRACE_DAYS = 2


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


def _match_age_days(m, today=None):
    """試合の現地開催日 (date) から today (JST) までの経過日数。
    date が無い/不正なら 0 (= 新しい扱い) を返し、 誤って blocking に昇格させない。"""
    d = m.get("date")
    if isinstance(d, str):
        try:
            d = datetime.date.fromisoformat(d)
        except ValueError:
            return 0
    if not isinstance(d, datetime.date):
        return 0
    return ((today or datetime.date.today()) - d).days


def validate(matches, rkeys, rmatches, today=None):
    """(blocking, pending) を返す。

    blocking = 公開を止めるべき finding (ref 欄欠落・未知 cat・URL 重複・
               articles が実在しない結果を指す)。 リンク欠落は **含めない**。
    pending  = スコアは記録済みだが FIFA 記事/動画リンクがまだ無い「配信待ち」。
               公開は止めず ⏳ surface のみ (毎回の run で再探索 backfill される)。
               PENDING_GRACE_DAYS を過ぎた未着は ⚠ で目立たせるが依然 pending。"""
    blocking = []
    pending = []
    seen_urls = {}
    for mt in matches:
        key = mt.get("key", "?")
        if rkeys and (mt.get("group"), mt.get("md")) not in rkeys:
            blocking.append(f"[{key}] results.yaml に (group={mt.get('group')}, md={mt.get('md')}) が無い")
        for r in mt.get("refs", []):
            for f in ("cat", "title", "url", "source"):
                if not r.get(f):
                    blocking.append(f"[{key}] ref に '{f}' が無い: {r.get('title') or r.get('url')}")
            if r.get("cat") not in CAT_ORDER:
                blocking.append(f"[{key}] 未知の cat: {r.get('cat')!r} ({r.get('title')})")
            u = r.get("url")
            if u:
                if u in seen_urls:
                    blocking.append(f"URL 重複: {u} ({seen_urls[u]} と {key})")
                else:
                    seen_urls[u] = key
    # 逆方向: results に記録済みなのに articles に対応リンクが無い試合。
    #   リンク欠落は **決して blocking にしない** (グローバルゲートで全公開を止めないため)。
    #   常に「配信待ち pending」とし、 ジョブは毎回の run で再探索して backfill する。
    #   猶予 (PENDING_GRACE_DAYS) を過ぎた未着は ⚠ で目立たせる (= 日本語記事が出ない試合かも
    #   → 動画②へフォールバック検討の合図) が、 それでも公開は止めない (2026-06-28)。
    for m in rmatches:
        if not m.get("group"):   # knockout 結果 (group 無し・no が鍵) は当面リンク必須対象外
            continue
        if _covered(m, matches):
            continue
        age = _match_age_days(m, today)
        desc = (f"{m.get('group')}組 第{m.get('md')}節 "
                f"{m.get('home')} {m.get('hg')}-{m.get('ag')} {m.get('away')} "
                f"({m.get('date')})")
        if age >= PENDING_GRACE_DAYS:
            pending.append(f"⚠ 配信待ち({age}日経過): {desc} — リンク未着。 "
                           f"日本語記事が出ない試合かも → ハイライト動画②へのフォールバックを検討 (公開は止めない)")
        else:
            pending.append(f"配信待ち: {desc} — FIFA記事/動画リンク未着 (スコア・順位は反映済、 次の run で再探索)")
    return blocking, pending


def _selftest():
    today = datetime.date(2026, 6, 28)
    # 1) 直近 (1日) の記録済み・リンク無し → pending (公開は止めない)
    recent = [{"group": "K", "md": 3, "date": "2026-06-27", "home": "コロンビア", "hg": 0, "ag": 0, "away": "ポルトガル"}]
    b, p = validate([], set(), recent, today=today)
    assert not b and len(p) == 1, (b, p)
    # 2) 猶予超過 (4日) のリンク無し → 依然 pending (公開は止めない) だが ⚠ 要確認マーク
    stale = [{"group": "A", "md": 1, "date": "2026-06-24", "home": "X", "hg": 1, "ag": 0, "away": "Y"}]
    b, p = validate([], set(), stale, today=today)
    assert not b and len(p) == 1 and "4日経過" in p[0] and "⚠" in p[0], (b, p)
    # 3) リンクあり → blocking/pending どちらにも出ない
    arts = [{"key": "K-md3-COL-POR", "group": "K", "md": 3, "title": "コロンビア 0-0 ポルトガル",
             "refs": [{"cat": "報道・公式", "title": "t", "url": "http://x", "source": "FIFA公式"}]}]
    b, p = validate(arts, {("K", 3)}, recent, today=today)
    assert not b and not p, (b, p)
    # 4) knockout (group 無し) はリンク必須対象外
    b, p = validate([], set(), [{"md": None, "date": "2026-07-01", "home": "A", "hg": 1, "ag": 0, "away": "B"}], today=today)
    assert not b and not p, (b, p)
    # 5) URL 重複 → blocking
    dup = [{"key": "k1", "group": "A", "md": 1, "title": "X 1-0 Y",
            "refs": [{"cat": "報道・公式", "title": "t", "url": "http://d", "source": "s"}]},
           {"key": "k2", "group": "A", "md": 2, "title": "Z 1-0 W",
            "refs": [{"cat": "報道・公式", "title": "t", "url": "http://d", "source": "s"}]}]
    b, p = validate(dup, {("A", 1), ("A", 2)}, [], today=today)
    assert any("URL 重複" in x for x in b), b
    print("✅ articles.py selftest OK (pending/blocking 分割・リンク欠落は非block・⚠昇格・knockout 除外・URL 重複)")


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
                    help="検証のみ実行。 blocking finding (欄欠落・未知cat・URL重複等) があれば exit 1。 "
                         "リンク未着は ⏳ 配信待ちとして surface するだけで止めない")
    ap.add_argument("--selftest", action="store_true",
                    help="pending/blocking 分割ロジックの自己検証")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        sys.exit(0)

    data = load(ARTICLES)
    meta = data.get("meta", {})
    matches = data.get("matches", [])
    rkeys = results_keys()
    rmatches = results_matches()

    blocking, pending = validate(matches, rkeys, rmatches)
    for w in pending:
        print(f"⏳ {w}", file=sys.stderr)
    for w in blocking:
        print(f"⚠ {w}", file=sys.stderr)

    if args.check:
        # AUTO_UPDATE.md / CI 用の gate:
        #   - pending (リンク未着) は公開を止めない。 毎回 surface し、 次の run で再探索 backfill する。
        #   - blocking (本物のデータ不整合) のみ exit 1 で止める。
        if pending:
            print(f"\n⏳ {len(pending)} 件は配信待ち (スコア・順位は公開済、 リンクは次回 run で再探索)。",
                  file=sys.stderr)
        if blocking:
            print(f"\n❌ {len(blocking)} 件の blocking finding (上記)。 articles.yaml を直して再実行。",
                  file=sys.stderr)
            sys.exit(1)
        print(f"✅ ゲート OK (blocking なし。 results {len(rmatches)} 試合、 配信待ち {len(pending)} 件)。")
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
