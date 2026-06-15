from __future__ import annotations

import pandas as pd

from .trading_calendar import previous_tse_session


def _truthy(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.fillna("").astype(str).str.strip().str.lower().isin(
        {"true", "1", "yes", "y"}
    )


def build_freshness_report(
    followups: pd.DataFrame,
    *,
    trade_date: str,
    candidate_count: int,
    feature_count: int,
    min_feature_coverage: float = 0.60,
    min_settlement_ratio: float = 0.80,
) -> dict[str, object]:
    coverage = feature_count / candidate_count if candidate_count else 0.0
    report: dict[str, object] = {
        "status": "initializing",
        "is_fresh": False,
        "trade_date": trade_date,
        "candidate_count": int(candidate_count),
        "feature_count": int(feature_count),
        "feature_coverage": round(float(coverage), 4),
        "settlement_date": None,
        "expected_settlement_date": previous_tse_session(trade_date),
        "settlement_count": 0,
        "settled_1d_count": 0,
        "settled_1d_ratio": None,
        "summary": "",
    }

    if coverage < min_feature_coverage:
        report["status"] = "partial"
        report["summary"] = (
            f"価格データ取得率が{coverage:.1%}で、基準{min_feature_coverage:.0%}を下回っています。"
        )
        return report

    if followups.empty or "trade_date" not in followups:
        report["summary"] = "初回運用のため、翌営業日以降の成績追跡を待っています。"
        return report

    dates = sorted(
        date
        for date in followups["trade_date"].dropna().astype(str).unique().tolist()
        if date < trade_date
    )
    if not dates:
        report["summary"] = "初回運用のため、翌営業日以降の成績追跡を待っています。"
        return report

    expected_settlement_date = str(report["expected_settlement_date"])
    settlement_date = dates[-1]
    if expected_settlement_date not in dates:
        report["status"] = "partial"
        report["settlement_date"] = settlement_date
        report["summary"] = (
            f"前営業日{expected_settlement_date}の追跡データがありません。"
            f" 最新の追跡日は{settlement_date}です。"
        )
        return report
    settlement_date = expected_settlement_date
    rows = followups[followups["trade_date"].astype(str).eq(settlement_date)]
    settled = (
        _truthy(rows["settled_1d"])
        if "settled_1d" in rows
        else pd.Series(False, index=rows.index)
    )
    ratio = float(settled.mean()) if len(rows) else 0.0
    report.update(
        {
            "settlement_date": settlement_date,
            "settlement_count": int(len(rows)),
            "settled_1d_count": int(settled.sum()),
            "settled_1d_ratio": round(ratio, 4),
        }
    )
    if ratio < min_settlement_ratio:
        report["status"] = "partial"
        report["summary"] = (
            f"{settlement_date}の1日成績は{int(settled.sum())}/{len(rows)}銘柄のみ確定しています。"
        )
        return report

    report["status"] = "fresh"
    report["is_fresh"] = True
    report["summary"] = (
        f"価格データ取得率は{coverage:.1%}、"
        f"{settlement_date}の1日成績は{int(settled.sum())}/{len(rows)}銘柄確定済みです。"
    )
    return report
