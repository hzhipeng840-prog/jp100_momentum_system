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
from .market_environment import build_market_environment
from .portfolio import build_virtual_portfolio
from .rule_evaluation import build_evaluation_bundle
from .rules import attach_evaluation_columns, evaluation_passthrough_columns
from .scoring import make_top100, select_daily_picks
from .sources import build_candidate_pool, load_jpx_list, load_yahoo_candidates
from .storage import make_run_id, publish_outputs, timestamp_now
from .trading_calendar import calendar_metadata
from .universe import (
    build_liquidity_universe,
    build_universe_comparison,
    build_universe_observations,
    build_version_comparison,
)
from .version import current_version


@dataclass
class PipelineResult:
    candidates: pd.DataFrame
    top100: pd.DataFrame
    daily_picks: pd.DataFrame
    followups: pd.DataFrame
    backtest_summary: pd.DataFrame
    evaluation_followups: pd.DataFrame
    rule_evaluation: pd.DataFrame
    factor_quantiles: pd.DataFrame
    factor_ic: pd.DataFrame
    factor_turnover: pd.DataFrame
    liquidity_universe: pd.DataFrame
    liquidity_top100: pd.DataFrame
    universe_comparison: pd.DataFrame
    version_comparison: pd.DataFrame
    portfolio_curve: pd.DataFrame
    portfolio_summary: pd.DataFrame
    virtual_positions: pd.DataFrame
    market_environment: pd.DataFrame
    risk_alerts: pd.DataFrame
    freshness: dict[str, object]
    metadata: dict[str, object]


class PriceDataDateMismatchError(RuntimeError):
    def __init__(self, expected_date: str, actual_date: str) -> None:
        self.expected_date = expected_date
        self.actual_date = actual_date
        super().__init__(
            "株価データの基準日が実行対象日と一致しません。"
            f" 期待日: {expected_date} / 取得日: {actual_date}"
        )


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
    evaluation_history_path = config.history_dir / "evaluation_observations.csv"
    evaluation_followups_path = config.history_dir / "evaluation_followups.csv"
    universe_history_path = config.history_dir / "universe_observations.csv"
    universe_followups_path = config.history_dir / "universe_followups.csv"
    environment_history_path = config.history_dir / "market_environment.csv"
    existing_candidate_history = load_history(candidate_history_path)
    existing_top100_history = load_history(top100_history_path)
    existing_picks_history = load_history(picks_history_path)
    existing_followups = load_history(followups_history_path)
    existing_evaluation_history = load_history(evaluation_history_path)
    existing_evaluation_followups = load_history(evaluation_followups_path)
    existing_universe_history = load_history(universe_history_path)
    existing_universe_followups = load_history(universe_followups_path)
    existing_environment_history = load_history(environment_history_path)

    liquidity_jpx = jpx[jpx["market"].isin(config.liquidity_scan_markets)].copy()
    requested_tickers = sorted(
        set(liquidity_jpx["ticker"].dropna().astype(str).tolist())
        | set(candidates["ticker"].dropna().astype(str).tolist())
        | set(recent_history_tickers(existing_picks_history))
        | set(recent_history_tickers(existing_top100_history))
        | set(recent_history_tickers(existing_evaluation_history))
        | set(recent_history_tickers(existing_universe_history))
        | {config.benchmark_ticker}
    )
    price_result = download_price_history(
        requested_tickers,
        period=config.history_period,
        batch_size=config.batch_size,
        cache_dir=config.raw_dir / "prices",
        incremental_period=config.incremental_history_period,
    )
    history, download_errors = price_result
    price_cache_stats = getattr(price_result, "stats", {})
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
    if config.expected_trade_date and trade_date != config.expected_trade_date:
        raise PriceDataDateMismatchError(config.expected_trade_date, trade_date)
    features = features[features["trade_date"].astype(str).eq(trade_date)].copy()
    jpx_tickers = set(jpx["ticker"].dropna().astype(str))
    jpx_features = all_features[
        all_features["ticker"].isin(jpx_tickers)
        & all_features["trade_date"].astype(str).eq(trade_date)
    ].copy()
    benchmark_history = history.get(config.benchmark_ticker)
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

    app_version = current_version()
    top100 = make_top100(current_candidates, features, config)
    top100 = attach_evaluation_columns(
        top100,
        config,
        evaluation_version=app_version,
    )
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
    evaluation_history = merge_history(
        existing_evaluation_history,
        top100,
        ["trade_date", "code", "evaluation_version"],
        ["trade_date", "evaluation_version", "rank", "code"],
    )
    liquidity_universe = build_liquidity_universe(
        liquidity_jpx,
        jpx_features,
        size=config.liquidity_universe_size,
        yahoo_codes=set(candidates["code"].astype(str)),
    )
    liquidity_metadata_columns = [
        "code",
        "ticker",
        "name",
        "market",
        "industry",
        "liquidity_rank",
        "in_yahoo_pool",
        "universe_source",
        "universe_label",
    ]
    liquidity_candidates = liquidity_universe[
        [
            column
            for column in liquidity_metadata_columns
            if column in liquidity_universe
        ]
    ].copy()
    if not liquidity_candidates.empty:
        liquidity_candidates = liquidity_candidates.merge(
            yahoo[
                [
                    "code",
                    "best_yahoo_rank",
                    "ranking_hits",
                    "ranking_sources",
                ]
            ],
            how="left",
            on="code",
        )
    liquidity_top100 = make_top100(
        liquidity_candidates,
        jpx_features,
        config,
    )
    liquidity_top100 = attach_evaluation_columns(
        liquidity_top100,
        config,
        evaluation_version=app_version,
    )
    current_universe_observations = build_universe_observations(
        top100,
        liquidity_top100,
        evaluation_version=app_version,
    )
    universe_history = merge_history(
        existing_universe_history,
        current_universe_observations,
        ["trade_date", "code", "evaluation_version", "universe_source"],
        ["trade_date", "evaluation_version", "universe_source", "rank", "code"],
    )
    followups = build_followups(
        picks_history,
        history,
        horizons=config.followup_days,
        existing=existing_followups,
        benchmark_history=benchmark_history,
        cost_scenarios_bps=config.cost_scenarios_bps,
    )
    evaluation_followups = build_followups(
        evaluation_history,
        history,
        horizons=config.followup_days,
        existing=existing_evaluation_followups,
        key_columns=("trade_date", "code", "evaluation_version"),
        passthrough_columns=evaluation_passthrough_columns(),
        benchmark_history=benchmark_history,
        cost_scenarios_bps=config.cost_scenarios_bps,
    )
    universe_followups = build_followups(
        universe_history,
        history,
        horizons=config.followup_days,
        existing=existing_universe_followups,
        key_columns=(
            "trade_date",
            "code",
            "evaluation_version",
            "universe_source",
        ),
        passthrough_columns=[
            *evaluation_passthrough_columns(),
            "universe_source",
            "universe_label",
            "liquidity_rank",
            "in_yahoo_pool",
        ],
        benchmark_history=benchmark_history,
        cost_scenarios_bps=config.cost_scenarios_bps,
    )
    evaluation = build_evaluation_bundle(
        evaluation_followups,
        quantiles=config.factor_quantiles,
        min_samples=config.evaluation_min_samples,
    )
    backtest_summary = build_backtest_summary(followups)
    universe_comparison = build_universe_comparison(
        universe_followups,
        horizons=config.followup_days,
        cost_bps=int(config.transaction_cost_bps),
    )
    version_comparison = build_version_comparison(
        evaluation_followups,
        horizons=config.followup_days,
        cost_bps=int(config.transaction_cost_bps),
    )
    portfolio = build_virtual_portfolio(
        picks_history,
        history,
        benchmark_history=benchmark_history,
        holding_days=config.portfolio_holding_days,
        cost_bps=config.transaction_cost_bps,
    )
    market_environment, risk_alerts = build_market_environment(
        benchmark_history,
        liquidity_universe,
        daily_picks,
        history,
        trade_date=trade_date,
        benchmark_ticker=config.benchmark_ticker,
    )
    environment_history = merge_history(
        existing_environment_history,
        market_environment,
        ["trade_date"],
        ["trade_date"],
    )
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
        "app_version": app_version,
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
        "evaluation_observation_count": int(len(evaluation_followups)),
        "rule_evaluation_count": int(len(evaluation.rule_evaluation)),
        "factor_quantile_count": int(len(evaluation.factor_quantiles)),
        "factor_ic_count": int(len(evaluation.factor_ic)),
        "factor_turnover_count": int(len(evaluation.factor_turnover)),
        "liquidity_universe_count": int(len(liquidity_universe)),
        "liquidity_top100_count": int(len(liquidity_top100)),
        "universe_comparison_count": int(len(universe_comparison)),
        "portfolio_observation_count": int(len(portfolio.curve)),
        "risk_alert_count": int(len(risk_alerts)),
        "download_errors": download_errors,
        "price_cache": price_cache_stats,
        "skipped_tickers": skipped,
        "freshness": freshness,
        "trading_calendar": calendar_metadata(trade_date),
        "method": {
            "universe": "JPX東証普通株とYahoo日本株ランキングの共通銘柄",
            "comparison_universe": (
                f"JPXの{'・'.join(config.liquidity_scan_markets)}普通株を"
                "20日平均売買代金で順位付けした"
                f"上位{config.liquidity_universe_size}銘柄"
            ),
            "price_source": "yfinance",
            "benchmark": f"TOPIX（yfinance: {config.benchmark_ticker}）",
            "ranking": "モメンタム・トレンド・流動性・量能・リスクの百分位合成",
            "signal_date": "各銘柄の最新日足が揃った基準日",
            "execution_assumption": "シグナル日の翌営業日寄付から追跡",
            "cost_assumption": (
                f"既定は片道{config.transaction_cost_bps:g}bp。"
                "0・10・25・50bpシナリオを併記"
            ),
            "portfolio": (
                f"翌営業日寄付で等金額建て、{config.portfolio_holding_days}"
                "営業日保有、日次コホート方式"
            ),
            "factor_evaluation": "日次横断五分位、Spearman IC、上位分位入替率、業種別集計",
            "rule_evaluation": "ルール通過群と未通過群の将来リターン差。自動最適化には使用しない",
        },
    }

    save_history(candidate_history, candidate_history_path)
    save_history(top100_history, top100_history_path)
    save_history(picks_history, picks_history_path)
    save_history(followups, followups_history_path)
    save_history(evaluation_history, evaluation_history_path)
    save_history(evaluation_followups, evaluation_followups_path)
    save_history(universe_history, universe_history_path)
    save_history(universe_followups, universe_followups_path)
    save_history(environment_history, environment_history_path)

    publish_outputs(
        {
            "jpx_universe.csv": jpx,
            "yahoo_candidates.csv": yahoo,
            "candidate_pool.csv": current_candidates,
            "top100.csv": top100,
            "daily_picks.csv": daily_picks,
            "followups.csv": followups,
            "backtest_summary.csv": backtest_summary,
            "evaluation_followups.csv": evaluation_followups,
            "rule_evaluation.csv": evaluation.rule_evaluation,
            "factor_quantile_evaluation.csv": evaluation.factor_quantiles,
            "factor_ic.csv": evaluation.factor_ic,
            "factor_turnover.csv": evaluation.factor_turnover,
            "jpx_liquidity_universe.csv": liquidity_universe,
            "jpx_liquidity_top100.csv": liquidity_top100,
            "universe_followups.csv": universe_followups,
            "universe_comparison.csv": universe_comparison,
            "version_comparison.csv": version_comparison,
            "portfolio_curve.csv": portfolio.curve,
            "portfolio_summary.csv": portfolio.summary,
            "virtual_positions.csv": portfolio.positions,
            "market_environment.csv": market_environment,
            "risk_alerts.csv": risk_alerts,
        },
        metadata,
        processed_dir=config.processed_dir,
        snapshot_dir=config.snapshot_dir,
    )
    return PipelineResult(
        candidates=current_candidates,
        top100=top100,
        daily_picks=daily_picks,
        followups=followups,
        backtest_summary=backtest_summary,
        evaluation_followups=evaluation_followups,
        rule_evaluation=evaluation.rule_evaluation,
        factor_quantiles=evaluation.factor_quantiles,
        factor_ic=evaluation.factor_ic,
        factor_turnover=evaluation.factor_turnover,
        liquidity_universe=liquidity_universe,
        liquidity_top100=liquidity_top100,
        universe_comparison=universe_comparison,
        version_comparison=version_comparison,
        portfolio_curve=portfolio.curve,
        portfolio_summary=portfolio.summary,
        virtual_positions=portfolio.positions,
        market_environment=market_environment,
        risk_alerts=risk_alerts,
        freshness=freshness,
        metadata=metadata,
    )
