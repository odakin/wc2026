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
- `scripts/articles.py` = `articles.md` 生成 + **記事ゲート**（`--check`）。スコアと記事リンクは
  分離（リンク未着は ⏳ 配信待ちで公開を止めない、 詳細は本 script の module docstring「スコアと
  記事リンクの分離」 節が canonical SoT）。`--selftest` 内蔵。
- `scripts/check-match-numbers.py` = **試合番号ゲート**（results.no と fixtures.no の一致・no 欠落/重複を検算、finding 時 exit 1。`--selftest` 内蔵）。
- `scripts/propagate-knockout.py` = **決勝T 対戦カード自動進行**（results の knockout winner から `fixtures.yaml` の slot label `M<no>勝者`/`M<no>敗者` を実チーム名に決定論的解決。R32結果→R16→QF→… と 1 段ずつ。`--apply` で書込、既定 dry-run、`--selftest` 内蔵）。AUTO_UPDATE.md §6 が毎回実行。
- `scripts/heartbeat.py` = **自動更新ジョブの死活監視**（`--beat` で `heartbeat.json` 打刻、`--check` で stale 検出 exit 1、`--selftest` 内蔵）。自動更新は no-op の回も commit しないため、毎回打刻して別マシンから死活を判定できるようにする（2026-06-26 のジョブ停止見逃し対策）。
- `build.py` = `data/` → `docs/{index,standings,links}.html`（日英）を生成。**順位は再実装せず
  `standings.py` を import**（= ロジック単一実装、クロス表・順位表・公開ページが必ず一致）。
- リンク選定基準（⓪ ja に何も無ければ書かない → ② ja 動画 → ① ja マッチレポート記事 の tier 進行、 後段配信で必ず upgrade、 マッチセンター不使用、 en は `fifa_localize()` 決定論変換）
  の正本は [`data/articles.yaml`](data/articles.yaml) ヘッダ「リンク優先順位」 節。
- `docs/` = 生成物。GitHub Pages が配信。直接編集しない（`python3 build.py` で再生成）。
- `AUTO_UPDATE.md` = 30 分ごとの自動更新 runbook（scheduled task が読む）。

## 更新（手動）
1. `data/results.yaml` に結果を追記（スコアは 2 ソース以上で裏取り、チーム名は `fixtures.yaml` と統一）。
   `"no"`（FIFA公式試合番号）も `fixtures.yaml` の同カードからコピーして付与する（`no:` でなく `"no":` とクォート）。
2. `data/articles.yaml` に FIFA公式リンクを追記（実在確認してから）。選定基準（⓪ → ② → ① の tier 進行 /
   後段配信で必ず upgrade / マッチセンター不使用 / `note` に選定理由）の正本は [`data/articles.yaml`](data/articles.yaml) ヘッダ「リンク優先順位」 節。
3. `python3 scripts/standings.py --write && python3 scripts/articles.py --write` でビューを再生成。
4. `python3 scripts/articles.py --check`（記事ゲート: blocking のみ exit 1、リンク未着は ⏳ 配信待ちで止めない）→ `python3 scripts/check-match-numbers.py`（試合番号ゲート）→ `python3 build.py`（docs 再生成）。
5. commit + push（main）。Pages が自動反映。

自動更新の毎回手順は `AUTO_UPDATE.md` が正本。

## カレンダー登録（別 private リポ）
このサイトとは独立に、試合を個人 Google Calendar に登録する private リポが別にある
（`fixtures.yaml` を読んで登録プランを生成、個人 calendarId 込み）。`data/fixtures.yaml` は
そのリポからも読まれる共有の日程 SoT（= 日程はここに 1 コピー）。

## Pages 設定
Settings → Pages → Deploy from a branch → `main` / `/docs`。
