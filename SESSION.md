# SESSION — wc2026

最終更新: 2026-06-23

## 現状
- 公開用の静的サイトを新設（クロス表 / 順位表 / 記事リンクの 3 ページ、共通ナビ・明るいテーマ）。
- `build.py` が `data/results.yaml` + `data/articles.yaml` から `docs/` を生成。
- GitHub Pages（main /docs）で公開。`https://odakin.github.io/wc2026/`。

## 運用
- 結果更新 → `python3 build.py` → commit + push で反映。
- `data/` は別 private プロジェクトの results.yaml / articles.yaml の copy（公開可なデータのみ）。

## TODO
- [ ] 残りのグループステージ・決勝トーナメントの結果を順次追記。
- [ ] data sync の自動化（private 側更新時に copy + build + push）。
