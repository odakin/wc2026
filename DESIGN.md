# DESIGN — wc2026

## リポ分割は「関心」で切る（= SoT 単一化）
当初は private プロジェクトの公開可ファイルを clean copy する「公開ミラー」だったが、コピー同期と
順位ロジックの二重実装（private と build.py）で SoT が割れていた。**分割線を「関心」で引き直した**:

- **このリポ（public `wc2026`）= ウェブサイトの単一 SoT**: 日程・結果・リンク（`data/`）、順位ロジック
  （`scripts/standings.py`）、ビルド（`build.py`）、自動更新（`AUTO_UPDATE.md`）。website に必要なものは
  すべてここに 1 コピーだけ。30 分ごとの自動更新もここを直接編集する（private→public のコピー同期は廃止）。
- **別の private リポ = カレンダー登録専用**: 個人 Google Calendar への登録機構（`gen-plan.py` 等・個人
  calendarId 込み）。これは公開できないので private のまま。日程 `data/fixtures.yaml` は public が SoT で、
  private 側がそれを read する（= public ⊇ private の依存方向で、日程は 1 コピー）。

→ 結果: データ（fixtures/results/articles）も順位ロジックも、各事実が 1 箇所にしか無い。今後の編集は
1 箇所で済み、クロス表・順位表・公開ページが必ず一致する。

## 設計方針
- **SoT は data/ の yaml、HTML は生成物**（二重管理しない）。順位も results.yaml から決定論導出。
- **順位ロジックは単一実装**: `scripts/standings.py` の `rank_group` が唯一の実装。`build.py` は再実装せず
  import する（旧 build.py は同じ tiebreak を別実装で持っていた → 統一）。
- 依存は stdlib + PyYAML のみ（ビルド環境を選ばない）。
- 順位 tiebreak は FIFA 2026 大会規定（直接対決優先・抽選廃止）を実装。
  フェアプレーポイント等の計算不能な criterion は results.yaml の meta.tiebreak にデータで持つ。
- 国旗は ISO コードから生成（ソースに絵文字リテラルを埋めない）。
- リンクは **FIFA公式マッチレポート記事** (`/articles/…`、ハイライト動画が埋込まれた記事) に統一
  （`/watch/` 動画頁・マッチセンター頁は使わない。日本語版優先・未配信は英語版へフォールバック。2026-06-23 確定）。
- 英語ページの FIFA リンクは `fifa_localize()` で決定論変換（日本語記事は語尾 `-ja` 除去 + `/ja/`→`/en/` /
  英語記事 URL はそのまま通り ja/en とも同じ記事）。規則から外れる試合は ref の `url_en` で明示上書き。

## Pages
`main` ブランチの `/docs` を配信。`docs/.nojekyll` で Jekyll 処理を無効化。
