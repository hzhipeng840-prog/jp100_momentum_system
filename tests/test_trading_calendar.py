from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.trading_calendar import (
    are_consecutive_tse_sessions,
    is_tse_session,
    next_tse_session,
    previous_tse_session,
)


class TradingCalendarTest(unittest.TestCase):
    def test_xtks_holidays_and_adjacent_sessions(self) -> None:
        self.assertFalse(is_tse_session("2026-01-01"))
        self.assertTrue(is_tse_session("2026-01-05"))
        self.assertEqual(previous_tse_session("2026-01-06"), "2026-01-05")
        self.assertEqual(next_tse_session("2026-01-05"), "2026-01-06")
        self.assertTrue(
            are_consecutive_tse_sessions("2026-01-05", "2026-01-06")
        )
        self.assertFalse(
            are_consecutive_tse_sessions("2026-01-05", "2026-01-07")
        )


if __name__ == "__main__":
    unittest.main()
