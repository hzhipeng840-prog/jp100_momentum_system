from __future__ import annotations

import math

import pandas as pd

from .market import adjusted_price_frame


BASE_COLUMNS = [
    "trade_date",
    "code",
    "ticker",
    "name",
    "market",
    "industry",
    "pick_rank",
    "score",
    "best_yahoo_rank",
    "selection_reason",
    "signal_close",
    "signal_raw_close",
    "signal_adjusted_close",
    "latest_price_date",
    "observed_days",
    "next_open_date",
    "next_open",
    "next_open_gap",
]


def _number(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else float(numeric)


def _return(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0:
        return None
    return float(current / base - 1)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _price_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    result = adjusted_price_frame(frame)
    result["date"] = pd.to_datetime(result.index, errors="coerce").normalize()
    for column in ("Open", "High", "Low", "Close"):
        result[column] = pd.to_numeric(result.get(column), errors="coerce")
    return (
        result.dropna(subset=["date", "Close"])
        .sort_values("date")
        .drop_duplicates("date", keep="last")
        .reset_index(drop=True)
    )


def calculate_followup(
    row: pd.Series,
    price_history: pd.DataFrame | None,
    horizons: tuple[int, ...] = (1, 3, 5, 10),
    *,
    benchmark_history: pd.DataFrame | None = None,
    cost_scenarios_bps: tuple[int, ...] = (0, 10, 25, 50),
) -> dict[str, object]:
    raw_close = _number(row.get("close"))
    result: dict[str, object] = {
        "signal_close": raw_close,
        "signal_raw_close": raw_close,
        "signal_adjusted_close": None,
        "latest_price_date": None,
        "observed_days": 0,
        "next_open_date": None,
        "next_open": None,
        "next_open_gap": None,
    }
    for day in horizons:
        result[f"return_{day}d"] = None
        result[f"max_gain_{day}d"] = None
        result[f"max_drawdown_{day}d"] = None
        result[f"open_buy_return_{day}d"] = None
        result[f"benchmark_return_{day}d"] = None
        result[f"benchmark_open_buy_return_{day}d"] = None
        result[f"excess_return_{day}d"] = None
        result[f"open_buy_excess_return_{day}d"] = None
        for cost_bps in cost_scenarios_bps:
            result[f"net_open_buy_return_{day}d_{cost_bps}bps"] = None
            result[f"net_excess_return_{day}d_{cost_bps}bps"] = None
        result[f"settled_{day}d"] = False

    signal_date = pd.to_datetime(row.get("trade_date"), errors="coerce")
    prices = _price_frame(price_history)
    if pd.isna(signal_date) or prices.empty:
        return result

    signal_date = pd.Timestamp(signal_date).normalize()
    signal_close = None
    matched = prices[prices["date"].eq(signal_date)]
    if not matched.empty:
        signal_close = _number(matched.iloc[-1].get("Close"))
        result["signal_adjusted_close"] = signal_close
        result["signal_close"] = signal_close
    if signal_close is None:
        signal_close = raw_close
        result["signal_adjusted_close"] = signal_close
    if signal_close is None or signal_close == 0:
        return result

    future = prices[prices["date"] > signal_date].copy().reset_index(drop=True)
    if future.empty:
        return result

    result["latest_price_date"] = future.iloc[-1]["date"].strftime("%Y-%m-%d")
    result["observed_days"] = int(len(future))
    next_row = future.iloc[0]
    next_open = _number(next_row.get("Open"))
    result["next_open_date"] = next_row["date"].strftime("%Y-%m-%d")
    result["next_open"] = next_open
    result["next_open_gap"] = _return(next_open, signal_close)

    for day in horizons:
        if len(future) < day:
            continue
        window = future.iloc[:day]
        end_close = _number(window.iloc[-1].get("Close"))
        high = pd.to_numeric(window["High"], errors="coerce").max()
        low = pd.to_numeric(window["Low"], errors="coerce").min()
        result[f"return_{day}d"] = _return(end_close, signal_close)
        result[f"max_gain_{day}d"] = (
            _return(float(high), signal_close) if pd.notna(high) else None
        )
        result[f"max_drawdown_{day}d"] = (
            _return(float(low), signal_close) if pd.notna(low) else None
        )
        result[f"open_buy_return_{day}d"] = _return(end_close, next_open)
        result[f"settled_{day}d"] = True

    benchmark = _price_frame(benchmark_history)
    benchmark_signal = (
        benchmark[benchmark["date"].eq(signal_date)]
        if "date" in benchmark
        else pd.DataFrame()
    )
    benchmark_future = (
        benchmark[benchmark["date"] > signal_date].reset_index(drop=True)
        if "date" in benchmark
        else pd.DataFrame()
    )
    benchmark_close = (
        _number(benchmark_signal.iloc[-1].get("Close"))
        if not benchmark_signal.empty
        else None
    )
    benchmark_open = (
        _number(benchmark_future.iloc[0].get("Open"))
        if not benchmark_future.empty
        else None
    )
    for day in horizons:
        if (
            benchmark_close is not None
            and len(benchmark_future) >= day
        ):
            benchmark_end = _number(
                benchmark_future.iloc[day - 1].get("Close")
            )
            result[f"benchmark_return_{day}d"] = _return(
                benchmark_end,
                benchmark_close,
            )
            result[f"benchmark_open_buy_return_{day}d"] = _return(
                benchmark_end,
                benchmark_open,
            )
        stock_return = _number(result.get(f"return_{day}d"))
        open_buy_return = _number(result.get(f"open_buy_return_{day}d"))
        benchmark_return = _number(result.get(f"benchmark_return_{day}d"))
        benchmark_open_return = _number(
            result.get(f"benchmark_open_buy_return_{day}d")
        )
        if stock_return is not None and benchmark_return is not None:
            result[f"excess_return_{day}d"] = stock_return - benchmark_return
        if open_buy_return is not None and benchmark_open_return is not None:
            result[f"open_buy_excess_return_{day}d"] = (
                open_buy_return - benchmark_open_return
            )
        for cost_bps in cost_scenarios_bps:
            if open_buy_return is None:
                continue
            one_way_cost = cost_bps / 10_000
            net_return = (
                (1 + open_buy_return)
                * (1 - one_way_cost)
                * (1 - one_way_cost)
                - 1
            )
            result[f"net_open_buy_return_{day}d_{cost_bps}bps"] = net_return
            if benchmark_open_return is not None:
                result[f"net_excess_return_{day}d_{cost_bps}bps"] = (
                    net_return - benchmark_open_return
                )
    return result


def _merge_followup_rows(
    existing: pd.DataFrame,
    fresh: pd.DataFrame,
    key_columns: tuple[str, ...],
) -> pd.DataFrame:
    if existing.empty:
        return fresh.copy()
    if fresh.empty:
        return existing.copy()

    existing_rows = {
        tuple(str(row.get(column)) for column in key_columns): row.to_dict()
        for _, row in existing.iterrows()
    }
    for _, row in fresh.iterrows():
        key = tuple(str(row.get(column)) for column in key_columns)
        merged = existing_rows.get(key, {}).copy()
        for column, value in row.to_dict().items():
            if column.startswith("settled_"):
                merged[column] = _as_bool(merged.get(column)) or _as_bool(value)
            elif column == "observed_days":
                merged[column] = max(
                    int(_number(merged.get(column)) or 0),
                    int(_number(value) or 0),
                )
            elif value is not None and not (
                isinstance(value, float) and math.isnan(value)
            ):
                merged[column] = value
        existing_rows[key] = merged
    result = pd.DataFrame(existing_rows.values())
    sort_columns = [
        column
        for column in ("trade_date", "evaluation_version", "pick_rank", "rank", "code")
        if column in result
    ]
    if sort_columns:
        result = result.sort_values(sort_columns, na_position="last")
    return result.reset_index(drop=True)


def build_followups(
    picks_history: pd.DataFrame,
    price_history: dict[str, pd.DataFrame],
    *,
    horizons: tuple[int, ...] = (1, 3, 5, 10),
    existing: pd.DataFrame | None = None,
    key_columns: tuple[str, ...] = ("trade_date", "code"),
    passthrough_columns: list[str] | None = None,
    benchmark_history: pd.DataFrame | None = None,
    cost_scenarios_bps: tuple[int, ...] = (0, 10, 25, 50),
) -> pd.DataFrame:
    if picks_history.empty:
        return pd.DataFrame() if existing is None else existing.copy()

    rows: list[dict[str, object]] = []
    record_columns = list(
        dict.fromkeys([*BASE_COLUMNS, *(passthrough_columns or [])])
    )
    for _, row in picks_history.iterrows():
        ticker = str(row.get("ticker") or "").strip()
        prices = price_history.get(ticker)
        followup = calculate_followup(
            row,
            prices,
            horizons=horizons,
            benchmark_history=benchmark_history,
            cost_scenarios_bps=cost_scenarios_bps,
        )
        record = {
            column: row.get(column)
            for column in record_columns
            if column not in followup
        }
        record.update(followup)
        rows.append(record)
    fresh = pd.DataFrame(rows)
    return _merge_followup_rows(
        pd.DataFrame() if existing is None else existing,
        fresh,
        key_columns,
    )
