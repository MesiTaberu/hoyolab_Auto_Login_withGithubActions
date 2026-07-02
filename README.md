# HoYoLAB Auto Login with GitHub Actions

このリポジトリは、次のデイリーチェックインを GitHub Actions で自動化します。

- HoYoLAB（原神 / 崩壊スターレイル / 崩壊3rd / ゼンレスゾーンゼロ）
- Endfield（Arknights: Endfield）

## 自動実行タイミング

`.github/workflows/auto-checkin.yml` の `cron` は現在 `毎日 01:00 JST` です。  
必要に応じて編集してください。

workflow 名は `Auto Hoyolab Check-in` です。  
初回 fork 後は `Actions` タブで workflow を有効化してから使ってください。

## GitHub Actions の自動無効化について

GitHub Actions の scheduled workflow は、リポジトリに 60 日間アクティビティがないと自動的に無効化されることがあります。  
無効化されそうな場合や定期実行が止まった場合は、`Actions` タブから対象 workflow を開いて有効化してください。

このリポジトリで定期実行される主な workflow:

| Workflow | File | 用途 |
|---|---|---|
| `Auto Hoyolab Check-in` | `.github/workflows/auto-checkin.yml` | HoYoLAB / Endfield のデイリーチェックイン |
| `Auto Game Code Redeem` | `.github/workflows/redeem-codes.yml` | HoYoverse 系ゲームの交換コード自動入力 |

## セットアップ

### 1. リポジトリを fork

GitHub 上で fork して使ってください。

fork 直後は Actions が無効になっている場合があります。  
その場合は `Actions` タブから有効化してください。

### 2. Actions Secrets を登録

`Settings > Secrets and variables > Actions > Repository secrets` に登録します。  
`Repository variables` ではなく `Repository secrets` に入れてください。

必須 Secret 一覧:

| Secret Name | 用途 |
|---|---|
| `LTUID` | HoYoLAB 用 Cookie |
| `LTOKEN` | HoYoLAB 用 Cookie |
| `COOKIE_TOKEN_V2` | HoYoLAB 用 Cookie |
| `ENDFIELD_CRED` | Endfield API 認証ヘッダ |
| `ENDFIELD_SK_GAME_ROLE` | Endfield API 認証ヘッダ |

補足:
- `ENDFIELD_PLATFORM` / `ENDFIELD_VNAME` / `ENDFIELD_ACCOUNT_NAME` はこの workflow では不要です。
- Secrets の編集画面は仕様上、既存値が空欄表示になります（値が消えているわけではありません）。

## HoYoLAB 用 Secret 取得方法

### cookiegrab.exe（推奨）

1. GitHub Releases から `cookiegrab.exe` をダウンロード
2. 対象ゲームのチェックインページを開く（ログイン済み状態にする）
3. DevTools (`F12`) → `Network`
4. `Preserve log` を ON にして、ページを再読み込み（通信を出す）
5. `Save all as HAR with content` で `.har` を保存
6. `cookiegrab.exe` で HAR を読み取って値を表示

例:

```bat
cookiegrab.exe --list-games
cookiegrab.exe 1 "C:\\path\\to\\hoyolab.har" --raw
```

出力された値をそのまま Secrets に登録してください:
- `LTUID`
- `LTOKEN`
- `COOKIE_TOKEN_V2`

注意:
- `.har` には Cookie やヘッダが含まれるので、他人に共有しないでください。使い終わったら削除推奨です。

## Endfield 用 Secret 取得方法（`ENDFIELD_CRED`, `ENDFIELD_SK_GAME_ROLE`）

1. Endfield サインインページを開いてログイン  
   `https://game.skport.com/endfield/sign-in?header=0&hg_media=skport&hg_link_campaign=tools`
2. DevTools (`F12`) → `Network`
3. `Preserve log` を ON にして、サインイン（出席）ボタンを 1 回押して通信を出す
4. `Save all as HAR with content` で `.har` を保存
5. `cookiegrab.exe` で HAR を読み取って値を表示

例:

```bat
cookiegrab.exe 5 "C:\\path\\to\\endfield.har" --raw
```

出力された値を Secrets に登録してください:
- `ENDFIELD_CRED`
- `ENDFIELD_SK_GAME_ROLE`

## 動作確認

1. `Actions` タブで `Auto Hoyolab Check-in` を開く
2. `Run workflow` を実行
3. ログで次を確認
   - HoYoLAB: `retcode -5003` は「本日分取得済み」
   - Endfield: `claimed` または `already-claimed`

## 交換コードの自動実行

`.github/workflows/redeem-codes.yml` で、HoYoverse 系ゲームの交換コード入力も自動化できます。  
コードは HoYoLAB 投稿検索 API から取得し、GitHub Actions 上で交換します。

登録する Secrets:

| Secret Name | 用途 |
|---|---|
| `LTUID` | HoYoLAB / HoYoverse Cookie |
| `LTOKEN` | HoYoLAB / HoYoverse Cookie |
| `COOKIE_TOKEN_V2` | HoYoLAB / HoYoverse Cookie |
| `HOYOVERSE_COOKIE` | 交換ページのCookieヘッダー。登録されている場合、交換APIではこちらを優先 |

UID / region は Cookie から自動取得します。複数アカウントなどで明示したい場合だけ Variables を登録してください。

| Game | Variables |
|---|---|
| 原神 | `GENSHIN_UID`, `GENSHIN_REGION` |
| 崩壊スターレイル | `HSR_UID`, `HSR_REGION` |
| ゼンレスゾーンゼロ | `ZZZ_UID`, `ZZZ_REGION` |

region の例:

```text
GENSHIN_REGION=os_asia
HSR_REGION=prod_official_asia
ZZZ_REGION=prod_gf_jp
```

スケジュール実行はログボと同じ毎日 01:00 JST です。`workflow_dispatch` でも入力なしで手動実行できます。

コード取得ロジック:

- HoYoLAB 検索 API をゲーム別に新しい順で検索
- タイトルに `code`, `redeem`, `redemption`, `コード`, `交換コード` などを含む投稿だけを候補にする
- コード候補は投稿本文、タイトル、リンクURLの `code=` から抽出する
- 交換APIに投げて、無効/期限切れコードは `rejected` としてログに出す

必要なら Variables で検索範囲を調整できます。

```text
HOYOLAB_LOOKBACK_HOURS=168
HOYOLAB_PAGE_SIZE=20
REDEEM_HOYOLAB_ENABLED=true
REDEEM_DELAY_SECONDS=5
```

注意:
- 画像内だけに書かれたコードは読み取れません。
- HoYoLAB 投稿の本文やタイトル表記によっては拾えないことがあります。
- HoYoLAB の一般投稿も検索対象になるため、最終的な有効判定は交換APIの結果に依存します。

## 継続運用メモ

- 定期実行が止まった場合は、まず `Actions` タブで workflow が無効化されていないか確認してください。60 日以上リポジトリ更新がない場合、GitHub により scheduled workflow が自動無効化されることがあります。
- Secret の値はログイン期限や認証更新で使えなくなることがあります。失敗が続く場合は HAR を取り直して Secret を更新してください。
- fork 元を更新したい場合は、定期的に upstream の変更を取り込んで workflow や API 変更に追従してください。
- 実行時刻を変えたい場合は [`.github/workflows/auto-checkin.yml`](c:/Users/hukuc/Documents/RPA_SWR/hoyolab_auto_login/hoyolab_Auto_Login_withGithubActions/.github/workflows/auto-checkin.yml) の `cron` を編集します。
