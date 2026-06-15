from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from .rules import FACTOR_SPECS, RULE_SPECS, FactorSpec, RuleSpec
from .trading_calendar import are_consecutive_tse_sessions


FORWARD_RETURN_SPECS = (
    ("1d", "return_1d", "settled_1d", "1営業日"),
    ("3d", "return_3d", "settled_3d", "3営業日"),
    ("5d", "return_5d", "settled_5d", "5営業日"),
    ("10d", "return_10d", "settled_10d", "10営業日"),
)


@dataclass
class EvaluationBundle:
    rule_evaluation: pd.DataFrame
    factor_quantiles: pd.DataFrame
    factor_ic: pd.DataFrame
    factor_turnover: pd.DataFrame


def _truthy(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.fillna("").astype(str).str.strip().str.lower().isin(
        {"true", "1", "yes", "y"}
    )


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(float("nan"), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _rank_bucket(value: object) -> str:
    rank = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(rank):
        return "不明"
    if rank <= 10:
        return "Yahoo Top10"
    if rank <= 30:
        return "Yahoo Top30"
    if rank <= 50:
        return "Yahoo Top50"
    return "Yahoo 51位以下"


def _versions(frame: pd.DataFrame) -> list[str]:
    if "evaluation_version" not in frame:
        return ["未設定"]
    versions = frame["evaluation_version"].dropna().astype(str).unique().tolist()
    return sorted(versions) or ["未設定"]


def _version_frame(frame: pd.DataFrame, version: str) -> pd.DataFrame:
    if "evaluation_version" not in frame:
        return frame.copy()
    return frame[frame["evaluation_version"].astype(str).eq(version)].copy()


def _with_quantiles(
    frame: pd.DataFrame,
    spec: FactorSpec,
    *,
    quantiles: int,
) -> pd.DataFrame:
    result = frame.copy()
    result["_factor_value"] = _numeric_column(result, spec.key)
    result["_adjusted_factor"] = result["_factor_value"] * spec.direction
    result["_factor_quantile"] = pd.NA

    for _, indexes in result.groupby("trade_date", dropna=False).groups.items():
        values = result.loc[indexes, "_adjusted_factor"].dropna()
        if len(values) < 2:
            continue
        bin_count = min(quantiles, int(values.nunique()), len(values))
        if bin_count < 2:
            continue
        ranked = values.rank(method="first")
        labels = pd.qcut(
            ranked,
            q=bin_count,
            labels=False,
            duplicates="drop",
        )
        result.loc[labels.index, "_factor_quantile"] = labels.astype(int) + 1
    return result


def _group_views(frame: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    return [
        ("全体", pd.Series("全体", index=frame.index, dtype=object)),
        (
            "業種",
            frame.get("industry", pd.Series("不明", index=frame.index))
            .fillna("不明")
            .astype(str),
        ),
    ]


def _return_values(
    frame: pd.DataFrame,
    return_column: str,
    settled_column: str,
) -> pd.Series:
    values = _numeric_column(frame, return_column)
    if settled_column in frame:
        values = values[_truthy(frame[settled_column])]
    return values.dropna()


def build_factor_quantile_evaluation(
    observations: pd.DataFrame,
    *,
    quantiles: int = 5,
    min_samples: int = 30,
) -> pd.DataFrame:
    if observations.empty or "trade_date" not in observations:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for version in _versions(observations):
        version_frame = _version_frame(observations, version)
        for spec in FACTOR_SPECS:
            if spec.key not in version_frame:
                continue
            factor_frame = _with_quantiles(
                version_frame,
                spec,
                quantiles=quantiles,
            )
            factor_frame = factor_frame.dropna(subset=["_factor_quantile"])
            if factor_frame.empty:
                continue
            factor_frame["_factor_quantile"] = factor_frame[
                "_factor_quantile"
            ].astype(int)
            for group_name, group_values in _group_views(factor_frame):
                grouped_frame = factor_frame.assign(_group_value=group_values)
                for group_value, group in grouped_frame.groupby(
                    "_group_value",
                    dropna=False,
                ):
                    for horizon, return_column, settled_column, horizon_label in (
                        FORWARD_RETURN_SPECS
                    ):
                        for quantile, quantile_group in group.groupby(
                            "_factor_quantile"
                        ):
                            values = _return_values(
                                quantile_group,
                                return_column,
                                settled_column,
                            )
                            rows.append(
                                {
                                    "evaluation_version": version,
                                    "factor_key": spec.key,
                                    "factor_label": spec.label,
                                    "factor_description": spec.description,
                                    "higher_is_better": spec.direction > 0,
                                    "group_name": group_name,
                                    "group_value": str(group_value),
                                    "horizon": horizon,
                                    "horizon_label": horizon_label,
                                    "quantile": int(quantile),
                                    "sample_count": int(len(quantile_group)),
                                    "valid_count": int(len(values)),
                                    "avg_return": (
                                        float(values.mean())
                                        if not values.empty
                                        else None
                                    ),
                                    "median_return": (
                                        float(values.median())
                                        if not values.empty
                                        else None
                                    ),
                                    "win_rate": (
                                        float((values > 0).mean())
                                        if not values.empty
                                        else None
                                    ),
                                    "status": (
                                        "評価可能"
                                        if len(values) >= min_samples
                                        else "サンプル不足"
                                    ),
                                }
                            )

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["top_bottom_spread"] = None
    group_columns = [
        "evaluation_version",
        "factor_key",
        "group_name",
        "group_value",
        "horizon",
    ]
    for _, indexes in result.groupby(group_columns, dropna=False).groups.items():
        group = result.loc[indexes]
        valid = group.dropna(subset=["avg_return"])
        if valid.empty:
            continue
        top = valid.loc[valid["quantile"].idxmax(), "avg_return"]
        bottom = valid.loc[valid["quantile"].idxmin(), "avg_return"]
        result.loc[indexes, "top_bottom_spread"] = float(top) - float(bottom)
    return result.sort_values(
        [*group_columns, "quantile"],
        na_position="last",
    ).reset_index(drop=True)


def _spearman(values: pd.DataFrame) -> float | None:
    clean = values.dropna()
    if len(clean) < 3:
        return None
    if clean.iloc[:, 0].nunique() < 2 or clean.iloc[:, 1].nunique() < 2:
        return None
    correlation = clean.iloc[:, 0].rank().corr(clean.iloc[:, 1].rank())
    return None if pd.isna(correlation) else float(correlation)


def build_factor_ic(
    observations: pd.DataFrame,
    *,
    min_samples: int = 30,
) -> pd.DataFrame:
    if observations.empty or "trade_date" not in observations:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for version in _versions(observations):
        version_frame = _version_frame(observations, version)
        for spec in FACTOR_SPECS:
            if spec.key not in version_frame:
                continue
            factor = _numeric_column(version_frame, spec.key) * spec.direction
            base = version_frame.assign(_adjusted_factor=factor)
            for group_name, group_values in _group_views(base):
                grouped_frame = base.assign(_group_value=group_values)
                for group_value, group in grouped_frame.groupby(
                    "_group_value",
                    dropna=False,
                ):
                    for horizon, return_column, settled_column, horizon_label in (
                        FORWARD_RETURN_SPECS
                    ):
                        daily_ics: list[float] = []
                        for _, daily in group.groupby("trade_date"):
                            returns = _numeric_column(daily, return_column)
                            if settled_column in daily:
                                returns = returns.where(
                                    _truthy(daily[settled_column])
                                )
                            correlation = _spearman(
                                pd.DataFrame(
                                    {
                                        "factor": daily["_adjusted_factor"],
                                        "return": returns,
                                    }
                                )
                            )
                            if correlation is not None:
                                daily_ics.append(correlation)
                        values = pd.Series(daily_ics, dtype=float)
                        rows.append(
                            {
                                "evaluation_version": version,
                                "factor_key": spec.key,
                                "factor_label": spec.label,
                                "group_name": group_name,
                                "group_value": str(group_value),
                                "horizon": horizon,
                                "horizon_label": horizon_label,
                                "ic_count": int(len(values)),
                                "mean_ic": (
                                    float(values.mean())
                                    if not values.empty
                                    else None
                                ),
                                "median_ic": (
                                    float(values.median())
                                    if not values.empty
                                    else None
                                ),
                                "positive_ic_rate": (
                                    float((values > 0).mean())
                                    if not values.empty
                                    else None
                                ),
                                "status": (
                                    "評価可能"
                                    if len(values) >= min_samples
                                    else "サンプル不足"
                                ),
                            }
                        )
    return pd.DataFrame(rows)


def build_factor_turnover(
    observations: pd.DataFrame,
    *,
    quantiles: int = 5,
    min_samples: int = 10,
) -> pd.DataFrame:
    if observations.empty or not {"trade_date", "ticker"}.issubset(
        observations.columns
    ):
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for version in _versions(observations):
        version_frame = _version_frame(observations, version)
        for spec in FACTOR_SPECS:
            if spec.key not in version_frame:
                continue
            factor_frame = _with_quantiles(
                version_frame,
                spec,
                quantiles=quantiles,
            ).dropna(subset=["_factor_quantile"])
            if factor_frame.empty:
                continue
            top_sets: list[tuple[str, set[str]]] = []
            for trade_date, daily in factor_frame.groupby("trade_date"):
                top_quantile = daily["_factor_quantile"].max()
                members = set(
                    daily.loc[
                        daily["_factor_quantile"].eq(top_quantile), "ticker"
                    ]
                    .dropna()
                    .astype(str)
                )
                if members:
                    top_sets.append((str(trade_date), members))

            turnover_values: list[float] = []
            transition_dates: list[str] = []
            for (previous_date, previous), (current_date, current) in zip(
                top_sets,
                top_sets[1:],
            ):
                if not are_consecutive_tse_sessions(previous_date, current_date):
                    continue
                retained = len(previous & current) / len(previous)
                turnover_values.append(1.0 - retained)
                transition_dates.append(current_date)
            values = pd.Series(turnover_values, dtype=float)
            rows.append(
                {
                    "evaluation_version": version,
                    "factor_key": spec.key,
                    "factor_label": spec.label,
                    "transition_count": int(len(values)),
                    "avg_turnover": (
                        float(values.mean()) if not values.empty else None
                    ),
                    "median_turnover": (
                        float(values.median()) if not values.empty else None
                    ),
                    "latest_turnover": (
                        float(values.iloc[-1]) if not values.empty else None
                    ),
                    "latest_transition_date": (
                        transition_dates[-1] if transition_dates else None
                    ),
                    "status": (
                        "評価可能"
                        if len(values) >= min_samples
                        else "サンプル不足"
                    ),
                }
            )
    return pd.DataFrame(rows)


def _mean_stats(values: pd.Series) -> dict[str, object]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return {
        "valid_count": int(len(clean)),
        "avg_return": float(clean.mean()) if not clean.empty else None,
        "median_return": float(clean.median()) if not clean.empty else None,
        "win_rate": float((clean > 0).mean()) if not clean.empty else None,
        "variance": float(clean.var(ddof=1)) if len(clean) >= 2 else None,
    }


def _spread_interval(
    pass_stats: dict[str, object],
    fail_stats: dict[str, object],
) -> tuple[float | None, float | None]:
    pass_count = int(pass_stats["valid_count"])
    fail_count = int(fail_stats["valid_count"])
    pass_variance = pass_stats["variance"]
    fail_variance = fail_stats["variance"]
    pass_average = pass_stats["avg_return"]
    fail_average = fail_stats["avg_return"]
    if (
        pass_count < 2
        or fail_count < 2
        or pass_variance is None
        or fail_variance is None
        or pass_average is None
        or fail_average is None
    ):
        return None, None
    spread = float(pass_average) - float(fail_average)
    standard_error = math.sqrt(
        float(pass_variance) / pass_count + float(fail_variance) / fail_count
    )
    return spread - 1.96 * standard_error, spread + 1.96 * standard_error


def _rule_group_views(frame: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    yahoo_buckets = frame.get(
        "best_yahoo_rank",
        pd.Series(index=frame.index, dtype=float),
    ).apply(_rank_bucket)
    return [
        ("全体", pd.Series("全体", index=frame.index, dtype=object)),
        (
            "市場",
            frame.get("market", pd.Series("不明", index=frame.index))
            .fillna("不明")
            .astype(str),
        ),
        (
            "業種",
            frame.get("industry", pd.Series("不明", index=frame.index))
            .fillna("不明")
            .astype(str),
        ),
        ("Yahoo順位帯", yahoo_buckets),
    ]


def build_rule_evaluation(
    observations: pd.DataFrame,
    *,
    min_samples: int = 30,
) -> pd.DataFrame:
    if observations.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for version in _versions(observations):
        version_frame = _version_frame(observations, version)
        for spec in RULE_SPECS:
            if spec.key not in version_frame:
                continue
            passed = _truthy(version_frame[spec.key])
            base = version_frame.assign(_rule_passed=passed)
            for group_name, group_values in _rule_group_views(base):
                grouped_frame = base.assign(_group_value=group_values)
                for group_value, group in grouped_frame.groupby(
                    "_group_value",
                    dropna=False,
                ):
                    for horizon, return_column, settled_column, horizon_label in (
                        FORWARD_RETURN_SPECS
                    ):
                        returns = _numeric_column(group, return_column)
                        if settled_column in group:
                            returns = returns.where(
                                _truthy(group[settled_column])
                            )
                        pass_stats = _mean_stats(
                            returns[group["_rule_passed"]]
                        )
                        fail_stats = _mean_stats(
                            returns[~group["_rule_passed"]]
                        )
                        pass_average = pass_stats["avg_return"]
                        fail_average = fail_stats["avg_return"]
                        spread = (
                            float(pass_average) - float(fail_average)
                            if pass_average is not None and fail_average is not None
                            else None
                        )
                        ci_low, ci_high = _spread_interval(
                            pass_stats,
                            fail_stats,
                        )
                        sufficient = (
                            int(pass_stats["valid_count"]) >= min_samples
                            and int(fail_stats["valid_count"]) >= min_samples
                        )
                        if not sufficient:
                            finding = "サンプル不足"
                        elif spread is not None and spread > 0:
                            finding = "通過側が良好"
                        elif spread is not None and spread < 0:
                            finding = "未通過側が良好"
                        else:
                            finding = "差が小さい"
                        rows.append(
                            {
                                "evaluation_version": version,
                                "rule_key": spec.key,
                                "rule_label": spec.label,
                                "rule_category": spec.category,
                                "rule_description": spec.description,
                                "group_name": group_name,
                                "group_value": str(group_value),
                                "horizon": horizon,
                                "horizon_label": horizon_label,
                                "sample_count": int(len(group)),
                                "pass_count": int(group["_rule_passed"].sum()),
                                "fail_count": int((~group["_rule_passed"]).sum()),
                                "pass_valid_count": pass_stats["valid_count"],
                                "fail_valid_count": fail_stats["valid_count"],
                                "pass_avg_return": pass_average,
                                "fail_avg_return": fail_average,
                                "return_spread": spread,
                                "spread_ci_low": ci_low,
                                "spread_ci_high": ci_high,
                                "pass_median_return": pass_stats["median_return"],
                                "fail_median_return": fail_stats["median_return"],
                                "pass_win_rate": pass_stats["win_rate"],
                                "fail_win_rate": fail_stats["win_rate"],
                                "status": (
                                    "評価可能" if sufficient else "サンプル不足"
                                ),
                                "finding": finding,
                            }
                        )
    return pd.DataFrame(rows)


def build_evaluation_bundle(
    observations: pd.DataFrame,
    *,
    quantiles: int = 5,
    min_samples: int = 30,
) -> EvaluationBundle:
    return EvaluationBundle(
        rule_evaluation=build_rule_evaluation(
            observations,
            min_samples=min_samples,
        ),
        factor_quantiles=build_factor_quantile_evaluation(
            observations,
            quantiles=quantiles,
            min_samples=min_samples,
        ),
        factor_ic=build_factor_ic(
            observations,
            min_samples=min_samples,
        ),
        factor_turnover=build_factor_turnover(
            observations,
            quantiles=quantiles,
        ),
    )
