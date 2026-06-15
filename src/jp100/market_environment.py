from __future__ import annotations

import numpy as np
import pandas as pd

from .market import adjusted_price_frame, calculate_features


def _pairwise_correlation(
    picks: pd.DataFrame,
    price_history: dict[str, pd.DataFrame],
) -> float | None:
    series: dict[str, pd.Series] = {}
    for ticker in picks.get("ticker", pd.Series(dtype=str)).dropna().astype(str):
        frame = adjusted_price_frame(price_history.get(ticker))
        if frame.empty or "Close" not in frame:
            continue
        returns = pd.to_numeric(frame["Close"], errors="coerce").pct_change(
            fill_method=None
        )
        series[ticker] = returns.tail(60)
    if len(series) < 2:
        return None
    correlations = pd.DataFrame(series).corr()
    values = correlations.where(
        ~np.eye(len(correlations), dtype=bool)
    ).stack()
    return float(values.mean()) if not values.empty else None


def build_market_environment(
    benchmark_history: pd.DataFrame | None,
    liquidity_universe: pd.DataFrame,
    daily_picks: pd.DataFrame,
    price_history: dict[str, pd.DataFrame],
    *,
    trade_date: str,
    benchmark_ticker: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    benchmark_feature = calculate_features(
        benchmark_ticker,
        benchmark_history if benchmark_history is not None else pd.DataFrame(),
    )
    benchmark_return_20d = (
        float(benchmark_feature["return_20d"]) if benchmark_feature else None
    )
    benchmark_above_ma20 = (
        bool(float(benchmark_feature["distance_ma20"]) > 0)
        if benchmark_feature
        else None
    )
    benchmark_above_ma60 = (
        bool(float(benchmark_feature["distance_ma60"]) > 0)
        if benchmark_feature
        else None
    )
    benchmark_volatility = (
        float(benchmark_feature["volatility_20d"])
        if benchmark_feature
        else None
    )

    breadth_20d = None
    breadth_ma60 = None
    if not liquidity_universe.empty:
        return_20d = pd.to_numeric(
            liquidity_universe.get("return_20d"),
            errors="coerce",
        ).dropna()
        distance_ma60 = pd.to_numeric(
            liquidity_universe.get("distance_ma60"),
            errors="coerce",
        ).dropna()
        breadth_20d = (
            float(return_20d.gt(0).mean()) if not return_20d.empty else None
        )
        breadth_ma60 = (
            float(distance_ma60.gt(0).mean())
            if not distance_ma60.empty
            else None
        )

    pick_volatility = pd.to_numeric(
        daily_picks.get("volatility_20d"),
        errors="coerce",
    ).dropna()
    average_pick_volatility = (
        float(pick_volatility.mean()) if not pick_volatility.empty else None
    )
    industry_concentration = None
    if not daily_picks.empty and "industry" in daily_picks:
        industry_concentration = float(
            daily_picks["industry"].fillna("未分類").value_counts(
                normalize=True
            ).max()
        )
    average_pick_correlation = _pairwise_correlation(
        daily_picks,
        price_history,
    )

    risk_points = 0
    alerts: list[dict[str, object]] = []

    def add_alert(severity: str, category: str, message: str) -> None:
        alerts.append(
            {
                "trade_date": trade_date,
                "severity": severity,
                "category": category,
                "message": message,
            }
        )

    if benchmark_above_ma60 is False:
        risk_points += 2
        add_alert("高", "市場トレンド", "TOPIXが60日移動平均を下回っています。")
    elif benchmark_above_ma20 is False:
        risk_points += 1
        add_alert("中", "市場トレンド", "TOPIXが20日移動平均を下回っています。")
    if breadth_ma60 is not None and breadth_ma60 < 0.40:
        risk_points += 1
        add_alert(
            "中",
            "市場の広がり",
            "流動性上位銘柄のうち60日線上にある銘柄が40%未満です。",
        )
    if benchmark_volatility is not None and benchmark_volatility > 0.25:
        risk_points += 1
        add_alert("中", "市場変動", "TOPIXの20日年率変動率が25%を超えています。")
    if average_pick_correlation is not None and average_pick_correlation > 0.70:
        risk_points += 1
        add_alert("中", "相関", "本日の厳選銘柄間の平均相関が70%を超えています。")
    if industry_concentration is not None and industry_concentration > 0.40:
        risk_points += 1
        add_alert("中", "業種集中", "本日の厳選が一つの業種へ40%超集中しています。")
    if benchmark_feature is None:
        risk_points += 1
        add_alert("中", "データ", "TOPIX基準データを取得できていません。")
    if not alerts:
        add_alert("低", "総合", "現在の定量リスク警告はありません。")

    if risk_points <= 1:
        risk_level = "積極"
        action = "通常の候補比較が可能です。個別銘柄の過熱度を確認してください。"
    elif risk_points <= 3:
        risk_level = "中立"
        action = "銘柄数と投入比率を抑え、流動性と分散を優先してください。"
    else:
        risk_level = "慎重"
        action = "新規候補は観察中心とし、相場環境の改善を待つ判断も検討してください。"

    environment = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "benchmark_ticker": benchmark_ticker,
                "market_regime": risk_level,
                "risk_points": risk_points,
                "recommended_action": action,
                "benchmark_return_20d": benchmark_return_20d,
                "benchmark_above_ma20": benchmark_above_ma20,
                "benchmark_above_ma60": benchmark_above_ma60,
                "benchmark_volatility_20d": benchmark_volatility,
                "breadth_positive_20d": breadth_20d,
                "breadth_above_ma60": breadth_ma60,
                "average_pick_volatility": average_pick_volatility,
                "average_pick_correlation": average_pick_correlation,
                "industry_concentration": industry_concentration,
                "liquidity_universe_count": int(len(liquidity_universe)),
                "daily_pick_count": int(len(daily_picks)),
            }
        ]
    )
    return environment, pd.DataFrame(alerts)
