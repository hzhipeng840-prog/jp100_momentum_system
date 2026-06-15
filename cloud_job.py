from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from jp100.config import PipelineConfig  # noqa: E402
from jp100.pipeline import run_pipeline  # noqa: E402
from jp100.storage import save_metadata, timestamp_now  # noqa: E402
from jp100.trading_calendar import is_tse_session  # noqa: E402
from jp100.version import current_version  # noqa: E402


JST = ZoneInfo("Asia/Tokyo")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GitHub Actions向けの日次更新を実行します。"
    )
    parser.add_argument("--yahoo-pages", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--daily-count", type=int, default=5, choices=range(3, 6))
    parser.add_argument(
        "--force",
        action="store_true",
        help="同じ基準日の同じ版が存在しても再実行します。",
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        help="実行状態JSONの保存先です。",
    )
    return parser.parse_args()


def load_existing_metadata(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def should_skip_completed(
    metadata: dict[str, object],
    *,
    target_date: str,
    app_version: str,
    force: bool,
) -> bool:
    if force:
        return False
    return (
        str(metadata.get("trade_date") or "") == target_date
        and str(metadata.get("app_version") or "") == app_version
    )


def write_status(path: Path | None, status: dict[str, object]) -> None:
    if path is not None:
        save_metadata(status, path)


def execute_cloud_job(
    *,
    target_date: str,
    yahoo_pages: int,
    daily_count: int,
    force: bool,
    status_path: Path | None,
) -> int:
    version = current_version()
    base_status: dict[str, object] = {
        "target_date": target_date,
        "app_version": version,
        "checked_at": timestamp_now(),
    }

    try:
        is_session = is_tse_session(target_date)
    except Exception as exc:
        status = {
            **base_status,
            "status": "failed",
            "reason": "calendar_error",
            "message": f"東証営業日の判定に失敗しました: {exc}",
        }
        write_status(status_path, status)
        print(status["message"], file=sys.stderr)
        return 1

    if not is_session:
        status = {
            **base_status,
            "status": "skipped",
            "reason": "market_closed",
            "message": "東証休場日のため更新をスキップしました。",
        }
        write_status(status_path, status)
        print(status["message"])
        return 0

    config = PipelineConfig(
        yahoo_pages=yahoo_pages,
        daily_count=daily_count,
        expected_trade_date=target_date,
    )
    existing = load_existing_metadata(config.processed_dir / "metadata.json")
    if should_skip_completed(
        existing,
        target_date=target_date,
        app_version=version,
        force=force,
    ):
        status = {
            **base_status,
            "status": "skipped",
            "reason": "already_completed",
            "message": "同じ基準日・同じ版の更新が完了済みです。",
            "run_id": existing.get("run_id"),
        }
        write_status(status_path, status)
        print(status["message"])
        return 0

    try:
        result = run_pipeline(config)
    except Exception as exc:
        status = {
            **base_status,
            "status": "failed",
            "reason": "pipeline_error",
            "message": f"日次更新に失敗しました: {exc}",
        }
        write_status(status_path, status)
        print(status["message"], file=sys.stderr)
        return 1

    status = {
        **base_status,
        "status": "completed",
        "message": "日次更新が完了しました。",
        "trade_date": result.metadata.get("trade_date"),
        "run_id": result.metadata.get("run_id"),
        "candidate_count": len(result.candidates),
        "top100_count": len(result.top100),
        "daily_pick_count": len(result.daily_picks),
    }
    write_status(status_path, status)
    print(
        f"{status['message']} 基準日: {status['trade_date']} / "
        f"Top100: {status['top100_count']} / "
        f"毎日厳選: {status['daily_pick_count']}"
    )
    return 0


def main() -> int:
    args = parse_args()
    target_date = datetime.now(JST).date().isoformat()
    return execute_cloud_job(
        target_date=target_date,
        yahoo_pages=args.yahoo_pages,
        daily_count=args.daily_count,
        force=args.force,
        status_path=args.status_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
