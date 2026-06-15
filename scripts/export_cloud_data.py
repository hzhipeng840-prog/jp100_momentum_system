from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="dataブランチへ公開する日次データを準備します。"
    )
    parser.add_argument("--source-data", type=Path, default=Path("data"))
    parser.add_argument("--target", type=Path, required=True)
    return parser.parse_args()


def _copy_directory(source: Path, target: Path) -> None:
    if not source.exists():
        return
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def _latest_snapshot(source_data: Path) -> Path | None:
    pointer_path = source_data / "processed" / "latest.json"
    if not pointer_path.exists():
        return None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    run_dir = Path(str(pointer.get("run_dir") or ""))
    if not run_dir.is_absolute():
        run_dir = source_data / run_dir
    return run_dir if run_dir.exists() else None


def export_cloud_data(source_data: Path, target: Path) -> None:
    metadata_path = source_data / "processed" / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError("公開対象のmetadata.jsonがありません。")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not metadata.get("trade_date") or not metadata.get("run_id"):
        raise ValueError("metadata.jsonに基準日または実行IDがありません。")

    target.mkdir(parents=True, exist_ok=True)
    target_data = target / "data"
    if target_data.exists():
        shutil.rmtree(target_data)
    _copy_directory(source_data / "processed", target_data / "processed")
    _copy_directory(source_data / "history", target_data / "history")

    snapshot = _latest_snapshot(source_data)
    if snapshot is not None:
        relative = snapshot.relative_to(source_data)
        _copy_directory(snapshot, target_data / relative)

    readme = (
        "# JP100 generated data\n\n"
        "このブランチはGitHub Actionsが生成した日次データ専用です。\n"
        "アプリ本体のコードは`main`ブランチを参照してください。\n"
    )
    (target / "README.md").write_text(readme, encoding="utf-8")


def main() -> int:
    args = parse_args()
    export_cloud_data(args.source_data.resolve(), args.target.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
