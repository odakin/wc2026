# DESIGN — wc2026

## なぜ別リポか
データ元の private プロジェクトには公開できない情報（個人カレンダーの ID 等）が
file 本文・git 履歴に含まれるため、無料の GitHub Pages（public リポ必須）には使えない。
→ 公開して問題ないファイル（試合結果・FIFA レポート URL・generator・生成 HTML）だけを
集めた **clean な public リポ**を新設し、履歴も最初から公開前提で作る。

## 設計方針
- **SoT は data/ の yaml、HTML は生成物**（二重管理しない）。順位も results.yaml から決定論導出。
- 依存は stdlib + PyYAML のみ（ビルド環境を選ばない）。
- 順位 tiebreak は FIFA 2026 大会規定（直接対決優先・抽選廃止）を実装。
  フェアプレーポイント等の計算不能な criterion は results.yaml の meta.tiebreak にデータで持つ。
- 国旗は ISO コードから生成（ソースに絵文字リテラルを埋めない）。

## Pages
`main` ブランチの `/docs` を配信。`docs/.nojekyll` で Jekyll 処理を無効化。
