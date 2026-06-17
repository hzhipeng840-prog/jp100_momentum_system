from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from jp100.config import PROCESSED_DIR, PipelineConfig  # noqa: E402
from jp100.pipeline import run_pipeline  # noqa: E402
from jp100.storage import resolve_latest_output  # noqa: E402
from jp100.watchlist import (  # noqa: E402
    add_watchlist_entry,
    enrich_watchlist,
    load_watchlist,
    remove_watchlist_entries,
    save_watchlist,
)


st.set_page_config(
    page_title="日株モメンタム100",
    page_icon="株",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --ink: #15233a;
        --muted: #667085;
        --navy: #0f3159;
        --blue: #1769aa;
        --pale: #eef5fb;
        --gold: #b9872d;
        --line: #dce6ef;
    }
    .stApp {
        background:
            radial-gradient(circle at 90% 3%, rgba(23,105,170,.08), transparent 26rem),
            linear-gradient(180deg, #fbfdff 0%, #f5f8fb 100%);
        color: var(--ink);
    }
    .block-container { padding-top: 1.8rem; max-width: 1500px; }
    h1, h2, h3 { color: var(--navy); letter-spacing: .01em; }
    [data-testid="stMetric"] {
        background: rgba(255,255,255,.88);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 14px 16px;
        box-shadow: 0 8px 24px rgba(15,49,89,.05);
    }
    .hero {
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 25px 28px;
        background: linear-gradient(120deg, rgba(255,255,255,.96), rgba(238,245,251,.94));
        box-shadow: 0 16px 40px rgba(15,49,89,.07);
        margin-bottom: 18px;
    }
    .hero-kicker {
        color: var(--blue);
        font-size: .78rem;
        font-weight: 700;
        letter-spacing: .14em;
        margin-bottom: .35rem;
    }
    .hero-title {
        color: var(--navy);
        font-size: 2rem;
        line-height: 1.25;
        font-weight: 800;
        margin-bottom: .5rem;
    }
    .hero-copy { color: var(--muted); max-width: 860px; line-height: 1.8; }
    .pick-card {
        background: rgba(255,255,255,.94);
        border: 1px solid var(--line);
        border-top: 4px solid var(--blue);
        border-radius: 15px;
        padding: 17px;
        min-height: 220px;
        box-shadow: 0 10px 28px rgba(15,49,89,.06);
    }
    .pick-rank { color: var(--gold); font-weight: 800; font-size: .8rem; }
    .pick-name { color: var(--navy); font-weight: 800; font-size: 1.06rem; margin: 7px 0 2px; }
    .pick-code { color: var(--muted); font-size: .78rem; }
    .pick-score { color: var(--blue); font-size: 1.55rem; font-weight: 800; margin: 13px 0 4px; }
    .pick-reason { color: var(--ink); font-size: .86rem; line-height: 1.55; }
    .pick-detail { color: var(--muted); font-size: .78rem; margin-top: 11px; line-height: 1.55; }
    .notice {
        border-left: 4px solid var(--gold);
        background: #fffaf0;
        padding: 12px 15px;
        border-radius: 8px;
        color: #59451f;
        font-size: .86rem;
        line-height: 1.7;
    }
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stButton"] button {
        border-radius: 10px;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_outputs() -> tuple[dict[str, pd.DataFrame], dict]:
    def read_csv(name: str) -> pd.DataFrame:
        path = resolve_latest_output(PROCESSED_DIR, name)
        if not path.exists():
            return pd.DataFrame()
        try:
            return pd.read_csv(path, dtype={"code": str})
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    output_names = [
        "daily_picks.csv",
        "top100.csv",
        "candidate_pool.csv",
        "followups.csv",
        "backtest_summary.csv",
        "rule_evaluation.csv",
        "factor_quantile_evaluation.csv",
        "factor_ic.csv",
        "factor_turnover.csv",
        "jpx_universe.csv",
        "jpx_liquidity_universe.csv",
        "jpx_liquidity_top100.csv",
        "universe_comparison.csv",
        "version_comparison.csv",
        "portfolio_curve.csv",
        "portfolio_summary.csv",
        "virtual_positions.csv",
        "market_environment.csv",
        "risk_alerts.csv",
    ]
    metadata_path = resolve_latest_output(PROCESSED_DIR, "metadata.json")
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else {}
    )
    return ({name: read_csv(name) for name in output_names}, metadata)


def pct(value: object) -> str:
    try:
        number = float(value)
        if not math.isfinite(number):
            return "―"
        return f"{number:+.1%}"
    except (TypeError, ValueError):
        return "―"


def yen(value: object) -> str:
    try:
        number = float(value)
        if not math.isfinite(number):
            return "―"
        return f"¥{number:,.0f}"
    except (TypeError, ValueError):
        return "―"


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def render_pick_cards(picks: pd.DataFrame) -> None:
    columns = st.columns(min(5, max(1, len(picks))))
    for index, (_, row) in enumerate(picks.iterrows()):
        with columns[index % len(columns)]:
            st.markdown(
                f"""
                <div class="pick-card">
                    <div class="pick-rank">本日の厳選 {int(row.get('pick_rank', index + 1))}</div>
                    <div class="pick-name">{row.get('name', '')}</div>
                    <div class="pick-code">{row.get('code', '')} ・ {row.get('market', '')} ・ {row.get('industry', '')}</div>
                    <div class="pick-score">{float(row.get('score', 0)):.1f}<span style="font-size:.72rem;color:#667085"> 点</span></div>
                    <div class="pick-reason">{row.get('selection_reason', '総合スコア上位')}</div>
                    <div class="pick-detail">
                        終値 {yen(row.get('close'))}<br>
                        20日 {pct(row.get('return_20d'))} ／ 60日 {pct(row.get('return_60d'))}<br>
                        出来高倍率 {float(row.get('volume_ratio_20d', 0)):.2f}倍<br>
                        候補出現 {int(row.get('appearance_count', 1))}回 ／ 連続 {int(row.get('consecutive_appearances', 1))}回
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def top100_view(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "rank",
        "code",
        "name",
        "market",
        "industry",
        "score",
        "close",
        "return_1d",
        "return_20d",
        "return_60d",
        "volume_ratio_20d",
        "avg_turnover_20d",
        "appearance_count",
        "consecutive_appearances",
        "yahoo_rank_change",
        "ranking_sources",
    ]
    view = frame[[column for column in columns if column in frame]].copy()
    for column in ("return_1d", "return_20d", "return_60d"):
        if column in view:
            view[column] = view[column] * 100
    return view


with st.sidebar:
    st.markdown("## 更新設定")
    yahoo_pages = st.slider(
        "ランキング取得ページ数",
        min_value=1,
        max_value=5,
        value=3,
        help="値上がり率・出来高・出来高増加率から、それぞれ最大50件×ページ数を取得します。",
    )
    daily_count = st.slider("毎日厳選の銘柄数", 3, 5, 5)
    refresh = st.button("最新データを取得", type="primary", width="stretch")
    st.caption("取得には数分かかる場合があります。")
    st.divider()
    st.markdown("### データソース")
    st.markdown("JPX 東証上場銘柄一覧")
    st.markdown("Yahoo!ファイナンス 日本株ランキング")
    st.markdown("yfinance 無料日足データ")

if refresh:
    try:
        with st.spinner("JPX・Yahoo・yfinanceから最新データを取得しています…"):
            run_pipeline(
                PipelineConfig(
                    yahoo_pages=yahoo_pages,
                    daily_count=daily_count,
                )
            )
        load_outputs.clear()
        st.success("最新データに更新しました。")
        st.rerun()
    except Exception as exc:
        st.error(f"更新に失敗しました: {exc}")

outputs, metadata = load_outputs()
daily_picks = outputs["daily_picks.csv"]
top100 = outputs["top100.csv"]
candidates = outputs["candidate_pool.csv"]
followups = outputs["followups.csv"]
backtest_summary = outputs["backtest_summary.csv"]
rule_evaluation = outputs["rule_evaluation.csv"]
factor_quantiles = outputs["factor_quantile_evaluation.csv"]
factor_ic = outputs["factor_ic.csv"]
factor_turnover = outputs["factor_turnover.csv"]
jpx_universe = outputs["jpx_universe.csv"]
liquidity_universe = outputs["jpx_liquidity_universe.csv"]
liquidity_top100 = outputs["jpx_liquidity_top100.csv"]
universe_comparison = outputs["universe_comparison.csv"]
version_comparison = outputs["version_comparison.csv"]
portfolio_curve = outputs["portfolio_curve.csv"]
portfolio_summary = outputs["portfolio_summary.csv"]
virtual_positions = outputs["virtual_positions.csv"]
market_environment = outputs["market_environment.csv"]
risk_alerts = outputs["risk_alerts.csv"]

st.markdown(
    """
    <div class="hero">
        <div class="hero-kicker">日本株 モメンタム監視</div>
        <div class="hero-title">日株モメンタム100</div>
        <div class="hero-copy">
            JPXの東証上場普通株を母集団とし、Yahoo!ファイナンスの複数ランキングで注目候補を抽出。
            yfinanceの日足データから、値動き・トレンド・流動性・量能・リスクを横断評価します。
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if top100.empty:
    st.info(
        "まだ分析結果がありません。左側の「最新データを取得」を押すか、"
        "ターミナルで `python daily_job.py` を実行してください。"
    )
    st.stop()

metric_columns = st.columns(4)
metric_columns[0].metric("基準日", metadata.get("trade_date", "―"))
metric_columns[1].metric("ランキング候補", f"{metadata.get('candidate_count', len(candidates)):,} 銘柄")
metric_columns[2].metric("注目リスト", f"{len(top100):,} 銘柄")
metric_columns[3].metric("本日の厳選", f"{len(daily_picks):,} 銘柄")
st.caption(
    f"システム版: {metadata.get('app_version', 'v0')} ／ "
    f"実行ID: {metadata.get('run_id', '―')}"
)

(
    tab_decision,
    tab_daily,
    tab_top,
    tab_pool,
    tab_portfolio,
    tab_history,
    tab_version,
    tab_evaluation,
    tab_watchlist,
    tab_guide,
) = st.tabs(
    [
        "今日の判断",
        "本日の厳選",
        "注目Top100",
        "候補比較",
        "仮想ポートフォリオ",
        "履歴検証",
        "ルール版比較",
        "ルール・因子評価",
        "ウォッチリスト",
        "運用ガイド",
    ]
)

with tab_decision:
    st.subheader("今日の判断")
    if market_environment.empty:
        st.info("v3の日次更新後に、市場環境とリスク判断が表示されます。")
    else:
        environment = market_environment.iloc[-1]
        decision_columns = st.columns(5)
        decision_columns[0].metric(
            "市場判断",
            str(environment.get("market_regime", "―")),
        )
        decision_columns[1].metric(
            "TOPIX 20日",
            pct(environment.get("benchmark_return_20d")),
        )
        decision_columns[2].metric(
            "上昇銘柄比率",
            pct(environment.get("breadth_positive_20d")),
        )
        decision_columns[3].metric(
            "60日線上比率",
            pct(environment.get("breadth_above_ma60")),
        )
        decision_columns[4].metric(
            "厳選平均相関",
            pct(environment.get("average_pick_correlation")),
        )
        regime = str(environment.get("market_regime", "中立"))
        action = str(environment.get("recommended_action", ""))
        if regime == "慎重":
            st.error(f"本日の運用方針: {action}")
        elif regime == "中立":
            st.warning(f"本日の運用方針: {action}")
        else:
            st.success(f"本日の運用方針: {action}")
    if not risk_alerts.empty:
        st.markdown("#### リスク警告")
        st.dataframe(
            risk_alerts[
                [
                    column
                    for column in ("severity", "category", "message")
                    if column in risk_alerts
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "severity": "重要度",
                "category": "分類",
                "message": "内容",
            },
        )
    st.markdown("#### 本日の厳選概要")
    if daily_picks.empty:
        st.info("本日の厳選銘柄はありません。")
    else:
        decision_view = daily_picks[
            [
                column
                for column in (
                    "pick_rank",
                    "code",
                    "name",
                    "industry",
                    "score",
                    "selection_reason",
                )
                if column in daily_picks
            ]
        ]
        st.dataframe(
            decision_view,
            hide_index=True,
            width="stretch",
            column_config={
                "pick_rank": "順位",
                "code": "コード",
                "name": "銘柄名",
                "industry": "業種",
                "score": "総合点",
                "selection_reason": "選定理由",
            },
        )

with tab_daily:
    st.subheader("本日の厳選銘柄")
    st.caption("トレンド、流動性、過熱度、業種分散を加味してTop100から選定")
    if daily_picks.empty:
        st.warning("本日の条件を満たす銘柄はありませんでした。")
    else:
        render_pick_cards(daily_picks)
        st.write("")
        chart_data = daily_picks.set_index("name")[["momentum_score", "trend_score", "liquidity_score"]]
        chart_data.columns = ["モメンタム", "トレンド", "流動性・量能"]
        st.bar_chart(chart_data, horizontal=True, color=["#1769aa", "#4c9a8b", "#b9872d"])
        st.download_button(
            "本日の厳選をCSVで保存",
            csv_bytes(daily_picks),
            file_name=f"毎日厳選_{metadata.get('trade_date', 'latest')}.csv",
            mime="text/csv",
        )

with tab_top:
    st.subheader("注目Top100")
    filter_columns = st.columns([1, 1, 2])
    markets = sorted(top100["market"].dropna().unique().tolist())
    industries = sorted(top100["industry"].dropna().unique().tolist())
    selected_markets = filter_columns[0].multiselect(
        "市場", markets, default=markets
    )
    selected_industries = filter_columns[1].multiselect("業種", industries)
    keyword = filter_columns[2].text_input("銘柄名・コード検索")

    filtered = top100[top100["market"].isin(selected_markets)].copy()
    if selected_industries:
        filtered = filtered[filtered["industry"].isin(selected_industries)]
    if keyword:
        mask = (
            filtered["name"].str.contains(keyword, case=False, na=False)
            | filtered["code"].astype(str).str.contains(keyword, case=False, na=False)
        )
        filtered = filtered[mask]

    display = top100_view(filtered)
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=620,
        column_config={
            "rank": st.column_config.NumberColumn("順位", format="%d"),
            "code": "コード",
            "name": "銘柄名",
            "market": "市場",
            "industry": "業種",
            "score": st.column_config.ProgressColumn(
                "総合点", min_value=0, max_value=100, format="%.1f"
            ),
            "close": st.column_config.NumberColumn("終値", format="¥%.0f"),
            "return_1d": st.column_config.NumberColumn("1日", format="%+.1f%%"),
            "return_20d": st.column_config.NumberColumn("20日", format="%+.1f%%"),
            "return_60d": st.column_config.NumberColumn("60日", format="%+.1f%%"),
            "volume_ratio_20d": st.column_config.NumberColumn("出来高倍率", format="%.2f"),
            "avg_turnover_20d": st.column_config.NumberColumn("平均売買代金", format="¥%.0f"),
            "appearance_count": st.column_config.NumberColumn("候補出現", format="%d"),
            "consecutive_appearances": st.column_config.NumberColumn("連続出現", format="%d"),
            "yahoo_rank_change": st.column_config.NumberColumn("Yahoo順位変化", format="%+.0f"),
            "ranking_sources": "候補入り理由",
        },
    )
    st.download_button(
        "Top100をCSVで保存",
        csv_bytes(filtered),
        file_name=f"注目Top100_{metadata.get('trade_date', 'latest')}.csv",
        mime="text/csv",
    )

with tab_pool:
    st.subheader("候補ユニバース比較")
    st.caption(
        "正式主榜はYahooランキング候補です。JPX流動性ユニバースは、"
        "Yahoo依存の有無を検証するための並行実験です。"
    )
    yahoo_pool_tab, liquidity_pool_tab = st.tabs(
        ["Yahooランキング候補", "JPX流動性ユニバース"]
    )
    with yahoo_pool_tab:
        pool_columns = [
            "code",
            "name",
            "market",
            "industry",
            "ranking_hits",
            "best_yahoo_rank",
            "appearance_count",
            "consecutive_appearances",
            "yahoo_rank_change",
            "ranking_sources",
        ]
        st.dataframe(
            candidates[[column for column in pool_columns if column in candidates]],
            hide_index=True,
            width="stretch",
            height=620,
            column_config={
                "code": "コード",
                "name": "銘柄名",
                "market": "市場",
                "industry": "業種",
                "ranking_hits": "該当ランキング数",
                "best_yahoo_rank": "Yahoo最高順位",
                "appearance_count": "候補出現回数",
                "consecutive_appearances": "連続出現",
                "yahoo_rank_change": "順位変化",
                "ranking_sources": "ランキング",
            },
        )
    with liquidity_pool_tab:
        if liquidity_universe.empty:
            st.info("v3の日次更新後にJPX流動性ユニバースが表示されます。")
        else:
            liquidity_view = liquidity_universe[
                [
                    column
                    for column in (
                        "liquidity_rank",
                        "code",
                        "name",
                        "market",
                        "industry",
                        "avg_turnover_20d",
                        "return_20d",
                        "return_60d",
                        "in_yahoo_pool",
                    )
                    if column in liquidity_universe
                ]
            ].copy()
            for column in ("return_20d", "return_60d"):
                if column in liquidity_view:
                    liquidity_view[column] = (
                        pd.to_numeric(liquidity_view[column], errors="coerce")
                        * 100
                    )
            st.dataframe(
                liquidity_view,
                hide_index=True,
                width="stretch",
                height=620,
                column_config={
                    "liquidity_rank": "流動性順位",
                    "code": "コード",
                    "name": "銘柄名",
                    "market": "市場",
                    "industry": "業種",
                    "avg_turnover_20d": st.column_config.NumberColumn(
                        "20日平均売買代金",
                        format="¥%.0f",
                    ),
                    "return_20d": st.column_config.NumberColumn(
                        "20日",
                        format="%+.1f%%",
                    ),
                    "return_60d": st.column_config.NumberColumn(
                        "60日",
                        format="%+.1f%%",
                    ),
                    "in_yahoo_pool": "Yahoo候補入り",
                },
            )

with tab_portfolio:
    st.subheader("仮想ポートフォリオ")
    st.caption(
        "毎日厳選を翌営業日寄付で等金額建てし、5営業日保有する日次コホート方式です。"
        "既定の取引コストは片道10bpです。"
    )
    if portfolio_summary.empty or portfolio_curve.empty:
        st.info("複数営業日の厳選履歴が蓄積されると、資金曲線が表示されます。")
    else:
        summary = portfolio_summary.iloc[-1]
        portfolio_metrics = st.columns(5)
        portfolio_metrics[0].metric(
            "累積リターン",
            pct(summary.get("total_return")),
        )
        portfolio_metrics[1].metric(
            "TOPIX",
            pct(summary.get("benchmark_return")),
        )
        portfolio_metrics[2].metric(
            "超過収益",
            pct(summary.get("excess_return")),
        )
        portfolio_metrics[3].metric(
            "最大ドローダウン",
            pct(summary.get("max_drawdown")),
        )
        sharpe_value = pd.to_numeric(
            pd.Series([summary.get("sharpe")]),
            errors="coerce",
        ).iloc[0]
        portfolio_metrics[4].metric(
            "Sharpe",
            f"{sharpe_value:.2f}" if pd.notna(sharpe_value) else "―",
        )
        curve = portfolio_curve.copy()
        curve["date"] = pd.to_datetime(curve["date"], errors="coerce")
        curve = curve.dropna(subset=["date"]).set_index("date")
        chart_columns = [
            column
            for column in ("equity", "benchmark_equity")
            if column in curve
        ]
        chart = curve[chart_columns].rename(
            columns={
                "equity": "仮想ポートフォリオ",
                "benchmark_equity": "TOPIX",
            }
        )
        st.line_chart(chart, color=["#1769aa", "#b9872d"])
    st.markdown("#### 現在の仮想保有")
    if virtual_positions.empty:
        st.info("現在保有中として扱う仮想ポジションはありません。")
    else:
        positions_view = virtual_positions.copy()
        if "unrealized_return" in positions_view:
            positions_view["unrealized_return"] = (
                pd.to_numeric(
                    positions_view["unrealized_return"],
                    errors="coerce",
                )
                * 100
            )
        st.dataframe(
            positions_view,
            hide_index=True,
            width="stretch",
            column_config={
                "signal_date": "シグナル日",
                "entry_date": "建玉日",
                "planned_exit_date": "予定決済日",
                "code": "コード",
                "ticker": "ティッカー",
                "name": "銘柄名",
                "industry": "業種",
                "entry_price": "建値",
                "latest_price": "最新値",
                "unrealized_return": st.column_config.NumberColumn(
                    "含み損益",
                    format="%+.2f%%",
                ),
                "market_value": "仮想評価額",
            },
        )

with tab_history:
    st.subheader("履歴検証")
    st.caption(
        "本日の厳選をシグナル日終値で記録し、翌営業日寄付と1・3・5・10営業日後を追跡します。"
    )
    freshness = metadata.get("freshness", {})
    status = str(freshness.get("status", "initializing"))
    if status == "fresh":
        st.success(str(freshness.get("summary", "データは最新です。")))
    elif status == "partial":
        st.warning(str(freshness.get("summary", "一部データが未確定です。")))
    else:
        st.info(str(freshness.get("summary", "成績追跡を開始しています。")))

    if backtest_summary.empty:
        st.info("翌営業日以降の価格が蓄積されると、ここに簡易検証結果が表示されます。")
    else:
        overall = backtest_summary[
            backtest_summary["group_name"].astype(str).eq("全体")
        ].copy()
        overall["平均リターン"] = pd.to_numeric(
            overall["avg_return"], errors="coerce"
        ) * 100
        overall["中央値"] = pd.to_numeric(
            overall["median_return"], errors="coerce"
        ) * 100
        overall["勝率"] = pd.to_numeric(overall["win_rate"], errors="coerce") * 100
        st.markdown("#### 毎日厳選の簡易集計")
        st.dataframe(
            overall[
                [
                    "metric_label",
                    "sample_count",
                    "valid_count",
                    "平均リターン",
                    "中央値",
                    "勝率",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "metric_label": "追跡区間",
                "sample_count": "記録数",
                "valid_count": "確定数",
                "平均リターン": st.column_config.NumberColumn(
                    "平均", format="%+.2f%%"
                ),
                "中央値": st.column_config.NumberColumn(
                    "中央値", format="%+.2f%%"
                ),
                "勝率": st.column_config.NumberColumn("勝率", format="%.1f%%"),
            },
        )

    if not followups.empty:
        latest_followups = followups.sort_values(
            ["trade_date", "pick_rank"], ascending=[False, True]
        ).head(30)
        columns = [
            "trade_date",
            "code",
            "name",
            "pick_rank",
            "next_open_gap",
            "return_1d",
            "return_3d",
            "return_5d",
            "return_10d",
            "observed_days",
        ]
        display_followups = latest_followups[
            [column for column in columns if column in latest_followups]
        ].copy()
        for column in (
            "next_open_gap",
            "return_1d",
            "return_3d",
            "return_5d",
            "return_10d",
        ):
            if column in display_followups:
                display_followups[column] = (
                    pd.to_numeric(display_followups[column], errors="coerce") * 100
                )
        st.markdown("#### 最近の追跡状況")
        st.dataframe(
            display_followups,
            hide_index=True,
            width="stretch",
            column_config={
                "trade_date": "シグナル日",
                "code": "コード",
                "name": "銘柄名",
                "pick_rank": "厳選順位",
                "next_open_gap": st.column_config.NumberColumn(
                    "翌日寄付", format="%+.2f%%"
                ),
                "return_1d": st.column_config.NumberColumn(
                    "1日", format="%+.2f%%"
                ),
                "return_3d": st.column_config.NumberColumn(
                    "3日", format="%+.2f%%"
                ),
                "return_5d": st.column_config.NumberColumn(
                    "5日", format="%+.2f%%"
                ),
                "return_10d": st.column_config.NumberColumn(
                    "10日", format="%+.2f%%"
                ),
                "observed_days": "観測営業日",
            },
        )

with tab_version:
    st.subheader("ルール版比較")
    st.caption(
        "各版の評価観測を混ぜずに比較します。確定数が少ない版は暫定値です。"
    )
    version_result_tab, universe_result_tab = st.tabs(
        ["評価版の成績", "候補ユニバースの成績"]
    )
    with version_result_tab:
        if version_comparison.empty:
            st.info("v2・v3の将来リターンが確定すると比較できます。")
        else:
            horizons = version_comparison["horizon"].dropna().astype(str).unique()
            selected = st.selectbox(
                "比較期間",
                list(horizons),
                index=min(2, max(0, len(horizons) - 1)),
                key="version_compare_horizon",
            )
            version_view = version_comparison[
                version_comparison["horizon"].astype(str).eq(selected)
            ].copy()
            for column in (
                "avg_open_buy_return",
                "avg_excess_return",
                "avg_net_return",
                "win_rate",
                "top20_avg_return",
            ):
                if column in version_view:
                    version_view[column] = (
                        pd.to_numeric(version_view[column], errors="coerce")
                        * 100
                    )
            st.dataframe(
                version_view,
                hide_index=True,
                width="stretch",
                column_config={
                    "evaluation_version": "評価版",
                    "horizon": "期間",
                    "sample_count": "観測数",
                    "valid_count": "確定数",
                    "avg_open_buy_return": st.column_config.NumberColumn(
                        "寄付買い平均",
                        format="%+.2f%%",
                    ),
                    "avg_excess_return": st.column_config.NumberColumn(
                        "TOPIX超過",
                        format="%+.2f%%",
                    ),
                    "avg_net_return": st.column_config.NumberColumn(
                        "コスト後",
                        format="%+.2f%%",
                    ),
                    "win_rate": st.column_config.NumberColumn(
                        "勝率",
                        format="%.1f%%",
                    ),
                    "top20_avg_return": st.column_config.NumberColumn(
                        "上位20平均",
                        format="%+.2f%%",
                    ),
                    "cost_bps_one_way": "片道コストbp",
                },
            )
    with universe_result_tab:
        if universe_comparison.empty:
            st.info("両候補ユニバースの追跡結果が確定すると比較できます。")
        else:
            universe_horizons = (
                universe_comparison["horizon"].dropna().astype(str).unique()
            )
            selected_universe_horizon = st.selectbox(
                "候補比較期間",
                list(universe_horizons),
                index=min(2, max(0, len(universe_horizons) - 1)),
                key="universe_compare_horizon",
            )
            universe_view = universe_comparison[
                universe_comparison["horizon"]
                .astype(str)
                .eq(selected_universe_horizon)
            ].copy()
            for column in (
                "avg_open_buy_return",
                "median_open_buy_return",
                "win_rate",
                "avg_excess_return",
                "avg_net_return",
            ):
                if column in universe_view:
                    universe_view[column] = (
                        pd.to_numeric(universe_view[column], errors="coerce")
                        * 100
                    )
            st.dataframe(
                universe_view,
                hide_index=True,
                width="stretch",
                column_config={
                    "evaluation_version": "評価版",
                    "universe_source": "内部キー",
                    "universe_label": "候補ユニバース",
                    "horizon": "期間",
                    "sample_count": "観測数",
                    "valid_count": "確定数",
                    "avg_open_buy_return": st.column_config.NumberColumn(
                        "平均",
                        format="%+.2f%%",
                    ),
                    "median_open_buy_return": st.column_config.NumberColumn(
                        "中央値",
                        format="%+.2f%%",
                    ),
                    "win_rate": st.column_config.NumberColumn(
                        "勝率",
                        format="%.1f%%",
                    ),
                    "avg_excess_return": st.column_config.NumberColumn(
                        "TOPIX超過",
                        format="%+.2f%%",
                    ),
                    "avg_net_return": st.column_config.NumberColumn(
                        "コスト後",
                        format="%+.2f%%",
                    ),
                    "cost_bps_one_way": "片道コストbp",
                },
            )

with tab_evaluation:
    st.subheader("ルール・因子評価")
    st.caption(
        "Top100選定時点の因子値とルール発動状態を固定し、"
        "将来リターン確定後に有効性を検証します。評価結果は自動で選定条件へ反映しません。"
    )
    st.info(
        "初期は「サンプル不足」と表示されます。原則として通過群・未通過群または"
        "日次ICが30件以上蓄積してから改善判断に使用します。"
    )
    evaluation_versions = sorted(
        {
            *rule_evaluation.get(
                "evaluation_version",
                pd.Series(dtype=str),
            ).dropna().astype(str),
            *factor_quantiles.get(
                "evaluation_version",
                pd.Series(dtype=str),
            ).dropna().astype(str),
        }
    )
    selected_evaluation_version = (
        st.selectbox(
            "表示する評価版",
            evaluation_versions,
            index=len(evaluation_versions) - 1,
        )
        if evaluation_versions
        else None
    )

    rule_tab, factor_tab, ic_tab = st.tabs(
        ["ルール通過比較", "因子五分位", "IC・入替率"]
    )

    with rule_tab:
        if rule_evaluation.empty:
            st.info("将来リターンが蓄積されると、ルール評価が表示されます。")
        else:
            horizons = rule_evaluation["horizon"].dropna().astype(str).unique().tolist()
            horizon_labels = {
                str(row["horizon"]): str(row["horizon_label"])
                for _, row in rule_evaluation.drop_duplicates("horizon").iterrows()
            }
            selected_horizon = st.selectbox(
                "評価期間",
                horizons,
                format_func=lambda value: horizon_labels.get(value, value),
                key="rule_horizon",
            )
            rule_view = rule_evaluation[
                rule_evaluation["horizon"].astype(str).eq(selected_horizon)
                & rule_evaluation["group_name"].astype(str).eq("全体")
                & rule_evaluation["group_value"].astype(str).eq("全体")
            ].copy()
            if selected_evaluation_version is not None:
                rule_view = rule_view[
                    rule_view["evaluation_version"]
                    .astype(str)
                    .eq(selected_evaluation_version)
                ]
            percent_columns = [
                "pass_avg_return",
                "fail_avg_return",
                "return_spread",
                "spread_ci_low",
                "spread_ci_high",
                "pass_win_rate",
                "fail_win_rate",
            ]
            for column in percent_columns:
                if column in rule_view:
                    rule_view[column] = pd.to_numeric(
                        rule_view[column], errors="coerce"
                    ) * 100
            rule_columns = [
                "rule_category",
                "rule_label",
                "pass_valid_count",
                "fail_valid_count",
                "pass_avg_return",
                "fail_avg_return",
                "return_spread",
                "spread_ci_low",
                "spread_ci_high",
                "pass_win_rate",
                "fail_win_rate",
                "finding",
                "status",
            ]
            st.dataframe(
                rule_view[
                    [column for column in rule_columns if column in rule_view]
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "rule_category": "分類",
                    "rule_label": "ルール",
                    "pass_valid_count": "通過確定数",
                    "fail_valid_count": "未通過確定数",
                    "pass_avg_return": st.column_config.NumberColumn(
                        "通過平均", format="%+.2f%%"
                    ),
                    "fail_avg_return": st.column_config.NumberColumn(
                        "未通過平均", format="%+.2f%%"
                    ),
                    "return_spread": st.column_config.NumberColumn(
                        "平均差", format="%+.2f%%"
                    ),
                    "spread_ci_low": st.column_config.NumberColumn(
                        "95%下限", format="%+.2f%%"
                    ),
                    "spread_ci_high": st.column_config.NumberColumn(
                        "95%上限", format="%+.2f%%"
                    ),
                    "pass_win_rate": st.column_config.NumberColumn(
                        "通過勝率", format="%.1f%%"
                    ),
                    "fail_win_rate": st.column_config.NumberColumn(
                        "未通過勝率", format="%.1f%%"
                    ),
                    "finding": "暫定所見",
                    "status": "判定状態",
                },
            )
            st.download_button(
                "ルール評価をCSVで保存",
                csv_bytes(rule_evaluation),
                file_name=f"ルール評価_{metadata.get('trade_date', 'latest')}.csv",
                mime="text/csv",
            )

    with factor_tab:
        if factor_quantiles.empty:
            st.info("将来リターンが蓄積されると、因子五分位評価が表示されます。")
        else:
            overall_factors = factor_quantiles[
                factor_quantiles["group_name"].astype(str).eq("全体")
            ].copy()
            if selected_evaluation_version is not None:
                overall_factors = overall_factors[
                    overall_factors["evaluation_version"]
                    .astype(str)
                    .eq(selected_evaluation_version)
                ]
            factor_labels = overall_factors["factor_label"].dropna().astype(str).unique().tolist()
            selected_factor = st.selectbox(
                "表示する因子",
                factor_labels,
                key="factor_label",
            )
            factor_horizons = overall_factors[
                overall_factors["factor_label"].astype(str).eq(selected_factor)
            ]["horizon"].dropna().astype(str).unique().tolist()
            selected_factor_horizon = st.selectbox(
                "因子の評価期間",
                factor_horizons,
                key="factor_horizon",
            )
            factor_view = overall_factors[
                overall_factors["factor_label"].astype(str).eq(selected_factor)
                & overall_factors["horizon"].astype(str).eq(selected_factor_horizon)
            ].copy()
            for column in (
                "avg_return",
                "median_return",
                "win_rate",
                "top_bottom_spread",
            ):
                if column in factor_view:
                    factor_view[column] = pd.to_numeric(
                        factor_view[column], errors="coerce"
                    ) * 100
            st.dataframe(
                factor_view[
                    [
                        "quantile",
                        "sample_count",
                        "valid_count",
                        "avg_return",
                        "median_return",
                        "win_rate",
                        "top_bottom_spread",
                        "status",
                    ]
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "quantile": "分位（5が期待方向上位）",
                    "sample_count": "観測数",
                    "valid_count": "確定数",
                    "avg_return": st.column_config.NumberColumn(
                        "平均", format="%+.2f%%"
                    ),
                    "median_return": st.column_config.NumberColumn(
                        "中央値", format="%+.2f%%"
                    ),
                    "win_rate": st.column_config.NumberColumn(
                        "勝率", format="%.1f%%"
                    ),
                    "top_bottom_spread": st.column_config.NumberColumn(
                        "上位-下位差", format="%+.2f%%"
                    ),
                    "status": "判定状態",
                },
            )
            st.download_button(
                "因子五分位評価をCSVで保存",
                csv_bytes(factor_quantiles),
                file_name=f"因子五分位_{metadata.get('trade_date', 'latest')}.csv",
                mime="text/csv",
            )

    with ic_tab:
        if factor_ic.empty:
            st.info("複数日の将来リターンが確定すると、ICが表示されます。")
        else:
            ic_view = factor_ic[
                factor_ic["group_name"].astype(str).eq("全体")
                & factor_ic["horizon"].astype(str).eq("5d")
            ].copy()
            if selected_evaluation_version is not None:
                ic_view = ic_view[
                    ic_view["evaluation_version"]
                    .astype(str)
                    .eq(selected_evaluation_version)
                ]
            for column in ("mean_ic", "median_ic", "positive_ic_rate"):
                if column in ic_view:
                    ic_view[column] = pd.to_numeric(
                        ic_view[column], errors="coerce"
                    )
            if "positive_ic_rate" in ic_view:
                ic_view["positive_ic_rate"] = (
                    ic_view["positive_ic_rate"] * 100
                )
            st.markdown("#### 5営業日 Information Coefficient")
            st.dataframe(
                ic_view[
                    [
                        "factor_label",
                        "ic_count",
                        "mean_ic",
                        "median_ic",
                        "positive_ic_rate",
                        "status",
                    ]
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "factor_label": "因子",
                    "ic_count": "日次数",
                    "mean_ic": st.column_config.NumberColumn(
                        "平均IC", format="%+.3f"
                    ),
                    "median_ic": st.column_config.NumberColumn(
                        "中央値IC", format="%+.3f"
                    ),
                    "positive_ic_rate": st.column_config.NumberColumn(
                        "正のIC比率", format="%.1f%%"
                    ),
                    "status": "判定状態",
                },
            )
        if not factor_turnover.empty:
            turnover_view = factor_turnover.copy()
            if selected_evaluation_version is not None:
                turnover_view = turnover_view[
                    turnover_view["evaluation_version"]
                    .astype(str)
                    .eq(selected_evaluation_version)
                ]
            for column in ("avg_turnover", "median_turnover", "latest_turnover"):
                turnover_view[column] = pd.to_numeric(
                    turnover_view[column], errors="coerce"
                ) * 100
            st.markdown("#### 上位分位の入替率")
            st.dataframe(
                turnover_view[
                    [
                        "factor_label",
                        "transition_count",
                        "avg_turnover",
                        "median_turnover",
                        "latest_turnover",
                        "status",
                    ]
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "factor_label": "因子",
                    "transition_count": "連続営業日数",
                    "avg_turnover": st.column_config.NumberColumn(
                        "平均入替率", format="%.1f%%"
                    ),
                    "median_turnover": st.column_config.NumberColumn(
                        "中央値", format="%.1f%%"
                    ),
                    "latest_turnover": st.column_config.NumberColumn(
                        "直近", format="%.1f%%"
                    ),
                    "status": "判定状態",
                },
            )

with tab_watchlist:
    st.subheader("ウォッチリスト")
    st.caption(
        "個人メモ用のローカル機能です。データはdata/userに保存され、Gitへ登録しません。"
    )
    watchlist = load_watchlist()
    with st.form("watchlist_add_form", clear_on_submit=True):
        watch_columns = st.columns([1, 2, 4])
        watch_code = watch_columns[0].text_input("銘柄コード")
        watch_name = watch_columns[1].text_input("銘柄名（省略可）")
        watch_note = watch_columns[2].text_input("メモ")
        add_watch = st.form_submit_button("ウォッチリストへ追加")
    if add_watch:
        try:
            normalized_code = str(watch_code).strip().upper()
            resolved_name = str(watch_name).strip()
            if not resolved_name and not jpx_universe.empty:
                matched = jpx_universe[
                    jpx_universe["code"].astype(str).eq(normalized_code)
                ]
                if not matched.empty:
                    resolved_name = str(matched.iloc[0].get("name", ""))
            updated = add_watchlist_entry(
                watchlist,
                code=normalized_code,
                name=resolved_name,
                note=watch_note,
            )
            save_watchlist(updated)
            st.success("ウォッチリストへ追加しました。")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    enriched_watchlist = enrich_watchlist(
        watchlist,
        daily_picks=daily_picks,
        top100=top100,
        candidates=candidates,
        liquidity_top100=liquidity_top100,
        jpx_universe=jpx_universe,
    )
    if enriched_watchlist.empty:
        st.info("まだ登録銘柄はありません。")
    else:
        watch_view = enriched_watchlist.copy()
        if "return_20d" in watch_view:
            watch_view["return_20d"] = (
                pd.to_numeric(watch_view["return_20d"], errors="coerce") * 100
            )
        st.dataframe(
            watch_view,
            hide_index=True,
            width="stretch",
            column_config={
                "code": "コード",
                "name": "銘柄名",
                "note": "メモ",
                "added_at": "追加日時",
                "current_status": "現在の状態",
                "rank": "Top100順位",
                "score": "総合点",
                "return_20d": st.column_config.NumberColumn(
                    "20日",
                    format="%+.1f%%",
                ),
            },
        )
        remove_codes = st.multiselect(
            "削除する銘柄",
            enriched_watchlist["code"].astype(str).tolist(),
            format_func=lambda code: (
                f"{code} {enriched_watchlist.loc[enriched_watchlist['code'].astype(str).eq(code), 'name'].iloc[0]}"
            ),
        )
        if st.button("選択した銘柄を削除", disabled=not remove_codes):
            save_watchlist(remove_watchlist_entries(watchlist, remove_codes))
            st.success("ウォッチリストから削除しました。")
            st.rerun()

with tab_guide:
    st.subheader("評価方法")
    st.markdown(
        """
        1. **母集団**: JPXの東証プライム・スタンダード・グロース普通株
        2. **候補抽出**: Yahoo!ファイナンスの値上がり率・出来高・出来高増加率ランキング
        3. **価格評価**: yfinanceの日足から20日・60日・120日モメンタムを計算
        4. **品質調整**: 移動平均、平均売買代金、出来高倍率、120日高値との距離、20日変動率
        5. **毎日厳選**: 最低株価・流動性・過熱度・業種分散を追加判定
        6. **履歴検証**: シグナル日終値を記録し、翌営業日寄付と1・3・5・10営業日後を追跡
        """
    )
    st.markdown(
        """
        <div class="notice">
            本サービスは情報整理と研究を目的としたもので、投資助言ではありません。
            無料データには遅延・欠損・訂正があり得ます。売買判断の前に、取引所情報、
            適時開示、証券会社の正式な株価をご確認ください。
        </div>
        """,
        unsafe_allow_html=True,
    )
    if metadata.get("download_errors"):
        with st.expander("取得時の注意事項"):
            for error in metadata["download_errors"]:
                st.write(error)
