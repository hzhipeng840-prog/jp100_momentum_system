from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.rule_evaluation import build_evaluation_bundle


def evaluation_rows() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trade_date, top_ticker in (
        ("2026-06-10", "1004.T"),
        ("2026-06-11", "1003.T"),
    ):
        for index in range(5):
            ticker = f"{1000 + index}.T"
            score = float(index + 1)
            if trade_date == "2026-06-11" and ticker == top_ticker:
                score = 6.0
            rows.append(
                {
                    "trade_date": trade_date,
                    "code": str(1000 + index),
                    "ticker": ticker,
                    "industry": "業種A" if index < 3 else "業種B",
                    "market": "プライム",
                    "evaluation_version": "v2",
                    "score": score,
                    "rule_above_ma20": index >= 2,
                    "return_5d": score / 100,
                    "settled_5d": True,
                }
            )
    return pd.DataFrame(rows)


class RuleEvaluationTest(unittest.TestCase):
    def test_factor_quantile_ic_turnover_and_rule_spread(self) -> None:
        result = build_evaluation_bundle(
            evaluation_rows(),
            quantiles=5,
            min_samples=1,
        )

        quantiles = result.factor_quantiles[
            result.factor_quantiles["factor_key"].eq("score")
            & result.factor_quantiles["group_name"].eq("全体")
            & result.factor_quantiles["horizon"].eq("5d")
        ]
        self.assertEqual(set(quantiles["quantile"]), {1, 2, 3, 4, 5})
        self.assertGreater(
            float(quantiles["top_bottom_spread"].dropna().iloc[0]),
            0,
        )

        ic = result.factor_ic[
            result.factor_ic["factor_key"].eq("score")
            & result.factor_ic["group_name"].eq("全体")
            & result.factor_ic["horizon"].eq("5d")
        ].iloc[0]
        self.assertEqual(int(ic["ic_count"]), 2)
        self.assertAlmostEqual(float(ic["mean_ic"]), 1.0)

        turnover = result.factor_turnover[
            result.factor_turnover["factor_key"].eq("score")
        ].iloc[0]
        self.assertEqual(int(turnover["transition_count"]), 1)
        self.assertAlmostEqual(float(turnover["latest_turnover"]), 1.0)

        rule = result.rule_evaluation[
            result.rule_evaluation["rule_key"].eq("rule_above_ma20")
            & result.rule_evaluation["group_name"].eq("全体")
            & result.rule_evaluation["horizon"].eq("5d")
        ].iloc[0]
        self.assertGreater(float(rule["return_spread"]), 0)
        self.assertEqual(rule["status"], "評価可能")


if __name__ == "__main__":
    unittest.main()
