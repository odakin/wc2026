# AUTO_UPDATE — 30 分ごとの結果自動更新 runbook

> このファイルは **常時起動機の scheduled task が毎回読んで実行する手順書**。
> 期間限定で 30 分ごとに走り、最新の試合結果を結果 DB と公開サイトに反映し続ける。
> このリポ（`wc2026`）だけで完結する（= データ・生成器・公開がすべて単一 SoT）。

## 目的

最新の試合結果を **結果 DB（`data/results.yaml`）と公開サイト（`docs/`, GitHub Pages）に反映し続ける**。

- SoT = このリポの `data/`（`fixtures.yaml` = 日程 / `results.yaml` = 結果 / `articles.yaml` = リンク）。
- 公開 = `docs/`（`build.py` が生成、日英、GitHub Pages が配信）。

## 前提

- このリポが clone 済み・`gh` 認証済（push 可）・PyYAML 利用可。
- 期間: 大会の対象期間中のみ 30 分ごと。終了日以降は自分で停止する（§6）。

## 毎回の手順

1. **期間チェック（最優先）**: 今が**停止日以降**なら、この scheduled task を
   `scheduled-tasks` MCP で**削除して終了**（§6）。それ以前なら続行。
2. **同期**: `git fetch` → clean かつ ff 可能なら `git pull --ff-only`。
   diverged/dirty なら surface して**この回は中断**（壊さない）。
3. **未記録の消化済み試合を洗い出す**: `data/results.yaml` の `meta.as_of` と既存 matches を読み、
   `data/fixtures.yaml` の対戦カードのうち **キックオフ済みなのに `results.yaml` 未記録**のものを候補にする。
   - 日付の鉄則: `results.yaml` の `date` は**現地（北米）開催日**、`fixtures.yaml` の時刻は **JST**。
     両者は最大 1 日ずれる（JST が進む。夜の試合は JST だと翌日昼）。突合前に必ず時差変換する。
4. **裏取り（厳格・推測禁止）**: 各候補について web 検索で最終スコアを **2 ソース以上**
   （FIFA 公式 + ESPN / Sky Sports / Wikipedia / 各国紙のいずれか）で一致確認。
   - **中断・進行中・1 ソースのみ → 記録しない**（次回に回す）。スコアを憶測で埋めない。
5. **DB 追記**（確定したものだけ）:
   - `data/results.yaml` の `matches:` に 1 行追記（schema: `{group, md, date(現地開催日), home, away, hg, ag, note?}`、
     チーム名は `fixtures.yaml` と統一）。`meta.as_of` を今日（JST）に、`meta.note` を更新。
   - **FIFA公式マッチレポート記事の URL** を探して `data/articles.yaml` に追記（cat: 報道・公式 / source: FIFA公式）。
     **ハイライト動画はこのレポート記事 (`/articles/…`) に埋め込まれている**ので、必ず記事にリンクする。
     **むき出しの動画頁 (`/watch/<id>`) やマッチセンター (スタッツ頁 `/match-centre/…`) は使わない**
     （いずれも「レポート記事」ではないため。2026-06-23 方針確定）。
   - **リンク優先順位**: ① 日本語版記事 `/ja/…/articles/<slug>-ja` が配信済ならそれ（`url` に日本語 URL）。
     ② 日本語版が未配信なら**英語版記事** `/en/…/articles/<slug>`（`url` に英語 URL を直接入れ、
     `note` に「日本語版が未配信のため英語記事」と明記）。記事版そのものが見つからない時だけ最終手段を判断する。
   - URL は **実在確認**してから入れる（推測 slug 禁止）。fifa.com は SPA で fetch が空シェルを返すため、
     **検索インデックスのタイトル一致**で確認する（fetch が空 ≠ 確認不能）。チーム・スコアが当該カードと一致することも確認。
   - **英語ページの FIFA リンクは `build.py` の `fifa_localize()` が決定論変換**する: 日本語記事 URL を `url` に入れた場合は
     `/ja/`→`/en/` かつ語尾 `-ja` 除去（語順は ja と同一）で en を導出。英語記事 URL を `url` に入れた場合はそのまま通り、
     ja/en とも同じ英語記事を指す。例外で規則が外れる試合は ref に `url_en: "<英語URL>"` を足して上書きする（実在確認してから）。
   - 順位が 1〜5 で決着しない同点が出たら、フェアプレー点を FIFA/Wikipedia で確認し
     `meta.tiebreak.conduct` に出典付きで追加。
6. **再生成 + 公開**:
   - `python3 scripts/standings.py --write`（順位表 + `standings.md`）。
   - `python3 scripts/articles.py --write`（`articles.md`）。
   - **記事リンク欠落ゲート（必須）**: `python3 scripts/articles.py --check`。
     finding（記録済みなのに記事リンクが無い試合・欄欠落・URL 重複）が出たら **exit 1**。
     その場合は §5 に戻って欠落試合の FIFA レポート URL を追記してから先へ進む（取りこぼしのまま公開しない）。
   - `python3 build.py`（日英 docs 再生成）。
   - **leak gate**: 差分を `group\.calendar|@gmail|@.*\.ac\.jp|/Users/` 等（個人情報・カレンダー ID・
     個人パス・内部 private リポ名）で grep し、ヒットしたら push 中止して surface（公開リポに出さない）。
   - commit + push（main）。GitHub Pages が自動反映。
7. **何も新規が無い回**: commit せず終了（no-op で良い）。

## §6 終了（対象期間後）

停止日以降の最初の実行で、自分（この scheduled task）を `scheduled-tasks` MCP の delete で消し、
最後に最終結果を反映して終わる。

> ⚠️ **削除対象はこの scheduled task のみ**。公開サイト（`docs/` / GitHub Pages）とリポは**削除しない**。
> 止めるのは 30 分ごとの更新だけで、サイトは最終結果を表示したまま残す。

## 注意 / 限界

- これは **判断込みの自動公開**（web 検索 → 2 ソース確認 → 公開）。人手 review を毎回挟まないので、
  誤報の取り込みリスクはゼロではない（2 ソース gate で抑制）。**スコアの確定が曖昧な試合は飛ばす**。
- 公開 push は **leak gate を必ず通す**（個人情報・内部パスを public に出さない）。
