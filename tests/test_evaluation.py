from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.backtest import build_backtest_summary
from jp100.freshness import build_freshness_report


class EvaluationTest(unittest.TestCase):
    def test_freshness_requires_price_coverage_and_settlement(self) -> None:
        followups = pd.DataFrame(
            [
                {"trade_date": "2026-06-10", "settled_1d": True},
                {"trade_date": "2026-06-10", "settled_1d": True},
                {"trade_date": "2026-06-11", "settled_1d": False},
            ]
        )

        result = build_freshness_report(
            followups,
            trade_date="2026-06-11",
            candidate_count=100,
            feature_count=90,
        )

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["settlement_date"], "2026-06-10")
        self.assertEqual(result["settled_1d_ratio"], 1.0)

    def test_backtest_summary_counts_only_settled_values(self) -> None:
        followups = pd.DataFrame(
            [
                {
                    "trade_date": "2026-06-09",
                    "code": "7203",
                    "market": "プライム",
                    "industry": "輸送用機器",
                    "best_yahoo_rank": 5,
                    "return_1d": 0.04,
                    "settled_1d": True,
                },
                {
                    "trade_date": "2026-06-10",
                    "code": "6758",
                    "market": "プライム",
                    "industry": "電気機器",
                    "best_yahoo_rank": 20,
                    "return_1d": None,
                    "settled_1d": False,
                },
            ]
        )

        result = build_backtest_summary(followups)
        row = result[
            result["group_name"].eq("全体")
            & result["metric_key"].eq("1d")
        ].iloc[0]

        self.assertEqual(int(row["sample_count"]), 2)
        self.assertEqual(int(row["valid_count"]), 1)
        self.assertAlmostEqual(float(row["avg_return"]), 0.04)
        self.assertAlmostEqual(float(row["win_rate"]), 1.0)


if __name__ == "__main__":
    unittest.main()
