from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import PipelineConfig


@dataclass(frozen=True)
class FactorSpec:
    key: str
    label: str
    direction: int
    description: str


@dataclass(frozen=True)
class RuleSpec:
    key: str
    label: str
    category: str
    description: str


FACTOR_SPECS = (
    FactorSpec("score", "総合スコア", 1, "現行の全評価要素を合成した順位スコア"),
    FactorSpec("return_20d", "20日モメンタム", 1, "20営業日の騰落率"),
    FactorSpec("return_60d", "60日モメンタム", 1, "60営業日の騰落率"),
    FactorSpec("return_120d", "120日モメンタム", 1, "120営業日の騰落率"),
    FactorSpec("distance_ma20", "20日移動平均乖離", 1, "終値の20日移動平均からの乖離"),
    FactorSpec("distance_ma60", "60日移動平均乖離", 1, "終値の60日移動平均からの乖離"),
    FactorSpec("avg_turnover_20d", "20日平均売買代金", 1, "流動性の代理指標"),
    FactorSpec("volume_ratio_20d", "出来高比", 1, "当日出来高と20日平均出来高の比率"),
    FactorSpec("distance_high_120d", "120日高値接近度", 1, "終値と120日高値の距離"),
    FactorSpec("volatility_20d", "20日変動率", -1, "低いほど望ましい年率換算変動率"),
)


RULE_SPECS = (
    RuleSpec("rule_price_floor", "最低株価", "適格性", "終値が最低株価以上"),
    RuleSpec("rule_liquidity_floor", "最低流動性", "適格性", "20日平均売買代金が最低基準以上"),
    RuleSpec("rule_momentum_20_positive", "20日モメンタム正", "モメンタム", "20日騰落率が正"),
    RuleSpec("rule_momentum_60_positive", "60日モメンタム正", "モメンタム", "60日騰落率が正"),
    RuleSpec("rule_above_ma20", "20日線上", "トレンド", "終値が20日移動平均を上回る"),
    RuleSpec("rule_above_ma60", "60日線上", "トレンド", "終値が60日移動平均を上回る"),
    RuleSpec("rule_trend_alignment", "上昇トレンド", "トレンド", "終値が20日線と60日線をともに上回る"),
    RuleSpec("rule_volume_expansion", "出来高増加", "量能", "出来高比が1.2倍以上"),
    RuleSpec("rule_near_120d_high", "120日高値圏", "モメンタム", "120日高値から5%以内"),
    RuleSpec("rule_overheat_control", "過熱抑制", "リスク", "20日線乖離18%以下かつ当日上昇15%未満"),
    RuleSpec("rule_volatility_control", "変動率抑制", "リスク", "20日変動率が80%未満"),
    RuleSpec(
        "rule_daily_base",
        "毎日厳選基本条件",
        "複合条件",
        "株価、流動性、トレンド、過熱度、変動率の基本条件をすべて通過",
    ),
)


FACTOR_COLUMNS = tuple(spec.key for spec in FACTOR_SPECS)
RULE_COLUMNS = tuple(spec.key for spec in RULE_SPECS)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(float("nan"), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def attach_evaluation_columns(
    frame: pd.DataFrame,
    config: PipelineConfig,
    *,
    evaluation_version: str,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    result = frame.copy()
    close = _numeric(result, "close")
    turnover = _numeric(result, "avg_turnover_20d")
    return_1d = _numeric(result, "return_1d")
    return_20d = _numeric(result, "return_20d")
    return_60d = _numeric(result, "return_60d")
    distance_ma20 = _numeric(result, "distance_ma20")
    distance_ma60 = _numeric(result, "distance_ma60")
    volume_ratio = _numeric(result, "volume_ratio_20d")
    distance_high = _numeric(result, "distance_high_120d")
    volatility = _numeric(result, "volatility_20d")

    result["evaluation_version"] = evaluation_version
    result["rule_price_floor"] = close.ge(config.min_price)
    result["rule_liquidity_floor"] = turnover.ge(config.min_turnover_20d)
    result["rule_momentum_20_positive"] = return_20d.gt(0)
    result["rule_momentum_60_positive"] = return_60d.gt(0)
    result["rule_above_ma20"] = distance_ma20.gt(0)
    result["rule_above_ma60"] = distance_ma60.gt(0)
    result["rule_trend_alignment"] = (
        result["rule_above_ma20"] & result["rule_above_ma60"]
    )
    result["rule_volume_expansion"] = volume_ratio.ge(1.2)
    result["rule_near_120d_high"] = distance_high.ge(-0.05)
    result["rule_overheat_control"] = distance_ma20.le(0.18) & return_1d.lt(0.15)
    result["rule_volatility_control"] = volatility.lt(0.80)
    result["rule_daily_base"] = (
        result["rule_price_floor"]
        & result["rule_liquidity_floor"]
        & result["rule_trend_alignment"]
        & result["rule_overheat_control"]
        & result["rule_volatility_control"]
    )
    return result


def evaluation_passthrough_columns() -> list[str]:
    identity = [
        "trade_date",
        "code",
        "ticker",
        "name",
        "market",
        "industry",
        "rank",
        "score",
        "best_yahoo_rank",
        "appearance_count",
        "consecutive_appearances",
        "evaluation_version",
    ]
    return list(dict.fromkeys([*identity, *FACTOR_COLUMNS, *RULE_COLUMNS]))
