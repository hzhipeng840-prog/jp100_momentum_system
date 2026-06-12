# 日株モメンタム100

JPXの東証上場銘柄一覧、Yahoo!ファイナンスの日本株ランキング、yfinanceの無料日足データを組み合わせ、以下を毎日生成するStreamlitアプリです。

現在の正式版はルートの `VERSION` を参照してください。変更履歴は `CHANGELOG.md`、各版の詳細は `docs/versions/` に記録します。

- 注目Top100
- 毎日厳選3～5銘柄
- Yahooランキング候補銘柄一覧
- 翌日寄付・1/3/5/10営業日の履歴追跡
- 簡易検証、データ鮮度、日付別スナップショット

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 日次更新

実データを取得する全量更新です。通常の開発確認では毎回実行する必要はありません。

```powershell
python daily_job.py
```

毎日厳選を3銘柄、Yahooランキングを各5ページ取得する場合:

```powershell
python daily_job.py --daily-count 3 --yahoo-pages 5
```

生成ファイル:

- `data/processed/candidate_pool.csv`
- `data/processed/top100.csv`
- `data/processed/daily_picks.csv`
- `data/processed/followups.csv`
- `data/processed/backtest_summary.csv`
- `data/processed/metadata.json`
- `data/processed/latest.json`

各実行の完成済みデータは `data/snapshots/YYYY-MM-DD/実行ID/` に保存されます。
画面は `latest.json` が指す同一実行のファイルだけを読み込むため、更新途中の不完全な結果を表示しません。

候補、Top100、毎日厳選、追跡結果の累積履歴は `data/history/` に保存されます。

## 画面起動

```powershell
python -m streamlit run app.py
```

Windowsで `streamlit` コマンドが見つからない場合も、上記のモジュール実行形式なら起動できます。

## 開発時の高速確認

ネットワークへ接続せず、構文、単体テスト、差分形式を確認します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

開発中はこの高速確認を基本とし、JPX・Yahoo・yfinanceへの全量アクセスは、データ処理変更の最終確認時だけ行います。

AIエージェントを含む開発規約、Planモード、禁止操作、コマンドの実行時間制限は `AGENTS.md` を参照してください。

## バージョン履歴

正式版は `v1`、`v2`、`v3` の連番で管理し、`v100`以降も同じ規則で継続します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/new_version.ps1
```

新しい版を公開する前に、`CHANGELOG.md` と `docs/versions/vN.md` を更新し、同じ番号のGitタグを付けます。詳しい規約は `docs/versioning.md` を参照してください。

## 評価ロジック

候補銘柄ごとに20日・60日・120日騰落率、20日・60日移動平均との距離、平均売買代金、前20営業日平均に対する当日出来高倍率、120日高値との距離、20日変動率を計算します。各指標を候補内百分位に変換して合成し、Top100を作成します。

毎日厳選では、Top100に株価、流動性、トレンド、過熱度、変動率、業種分散の条件を追加します。

## 履歴検証

毎日厳選は基準日終値で記録し、翌営業日寄付を実行想定として追跡します。これはシグナルの簡易統計であり、資金配分、100株単位、手数料、スリッページを含む正式なポートフォリオ回測ではありません。

## 注意事項

本プロジェクトは情報整理・研究用です。投資助言ではありません。Yahoo!ファイナンスおよびyfinanceの提供仕様変更、無料データの遅延・欠損により更新できない場合があります。各サイトの利用条件を確認し、過度なアクセスを避けてください。
