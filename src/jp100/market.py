from __future__ import annotations

import math
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from .sources import DataSourceError


PRICE_COLUMNS = ("Open", "High", "Low", "Close", "Adj Close", "Volume")


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _configure_curl_ca_bundle() -> None:
    """curlが非ASCIIの証明書パスを扱えないWindows環境を補正する。"""
    try:
        import certifi

        source = Path(certifi.where())
        if not any(ord(character) > 127 for character in str(source)):
            return
        cache_dir = Path.cwd() / ".cache"
        target = cache_dir / "cacert.pem"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != source.stat().st_size:
            shutil.copyfile(source, target)
        relative_target = os.path.relpath(target, Path.cwd())
        os.environ["CURL_CA_BUNDLE"] = relative_target
        os.environ["SSL_CERT_FILE"] = relative_target
    except (OSError, ImportError):
        return


def _download_batch(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    _configure_curl_ca_bundle()
    try:
        import yfinance as yf
    except ImportError as exc:
        raise DataSourceError(
            "yfinance がインストールされていません。"
            "「pip install -r requirements.txt」を実行してください。"
        ) from exc

    downloaded = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        auto_adjust=False,
        actions=False,
        progress=False,
        group_by="ticker",
        threads=True,
        timeout=20,
        multi_level_index=True,
    )
    if downloaded is None or downloaded.empty:
        return {}
    return split_downloaded_history(downloaded, tickers)


def split_downloaded_history(
    downloaded: pd.DataFrame, tickers: list[str]
) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    if isinstance(downloaded.columns, pd.MultiIndex):
        level0 = set(map(str, downloaded.columns.get_level_values(0)))
        level1 = set(map(str, downloaded.columns.get_level_values(1)))
        ticker_first = bool(level0.intersection(tickers))
        for ticker in tickers:
            try:
                frame = (
                    downloaded[ticker].copy()
                    if ticker_first
                    else downloaded.xs(ticker, axis=1, level=1).copy()
                )
            except (KeyError, ValueError):
                continue
            frame.columns = [str(column) for column in frame.columns]
            frame = frame.dropna(how="all")
            if not frame.empty:
                result[ticker] = frame
        return result

    if len(tickers) == 1:
        frame = downloaded.copy()
        frame.columns = [str(column) for column in frame.columns]
        result[tickers[0]] = frame.dropna(how="all")
    return result


def download_price_history(
    tickers: list[str], period: str = "1y", batch_size: int = 80
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    history: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    for batch in _chunks(tickers, batch_size):
        try:
            history.update(_download_batch(batch, period))
        except Exception as exc:
            errors.append(f"{batch[0]}～: {exc}")
    return history, errors


def _series(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[name], errors="coerce").dropna()


def _return(close: pd.Series, days: int) -> float:
    if len(close) <= days or close.iloc[-days - 1] <= 0:
        return math.nan
    return float(close.iloc[-1] / close.iloc[-days - 1] - 1)


def calculate_features(ticker: str, frame: pd.DataFrame) -> dict[str, object] | None:
    close = _series(frame, "Adj Close")
    if close.empty:
        close = _series(frame, "Close")
    raw_close = _series(frame, "Close")
    volume = _series(frame, "Volume")
    if len(close) < 65 or raw_close.empty or len(volume) < 20:
        return None

    aligned = pd.concat(
        [raw_close.rename("close"), volume.rename("volume")], axis=1
    ).dropna()
    if len(aligned) < 20:
        return None

    daily_returns = close.pct_change(fill_method=None).dropna()
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean())
    latest = float(close.iloc[-1])
    raw_latest = float(raw_close.iloc[-1])
    avg_volume_20d = float(aligned["volume"].tail(20).mean())
    latest_volume = float(aligned["volume"].iloc[-1])
    high_120 = float(close.tail(min(120, len(close))).max())
    volatility = (
        float(daily_returns.tail(20).std(ddof=0) * np.sqrt(252))
        if len(daily_returns) >= 20
        else math.nan
    )
    return {
        "ticker": ticker,
        "trade_date": pd.Timestamp(close.index[-1]).date().isoformat(),
        "close": raw_latest,
        "return_1d": _return(close, 1),
        "return_5d": _return(close, 5),
        "return_20d": _return(close, 20),
        "return_60d": _return(close, 60),
        "return_120d": _return(close, 120),
        "ma20": ma20,
        "ma60": ma60,
        "distance_ma20": latest / ma20 - 1 if ma20 else math.nan,
        "distance_ma60": latest / ma60 - 1 if ma60 else math.nan,
        "distance_high_120d": latest / high_120 - 1 if high_120 else math.nan,
        "volatility_20d": volatility,
        "latest_volume": latest_volume,
        "avg_volume_20d": avg_volume_20d,
        "volume_ratio_20d": (
            latest_volume / avg_volume_20d if avg_volume_20d else math.nan
        ),
        "avg_turnover_20d": float(
            (aligned["close"].tail(20) * aligned["volume"].tail(20)).mean()
        ),
        "history_days": int(len(close)),
    }


def build_feature_table(
    history: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, object]] = []
    skipped: list[str] = []
    for ticker, frame in history.items():
        feature = calculate_features(ticker, frame)
        if feature is None:
            skipped.append(ticker)
        else:
            rows.append(feature)
    return pd.DataFrame(rows), skipped
