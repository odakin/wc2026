# wc2026 — 2026 FIFA ワールドカップ 観戦表（非公式）

2026 FIFA ワールドカップ（北中米開催）のグループステージを、**クロス表・順位表・試合別 FIFA 日本語マッチレポートのリンク集**としてまとめた個人運営の非公式ファンページです。

🌐 **サイト**: https://odakin.github.io/wc2026/

> 本サイトは個人運営の非公式ファンページで、FIFA とは一切関係ありません。試合結果は FIFA 公式・各報道を 2 ソース以上で確認したものですが、正確性は保証しません。

## ページ

| ページ | 内容 |
|---|---|
| [クロス表](https://odakin.github.io/wc2026/) | 各組の対戦結果を「行チーム視点のスコア」で勝=緑/分=灰/負=赤に色分け。クリックで FIFA 日本語レポート |
| [順位表](https://odakin.github.io/wc2026/standings.html) | グループ順位（FIFA 2026 規定の tiebreak を実装） |
| [記事リンク](https://odakin.github.io/wc2026/links.html) | 消化済み全試合の FIFA 公式マッチレポート（日本語）への直リンク |

## 順位の決め方（FIFA 2026 規定）

2026 大会から tiebreak の順序が変わり、**直接対決が最優先**になりました（抽選は廃止）:

1. 勝点 → 2. 直接対決の勝点 → 3. 直接対決の得失差 → 4. 直接対決の総得点
→ 5. 全試合の得失差 → 6. 全試合の総得点 → 7. フェアプレーポイント → 8. FIFA ランキング

`build.py` がこの規定を決定論的に実装しています（head-to-head は同点サブグループ内で再帰計算）。

## 構成 / 再生成

```
wc2026/
├── data/                 # SoT（生事実）
│   ├── results.yaml      #   試合結果
│   └── articles.yaml     #   FIFA 日本語レポートの URL
├── build.py              # data/ → docs/ を生成（stdlib + PyYAML のみ）
└── docs/                 # 生成物（GitHub Pages がここを配信）
    ├── index.html        #   クロス表
    ├── standings.html    #   順位表
    └── links.html        #   記事リンク
```

結果を追記したら再生成して push:

```bash
python3 build.py        # docs/ を再生成
```

国旗は ISO 3166-1 alpha-2 から regional indicator を生成しています（スコットランド／イングランドは UK の subdivision flag）。

## ライセンス

MIT（`LICENSE`）。試合結果・順位は事実データ、FIFA レポートへのリンクは各記事の URL を指すのみです。
