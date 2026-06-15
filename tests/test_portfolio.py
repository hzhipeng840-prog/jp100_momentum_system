from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.portfolio import build_virtual_portfolio


def prices(start: float) -> pd.DataFrame:
    dates = pd.bdate_range("2026-06-01", periods=8)
    close = pd.Series(np.linspace(start, start * 1.08, len(dates)), index=dates)
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Adj Close": close,
            "Volume": 1000,
        },
        index=dates,
    )


class PortfolioTest(unittest.TestCase):
    def test_build_virtual_portfolio_creates_costed_curve(self) -> None:
        picks = pd.DataFrame(
            [
                {
                    "trade_date": "2026-06-01",
                    "code": "1000",
                    "ticker": "1000.T",
                    "name": "銘柄A",
                    "industry": "業種A",
                    "pick_rank": 1,
                },
                {
                    "trade_date": "2026-06-02",
                    "code": "1001",
                    "ticker": "1001.T",
                    "name": "銘柄B",
                    "industry": "業種B",
                    "pick_rank": 1,
                },
            ]
        )
        result = build_virtual_portfolio(
            picks,
            {
                "1000.T": prices(100),
                "1001.T": prices(200),
            },
            benchmark_history=prices(1000),
            holding_days=3,
            cost_bps=10,
        )

        self.assertFalse(result.curve.empty)
        self.assertFalse(result.summary.empty)
        self.assertIn("benchmark_equity", result.curve)
        self.assertGreater(float(result.summary.iloc[0]["total_return"]), 0)
        self.assertEqual(float(result.summary.iloc[0]["cost_bps_one_way"]), 10)


if __name__ == "__main__":
    unittest.main()
