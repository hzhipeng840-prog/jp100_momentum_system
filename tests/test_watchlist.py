from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.watchlist import (
    add_watchlist_entry,
    load_watchlist,
    remove_watchlist_entries,
    save_watchlist,
)


class WatchlistTest(unittest.TestCase):
    def test_watchlist_roundtrip(self) -> None:
        path = Path.cwd() / ".test-tmp" / uuid.uuid4().hex / "watchlist.csv"
        current = load_watchlist(path)
        current = add_watchlist_entry(
            current,
            code="7203",
            name="トヨタ自動車",
            note="決算確認",
            added_at="2026-06-15T10:00:00+09:00",
        )
        save_watchlist(current, path)
        loaded = load_watchlist(path)
        self.assertEqual(loaded.iloc[0]["code"], "7203")
        self.assertEqual(loaded.iloc[0]["note"], "決算確認")
        removed = remove_watchlist_entries(loaded, ["7203"])
        self.assertTrue(removed.empty)


if __name__ == "__main__":
    unittest.main()
