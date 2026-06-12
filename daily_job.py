from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from jp100.config import PipelineConfig  # noqa: E402
from jp100.pipeline import run_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="日株モメンタム100の日次データを生成します。"
    )
    parser.add_argument(
        "--yahoo-pages",
        type=int,
        default=3,
        choices=range(1, 6),
        metavar="1-5",
        help="各Yahooランキングの取得ページ数（既定: 3）",
    )
    parser.add_argument(
        "--daily-count",
        type=int,
        default=5,
        choices=range(3, 6),
        metavar="3-5",
        help="毎日厳選の銘柄数（既定: 5）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = PipelineConfig(
        yahoo_pages=args.yahoo_pages,
        daily_count=args.daily_count,
    )
    try:
        result = run_pipeline(config)
    except Exception as exc:
        print(f"更新に失敗しました: {exc}", file=sys.stderr)
        return 1

    print(
        "更新完了: "
        f"候補 {len(result.candidates)}銘柄 / "
        f"注目Top100 {len(result.top100)}銘柄 / "
        f"毎日厳選 {len(result.daily_picks)}銘柄"
    )
    print(f"基準日: {result.metadata['trade_date']}")
    print(f"システム版: {result.metadata['app_version']}")
    print(f"実行ID: {result.metadata['run_id']}")
    print(f"データ状態: {result.freshness.get('summary', '-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
