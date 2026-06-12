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


if __name__ == "__main__":
    unittest.main()
