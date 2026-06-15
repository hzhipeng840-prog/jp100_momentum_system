from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .market import adjusted_price_frame


@dataclass
class PortfolioBundle:
    curve: pd.DataFrame
    summary: pd.DataFrame
    positions: pd.DataFrame


def _prices_by_date(frame: pd.DataFrame | None) -> dict[pd.Timestamp, dict[str, float]]:
    adjusted = adjusted_price_frame(frame)
    if adjusted.empty:
        return {}
    result: dict[pd.Timestamp, dict[str, float]] = {}
    for date, row in adjusted.sort_index().iterrows():
        normalized = pd.Timestamp(date).normalize()
        open_price = pd.to_numeric(pd.Series([row.get("Open")]), errors="coerce").iloc[0]
        close_price = pd.to_numeric(pd.Series([row.get("Close")]), errors="coerce").iloc[0]
        if pd.isna(close_price):
            continue
        result[normalized] = {
            "open": float(open_price) if pd.notna(open_price) else float(close_price),
            "close": float(close_price),
        }
    return result


def _drawdown(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity.div(peak.where(peak.ne(0))).sub(1)


def build_virtual_portfolio(
    picks_history: pd.DataFrame,
    price_history: dict[str, pd.DataFrame],
    *,
    benchmark_history: pd.DataFrame | None = None,
    holding_days: int = 5,
    cost_bps: float = 10.0,
) -> PortfolioBundle:
    if picks_history.empty:
        return PortfolioBundle(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    relevant_tickers = set(
        picks_history.get("ticker", pd.Series(dtype=str))
        .dropna()
        .astype(str)
        .tolist()
    )
    price_maps = {
        ticker: _prices_by_date(frame)
        for ticker, frame in price_history.items()
        if ticker in relevant_tickers and frame is not None and not frame.empty
    }
    orders: dict[pd.Timestamp, list[dict[str, object]]] = {}
    for signal_date, group in picks_history.groupby("trade_date", dropna=False):
        signal = pd.to_datetime(signal_date, errors="coerce")
        if pd.isna(signal):
            continue
        cohort: list[dict[str, object]] = []
        entry_dates: list[pd.Timestamp] = []
        for _, row in group.sort_values("pick_rank", na_position="last").iterrows():
            ticker = str(row.get("ticker") or "").strip()
            prices = price_maps.get(ticker, {})
            future_dates = sorted(date for date in prices if date > signal.normalize())
            if not future_dates:
                continue
            entry_date = future_dates[0]
            exit_date = (
                future_dates[holding_days - 1]
                if len(future_dates) >= holding_days
                else None
            )
            entry_dates.append(entry_date)
            cohort.append(
                {
                    "signal_date": signal.normalize(),
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "ticker": ticker,
                    "code": str(row.get("code") or ""),
                    "name": str(row.get("name") or ""),
                    "industry": str(row.get("industry") or "未分類"),
                    "pick_rank": row.get("pick_rank"),
                }
            )
        if not cohort:
            continue
        common_entry = max(entry_dates)
        eligible = [
            item
            for item in cohort
            if common_entry in price_maps.get(str(item["ticker"]), {})
        ]
        if eligible:
            orders.setdefault(common_entry, []).append(
                {
                    "signal_date": signal.normalize(),
                    "positions": eligible,
                }
            )

    if not orders:
        return PortfolioBundle(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    first_date = min(orders)
    all_dates = sorted(
        {
            date
            for prices in price_maps.values()
            for date in prices
            if date >= first_date
        }
    )
    if not all_dates:
        return PortfolioBundle(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    one_way_cost = cost_bps / 10_000
    cash = 1.0
    previous_equity = 1.0
    active: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    total_traded = 0.0

    for date in all_dates:
        buy_value = 0.0
        sell_value = 0.0
        for cohort in orders.get(date, []):
            candidates = list(cohort["positions"])
            target = min(cash, max(previous_equity, 0) / holding_days)
            if target <= 0 or not candidates:
                continue
            allocation = target / len(candidates)
            opened = 0.0
            for item in candidates:
                ticker = str(item["ticker"])
                price = price_maps[ticker][date]["open"]
                if price <= 0:
                    continue
                shares = allocation / (price * (1 + one_way_cost))
                paid = shares * price * (1 + one_way_cost)
                opened += paid
                buy_value += shares * price
                active.append(
                    {
                        **item,
                        "shares": shares,
                        "entry_price": price,
                        "last_price": price,
                    }
                )
            cash -= opened

        remaining: list[dict[str, object]] = []
        for position in active:
            ticker = str(position["ticker"])
            current = price_maps.get(ticker, {}).get(date)
            if current:
                position["last_price"] = current["close"]
            exit_date = position.get("exit_date")
            if exit_date is not None and pd.Timestamp(exit_date) == date and current:
                gross_proceeds = float(position["shares"]) * current["close"]
                cash += gross_proceeds * (1 - one_way_cost)
                sell_value += gross_proceeds
            else:
                remaining.append(position)
        active = remaining

        market_value = sum(
            float(position["shares"]) * float(position["last_price"])
            for position in active
        )
        equity = cash + market_value
        daily_return = equity / previous_equity - 1 if previous_equity else 0.0
        traded = buy_value + sell_value
        total_traded += traded
        rows.append(
            {
                "date": date.date().isoformat(),
                "equity": equity,
                "daily_return": daily_return,
                "cash": cash,
                "market_value": market_value,
                "active_positions": len(active),
                "buy_value": buy_value,
                "sell_value": sell_value,
                "daily_turnover": traded / previous_equity if previous_equity else None,
            }
        )
        previous_equity = equity

    curve = pd.DataFrame(rows)
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    returns = pd.to_numeric(curve["daily_return"], errors="coerce").dropna()
    curve["drawdown"] = _drawdown(equity)

    benchmark_prices = _prices_by_date(benchmark_history)
    benchmark_series = pd.Series(
        {
            date: values["close"]
            for date, values in benchmark_prices.items()
            if date >= first_date
        },
        dtype=float,
    ).sort_index()
    if not benchmark_series.empty:
        benchmark_series = benchmark_series.reindex(
            pd.to_datetime(curve["date"])
        ).ffill()
        first_benchmark = benchmark_series.dropna().iloc[0]
        curve["benchmark_equity"] = (
            benchmark_series.to_numpy() / first_benchmark
        )
        curve["excess_equity"] = curve["equity"] - curve["benchmark_equity"]
    else:
        curve["benchmark_equity"] = np.nan
        curve["excess_equity"] = np.nan

    days = len(curve)
    total_return = float(equity.iloc[-1] - 1) if not equity.empty else None
    annualized_return = (
        float(equity.iloc[-1] ** (252 / days) - 1)
        if days > 1 and equity.iloc[-1] > 0
        else None
    )
    annualized_volatility = (
        float(returns.std(ddof=0) * np.sqrt(252))
        if len(returns) > 1
        else None
    )
    sharpe = (
        float(returns.mean() / returns.std(ddof=0) * np.sqrt(252))
        if len(returns) > 1 and returns.std(ddof=0) > 0
        else None
    )
    benchmark_return = (
        float(curve["benchmark_equity"].dropna().iloc[-1] - 1)
        if curve["benchmark_equity"].notna().any()
        else None
    )
    summary = pd.DataFrame(
        [
            {
                "start_date": curve.iloc[0]["date"],
                "end_date": curve.iloc[-1]["date"],
                "observation_days": days,
                "holding_days": holding_days,
                "cost_bps_one_way": cost_bps,
                "total_return": total_return,
                "benchmark_return": benchmark_return,
                "excess_return": (
                    total_return - benchmark_return
                    if total_return is not None and benchmark_return is not None
                    else None
                ),
                "annualized_return": annualized_return,
                "annualized_volatility": annualized_volatility,
                "sharpe": sharpe,
                "max_drawdown": (
                    float(curve["drawdown"].min()) if not curve.empty else None
                ),
                "average_daily_turnover": float(
                    pd.to_numeric(curve["daily_turnover"], errors="coerce").mean()
                ),
                "total_traded_value": total_traded,
            }
        ]
    )
    position_rows = []
    for position in active:
        entry_price = float(position["entry_price"])
        last_price = float(position["last_price"])
        position_rows.append(
            {
                "signal_date": pd.Timestamp(position["signal_date"]).date().isoformat(),
                "entry_date": pd.Timestamp(position["entry_date"]).date().isoformat(),
                "planned_exit_date": (
                    pd.Timestamp(position["exit_date"]).date().isoformat()
                    if position.get("exit_date") is not None
                    else None
                ),
                "code": position["code"],
                "ticker": position["ticker"],
                "name": position["name"],
                "industry": position["industry"],
                "entry_price": entry_price,
                "latest_price": last_price,
                "unrealized_return": last_price / entry_price - 1,
                "market_value": float(position["shares"]) * last_price,
            }
        )
    return PortfolioBundle(curve, summary, pd.DataFrame(position_rows))
