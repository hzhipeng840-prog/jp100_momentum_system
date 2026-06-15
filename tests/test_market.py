from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.market import (
    calculate_features,
    download_price_history,
    split_downloaded_history,
)


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

    @patch("jp100.market._download_batch")
    def test_price_cache_switches_to_incremental_download(
        self,
        mock_download,
    ) -> None:
        cache_dir = Path.cwd() / ".test-tmp" / uuid.uuid4().hex / "prices"
        dates = pd.bdate_range("2026-01-05", periods=70)
        initial = pd.DataFrame(
            {
                "Close": np.linspace(1000, 1100, len(dates)),
                "Adj Close": np.linspace(1000, 1100, len(dates)),
                "Volume": 100_000,
            },
            index=dates,
        )
        mock_download.return_value = {"7203.T": initial}

        first = download_price_history(
            ["7203.T"],
            cache_dir=cache_dir,
            period="1y",
            incremental_period="10d",
        )

        self.assertEqual(first.stats["bootstrap_count"], 1)
        self.assertEqual(mock_download.call_args.args[1], "1y")
        self.assertEqual(len(list(cache_dir.glob("*.csv"))), 1)

        latest_date = dates[-1] + pd.offsets.BDay(1)
        incremental = initial.tail(3).copy()
        incremental.loc[latest_date] = {
            "Close": 1110,
            "Adj Close": 1110,
            "Volume": 120_000,
        }
        mock_download.reset_mock()
        mock_download.return_value = {"7203.T": incremental}

        second = download_price_history(
            ["7203.T"],
            cache_dir=cache_dir,
            period="1y",
            incremental_period="10d",
        )

        self.assertEqual(second.stats["cache_hit_count"], 1)
        self.assertEqual(second.stats["incremental_count"], 1)
        self.assertEqual(mock_download.call_args.args[1], "10d")
        self.assertEqual(second.history["7203.T"].index[-1], latest_date)


if __name__ == "__main__":
    unittest.main()
