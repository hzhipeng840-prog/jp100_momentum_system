from __future__ import annotations

import math

import pandas as pd


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
    result = frame.copy()
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
) -> dict[str, object]:
    result: dict[str, object] = {
        "signal_close": _number(row.get("close")),
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
        result[f"settled_{day}d"] = False

    signal_date = pd.to_datetime(row.get("trade_date"), errors="coerce")
    prices = _price_frame(price_history)
    if pd.isna(signal_date) or prices.empty:
        return result

    signal_date = pd.Timestamp(signal_date).normalize()
    signal_close = result["signal_close"]
    if signal_close is None:
        matched = prices[prices["date"].eq(signal_date)]
        if not matched.empty:
            signal_close = _number(matched.iloc[-1].get("Close"))
            result["signal_close"] = signal_close
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
    return result


def _merge_followup_rows(
    existing: pd.DataFrame,
    fresh: pd.DataFrame,
) -> pd.DataFrame:
    if existing.empty:
        return fresh.copy()
    if fresh.empty:
        return existing.copy()

    existing_rows = {
        (str(row.get("trade_date")), str(row.get("code"))): row.to_dict()
        for _, row in existing.iterrows()
    }
    for _, row in fresh.iterrows():
        key = (str(row.get("trade_date")), str(row.get("code")))
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
    return pd.DataFrame(existing_rows.values()).sort_values(
        ["trade_date", "pick_rank", "code"], na_position="last"
    ).reset_index(drop=True)


def build_followups(
    picks_history: pd.DataFrame,
    price_history: dict[str, pd.DataFrame],
    *,
    horizons: tuple[int, ...] = (1, 3, 5, 10),
    existing: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if picks_history.empty:
        return pd.DataFrame() if existing is None else existing.copy()

    rows: list[dict[str, object]] = []
    for _, row in picks_history.iterrows():
        ticker = str(row.get("ticker") or "").strip()
        prices = price_history.get(ticker)
        followup = calculate_followup(row, prices, horizons=horizons)
        record = {
            column: row.get(column)
            for column in BASE_COLUMNS
            if column not in followup
        }
        record.update(followup)
        rows.append(record)
    fresh = pd.DataFrame(rows)
    return _merge_followup_rows(
        pd.DataFrame() if existing is None else existing,
        fresh,
    )
