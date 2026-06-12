from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PipelineConfig


SCORE_WEIGHTS = {
    "return_20d": 20.0,
    "return_60d": 18.0,
    "return_120d": 10.0,
    "distance_ma20": 10.0,
    "distance_ma60": 10.0,
    "avg_turnover_20d": 10.0,
    "volume_ratio_20d": 8.0,
    "distance_high_120d": 7.0,
    "volatility_20d": -7.0,
}


def _winsorize(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() < 5:
        return numeric
    low, high = numeric.quantile([0.02, 0.98])
    return numeric.clip(lower=low, upper=high)


def _percentile(series: pd.Series, ascending: bool = True) -> pd.Series:
    values = _winsorize(series)
    return values.rank(pct=True, ascending=ascending, method="average") * 100


def score_candidates(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return features.copy()
    scored = features.copy()
    components: list[pd.Series] = []
    for column, weight in SCORE_WEIGHTS.items():
        if column not in scored:
            scored[column] = np.nan
        ascending = weight > 0
        percentile = _percentile(scored[column], ascending=ascending).fillna(50.0)
        contribution = percentile * abs(weight) / 100
        scored[f"score_{column}"] = contribution
        components.append(contribution)
    scored["score"] = sum(components)
    scored["score"] = scored["score"].round(2)
    scored["momentum_score"] = (
        scored["score_return_20d"]
        + scored["score_return_60d"]
        + scored["score_return_120d"]
    ).round(2)
    scored["trend_score"] = (
        scored["score_distance_ma20"] + scored["score_distance_ma60"]
    ).round(2)
    scored["liquidity_score"] = (
        scored["score_avg_turnover_20d"]
        + scored["score_volume_ratio_20d"]
    ).round(2)
    return scored.sort_values("score", ascending=False).reset_index(drop=True)


def make_top100(
    candidates: pd.DataFrame,
    features: pd.DataFrame,
    config: PipelineConfig,
) -> pd.DataFrame:
    if features.empty or "ticker" not in features:
        return pd.DataFrame()
    merged = candidates.merge(features, how="inner", on="ticker")
    scored = score_candidates(merged)
    scored = scored[
        (scored["close"] > 0)
        & (scored["avg_turnover_20d"] > 0)
        & scored["return_20d"].notna()
        & scored["return_60d"].notna()
    ].copy()
    top = scored.head(config.top_count).copy()
    top.insert(0, "rank", range(1, len(top) + 1))
    return top


def _selection_reason(row: pd.Series) -> str:
    reasons: list[str] = []
    if row.get("return_20d", 0) > 0.08:
        reasons.append("20日モメンタム")
    if row.get("return_60d", 0) > 0.15:
        reasons.append("中期上昇")
    if row.get("distance_ma20", -1) > 0 and row.get("distance_ma60", -1) > 0:
        reasons.append("移動平均線上")
    if row.get("volume_ratio_20d", 0) >= 1.2:
        reasons.append("出来高増加")
    if row.get("distance_high_120d", -1) >= -0.05:
        reasons.append("高値圏")
    return "・".join(reasons[:3]) or "総合スコア上位"


def select_daily_picks(
    top100: pd.DataFrame, config: PipelineConfig
) -> pd.DataFrame:
    if top100.empty:
        return top100.copy()
    eligible = top100[
        (top100["close"] >= config.min_price)
        & (top100["avg_turnover_20d"] >= config.min_turnover_20d)
        & (top100["distance_ma20"] > 0)
        & (top100["distance_ma60"] > 0)
        & (top100["distance_ma20"] <= 0.18)
        & (top100["return_1d"] < 0.15)
        & (top100["volatility_20d"] < 0.80)
    ].copy()
    if len(eligible) < 3:
        eligible = top100[
            (top100["close"] >= config.min_price)
            & (top100["avg_turnover_20d"] >= config.min_turnover_20d)
        ].copy()

    picks: list[pd.Series] = []
    industry_counts: dict[str, int] = {}
    for _, row in eligible.iterrows():
        industry = str(row.get("industry", "未分類"))
        if industry_counts.get(industry, 0) >= 1 and len(eligible) >= config.daily_count:
            continue
        picks.append(row)
        industry_counts[industry] = industry_counts.get(industry, 0) + 1
        if len(picks) >= config.daily_count:
            break
    if len(picks) < min(3, len(eligible)):
        selected_codes = {str(row["code"]) for row in picks}
        for _, row in eligible.iterrows():
            if str(row["code"]) in selected_codes:
                continue
            picks.append(row)
            if len(picks) >= min(config.daily_count, len(eligible)):
                break

    if not picks:
        return eligible.head(0)
    result = pd.DataFrame(picks).reset_index(drop=True)
    result.insert(0, "pick_rank", range(1, len(result) + 1))
    result["selection_reason"] = result.apply(_selection_reason, axis=1)
    return result
