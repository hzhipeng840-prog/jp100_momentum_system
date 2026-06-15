from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import USER_DIR
from .sources import normalize_code
from .storage import save_frame, timestamp_now


WATCHLIST_COLUMNS = ["code", "name", "note", "added_at"]


def watchlist_path() -> Path:
    return USER_DIR / "watchlist.csv"


def load_watchlist(path: Path | None = None) -> pd.DataFrame:
    target = path or watchlist_path()
    if not target.exists():
        return pd.DataFrame(columns=WATCHLIST_COLUMNS)
    frame = pd.read_csv(target, dtype={"code": str})
    for column in WATCHLIST_COLUMNS:
        if column not in frame:
            frame[column] = ""
    return frame[WATCHLIST_COLUMNS].drop_duplicates("code", keep="last")


def add_watchlist_entry(
    frame: pd.DataFrame,
    *,
    code: str,
    name: str = "",
    note: str = "",
    added_at: str | None = None,
) -> pd.DataFrame:
    normalized = normalize_code(code)
    if not normalized or not pd.Series([normalized]).str.fullmatch(
        r"[0-9A-Z]{4,5}"
    ).iloc[0]:
        raise ValueError("銘柄コードは4～5桁の英数字で入力してください。")
    current = frame.copy()
    entry = pd.DataFrame(
        [
            {
                "code": normalized,
                "name": str(name or "").strip(),
                "note": str(note or "").strip(),
                "added_at": added_at or timestamp_now(),
            }
        ]
    )
    current = current[current["code"].astype(str).ne(normalized)]
    return pd.concat([current, entry], ignore_index=True)[WATCHLIST_COLUMNS]


def remove_watchlist_entries(
    frame: pd.DataFrame,
    codes: list[str],
) -> pd.DataFrame:
    removing = {normalize_code(code) for code in codes}
    return frame[~frame["code"].astype(str).isin(removing)].reset_index(drop=True)


def save_watchlist(frame: pd.DataFrame, path: Path | None = None) -> None:
    target = path or watchlist_path()
    save_frame(frame[WATCHLIST_COLUMNS], target)


def enrich_watchlist(
    watchlist: pd.DataFrame,
    *,
    daily_picks: pd.DataFrame,
    top100: pd.DataFrame,
    candidates: pd.DataFrame,
    liquidity_top100: pd.DataFrame,
    jpx_universe: pd.DataFrame,
) -> pd.DataFrame:
    if watchlist.empty:
        return watchlist.copy()
    result = watchlist.copy()
    master_frames = [
        frame[[column for column in ("code", "name") if column in frame]].copy()
        for frame in (jpx_universe, top100, candidates)
        if not frame.empty and "code" in frame
    ]
    if master_frames:
        master = pd.concat(master_frames, ignore_index=True).drop_duplicates(
            "code",
            keep="first",
        )
        name_map = master.set_index("code")["name"].to_dict()
        result["name"] = result.apply(
            lambda row: str(row.get("name") or "").strip()
            or str(name_map.get(str(row["code"]), "")),
            axis=1,
        )

    daily_codes = set(daily_picks.get("code", pd.Series(dtype=str)).astype(str))
    top_codes = set(top100.get("code", pd.Series(dtype=str)).astype(str))
    candidate_codes = set(candidates.get("code", pd.Series(dtype=str)).astype(str))
    liquidity_codes = set(
        liquidity_top100.get("code", pd.Series(dtype=str)).astype(str)
    )

    def status(code: object) -> str:
        value = str(code)
        if value in daily_codes:
            return "本日の厳選"
        if value in top_codes:
            return "注目Top100"
        if value in candidate_codes:
            return "Yahoo候補"
        if value in liquidity_codes:
            return "JPX流動性Top100"
        return "圏外"

    result["current_status"] = result["code"].map(status)
    if not top100.empty and "code" in top100:
        details = top100[
            [column for column in ("code", "rank", "score", "return_20d") if column in top100]
        ].drop_duplicates("code")
        result = result.merge(details, how="left", on="code")
    return result
