from __future__ import annotations

from functools import lru_cache

import pandas as pd


CALENDAR_NAME = "XTKS"


@lru_cache(maxsize=1)
def tse_calendar():
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise RuntimeError(
            "東証営業日判定には exchange_calendars が必要です。"
            " requirements.txt をインストールしてください。"
        ) from exc
    return xcals.get_calendar(CALENDAR_NAME)


def _date(value: object) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        raise ValueError(f"営業日に変換できない日付です: {value}")
    return pd.Timestamp(timestamp).tz_localize(None).normalize()


def is_tse_session(value: object) -> bool:
    return bool(tse_calendar().is_session(_date(value)))


def previous_tse_session(value: object) -> str:
    session = tse_calendar().date_to_session(_date(value), direction="previous")
    if session == _date(value):
        session = tse_calendar().previous_session(session)
    return pd.Timestamp(session).tz_localize(None).strftime("%Y-%m-%d")


def next_tse_session(value: object) -> str:
    session = tse_calendar().date_to_session(_date(value), direction="next")
    if session == _date(value):
        session = tse_calendar().next_session(session)
    return pd.Timestamp(session).tz_localize(None).strftime("%Y-%m-%d")


def are_consecutive_tse_sessions(previous: object, current: object) -> bool:
    try:
        return next_tse_session(previous) == _date(current).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return False


def calendar_metadata(trade_date: object) -> dict[str, object]:
    date_text = _date(trade_date).strftime("%Y-%m-%d")
    return {
        "name": CALENDAR_NAME,
        "trade_date": date_text,
        "is_session": is_tse_session(date_text),
        "previous_session": previous_tse_session(date_text),
        "next_session": next_tse_session(date_text),
    }
