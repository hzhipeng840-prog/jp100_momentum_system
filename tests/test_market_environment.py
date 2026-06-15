from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.market_environment import build_market_environment


def history() -> pd.DataFrame:
    dates = pd.bdate_range("2025-12-01", periods=130)
    close = pd.Series(np.linspace(100, 140, len(dates)), index=dates)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Adj Close": close,
            "Volume": 100_000,
        },
        index=dates,
    )


class MarketEnvironmentTest(unittest.TestCase):
    def test_build_market_environment(self) -> None:
        liquidity = pd.DataFrame(
            [
                {"return_20d": 0.1, "distance_ma60": 0.1},
                {"return_20d": 0.2, "distance_ma60": 0.2},
            ]
        )
        picks = pd.DataFrame(
            [
                {
                    "ticker": "1000.T",
                    "industry": "業種A",
                    "volatility_20d": 0.2,
                },
                {
                    "ticker": "1001.T",
                    "industry": "業種B",
                    "volatility_20d": 0.2,
                },
            ]
        )
        environment, alerts = build_market_environment(
            history(),
            liquidity,
            picks,
            {"1000.T": history(), "1001.T": history()},
            trade_date="2026-05-29",
            benchmark_ticker="^TOPX",
        )

        self.assertEqual(environment.iloc[0]["market_regime"], "中立")
        self.assertEqual(float(environment.iloc[0]["breadth_above_ma60"]), 1.0)
        self.assertFalse(alerts.empty)


if __name__ == "__main__":
    unittest.main()
