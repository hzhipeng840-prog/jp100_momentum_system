from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.universe import (
    build_liquidity_universe,
    build_universe_comparison,
    build_version_comparison,
)


class UniverseTest(unittest.TestCase):
    def test_liquidity_universe_and_comparisons(self) -> None:
        jpx = pd.DataFrame(
            [
                {
                    "code": str(1000 + index),
                    "ticker": f"{1000 + index}.T",
                    "name": f"銘柄{index}",
                    "market": "プライム",
                    "industry": "業種",
                }
                for index in range(3)
            ]
        )
        features = pd.DataFrame(
            [
                {
                    "ticker": f"{1000 + index}.T",
                    "trade_date": "2026-06-10",
                    "avg_turnover_20d": turnover,
                    "return_20d": 0.1,
                    "return_60d": 0.2,
                }
                for index, turnover in enumerate((100, 300, 200))
            ]
        )
        liquidity = build_liquidity_universe(
            jpx,
            features,
            size=2,
            yahoo_codes={"1000"},
        )
        self.assertEqual(liquidity["code"].tolist(), ["1001", "1002"])

        followups = pd.DataFrame(
            [
                {
                    "evaluation_version": version,
                    "universe_source": source,
                    "universe_label": label,
                    "rank": rank,
                    "settled_5d": True,
                    "open_buy_return_5d": value,
                    "open_buy_excess_return_5d": value - 0.01,
                    "net_open_buy_return_5d_10bps": value - 0.002,
                }
                for version, source, label, rank, value in (
                    ("v2", "yahoo", "Yahooランキング", 1, 0.03),
                    ("v3", "jpx_liquidity", "JPX流動性", 2, 0.04),
                )
            ]
            + [
                {
                    "evaluation_version": "v2",
                    "universe_source": "yahoo",
                    "universe_label": "Yahooランキング",
                    "rank": 3,
                    "settled_5d": "False",
                    "open_buy_return_5d": 1.0,
                    "open_buy_excess_return_5d": 1.0,
                    "net_open_buy_return_5d_10bps": 1.0,
                }
            ]
        )
        universe = build_universe_comparison(followups, horizons=(5,))
        versions = build_version_comparison(followups, horizons=(5,))
        self.assertEqual(len(universe), 2)
        self.assertEqual(set(versions["evaluation_version"]), {"v2", "v3"})
        yahoo = universe[universe["universe_source"].eq("yahoo")].iloc[0]
        self.assertEqual(int(yahoo["valid_count"]), 1)


if __name__ == "__main__":
    unittest.main()
