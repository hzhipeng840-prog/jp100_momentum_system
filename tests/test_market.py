from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.market import calculate_features, split_downloaded_history


class MarketFeatureTest(unittest.TestCase):
    def test_split_ticker_first_multiindex(self) -> None:
        dates = pd.date_range("2025-01-01", periods=3)
        columns = pd.MultiIndex.from_product(
            [["7203.T", "6758.T"], ["Close", "Volume"]]
        )
        downloaded = pd.DataFrame(
            np.arange(12).reshape(3, 4), index=dates, columns=columns
        )
        result = split_downloaded_history(downloaded, ["7203.T", "6758.T"])
        self.assertEqual(set(result), {"7203.T", "6758.T"})
        self.assertEqual(list(result["7203.T"].columns), ["Close", "Volume"])

    def test_calculate_features(self) -> None:
        dates = pd.bdate_range("2025-01-01", periods=130)
        close = pd.Series(np.linspace(1000, 1400, len(dates)), index=dates)
        frame = pd.DataFrame(
            {
                "Open": close - 5,
                "High": close + 10,
                "Low": close - 10,
                "Close": close,
                "Adj Close": close,
                "Volume": np.linspace(100_000, 200_000, len(dates)),
            },
            index=dates,
        )
        result = calculate_features("7203.T", frame)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreater(result["return_20d"], 0)
        self.assertGreater(result["distance_ma20"], 0)
        self.assertGreater(result["avg_turnover_20d"], 0)

    def test_volume_ratio_uses_previous_twenty_days(self) -> None:
        dates = pd.bdate_range("2025-01-01", periods=80)
        close = pd.Series(np.linspace(1000, 1200, len(dates)), index=dates)
        volume = np.full(len(dates), 100_000.0)
        volume[-1] = 200_000.0
        frame = pd.DataFrame(
            {
                "Open": close,
                "High": close + 5,
                "Low": close - 5,
                "Close": close,
                "Adj Close": close,
                "Volume": volume,
            },
            index=dates,
        )

        result = calculate_features("7203.T", frame)

        assert result is not None
        self.assertEqual(result["avg_volume_20d"], 100_000.0)
        self.assertEqual(result["volume_ratio_20d"], 2.0)


if __name__ == "__main__":
    unittest.main()
