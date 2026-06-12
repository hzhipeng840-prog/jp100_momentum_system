from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


JST = ZoneInfo("Asia/Tokyo")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_frame(frame: pd.DataFrame, path: Path) -> None:
    _atomic_write(path, frame.to_csv(index=False).encode("utf-8-sig"))


def save_metadata(metadata: dict[str, object], path: Path) -> None:
    payload = json.dumps(
        metadata,
        ensure_ascii=False,
        indent=2,
        default=str,
    ).encode("utf-8")
    _atomic_write(path, payload)


def make_run_id(now: datetime | None = None) -> str:
    current = now.astimezone(JST) if now is not None else datetime.now(JST)
    return current.strftime("%Y%m%dT%H%M%S%f")


def publish_outputs(
    frames: dict[str, pd.DataFrame],
    metadata: dict[str, object],
    *,
    processed_dir: Path,
    snapshot_dir: Path,
) -> dict[str, object]:
    trade_date = str(metadata.get("trade_date") or "").strip()
    run_id = str(metadata.get("run_id") or make_run_id()).strip()
    if not trade_date:
        raise ValueError("スナップショットの基準日がありません。")

    staging_root = snapshot_dir.parent / ".staging"
    staging_dir = staging_root / run_id
    target_dir = snapshot_dir / trade_date / run_id
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=False)

    try:
        for filename, frame in frames.items():
            save_frame(frame, staging_dir / filename)
        save_metadata(metadata, staging_dir / "metadata.json")
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_dir, target_dir)
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise

    pointer = {
        "run_id": run_id,
        "trade_date": trade_date,
        "generated_at": metadata.get("generated_at"),
        "run_dir": str(target_dir.resolve()),
        "files": sorted([*frames.keys(), "metadata.json"]),
    }
    save_metadata(pointer, processed_dir / "latest.json")

    # 既存ツールとの互換用ミラー。画面は整合性を保証するlatest.jsonを優先する。
    for filename, frame in frames.items():
        save_frame(frame, processed_dir / filename)
    save_metadata(metadata, processed_dir / "metadata.json")
    return pointer


def resolve_latest_output(processed_dir: Path, filename: str) -> Path:
    pointer_path = processed_dir / "latest.json"
    if pointer_path.exists():
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            run_dir = Path(str(pointer.get("run_dir") or ""))
            candidate = run_dir / filename
            if candidate.exists():
                return candidate
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    return processed_dir / filename


def timestamp_now() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")
