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
- リンク方針: 日本語版 FIFA マッチレポート記事 (`/ja/…/articles/<slug>-ja`、動画埋込) を優先し、
  未配信の試合は FIFA公式ハイライト動画 (`/ja/watch/<id>`) にリンク（英語記事より言語非依存の動画を優先）。
  マッチセンター頁は使わない。2026-06-23 確定。
- 英語ページの FIFA リンクは `fifa_localize()` で決定論変換（記事は語尾 `-ja` 除去 + `/ja/`→`/en/` /
  `/watch/` は `/ja/`→`/en/` で ID 不変）。規則から外れる試合は ref の `url_en` で明示上書き。

## 試合番号 `no` = 堅牢化の join key（2026-06-25 / 背後の思想）

results と fixtures を**チーム名一致で突合していた**のを、FIFA 公式試合番号 `no`（1-104）を両者に
持たせた **key-join** に変えた。単に列を 1 本足した作業に見えるが、背後にある設計思想:

- **stable identity を足すこと自体が整合性検査の forcing function になる**。「名前一致は表記ゆれに
  脆い」という利便性の話に見えるが、実際に全 50 試合へ `no` を付ける作業が、fixtures に潜んでいた
  既存バグ（同時刻ペアの番号左右違い 2 組: I組 41↔42・E組 55↔56）を炙り出した。識別子を名前・位置
  から切り離すと、暗黙に一致していた前提が機械検査の対象に変わる。
- **SoT の値は推測で埋めない（cell-fill しない）**。早期試合の番号は repo にも Wikipedia 本文にも
  無かったが、捏造せず決定論ソースを掘った: ① FIFA 公式レポート PDF 名 `PMSR-M<NN>` の実在を
  HTTP 200/404 で probe ② 未消化試合は Wikipedia の Match番号 placeholder ③ block bijection で
  消去確定（M47）④「節内スロット順 = 番号昇順」規則を確定済の C/A/E 組で検証してから B組へ適用
  （M51/M52）。いずれも反証可能な根拠で、得られなければ空欄/保留にする（埋めない方を選ぶ）。
- **source は信頼度で階層化する**。WebSearch の自然文要約は試合番号を**幻覚**した（実在しない並びを
  自信満々に返す）ため不採用。raw wikitext と公式 PDF ファイル名という決定論的・構造化ソースを正と
  し、LLM 要約は SoT に焼かない。
- **派生値は単一ソースで満足せず独立 anchor で自己検算してから書く**。fixtures 重複14件・placeholder・
  グループ別ロスター・PMSR 由来40件を相互照合し「矛盾ゼロ」を確認してから results に焼いた。
- **home/away はこのままで正しい（schema を疑った末の結論）**。中立地開催でも FIFA は全試合に第1/第2
  チーム（= home/away）を公式に designation する（kit 選択・ベンチ・表記順を規定）。`hg/ag` はその
  directed score の入れ物で、順位計算は左右に依存しない（一貫していれば結果は同一）。「会場の所有」を
  主張する語ではないので改名は不要。
- **整合は gate で恒久化する（人手の注意に頼らない）**。`no` は results・fixtures・（別 private リポの）
  カレンダーマーカー `[wc2026:M<no>]` の三者共有 key。`scripts/check-match-numbers.py` が overlap で
  一致を検算する（build 前ゲート）。YAML 1.1 では `no:` が bool キーに化けるので必ず `"no":` とクォート。

## Pages
`main` ブランチの `/docs` を配信。`docs/.nojekyll` で Jekyll 処理を無効化。
