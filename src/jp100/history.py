from __future__ import annotations

from pathlib import Path

import pandas as pd

from .storage import save_frame
from .trading_calendar import are_consecutive_tse_sessions


def load_history(path: Path, code_column: str = "code") -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(
            path,
            encoding="utf-8-sig",
            dtype={code_column: str},
        )
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    if code_column in frame:
        frame[code_column] = frame[code_column].fillna("").astype(str)
    return frame


def merge_history(
    existing: pd.DataFrame,
    current: pd.DataFrame,
    key_columns: list[str],
    sort_columns: list[str] | None = None,
) -> pd.DataFrame:
    if existing.empty:
        merged = current.copy()
    elif current.empty:
        merged = existing.copy()
    else:
        merged = pd.concat([existing, current], ignore_index=True, sort=False)
    if merged.empty:
        return merged
    available_keys = [column for column in key_columns if column in merged]
    if available_keys:
        merged = merged.drop_duplicates(available_keys, keep="last")
    available_sort = [
        column for column in (sort_columns or key_columns) if column in merged
    ]
    if available_sort:
        merged = merged.sort_values(available_sort, na_position="last")
    return merged.reset_index(drop=True)


def add_candidate_appearance_stats(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history.copy()
    required = {"snapshot_date", "code"}
    if not required.issubset(history.columns):
        raise ValueError("候補履歴に snapshot_date または code がありません。")

    frame = history.copy()
    frame["snapshot_date"] = pd.to_datetime(
        frame["snapshot_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    frame["code"] = frame["code"].fillna("").astype(str)
    frame = frame.dropna(subset=["snapshot_date"])
    frame = frame[frame["code"].ne("")]
    frame = frame.drop_duplicates(["snapshot_date", "code"], keep="last")

    rows: list[dict[str, object]] = []
    state: dict[str, dict[str, object]] = {}
    for _, row in frame.sort_values(
        ["snapshot_date", "best_yahoo_rank", "code"], na_position="last"
    ).iterrows():
        code = str(row["code"])
        current_date = str(row["snapshot_date"])
        previous = state.get(code, {})
        previous_date = previous.get("snapshot_date")
        appearance_count = int(previous.get("appearance_count", 0)) + 1
        consecutive = (
            int(previous.get("consecutive_appearances", 0)) + 1
            if previous_date
            and are_consecutive_tse_sessions(previous_date, current_date)
            else 1
        )
        current_rank = pd.to_numeric(
            pd.Series([row.get("best_yahoo_rank")]), errors="coerce"
        ).iloc[0]
        previous_rank = previous.get("best_yahoo_rank")
        rank_change = (
            float(previous_rank) - float(current_rank)
            if previous_rank is not None and pd.notna(current_rank)
            else None
        )
        record = row.to_dict()
        record.update(
            {
                "first_seen_date": previous.get("first_seen_date", current_date),
                "appearance_count": appearance_count,
                "consecutive_appearances": consecutive,
                "previous_yahoo_rank": previous_rank,
                "yahoo_rank_change": rank_change,
            }
        )
        rows.append(record)
        state[code] = {
            "snapshot_date": current_date,
            "appearance_count": appearance_count,
            "consecutive_appearances": consecutive,
            "best_yahoo_rank": (
                None if pd.isna(current_rank) else float(current_rank)
            ),
            "first_seen_date": record["first_seen_date"],
        }
    return pd.DataFrame(rows).sort_values(
        ["snapshot_date", "best_yahoo_rank", "code"], na_position="last"
    ).reset_index(drop=True)


def recent_history_tickers(
    history: pd.DataFrame,
    *,
    recent_dates: int = 10,
) -> list[str]:
    if history.empty or not {"trade_date", "ticker"}.issubset(history.columns):
        return []
    dates = sorted(history["trade_date"].dropna().astype(str).unique().tolist())
    selected_dates = set(dates[-recent_dates:])
    return sorted(
        history.loc[
            history["trade_date"].astype(str).isin(selected_dates), "ticker"
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )


def save_history(frame: pd.DataFrame, path: Path) -> None:
    save_frame(frame, path)
