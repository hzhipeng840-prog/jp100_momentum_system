from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from jp100.config import PROCESSED_DIR, PipelineConfig  # noqa: E402
from jp100.pipeline import run_pipeline  # noqa: E402


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
def load_outputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    def read_csv(name: str) -> pd.DataFrame:
        path = PROCESSED_DIR / name
        return pd.read_csv(path, dtype={"code": str}) if path.exists() else pd.DataFrame()

    metadata_path = PROCESSED_DIR / "metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else {}
    )
    return (
        read_csv("daily_picks.csv"),
        read_csv("top100.csv"),
        read_csv("candidate_pool.csv"),
        metadata,
    )


def pct(value: object) -> str:
    try:
        return f"{float(value):+.1%}"
    except (TypeError, ValueError):
        return "―"


def yen(value: object) -> str:
    try:
        return f"¥{float(value):,.0f}"
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
                        出来高倍率 {float(row.get('volume_ratio_20d', 0)):.2f}倍
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
    refresh = st.button("最新データを取得", type="primary", use_container_width=True)
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

daily_picks, top100, candidates, metadata = load_outputs()

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

tab_daily, tab_top, tab_pool, tab_guide = st.tabs(
    ["本日の厳選", "注目Top100", "候補銘柄", "運用ガイド"]
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
        use_container_width=True,
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
    st.subheader("Yahooランキング候補銘柄")
    st.caption("JPX東証普通株と照合済み。ETF・REIT・他市場銘柄は除外しています。")
    pool_columns = [
        "code",
        "name",
        "market",
        "industry",
        "ranking_hits",
        "best_yahoo_rank",
        "ranking_sources",
    ]
    st.dataframe(
        candidates[[column for column in pool_columns if column in candidates]],
        hide_index=True,
        use_container_width=True,
        height=620,
        column_config={
            "code": "コード",
            "name": "銘柄名",
            "market": "市場",
            "industry": "業種",
            "ranking_hits": "該当ランキング数",
            "best_yahoo_rank": "Yahoo最高順位",
            "ranking_sources": "ランキング",
        },
    )

with tab_guide:
    st.subheader("評価方法")
    st.markdown(
        """
        1. **母集団**: JPXの東証プライム・スタンダード・グロース普通株
        2. **候補抽出**: Yahoo!ファイナンスの値上がり率・出来高・出来高増加率ランキング
        3. **価格評価**: yfinanceの日足から20日・60日・120日モメンタムを計算
        4. **品質調整**: 移動平均、平均売買代金、出来高倍率、120日高値との距離、20日変動率
        5. **毎日厳選**: 最低株価・流動性・過熱度・業種分散を追加判定
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
