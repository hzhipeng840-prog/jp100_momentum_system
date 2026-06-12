from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .backtest import build_backtest_summary
from .config import PipelineConfig
from .followups import build_followups
from .freshness import build_freshness_report
from .history import (
    add_candidate_appearance_stats,
    load_history,
    merge_history,
    recent_history_tickers,
    save_history,
)
from .market import build_feature_table, download_price_history
from .scoring import make_top100, select_daily_picks
from .sources import build_candidate_pool, load_jpx_list, load_yahoo_candidates
from .storage import make_run_id, publish_outputs, timestamp_now
from .version import current_version


@dataclass
class PipelineResult:
    candidates: pd.DataFrame
    top100: pd.DataFrame
    daily_picks: pd.DataFrame
    followups: pd.DataFrame
    backtest_summary: pd.DataFrame
    freshness: dict[str, object]
    metadata: dict[str, object]


def run_pipeline(config: PipelineConfig | None = None) -> PipelineResult:
    config = config or PipelineConfig()
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    config.processed_dir.mkdir(parents=True, exist_ok=True)
    config.history_dir.mkdir(parents=True, exist_ok=True)
    config.snapshot_dir.mkdir(parents=True, exist_ok=True)

    jpx, jpx_meta = load_jpx_list(config)
    yahoo, yahoo_meta = load_yahoo_candidates(config)
    candidates = build_candidate_pool(jpx, yahoo)
    if candidates.empty:
        raise RuntimeError("JPX銘柄一覧とYahooランキングに共通する銘柄がありません。")

    candidate_history_path = config.history_dir / "candidate_history.csv"
    top100_history_path = config.history_dir / "top100_history.csv"
    picks_history_path = config.history_dir / "daily_picks_history.csv"
    followups_history_path = config.history_dir / "followups.csv"
    existing_candidate_history = load_history(candidate_history_path)
    existing_top100_history = load_history(top100_history_path)
    existing_picks_history = load_history(picks_history_path)
    existing_followups = load_history(followups_history_path)

    requested_tickers = sorted(
        set(candidates["ticker"].dropna().astype(str).tolist())
        | set(recent_history_tickers(existing_picks_history))
    )
    history, download_errors = download_price_history(
        requested_tickers,
        period=config.history_period,
        batch_size=config.batch_size,
    )
    all_features, skipped = build_feature_table(history)
    if all_features.empty or "ticker" not in all_features:
        detail = f" 取得エラー: {' / '.join(download_errors[:2])}" if download_errors else ""
        raise RuntimeError(
            "yfinanceから有効な価格履歴を取得できませんでした。" + detail
        )
    candidate_tickers = set(candidates["ticker"].dropna().astype(str))
    features = all_features[all_features["ticker"].isin(candidate_tickers)].copy()
    if features.empty:
        detail = f" 取得エラー: {' / '.join(download_errors[:2])}" if download_errors else ""
        raise RuntimeError(
            "yfinanceから有効な価格履歴を取得できませんでした。" + detail
        )

    trade_date = str(features["trade_date"].dropna().astype(str).max())
    features = features[features["trade_date"].astype(str).eq(trade_date)].copy()
    feature_coverage = len(features) / len(candidates)
    if feature_coverage < config.min_feature_coverage:
        raise RuntimeError(
            "最新基準日の価格データ取得率が不足しています。"
            f" {len(features)}/{len(candidates)}銘柄 ({feature_coverage:.1%})"
        )

    current_candidates = candidates.copy()
    current_candidates["snapshot_date"] = trade_date
    candidate_history = merge_history(
        existing_candidate_history,
        current_candidates,
        ["snapshot_date", "code"],
        ["snapshot_date", "best_yahoo_rank", "code"],
    )
    candidate_history = add_candidate_appearance_stats(candidate_history)
    current_candidates = candidate_history[
        candidate_history["snapshot_date"].astype(str).eq(trade_date)
    ].copy()

    top100 = make_top100(current_candidates, features, config)
    daily_picks = select_daily_picks(top100, config)
    if top100.empty:
        raise RuntimeError("有効な価格履歴がなく、注目Top100を作成できませんでした。")

    top100_history = merge_history(
        existing_top100_history,
        top100,
        ["trade_date", "code"],
        ["trade_date", "rank", "code"],
    )
    picks_history = merge_history(
        existing_picks_history,
        daily_picks,
        ["trade_date", "code"],
        ["trade_date", "pick_rank", "code"],
    )
    followups = build_followups(
        picks_history,
        history,
        horizons=config.followup_days,
        existing=existing_followups,
    )
    backtest_summary = build_backtest_summary(followups)
    freshness = build_freshness_report(
        followups,
        trade_date=trade_date,
        candidate_count=len(candidates),
        feature_count=len(features),
        min_feature_coverage=config.min_feature_coverage,
    )

    generated_at = timestamp_now()
    run_id = make_run_id()
    metadata: dict[str, object] = {
        "app_version": current_version(),
        "run_id": run_id,
        "generated_at": generated_at,
        "trade_date": trade_date,
        "jpx": jpx_meta,
        "yahoo": yahoo_meta,
        "candidate_count": int(len(current_candidates)),
        "history_count": int(len(history)),
        "feature_count": int(len(features)),
        "feature_coverage": round(float(feature_coverage), 4),
        "top100_count": int(len(top100)),
        "daily_pick_count": int(len(daily_picks)),
        "followup_count": int(len(followups)),
        "backtest_summary_count": int(len(backtest_summary)),
        "download_errors": download_errors,
        "skipped_tickers": skipped,
        "freshness": freshness,
        "method": {
            "universe": "JPX東証普通株とYahoo日本株ランキングの共通銘柄",
            "price_source": "yfinance",
            "ranking": "モメンタム・トレンド・流動性・量能・リスクの百分位合成",
            "signal_date": "各銘柄の最新日足が揃った基準日",
            "execution_assumption": "シグナル日の翌営業日寄付から追跡",
        },
    }

    save_history(candidate_history, candidate_history_path)
    save_history(top100_history, top100_history_path)
    save_history(picks_history, picks_history_path)
    save_history(followups, followups_history_path)

    publish_outputs(
        {
            "jpx_universe.csv": jpx,
            "yahoo_candidates.csv": yahoo,
            "candidate_pool.csv": current_candidates,
            "top100.csv": top100,
            "daily_picks.csv": daily_picks,
            "followups.csv": followups,
            "backtest_summary.csv": backtest_summary,
        },
        metadata,
        processed_dir=config.processed_dir,
        snapshot_dir=config.snapshot_dir,
    )
    return PipelineResult(
        current_candidates,
        top100,
        daily_picks,
        followups,
        backtest_summary,
        freshness,
        metadata,
    )
