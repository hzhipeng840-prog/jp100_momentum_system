from __future__ import annotations

import pandas as pd


METRICS = [
    ("next_open", "next_open_gap", None, "翌日寄付ギャップ"),
    ("1d", "return_1d", "settled_1d", "1日リターン"),
    ("3d", "return_3d", "settled_3d", "3日リターン"),
    ("5d", "return_5d", "settled_5d", "5日リターン"),
    ("10d", "return_10d", "settled_10d", "10日リターン"),
    ("open_buy_1d", "open_buy_return_1d", "settled_1d", "翌日寄付買い1日"),
    ("open_buy_3d", "open_buy_return_3d", "settled_3d", "翌日寄付買い3日"),
    ("open_buy_5d", "open_buy_return_5d", "settled_5d", "翌日寄付買い5日"),
]


def _truthy(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.fillna("").astype(str).str.strip().str.lower().isin(
        {"true", "1", "yes", "y"}
    )


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


def build_backtest_summary(followups: pd.DataFrame) -> pd.DataFrame:
    if followups.empty:
        return pd.DataFrame()
    frame = followups.copy()
    frame["yahoo_rank_bucket"] = frame.get(
        "best_yahoo_rank", pd.Series(index=frame.index, dtype=float)
    ).apply(_rank_bucket)
    groups = [
        ("全体", pd.Series("毎日厳選", index=frame.index)),
        ("市場", frame.get("market", pd.Series("不明", index=frame.index))),
        ("業種", frame.get("industry", pd.Series("不明", index=frame.index))),
        ("Yahoo順位帯", frame["yahoo_rank_bucket"]),
    ]

    rows: list[dict[str, object]] = []
    for group_name, group_values in groups:
        working = frame.assign(_group_value=group_values.fillna("不明").astype(str))
        for group_value, group in working.groupby("_group_value", dropna=False):
            for metric_key, column, settled_column, label in METRICS:
                if column not in group:
                    continue
                values = pd.to_numeric(group[column], errors="coerce")
                if settled_column and settled_column in group:
                    values = values[_truthy(group[settled_column])]
                values = values.dropna()
                rows.append(
                    {
                        "group_name": group_name,
                        "group_value": str(group_value),
                        "metric_key": metric_key,
                        "metric_label": label,
                        "sample_count": int(len(group)),
                        "valid_count": int(len(values)),
                        "avg_return": (
                            float(values.mean()) if not values.empty else None
                        ),
                        "median_return": (
                            float(values.median()) if not values.empty else None
                        ),
                        "win_rate": (
                            float((values > 0).mean()) if not values.empty else None
                        ),
                    }
                )
    return pd.DataFrame(rows)
