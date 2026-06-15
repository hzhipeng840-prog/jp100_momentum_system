# 日株モメンタム100

JPXの東証上場銘柄一覧、Yahoo!ファイナンスの日本株ランキング、yfinanceの無料日足データを組み合わせ、以下を毎日生成するStreamlitアプリです。

現在の正式版はルートの `VERSION` を参照してください。変更履歴は `CHANGELOG.md`、各版の詳細は `docs/versions/` に記録します。

- 注目Top100
- 毎日厳選3～5銘柄
- Yahooランキング候補銘柄一覧
- 翌日寄付・1/3/5/10営業日の履歴追跡
- 簡易検証、データ鮮度、日付別スナップショット
- ルール通過比較、因子五分位、IC、上位分位入替率
- TOPIX超過収益、取引コスト、仮想ポートフォリオ
- Yahoo候補とJPX流動性ユニバースの比較
- 今日の市場判断、リスク警告、ローカルウォッチリスト

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 日次更新

実データを取得する全量更新です。通常の開発確認では毎回実行する必要はありません。
JPXプライム普通株の流動性走査も行うため、価格キャッシュがない初回更新は
2回目以降より時間がかかります。

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
- `data/processed/evaluation_followups.csv`
- `data/processed/rule_evaluation.csv`
- `data/processed/factor_quantile_evaluation.csv`
- `data/processed/factor_ic.csv`
- `data/processed/factor_turnover.csv`
- `data/processed/jpx_liquidity_universe.csv`
- `data/processed/jpx_liquidity_top100.csv`
- `data/processed/universe_comparison.csv`
- `data/processed/version_comparison.csv`
- `data/processed/portfolio_curve.csv`
- `data/processed/portfolio_summary.csv`
- `data/processed/virtual_positions.csv`
- `data/processed/market_environment.csv`
- `data/processed/risk_alerts.csv`
- `data/processed/metadata.json`
- `data/processed/latest.json`

各実行の完成済みデータは `data/snapshots/YYYY-MM-DD/実行ID/` に保存されます。
画面は `latest.json` が指す同一実行のファイルだけを読み込むため、更新途中の不完全な結果を表示しません。

候補、Top100、毎日厳選、追跡結果の累積履歴は `data/history/` に保存されます。

## GitHub Actionsによる自動更新

`.github/workflows/daily_pipeline.yml` は次の時刻に起動します。

- 平日19:17（日本時間）: 通常実行
- 平日21:47（日本時間）: 未完了時の補完実行

日本の祝日と休場日は `exchange_calendars` の `XTKS` で判定してスキップします。
同じ基準日・同じ版が完了済みの場合も再生成しません。
Actions画面の「Run workflow」から手動実行でき、必要な場合だけ
`force` を有効にして同日再実行できます。

生成結果はコードの `main` ではなく、独立した `data` ブランチへ公開します。
最初に成功した自動更新で `data` ブランチが作成されます。
Actions Cacheは `data/raw/` の再取得量削減だけに使用し、
正式な履歴保存先にはしません。実行状態、ログ、処理済み結果は
Actions Artifactへ14日保存します。

GitHub Actionsのスケジュールは混雑により遅延する場合があります。
本システムは日次終値ベースのため、外部cronは使わず、
通常実行と補完実行の二段構成で運用します。

クラウドの最新結果をローカルへ同期する場合:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync_cloud_data.ps1
```

ローカル結果の基準日がクラウドより新しい場合は同期を拒否します。
確認後に上書きする場合だけ `-Force` を追加します。

## 画面起動

```powershell
python -m streamlit run app.py
```

Windowsで `streamlit` コマンドが見つからない場合も、上記のモジュール実行形式なら起動できます。
Python Install Managerが別のPythonを選ぶ環境では、Streamlit導入済みPythonを自動検出する次のスクリプトを使用してください。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_app.ps1
```

依存関係の導入も同じPythonへ揃える場合:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

## 開発時の高速確認

ネットワークへ接続せず、構文、単体テスト、差分形式を確認します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

開発中はこの高速確認を基本とし、JPX・Yahoo・yfinanceへの全量アクセスは、データ処理変更の最終確認時だけ行います。

AIエージェントを含む開発規約、Planモード、禁止操作、コマンドの実行時間制限は `AGENTS.md` を参照してください。

## バージョン履歴

正式版は `v1`、`v2`、`v3`、`v4` の連番で管理し、
`v100`以降も同じ規則で継続します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/new_version.ps1
```

新しい版を公開する前に、`CHANGELOG.md` と `docs/versions/vN.md` を更新し、同じ番号のGitタグを付けます。詳しい規約は `docs/versioning.md` を参照してください。

## 評価ロジック

候補銘柄ごとに20日・60日・120日騰落率、20日・60日移動平均との距離、平均売買代金、前20営業日平均に対する当日出来高倍率、120日高値との距離、20日変動率を計算します。各指標を候補内百分位に変換して合成し、Top100を作成します。

毎日厳選では、Top100に株価、流動性、トレンド、過熱度、変動率、業種分散の条件を追加します。

## 履歴検証

毎日厳選は基準日終値で記録し、翌営業日寄付を実行想定として追跡します。
v3ではTOPIX超過収益、片道0・10・25・50bpのコストシナリオ、
5営業日保有の等金額仮想ポートフォリオも計算します。
100株単位、税金、指値約定、市場インパクトを再現する正式な売買シミュレーターではありません。

## 候補比較と市場判断

正式な注目Top100は従来どおりYahooランキング候補から作成します。
並行実験として、JPXプライム普通株を20日平均売買代金で絞った
流動性ユニバースのTop100を作り、同じ将来収益で比較します。

「今日の判断」ではTOPIXトレンド、市場の広がり、厳選銘柄の相関、
変動率、業種集中から「積極」「中立」「慎重」を表示します。
判定は情報整理用であり、自動売買や利益予測には使用しません。

## ウォッチリスト

画面から銘柄コードと個人メモを登録できます。
保存先は `data/user/watchlist.csv` で、Git管理対象外です。

## ルール・因子評価

Top100選定時点の因子値とルール発動状態を `evaluation_version` 付きで保存し、1・3・5・10営業日の将来リターン確定後に評価します。

- 因子五分位ごとの平均、中央値、勝率、上位分位と下位分位の差
- 日次Spearman Information Coefficient
- 期待方向上位分位の入替率
- 全体・業種別の因子評価
- ルール通過群と未通過群の平均差、勝率、95%信頼区間
- 最低サンプル数に達するまでの「サンプル不足」表示

評価結果は改善候補を判断する資料であり、自動で評価重みや毎日厳選条件を書き換えません。

設計は [Alphalens Reloaded](https://github.com/stefan-jansen/alphalens-reloaded) の収益分析、IC分析、入替率、グループ分析を参考にしています。研究用ティアシートを試す場合は次を使用します。

```powershell
python -m pip install -r requirements-research.txt
```

東証営業日は [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars) の `XTKS` を使用します。

## 注意事項

本プロジェクトは情報整理・研究用です。投資助言ではありません。Yahoo!ファイナンスおよびyfinanceの提供仕様変更、無料データの遅延・欠損により更新できない場合があります。各サイトの利用条件を確認し、過度なアクセスを避けてください。
