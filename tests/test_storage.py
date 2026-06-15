from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.storage import publish_outputs, resolve_latest_output


class SnapshotStorageTest(unittest.TestCase):
    def test_publish_outputs_switches_latest_pointer_after_snapshot(self) -> None:
        test_root = Path.cwd() / ".test-tmp"
        test_root.mkdir(parents=True, exist_ok=True)
        root = test_root / uuid.uuid4().hex
        processed = root / "processed"
        snapshots = root / "snapshots"
        metadata = {
            "run_id": "20260612T120000000000",
            "trade_date": "2026-06-11",
            "generated_at": "2026-06-12T12:00:00+09:00",
        }

        pointer = publish_outputs(
            {"top100.csv": pd.DataFrame([{"code": "7203", "rank": 1}])},
            metadata,
            processed_dir=processed,
            snapshot_dir=snapshots,
        )

        resolved = resolve_latest_output(processed, "top100.csv")
        self.assertTrue(resolved.exists())
        self.assertIn("2026-06-11", str(resolved))
        self.assertEqual(pointer["run_id"], metadata["run_id"])
        saved_pointer = json.loads(
            (processed / "latest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(saved_pointer["run_dir"], pointer["run_dir"])
        self.assertFalse(Path(saved_pointer["run_dir"]).is_absolute())
        self.assertEqual(saved_pointer["run_dir_base"], "data")
        saved = pd.read_csv(resolved, dtype={"code": str})
        self.assertEqual(saved.iloc[0]["code"], "7203")


if __name__ == "__main__":
    unittest.main()
