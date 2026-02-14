#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from openclaw_email_triage_v1_plugin.backup import BackupError, create_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create rollback backup snapshot of current OpenClaw runtime setup"
    )
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        required=True,
        help="Absolute or user-relative path to backup (repeatable)",
    )
    parser.add_argument(
        "--env-var",
        action="append",
        dest="env_vars",
        default=[],
        help="Environment variable name to capture in metadata (repeatable)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where backup snapshot and archive are written",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Record missing source paths instead of failing",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Skip creating .tar.gz archive",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        result = create_snapshot(
            source_paths=args.paths,
            output_dir=args.output_dir,
            allow_missing=args.allow_missing,
            create_archive=not args.no_archive,
            env_vars=args.env_vars,
        )
    except BackupError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "snapshot_dir": str(result.snapshot_dir),
                "metadata_path": str(result.metadata_path),
                "archive_path": str(result.archive_path) if result.archive_path else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
