from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.config import PipelineConfig
from jp100.scoring import make_top100, select_daily_picks


def make_rows(count: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates: list[dict[str, object]] = []
    features: list[dict[str, object]] = []
    for index in range(count):
        code = f"{1000 + index}"
        ticker = f"{code}.T"
        candidates.append(
            {
                "code": code,
                "ticker": ticker,
                "name": f"銘柄{index}",
                "market": "プライム",
                "industry": f"業種{index % 6}",
                "best_yahoo_rank": index + 1,
                "ranking_hits": 2,
                "ranking_sources": "出来高・値上がり率",
                "candidate_score": 300 - index,
            }
        )
        strength = count - index
        features.append(
            {
                "ticker": ticker,
                "trade_date": "2026-06-11",
                "close": 1000 + strength * 10,
                "return_1d": 0.01,
                "return_5d": strength * 0.005,
                "return_20d": strength * 0.012,
                "return_60d": strength * 0.02,
                "return_120d": strength * 0.03,
                "ma20": 1000.0,
                "ma60": 950.0,
                "distance_ma20": strength * 0.005,
                "distance_ma60": strength * 0.007,
                "distance_high_120d": -index * 0.005,
                "volatility_20d": 0.15 + index * 0.01,
                "latest_volume": 300_000,
                "avg_volume_20d": 200_000,
                "volume_ratio_20d": 1.5,
                "avg_turnover_20d": 200_000_000 + strength * 1_000_000,
                "history_days": 240,
            }
        )
    return pd.DataFrame(candidates), pd.DataFrame(features)


class ScoringTest(unittest.TestCase):
    def test_make_top_and_daily_picks(self) -> None:
        candidates, features = make_rows()
        config = PipelineConfig(top_count=10, daily_count=5)
        top = make_top100(candidates, features, config)
        picks = select_daily_picks(top, config)
        self.assertEqual(len(top), 10)
        self.assertEqual(top.iloc[0]["code"], "1000")
        self.assertGreaterEqual(len(picks), 3)
        self.assertLessEqual(len(picks), 5)
        self.assertIn("selection_reason", picks.columns)


if __name__ == "__main__":
    unittest.main()
