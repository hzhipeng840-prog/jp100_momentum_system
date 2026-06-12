# 日株モメンタム100

JPXの東証上場銘柄一覧、Yahoo!ファイナンスの日本株ランキング、yfinanceの無料日足データを組み合わせ、以下を毎日生成するStreamlitアプリです。

- 注目Top100
- 毎日厳選3～5銘柄
- Yahooランキング候補銘柄一覧
- CSV出力と更新メタデータ

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 日次更新

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
- `data/processed/metadata.json`

## 画面起動

```powershell
python -m streamlit run app.py
```

Windowsで `streamlit` コマンドが見つからない場合も、上記のモジュール実行形式なら起動できます。

## 評価ロジック

候補銘柄ごとに20日・60日・120日騰落率、20日・60日移動平均との距離、平均売買代金、出来高倍率、120日高値との距離、20日変動率を計算します。各指標を候補内百分位に変換して合成し、Top100を作成します。

毎日厳選では、Top100に株価、流動性、トレンド、過熱度、変動率、業種分散の条件を追加します。

## 注意事項

本プロジェクトは情報整理・研究用です。投資助言ではありません。Yahoo!ファイナンスおよびyfinanceの提供仕様変更、無料データの遅延・欠損により更新できない場合があります。各サイトの利用条件を確認し、過度なアクセスを避けてください。
