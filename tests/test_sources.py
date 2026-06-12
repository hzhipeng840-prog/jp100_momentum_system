from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.sources import build_candidate_pool, parse_yahoo_ranking


class YahooParserTest(unittest.TestCase):
    def test_parse_quote_links_and_rank(self) -> None:
        html = """
        <html><body>
          <a href="/quote/7203.T">トヨタ自動車(株)</a>
          <a href="/quote/6758.T">ソニーグループ(株)</a>
          <a href="/quote/7203.T">重複リンク</a>
        </body></html>
        """
        result = parse_yahoo_ranking(html, "出来高", page=2)
        self.assertEqual(result["code"].tolist(), ["7203", "6758"])
        self.assertEqual(result["rank"].tolist(), [51, 52])

    def test_candidate_pool_keeps_jpx_common_stocks(self) -> None:
        jpx = pd.DataFrame(
            [
                {
                    "code": "7203",
                    "name": "トヨタ自動車",
                    "market": "プライム",
                    "industry": "輸送用機器",
                    "ticker": "7203.T",
                },
                {
                    "code": "9999",
                    "name": "対象外",
                    "market": "スタンダード",
                    "industry": "小売業",
                    "ticker": "9999.T",
                },
            ]
        )
        yahoo = pd.DataFrame(
            [
                {
                    "code": "7203",
                    "yahoo_name": "トヨタ自動車(株)",
                    "best_yahoo_rank": 2,
                    "ranking_hits": 2,
                    "ranking_sources": "出来高・値上がり率",
                },
                {
                    "code": "6758",
                    "yahoo_name": "ソニーグループ(株)",
                    "best_yahoo_rank": 1,
                    "ranking_hits": 1,
                    "ranking_sources": "出来高",
                },
            ]
        )
        result = build_candidate_pool(jpx, yahoo)
        self.assertEqual(result["code"].tolist(), ["7203"])


if __name__ == "__main__":
    unittest.main()

