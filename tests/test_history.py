from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.history import add_candidate_appearance_stats, merge_history


class CandidateHistoryTest(unittest.TestCase):
    def test_appearance_and_rank_change_follow_snapshot_order(self) -> None:
        history = pd.DataFrame(
            [
                {
                    "snapshot_date": "2026-06-10",
                    "code": "7203",
                    "best_yahoo_rank": 30,
                },
                {
                    "snapshot_date": "2026-06-11",
                    "code": "7203",
                    "best_yahoo_rank": 12,
                },
                {
                    "snapshot_date": "2026-06-11",
                    "code": "6758",
                    "best_yahoo_rank": 5,
                },
            ]
        )

        result = add_candidate_appearance_stats(history)
        latest = result[
            result["snapshot_date"].eq("2026-06-11")
            & result["code"].eq("7203")
        ].iloc[0]

        self.assertEqual(int(latest["appearance_count"]), 2)
        self.assertEqual(int(latest["consecutive_appearances"]), 2)
        self.assertEqual(float(latest["previous_yahoo_rank"]), 30.0)
        self.assertEqual(float(latest["yahoo_rank_change"]), 18.0)

    def test_merge_history_replaces_same_date_and_code(self) -> None:
        existing = pd.DataFrame(
            [{"snapshot_date": "2026-06-11", "code": "7203", "best_yahoo_rank": 20}]
        )
        current = pd.DataFrame(
            [{"snapshot_date": "2026-06-11", "code": "7203", "best_yahoo_rank": 8}]
        )

        result = merge_history(
            existing,
            current,
            ["snapshot_date", "code"],
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(int(result.iloc[0]["best_yahoo_rank"]), 8)


if __name__ == "__main__":
    unittest.main()
