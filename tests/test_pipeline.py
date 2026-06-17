from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.config import PipelineConfig
from jp100.pipeline import run_pipeline


def market_history(offset: float) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-06-11", periods=130)
    close = pd.Series(
        np.linspace(1000 + offset, 1300 + offset, len(dates)),
        index=dates,
    )
    return pd.DataFrame(
        {
            "Open": close - 2,
            "High": close + 8,
            "Low": close - 8,
            "Close": close,
            "Adj Close": close,
            "Volume": np.linspace(100_000, 180_000, len(dates)),
        },
        index=dates,
    )


class PipelineIntegrationTest(unittest.TestCase):
    @patch("jp100.pipeline.load_yahoo_candidates")
    @patch("jp100.pipeline.load_jpx_list")
    @patch("jp100.pipeline.download_price_history")
    def test_pipeline_publishes_consistent_snapshot(
        self,
        mock_download,
        mock_load_jpx,
        mock_load_yahoo,
    ) -> None:
        root = Path.cwd() / ".test-tmp" / uuid.uuid4().hex
        codes = ["7203", "6758", "9984"]
        jpx = pd.DataFrame(
            [
                {
                    "code": code,
                    "name": f"銘柄{index}",
                    "market": "プライム",
                    "industry": f"業種{index}",
                    "ticker": f"{code}.T",
                }
                for index, code in enumerate(codes, start=1)
            ]
        )
        yahoo = pd.DataFrame(
            [
                {
                    "code": code,
                    "yahoo_name": f"銘柄{index}",
                    "best_yahoo_rank": index,
                    "ranking_hits": 2,
                    "ranking_sources": "出来高・値上がり率",
                }
                for index, code in enumerate(codes, start=1)
            ]
        )
        mock_load_jpx.return_value = (jpx, {"source": "unit-test", "count": 3})
        mock_load_yahoo.return_value = (
            yahoo,
            {"source": "unit-test", "count": 3},
        )
        mock_download.return_value = (
            {
                "7203.T": market_history(30),
                "6758.T": market_history(20),
                "9984.T": market_history(10),
            },
            [],
        )
        config = PipelineConfig(
            yahoo_pages=1,
            top_count=3,
            daily_count=3,
            min_feature_coverage=1.0,
            expected_trade_date="2026-06-11",
            raw_dir=root / "raw",
            processed_dir=root / "processed",
            history_dir=root / "history",
            snapshot_dir=root / "snapshots",
        )

        result = run_pipeline(config)

        self.assertEqual(result.metadata["trade_date"], "2026-06-11")
        self.assertEqual(result.metadata["app_version"], "v6")
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(len(result.top100), 3)
        self.assertEqual(len(result.daily_picks), 3)
        self.assertTrue((config.processed_dir / "latest.json").exists())
        run_dir = (
            config.snapshot_dir
            / "2026-06-11"
            / str(result.metadata["run_id"])
        )
        self.assertTrue((run_dir / "top100.csv").exists())
        self.assertTrue((run_dir / "followups.csv").exists())
        self.assertTrue((run_dir / "rule_evaluation.csv").exists())
        self.assertTrue((run_dir / "factor_quantile_evaluation.csv").exists())
        self.assertTrue((run_dir / "jpx_liquidity_top100.csv").exists())
        self.assertTrue((run_dir / "version_comparison.csv").exists())
        self.assertTrue((run_dir / "portfolio_summary.csv").exists())
        self.assertTrue((run_dir / "market_environment.csv").exists())
        self.assertTrue(
            (config.history_dir / "daily_picks_history.csv").exists()
        )
        self.assertTrue(
            (config.history_dir / "evaluation_observations.csv").exists()
        )


if __name__ == "__main__":
    unittest.main()
