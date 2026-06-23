# wc2026 — public 静的サイト（2026 W杯 観戦表）

2026 FIFA W杯のグループステージを観戦用にまとめた **public な非公式ファンページ**。
GitHub Pages (`https://odakin.github.io/wc2026/`) で配信。

## 🚨 public リポ
このリポは GitHub で公開されている。実名・メール・所属・非公開リポ名・私的データを
file 本文 / commit message に一切書かない。`data/` の試合結果と FIFA レポート URL は
すべて公開情報。

## 構造
- `data/results.yaml` / `data/articles.yaml` = SoT（別の private プロジェクトから sync した copy）。
- `build.py` = `data/` → `docs/{index,standings,links}.html` を生成（stdlib + PyYAML のみ）。
- `docs/` = 生成物。GitHub Pages が配信。直接編集しない（`python3 build.py` で再生成）。

## 更新
1. `data/results.yaml` に結果を追記（順位 tiebreak は FIFA 2026 規定を build.py が実装）。
2. `python3 build.py` で `docs/` 再生成。
3. commit + push（main）。Pages が自動反映。

## Pages 設定
Settings → Pages → Deploy from a branch → `main` / `/docs`。
