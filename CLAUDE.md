# wc2026 — public 静的サイト + 単一 SoT（2026 W杯 観戦表）

2026 FIFA W杯のグループステージを観戦用にまとめた **public な非公式ファンページ**。
GitHub Pages (`https://odakin.github.io/wc2026/` 日本語 / `/en/` 英語) で配信。
**このリポがウェブサイトの単一 SoT**（データ・順位ロジック・ビルド・自動更新がすべてここに集約）。

## 🚨 public リポ
このリポは GitHub で公開されている。実名・メール・所属・非公開リポ名・私的データ・内部の
private な doc パスを file 本文 / commit message に一切書かない。`data/` の試合日程・結果・
FIFA レポート URL はすべて公開情報。カレンダー登録機構（個人の calendarId 等）は**別の private リポ**にある。

## 構造
- `data/` = SoT（生事実）。`fixtures.yaml`（日程）/ `results.yaml`（結果）/ `articles.yaml`（リンク）。
  `fixtures.yaml` と `results.yaml` は **`"no"`（FIFA公式試合番号 1-104）を共有 join key** にする（突合は名前一致でなく no）。
  キーは必ず `"no":` とクォート（PyYAML が `no:` を boolean False キーに解釈する YAML1.1 の罠）。
- `scripts/standings.py` = **順位アルゴリズムの正本**（`rank_group` / FIFA 2026 tiebreak）+ `standings.md` 生成。
- `scripts/articles.py` = `articles.md` 生成 + **記事リンク欠落チェック**（`--check` で finding 時 exit 1）。
- `scripts/check-match-numbers.py` = **試合番号ゲート**（results.no と fixtures.no の一致・no 欠落/重複を検算、finding 時 exit 1。`--selftest` 内蔵）。
- `build.py` = `data/` → `docs/{index,standings,links}.html`（日英）を生成。**順位は再実装せず
  `standings.py` を import**（= ロジック単一実装、クロス表・順位表・公開ページが必ず一致）。
- リンク方針: ① 日本語版 FIFA マッチレポート記事 (`/ja/…/articles/<slug>-ja`、動画埋込) を優先、
  ② 未配信なら FIFA公式ハイライト動画 (`/ja/watch/<id>`) にリンク（英語記事より言語非依存の動画を優先）。
  マッチセンター頁は使わない。2026-06-23 確定。
- 英語ページの FIFA リンクは `build.py` の `fifa_localize()` が `/ja/`→`/en/`（記事は語尾 `-ja` 除去 /
  `/watch/` は ID 不変）で決定論変換。例外は ref の `url_en` で上書き。
- `docs/` = 生成物。GitHub Pages が配信。直接編集しない（`python3 build.py` で再生成）。
- `AUTO_UPDATE.md` = 30 分ごとの自動更新 runbook（scheduled task が読む）。

## 更新（手動）
1. `data/results.yaml` に結果を追記（スコアは 2 ソース以上で裏取り、チーム名は `fixtures.yaml` と統一）。
   `"no"`（FIFA公式試合番号）も `fixtures.yaml` の同カードからコピーして付与する（`no:` でなく `"no":` とクォート）。
2. `data/articles.yaml` に FIFA公式リンクを追記（実在確認してから）。優先順位:
   ① **日本語版マッチレポート記事** `/ja/…/articles/<slug>-ja`（ハイライト動画が埋込まれた記事）があればそれ。
   ② 無ければ **FIFA公式ハイライト動画** `/ja/watch/<id>`（英語記事より言語非依存の動画を優先）。
   マッチセンター（スタッツ頁）は使わない。`note` に選定理由を明記。
3. `python3 scripts/standings.py --write && python3 scripts/articles.py --write` でビューを再生成。
4. `python3 scripts/articles.py --check`（記事リンク欠落ゲート）→ `python3 scripts/check-match-numbers.py`（試合番号ゲート）→ `python3 build.py`（docs 再生成）。
5. commit + push（main）。Pages が自動反映。

自動更新の毎回手順は `AUTO_UPDATE.md` が正本。

## カレンダー登録（別 private リポ）
このサイトとは独立に、試合を個人 Google Calendar に登録する private リポが別にある
（`fixtures.yaml` を読んで登録プランを生成、個人 calendarId 込み）。`data/fixtures.yaml` は
そのリポからも読まれる共有の日程 SoT（= 日程はここに 1 コピー）。

## Pages 設定
Settings → Pages → Deploy from a branch → `main` / `/docs`。
