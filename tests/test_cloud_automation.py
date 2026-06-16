from __future__ import annotations

import json
import sys
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import cloud_job
from scripts.export_cloud_data import export_cloud_data


class CloudJobTest(unittest.TestCase):
    @patch("cloud_job.previous_tse_session", return_value="2026-06-15")
    @patch("cloud_job.is_tse_session", return_value=True)
    def test_target_date_before_data_ready_uses_previous_session(
        self,
        _mock_session,
        mock_previous_session,
    ) -> None:
        now = datetime(2026, 6, 16, 2, 46, tzinfo=cloud_job.JST)

        self.assertEqual(cloud_job.resolve_target_date(now), "2026-06-15")
        mock_previous_session.assert_called_once_with("2026-06-16")

    @patch("cloud_job.previous_tse_session", return_value="2026-06-15")
    @patch("cloud_job.is_tse_session", return_value=True)
    def test_target_date_after_data_ready_uses_current_session(
        self,
        _mock_session,
        mock_previous_session,
    ) -> None:
        now = datetime(2026, 6, 16, 18, 30, tzinfo=cloud_job.JST)

        self.assertEqual(cloud_job.resolve_target_date(now), "2026-06-16")
        mock_previous_session.assert_not_called()

    @patch("cloud_job.previous_tse_session", return_value="2026-06-12")
    @patch("cloud_job.is_tse_session", return_value=False)
    def test_target_date_market_closed_uses_previous_session(
        self,
        _mock_session,
        mock_previous_session,
    ) -> None:
        now = datetime(2026, 6, 13, 18, 30, tzinfo=cloud_job.JST)

        self.assertEqual(cloud_job.resolve_target_date(now), "2026-06-12")
        mock_previous_session.assert_called_once_with("2026-06-13")

    @patch("cloud_job.is_tse_session", return_value=False)
    def test_market_holiday_is_skipped(self, _mock_session) -> None:
        root = Path.cwd() / ".test-tmp" / uuid.uuid4().hex
        status_path = root / "status.json"

        exit_code = cloud_job.execute_cloud_job(
            target_date="2026-01-01",
            yahoo_pages=3,
            daily_count=5,
            force=False,
            status_path=status_path,
        )

        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(status["status"], "skipped")
        self.assertEqual(status["reason"], "market_closed")

    @patch("cloud_job.run_pipeline")
    @patch("cloud_job.PipelineConfig")
    @patch("cloud_job.is_tse_session", return_value=True)
    def test_successful_run_writes_completed_status(
        self,
        _mock_session,
        mock_config,
        mock_pipeline,
    ) -> None:
        root = Path.cwd() / ".test-tmp" / uuid.uuid4().hex
        processed = root / "processed"
        mock_config.return_value = SimpleNamespace(processed_dir=processed)
        mock_pipeline.return_value = SimpleNamespace(
            metadata={
                "trade_date": "2026-06-15",
                "run_id": "test-run",
            },
            candidates=[1, 2],
            top100=[1],
            daily_picks=[1],
        )
        status_path = root / "status.json"

        exit_code = cloud_job.execute_cloud_job(
            target_date="2026-06-15",
            yahoo_pages=3,
            daily_count=5,
            force=False,
            status_path=status_path,
        )

        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["trade_date"], "2026-06-15")
        self.assertEqual(status["run_id"], "test-run")

    def test_same_date_and_version_is_skipped_unless_forced(self) -> None:
        metadata = {"trade_date": "2026-06-15", "app_version": "v4"}
        self.assertTrue(
            cloud_job.should_skip_completed(
                metadata,
                target_date="2026-06-15",
                app_version="v4",
                force=False,
            )
        )
        self.assertFalse(
            cloud_job.should_skip_completed(
                metadata,
                target_date="2026-06-15",
                app_version="v4",
                force=True,
            )
        )


class CloudExportTest(unittest.TestCase):
    def test_export_contains_processed_history_and_latest_snapshot(self) -> None:
        root = Path.cwd() / ".test-tmp" / uuid.uuid4().hex
        source = root / "source-data"
        target = root / "export"
        run_dir = source / "snapshots" / "2026-06-15" / "run-1"
        processed = source / "processed"
        history = source / "history"
        run_dir.mkdir(parents=True)
        processed.mkdir(parents=True)
        history.mkdir(parents=True)
        metadata = {
            "trade_date": "2026-06-15",
            "run_id": "run-1",
            "app_version": "v4",
        }
        (processed / "metadata.json").write_text(
            json.dumps(metadata),
            encoding="utf-8",
        )
        (processed / "latest.json").write_text(
            json.dumps(
                {
                    **metadata,
                    "run_dir": "snapshots/2026-06-15/run-1",
                }
            ),
            encoding="utf-8",
        )
        (processed / "top100.csv").write_text("code\n7203\n", encoding="utf-8")
        (history / "daily_picks_history.csv").write_text(
            "code\n7203\n",
            encoding="utf-8",
        )
        (run_dir / "top100.csv").write_text("code\n7203\n", encoding="utf-8")

        export_cloud_data(source, target)

        self.assertTrue((target / "data/processed/top100.csv").exists())
        self.assertTrue(
            (target / "data/history/daily_picks_history.csv").exists()
        )
        self.assertTrue(
            (
                target
                / "data/snapshots/2026-06-15/run-1/top100.csv"
            ).exists()
        )
