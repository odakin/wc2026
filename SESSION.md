# SESSION — wc2026

最終更新: 2026-07-01

## 現状
- 公開用の静的サイトを新設（クロス表 / 順位表 / 記事リンクの 3 ページ、共通ナビ・明るいテーマ）。
- `build.py` が `data/results.yaml` + `data/articles.yaml` から `docs/` を生成。
- GitHub Pages（main /docs）で公開。`https://odakin.github.io/wc2026/`。
- **30 分自動更新稼働中** (`AUTO_UPDATE.md` runbook、 launchd cron + MCP scheduled-task の 2 経路。 停止日 = 2026-07-21、 決勝は現地 07-19 だが結果は JST 07-20 朝着地で 07-20 中は記録継続、 07-21 に自己停止)。
- **2026-07-01 incident**: iMac 側 CLI OAuth token expire で全経路沈黙 (site ~19.5h stale) → user 復旧完了 (詳細 = `~/Claude/odakin-prefs/plans/2026-07-01-wc2026-termination-fix-cold-eyes-review.md §12`)。 M79 メキシコ×エクアドル は独立 WebSearch 検証で 2-1→2-0 に訂正済 (Ecuador 完封・40 年ぶり knockout 勝利)。

## 運用
- 結果更新 → `python3 build.py` → commit + push で反映。
- `data/` は別 private プロジェクトの results.yaml / articles.yaml の copy（公開可なデータのみ）。

## TODO
- [ ] 残りのグループステージ・決勝トーナメントの結果を順次追記。
- [ ] data sync の自動化（private 側更新時に copy + build + push）。
