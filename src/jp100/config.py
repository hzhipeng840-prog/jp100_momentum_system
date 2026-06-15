from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
HISTORY_DIR = DATA_DIR / "history"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
USER_DIR = DATA_DIR / "user"

JPX_LIST_PAGE = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
JPX_LIST_FALLBACK = (
    "https://www.jpx.co.jp/markets/statistics-equities/misc/"
    "tvdivq0000001vg2-att/data_j.xls"
)

YAHOO_RANKINGS = {
    "値上がり率": "up",
    "出来高": "volume",
    "出来高増加率": "volumeIncrease",
}


@dataclass(frozen=True)
class PipelineConfig:
    yahoo_pages: int = 3
    history_period: str = "1y"
    incremental_history_period: str = "10d"
    expected_trade_date: str | None = None
    top_count: int = 100
    daily_count: int = 5
    batch_size: int = 80
    request_timeout: int = 20
    min_price: float = 300.0
    min_turnover_20d: float = 50_000_000.0
    min_feature_coverage: float = 0.60
    followup_days: tuple[int, ...] = (1, 3, 5, 10)
    factor_quantiles: int = 5
    evaluation_min_samples: int = 30
    benchmark_ticker: str = "^TOPX"
    liquidity_universe_size: int = 600
    liquidity_scan_markets: tuple[str, ...] = ("プライム",)
    portfolio_holding_days: int = 5
    transaction_cost_bps: float = 10.0
    cost_scenarios_bps: tuple[int, ...] = (0, 10, 25, 50)
    allowed_markets: tuple[str, ...] = ("プライム", "スタンダード", "グロース")
    raw_dir: Path = field(default=RAW_DIR)
    processed_dir: Path = field(default=PROCESSED_DIR)
    history_dir: Path = field(default=HISTORY_DIR)
    snapshot_dir: Path = field(default=SNAPSHOT_DIR)

    def __post_init__(self) -> None:
        if not 1 <= self.yahoo_pages <= 5:
            raise ValueError("Yahooランキングの取得ページ数は1～5で指定してください。")
        if self.expected_trade_date is not None:
            try:
                date.fromisoformat(self.expected_trade_date)
            except ValueError as exc:
                raise ValueError(
                    "expected_trade_dateはYYYY-MM-DD形式で指定してください。"
                ) from exc
        if not 3 <= self.daily_count <= 5:
            raise ValueError("毎日厳選の銘柄数は3～5で指定してください。")
        if self.top_count < self.daily_count:
            raise ValueError("Top件数は毎日厳選の銘柄数以上にしてください。")
        if not 0 < self.min_feature_coverage <= 1:
            raise ValueError("価格データの最低取得率は0より大きく1以下で指定してください。")
        if not self.followup_days or any(day <= 0 for day in self.followup_days):
            raise ValueError("追跡日数は1以上で指定してください。")
        if not 2 <= self.factor_quantiles <= 10:
            raise ValueError("因子分位数は2～10で指定してください。")
        if self.evaluation_min_samples < 10:
            raise ValueError("評価の最低サンプル数は10以上で指定してください。")
        if self.liquidity_universe_size < self.top_count:
            raise ValueError("流動性ユニバース件数はTop件数以上にしてください。")
        if not self.liquidity_scan_markets:
            raise ValueError("流動性ユニバースの市場区分を指定してください。")
        if self.portfolio_holding_days <= 0:
            raise ValueError("仮想ポートフォリオの保有日数は1以上で指定してください。")
        if self.transaction_cost_bps < 0:
            raise ValueError("取引コストは0以上で指定してください。")
        if not self.cost_scenarios_bps or any(
            cost < 0 for cost in self.cost_scenarios_bps
        ):
            raise ValueError("コストシナリオは0以上で指定してください。")
