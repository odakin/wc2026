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
- 期間: 大会の対象期間中のみ 30 分ごと。**停止日 = 2026-07-20**（W杯決勝 2026-07-19 の翌日）。
  それ以降は自分で停止する（「終了」 セクション）。⚠️ 決勝トーナメントは 7 月まで続くので、停止日を前倒しして大会途中で止めないこと。

## このジョブの登録（再登録）

別マシン（iMac 等）でこのジョブを 30 分ごとに走らせる登録 spec。Claude はこの通りに
`create_scheduled_task` を呼ぶ（重複防止に、先に `list_scheduled_tasks` で同 taskId が無いか確認）:

- taskId: `wc2026-auto-update`
- cronExpression: `*/30 * * * *`
- notifyOnCompletion: false
- prompt: 「`~/Claude/wc2026` の `AUTO_UPDATE.md` を読み、その手順を最初から最後まで実行する。fresh session 前提なので全て self-contained に進める。」

> アカウント切替後など登録が消えたら、この spec で登録し直すだけでよい。

## 毎回の手順

1. **期間チェック（最優先）**: 今が**停止日（2026-07-20）以降**なら 「終了」 セクションに従い停止して終了。
   それ以前なら続行。
2. **同期**: `git fetch` → clean かつ ff 可能なら `git pull --ff-only`。
   diverged/dirty なら surface して**この回は中断**（壊さない）。
3. **未記録の消化済み試合を洗い出す**: `data/results.yaml` の `meta.as_of` と既存 matches を読み、
   `data/fixtures.yaml` の対戦カードのうち **キックオフ済みなのに `results.yaml` 未記録**のものを候補にする。
   - 日付の鉄則: `results.yaml` の `date` は**現地（北米）開催日**、`fixtures.yaml` の時刻は **JST**。
     両者は最大 1 日ずれる（JST が進む。夜の試合は JST だと翌日昼）。突合前に必ず時差変換する。
   - **もう一つの候補 = 配信待ちの backfill**: `articles.py --check` の ⏳ 配信待ちリスト
     （= スコア記録済みだがリンク未着の試合）も毎 run の探索対象に含める（リンクは時間差で出るため）。
     決して止めない設計理由は [`scripts/articles.py`](scripts/articles.py) docstring。
4. **裏取り（厳格・推測禁止）**: 各候補について web 検索で最終スコアを **2 ソース以上**
   （FIFA 公式 + ESPN / Sky Sports / Wikipedia / 各国紙のいずれか）で一致確認。
   - **中断・進行中・1 ソースのみ → 記録しない**（次回に回す）。スコアを憶測で埋めない。
5. **スコアを追記**（確定したものだけ・**記事リンクの有無に関わらず即記録する**）:
   - スコアと記事リンクは分離: リンク未着でも `results.yaml` にスコアを記録 → `standings.py` 経由で
     順位表・公開サイトに即反映。原則の正本は [`scripts/articles.py`](scripts/articles.py) docstring。
   - `data/results.yaml` の `matches:` に 1 行追記（schema: `{"no", group, md, date(現地開催日), home, away, hg, ag, note?}`、
     チーム名は `fixtures.yaml` と統一）。`meta.as_of` を今日（JST）に、`meta.note` を更新。
   - **`"no"`（FIFA公式試合番号）も必ず付与**: `fixtures.yaml` の同カード（同 group + 同チーム対）の `no` をそのままコピー
     （= results と fixtures を no で join できる状態を保つ）。キーは **`no:` でなく `"no":` とクォート**する
     （PyYAML が `no:` を boolean False キーに解釈する YAML1.1 の罠）。fixtures に無い早期試合は触らない想定だが、
     念のため §7 の検算ゲートで欠落・不一致を検出する。
   - **決勝T（knockout）の結果は `winner:`（チーム名）も記録する**（= 延長・PK では score だけで勝者が
     出ないため）。**PK 戦は `winner` 必須** + `note` に「PK ○-○ で◯◯勝利」を 2 ソースで明記（hg/ag は
     延長終了時のスコア）。score 決着でも `winner` を付けると伝播が確実（無ければ hg/ag から導出、引き分け
     かつ `winner` 無しは未解決扱い）。knockout は `group` を付けない（順位計算対象外）。`winner` は home/away
     のどちらかに一致させる。次ラウンドの対戦カードは §7 の伝播ステップが自動で埋めるので手で書かない。
   - **記事リンクは best-effort（見つかれば追記、無ければ配信待ちのまま先へ）**: FIFA公式リンクの URL を探して
     `data/articles.yaml` に追記（cat: 報道・公式 / source: FIFA公式）。 見つからなければ追記しないだけで、
     スコアは上で記録済み（= 順位は反映済）。そのリンクは次回 run の §3 backfill 候補として再探索される。
     **リンク優先順位**: ① 日本語版マッチレポート記事 `/ja/…/articles/<slug>-ja` が配信済ならそれ →
     ② 未配信なら FIFA公式ハイライト動画 `/ja/watch/<id>`（note に「日本語記事版が未配信のため動画にリンク」 と明記）。
     選定基準・en 変換・url_en 上書き・マッチセンター不使用 等の詳細は
     [`data/articles.yaml`](data/articles.yaml) ヘッダ「リンク優先順位」 節が正本。
   - URL は **実在確認**してから入れる（推測 slug / 動画 ID 禁止）。fifa.com は SPA で fetch が空シェルを返すため、
     **検索インデックスのタイトル一致**で確認する（fetch が空 ≠ 確認不能）。チーム・スコアが当該カードと一致することも確認。
   - 順位が 1〜5 で決着しない同点が出たら、フェアプレー点を FIFA/Wikipedia で確認し
     `meta.tiebreak.conduct` に出典付きで追加。**逆に、後の節で同点が解消し criterion 1〜5 で
     決着したら、その組の conduct エントリは削除する**（追加するルールだけだと決着後も残って
     stale な順位注記になる。2026-06-28 に K組で実際に発生＝「(コンゴが上位)」が決着後も残存）。
6. **② → ① upgrade sweep（link 軸の毎 run 保守、 必ず §7 の rebuild より前に走らせる）**:
   既存の video-primary entry（= ② tier）を全部走査して、 FIFA が後追いで ja マッチレポート記事を
   配信していないか WebSearch で再 audit する。 配信されていれば自動で ②→① に upgrade。
   - **対象列挙**（primary url が `/watch/` を含む match block を全部）:
     ```
     python3 -c "import yaml; arts=yaml.safe_load(open('data/articles.yaml'))['matches']; [print(m.get('key'), '|', m.get('title')) for m in arts if (m.get('refs') or [{}])[0].get('url','').find('/watch/')>=0]"
     ```
   - **試合終了直後の skip**: 各候補の試合終了から **1h 未満なら skip**（= FIFA 未配信時間帯。
     試合 ~2h と見なし `fixtures.yaml` の `start_jst` + 2h で判定）。 これで次戦 R32 などの新規 ② が
     入った直後の無駄打ちを抑える。
   - **WebSearch query**（両表記を必ず check。 FIFA はホーム/アウェイ表記を逆にすることがあるので
     片側だけだと取り逃す。 2026-06-30 sweep で M73 が「カナダ 1-0 南アフリカ」 タイトルだった実例あり）:
     - group: `site:fifa.com/ja "{home} {hg}-{ag} {away}" マッチレポート ハイライト`
       + `site:fifa.com/ja "{away} {ag}-{hg} {home}" マッチレポート ハイライト`
     - knockout: 同上 + 必要に応じ「ラウンド32」/「準々決勝」 等を query に追加
   - **必須 gate（= false positive 防止）**:
     1. 検索結果の URL が `/ja/(...)/articles/{slug}-ja`（長 path）または `/ja/articles/{slug}-ja`（短 path）
        の形であること。
     2. その検索結果のタイトルに「{home} {hg}-{ag} {away}」 か「{away} {ag}-{hg} {home}」 が**含まれる**こと。
     ⚠️ `fifa.com` は SPA なので HEAD 200 を全 URL に返す → URL 単独確認は無効。 **検索 hit のタイトル一致が
     唯一の生死確認 gate**。 上 2 条件いずれか欠ければ apply しない。
   - **apply**（gate 通過したら `articles.yaml` の該当 entry を書き換え）:
     - `url`: 採用した ja 記事 URL
     - `title`: 「{home} {hg}-{ag} {away}｜マッチレポート＆ハイライト」（PK 戦は `(PK x-y)` を含める、
       例「ドイツ 1-1 パラグアイ (PK 3-4)｜マッチレポートとハイライト」）
     - `note`: 「FIFA公式マッチレポート＋ハイライト（YYYY-MM-DD ② → ① upgrade sweep、
       検索 hit タイトル『{hit title}』 で実在 ∧ 試合一致確認）」 で完全置換（古い動画 note は捨てる）
   - **不一致 / 0 hit / WebSearch エラー**: そのまま video のまま放置（= **downgrade しない**、
     次回 run で再 sweep される）。
   - **ヘッダ自己 maintenance**: 1 件以上 upgrade した場合は `articles.yaml` ヘッダの
     「現在 ② 止まりは N 試合 (XX/YY/...)」 の N と list、 snapshot 日付も更新する（= 次回 sweep 対象判定の
     SoT になっているわけではないが、 ヘッダの記述と実態を一致させる）。
   - ⚠️ **推測 URL 禁止**。 video のまま放置するのは安全側、 誤 upgrade は不可逆（= 死 URL を public に
     出してしまう、 fifa_localize で en 側にも同型死 URL が伝播する）。 タイトル一致 gate を必ず通す。
   - sweep が 0 件で済む run の方が普通（= 新規 ② が無ければ run skip と等価）。 1 件以上 upgrade した
     run は commit に「articles: ② → ① sweep upgrade N 件 (...)」 を含めて他 session から見えるようにする。
7. **再生成 + 公開**:
   - `python3 scripts/standings.py --write`（順位表 + `standings.md`）。
   - `python3 scripts/articles.py --write`（`articles.md`）。
   - **記事ゲート**: `python3 scripts/articles.py --check`。 blocking finding（ref 欄欠落・未知
     cat・URL 重複・実在しない結果を指す記事ブロック）のみ exit 1 → §5 に戻って `articles.yaml` を
     直す。リンク未着は ⏳ 配信待ちで止まらない（次 run で再探索）。 原則の正本は
     [`scripts/articles.py`](scripts/articles.py) docstring。
     ⚠ マーク付き（猶予日数超過）の配信待ちは「日本語記事が出ない試合かも」の合図 → 動画②へのフォールバックを検討。
   - **試合番号ゲート（必須）**: `python3 scripts/check-match-numbers.py`。
     finding（result の `no` 欠落・重複、fixtures との `no` 不一致）が出たら **exit 1**。
     その場合は §5 に戻って `no` を正す（fixtures の同カードの no と一致させる）。番号がズレたまま公開しない。
   - **決勝T 伝播（knockout の対戦カード自動進行）**: `python3 scripts/propagate-knockout.py --apply`。
     記録済み knockout 結果から、次ラウンドの `fixtures.yaml` の slot label（`M<no>勝者`/`M<no>敗者`）を
     実チーム名に決定論的に解決する（冪等。R32 結果→R16、R16 結果→QF、… と 1 段ずつ自動で埋まる）。
     **変更があれば `data/fixtures.yaml` を commit に含める**（build はこの後なので bracket に反映される）。
     ⚠ 出力に「引き分けだが winner 未記録」警告が出たら §5 に戻り PK 勝者を `winner:` に追記して再実行。
   - `python3 build.py`（日英 docs 再生成）。
   - **死活打刻（必須）**: `python3 scripts/heartbeat.py --beat`。`heartbeat.json` を今の時刻で更新する
     （= ジョブが生きている証跡。`commit` に必ず含める）。
   - **leak gate**: 差分を `group\.calendar|@gmail|@.*\.ac\.jp|/Users/` 等（個人情報・カレンダー ID・
     個人パス・内部 private リポ名）で grep し、ヒットしたら push 中止して surface（公開リポに出さない）。
   - commit + push（main）。GitHub Pages が自動反映。
8. **何も新規が無い回**: それでも **死活打刻だけは必ず行う** —
   `python3 scripts/heartbeat.py --beat` → `heartbeat.json` のみを commit + push して終了。
   - これを毎回やることで、別マシンから `python3 scripts/heartbeat.py --check` でジョブの死活が判る
     （= no-op を理由に打刻を飛ばすと「試合が無いだけ」か「ジョブが死んだ」かが区別できなくなる。
     2026-06-26 に実際にこれで 6 試合を取りこぼした）。閾値超で `--check` は exit 1。

## 終了（対象期間後 = 2026-07-20 以降）

停止日（2026-07-20）以降の最初の実行で、最後に最終結果を反映してから、自分（この自動更新ジョブ）を停止する。
このジョブが **scheduled task** か **launchd cron** かで止め方が違う:

- **launchd cron 版**（現行の標準）: そのマシンの terminal で `--uninstall-one wc2026-auto-update`
  （= plist の bootout + 削除）を実行する。launchd cron の登録機構（plist 生成・`--uninstall-one` 等）は
  公開リポ claude-config の `scripts/install-launchd-cron.sh` が SoT:
  `zsh ~/Claude/claude-config/scripts/install-launchd-cron.sh --label-prefix com.odakin.claude-cron --uninstall-one wc2026-auto-update`
  ジョブ自身（headless 実行中）は止め方を出力に書き残すだけにして、無理に自分を kill しない。
- **scheduled task 版**（旧経路）: `scheduled-tasks` MCP の delete で自分を消す。

> ⚠️ **止めるのは 30 分ごとの更新ジョブだけ**。公開サイト（`docs/` / GitHub Pages）とリポは**削除しない**。
> サイトは最終結果を表示したまま残す。

## 注意 / 限界

- これは **判断込みの自動公開**（web 検索 → 2 ソース確認 → 公開）。人手 review を毎回挟まないので、
  誤報の取り込みリスクはゼロではない（2 ソース gate で抑制）。**スコアの確定が曖昧な試合は飛ばす**。
- 公開 push は **leak gate を必ず通す**（個人情報・内部パスを public に出さない）。
