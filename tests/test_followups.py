from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.followups import build_followups, calculate_followup


def price_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100, 105, 108, 111],
            "High": [102, 110, 112, 115],
            "Low": [98, 103, 106, 109],
            "Close": [100, 108, 110, 114],
            "Volume": [1000, 1200, 1300, 1400],
        },
        index=pd.to_datetime(
            ["2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11"]
        ),
    )


class FollowupTest(unittest.TestCase):
    def test_calculate_followup_uses_next_trading_row(self) -> None:
        row = pd.Series(
            {
                "trade_date": "2026-06-08",
                "code": "7203",
                "ticker": "7203.T",
                "close": 100,
            }
        )

        result = calculate_followup(row, price_frame(), horizons=(1, 3, 5))

        self.assertEqual(result["next_open_date"], "2026-06-09")
        self.assertAlmostEqual(float(result["next_open_gap"]), 0.05)
        self.assertAlmostEqual(float(result["return_1d"]), 0.08)
        self.assertAlmostEqual(float(result["return_3d"]), 0.14)
        self.assertTrue(bool(result["settled_3d"]))
        self.assertFalse(bool(result["settled_5d"]))

    def test_followup_uses_adjusted_prices_benchmark_and_costs(self) -> None:
        dates = pd.to_datetime(["2026-06-08", "2026-06-09"])
        stock = pd.DataFrame(
            {
                "Open": [98, 51],
                "High": [102, 53],
                "Low": [97, 50],
                "Close": [100, 52],
                "Adj Close": [50, 52],
                "Volume": [1000, 1200],
            },
            index=dates,
        )
        benchmark = pd.DataFrame(
            {
                "Open": [200, 201],
                "High": [201, 204],
                "Low": [199, 200],
                "Close": [200, 202],
                "Adj Close": [200, 202],
                "Volume": [1000, 1000],
            },
            index=dates,
        )
        row = pd.Series(
            {
                "trade_date": "2026-06-08",
                "code": "1000",
                "ticker": "1000.T",
                "close": 100,
            }
        )

        result = calculate_followup(
            row,
            stock,
            horizons=(1,),
            benchmark_history=benchmark,
            cost_scenarios_bps=(10,),
        )

        self.assertAlmostEqual(float(result["signal_adjusted_close"]), 50)
        self.assertAlmostEqual(float(result["return_1d"]), 0.04)
        expected_open_return = 52 / 51 - 1
        expected_benchmark = 202 / 201 - 1
        self.assertAlmostEqual(
            float(result["open_buy_excess_return_1d"]),
            expected_open_return - expected_benchmark,
        )
        self.assertAlmostEqual(
            float(result["net_open_buy_return_1d_10bps"]),
            (1 + expected_open_return) * 0.999 * 0.999 - 1,
        )

    def test_existing_settled_result_does_not_regress(self) -> None:
        picks = pd.DataFrame(
            [
                {
                    "trade_date": "2026-06-08",
                    "code": "7203",
                    "ticker": "7203.T",
                    "name": "トヨタ自動車",
                    "close": 100,
                    "pick_rank": 1,
                }
            ]
        )
        existing = pd.DataFrame(
            [
                {
                    "trade_date": "2026-06-08",
                    "code": "7203",
                    "ticker": "7203.T",
                    "settled_5d": True,
                    "return_5d": 0.20,
                    "observed_days": 5,
                }
            ]
        )

        result = build_followups(
            picks,
            {"7203.T": price_frame()},
            horizons=(1, 5),
            existing=existing,
        )
        row = result.iloc[0]

        self.assertTrue(bool(row["settled_5d"]))
        self.assertAlmostEqual(float(row["return_5d"]), 0.20)
        self.assertEqual(int(row["observed_days"]), 5)

    def test_custom_key_keeps_evaluation_versions_separate(self) -> None:
        observations = pd.DataFrame(
            [
                {
                    "trade_date": "2026-06-08",
                    "code": "7203",
                    "ticker": "7203.T",
                    "close": 100,
                    "rank": 1,
                    "evaluation_version": version,
                    "score": score,
                }
                for version, score in (("v1", 60), ("v2", 70))
            ]
        )

        result = build_followups(
            observations,
            {"7203.T": price_frame()},
            horizons=(1,),
            key_columns=("trade_date", "code", "evaluation_version"),
            passthrough_columns=["evaluation_version", "score", "rank"],
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(set(result["evaluation_version"]), {"v1", "v2"})


if __name__ == "__main__":
    unittest.main()
