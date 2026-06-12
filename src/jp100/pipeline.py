from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import PipelineConfig
from .market import build_feature_table, download_price_history
from .scoring import make_top100, select_daily_picks
from .sources import build_candidate_pool, load_jpx_list, load_yahoo_candidates
from .storage import save_frame, save_metadata, timestamp_now


@dataclass
class PipelineResult:
    candidates: pd.DataFrame
    top100: pd.DataFrame
    daily_picks: pd.DataFrame
    metadata: dict[str, object]


def run_pipeline(config: PipelineConfig | None = None) -> PipelineResult:
    config = config or PipelineConfig()
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    config.processed_dir.mkdir(parents=True, exist_ok=True)

    jpx, jpx_meta = load_jpx_list(config)
    yahoo, yahoo_meta = load_yahoo_candidates(config)
    candidates = build_candidate_pool(jpx, yahoo)
    if candidates.empty:
        raise RuntimeError("JPX銘柄一覧とYahooランキングに共通する銘柄がありません。")

    history, download_errors = download_price_history(
        candidates["ticker"].tolist(),
        period=config.history_period,
        batch_size=config.batch_size,
    )
    features, skipped = build_feature_table(history)
    if features.empty:
        detail = f" 取得エラー: {' / '.join(download_errors[:2])}" if download_errors else ""
        raise RuntimeError(
            "yfinanceから有効な価格履歴を取得できませんでした。" + detail
        )
    top100 = make_top100(candidates, features, config)
    daily_picks = select_daily_picks(top100, config)
    if top100.empty:
        raise RuntimeError("有効な価格履歴がなく、注目Top100を作成できませんでした。")

    metadata: dict[str, object] = {
        "generated_at": timestamp_now(),
        "trade_date": str(top100["trade_date"].max()),
        "jpx": jpx_meta,
        "yahoo": yahoo_meta,
        "candidate_count": int(len(candidates)),
        "history_count": int(len(history)),
        "feature_count": int(len(features)),
        "top100_count": int(len(top100)),
        "daily_pick_count": int(len(daily_picks)),
        "download_errors": download_errors,
        "skipped_tickers": skipped,
        "method": {
            "universe": "JPX東証普通株とYahoo日本株ランキングの共通銘柄",
            "price_source": "yfinance",
            "ranking": "モメンタム・トレンド・流動性・量能・リスクの百分位合成",
        },
    }

    save_frame(candidates, config.processed_dir / "candidate_pool.csv")
    save_frame(top100, config.processed_dir / "top100.csv")
    save_frame(daily_picks, config.processed_dir / "daily_picks.csv")
    save_metadata(metadata, config.processed_dir / "metadata.json")
    return PipelineResult(candidates, top100, daily_picks, metadata)
