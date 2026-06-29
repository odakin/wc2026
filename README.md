# wc2026 — 2026 FIFA ワールドカップ 観戦表（非公式）

2026 FIFA ワールドカップ（北中米開催）のグループステージを、**クロス表・順位表・試合別 FIFA マッチレポートのリンク集**としてまとめた個人運営の非公式ファンページです。**結果は 30 分ごとに自動で裏取り・公開**しています（仕組みは下記）。

🌐 **サイト**: https://odakin.github.io/wc2026/ （日本語） / https://odakin.github.io/wc2026/en/ （English）

> 本サイトは個人運営の非公式ファンページで、FIFA とは一切関係ありません。試合結果は FIFA 公式・各報道を 2 ソース以上で確認したものですが、正確性は保証しません。

## ページ

| ページ | 内容 |
|---|---|
| [クロス表](https://odakin.github.io/wc2026/) | 各組の対戦結果を「行チーム視点のスコア」で勝=緑/分=灰/負=赤に色分け。クリックで FIFA マッチレポート |
| [順位表](https://odakin.github.io/wc2026/standings.html) | グループ順位（FIFA 2026 規定の tiebreak を実装） |
| [記事リンク](https://odakin.github.io/wc2026/links.html) | 消化済み全試合の FIFA 公式マッチレポートへの直リンク |

英語ページ（`/en/`）は同じデータから生成され、FIFA リンクも英語記事を指します。

## このリポは「作り方」も込みの単一 SoT

データ（生事実）→ 決定論生成 → 日英ビルド → 自動更新まで、**ウェブサイトに必要なものがすべてこの 1 リポに入っています**（= single source of truth）。順位ロジックもサイト生成もコピーを持たず 1 箇所に集約しています。

```
wc2026/
├── data/                 # SoT（生事実）
│   ├── fixtures.yaml     #   日程（対戦カード・JST 時刻・会場）
│   ├── results.yaml      #   試合結果（消化済みのスコア）
│   └── articles.yaml     #   試合ごとの FIFA レポート / 記事リンク
├── scripts/
│   ├── standings.py      #   順位アルゴリズムの正本（rank_group / tiebreak）+ standings.md 生成
│   └── articles.py       #   articles.md 生成 + リンク欠落チェック（--check）
├── build.py              # data/ → docs/ を生成（standings.py を import = 順位ロジックは単一実装）
├── AUTO_UPDATE.md        # 30 分ごとの自動更新 runbook（下記）
└── docs/                 # 生成物（GitHub Pages がここを配信、日本語 + /en/）
```

### 設計の要点

- **生事実だけを SoT に**: 順位表は持たず、`results.yaml` から毎回計算して導出（二重管理ゼロ）。
- **順位ロジックは 1 実装**: `scripts/standings.py` の `rank_group` が唯一の実装で、`build.py` も
  `gen` も import して使う（クロス表・順位表・公開ページが必ず一致する）。
- **リンクの選び方**: ① 日本語版 FIFA マッチレポート記事（ハイライト動画埋込）を優先、② 未配信の試合は
  FIFA公式ハイライト動画にリンク（英語記事より言語非依存の動画を優先）。マッチセンター頁は使わない。
- **日英リンクは決定論変換**: `build.py` の `fifa_localize()` が日本語 URL を `/ja/`→`/en/`（記事は語尾 `-ja` 除去 /
  `/watch/` は ID 不変）で英語ページ用に変換。例外は ref の `url_en` で上書き可。

## 順位の決め方（FIFA 2026 規定）

2026 大会から tiebreak の順序が変わり、**直接対決が最優先**になりました（抽選は廃止）:

1. 勝点 → 2. 直接対決の勝点 → 3. 直接対決の得失差 → 4. 直接対決の総得点
→ 5. 全試合の得失差 → 6. 全試合の総得点 → 7. フェアプレーポイント → 8. FIFA ランキング

`scripts/standings.py` がこの規定を決定論的に実装しています（head-to-head は同点サブグループ内で再帰計算）。

## 手元で再生成する

```bash
python3 scripts/standings.py --write   # 順位表 + standings.md
python3 scripts/articles.py  --write   # articles.md
python3 scripts/articles.py  --check   # 記事ゲート（blocking のみ exit 1: ref 欄欠落・未知 cat・URL 重複等。リンク未着は ⏳ 配信待ちで止めない）
python3 build.py                       # docs/（日英）を再生成
```

国旗は ISO 3166-1 alpha-2 から regional indicator を生成しています（スコットランド／イングランドは UK の subdivision flag）。

## 30 分ごとの自動更新（仕組み）

このサイトは人手をほぼ介さず更新されます。常時起動機の **scheduled task が 30 分ごとに [`AUTO_UPDATE.md`](AUTO_UPDATE.md) を読んで実行**します:

1. `fixtures.yaml` と `results.yaml` を突き合わせ、**キックオフ済みなのに未記録の試合**を洗い出す
2. 各試合のスコアを web 検索で **2 ソース以上**裏取り（中断・進行中・1 ソースのみは記録しない＝憶測で埋めない）
3. `results.yaml` / `articles.yaml` に追記 → 順位・記事ビューを再生成 → `build.py` で日英ページを生成
4. 記事ゲート（`articles.py --check`、blocking finding〔ref 欄欠落・未知 cat・URL 重複等〕のみ exit 1。**リンク欠落は ⏳ 配信待ちで公開を止めない**、 2026-06-28 方針）と leak gate を通してから commit + push（Pages が自動反映）

決定論的な部分（順位計算・日英変換・ビルド）はスクリプトに閉じ込め、判断が要る部分（結果の裏取り・記事 URL の確認）だけを毎回の実行で行う設計です。

## ライセンス

MIT（`LICENSE`）。試合結果・順位は事実データ、FIFA レポートへのリンクは各記事の URL を指すのみです。
