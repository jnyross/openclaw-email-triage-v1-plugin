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

from openclaw_email_triage_v1_plugin.backup import (
    BackupError,
    restore_snapshot,
    write_env_restore_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore OpenClaw runtime setup from a backup snapshot"
    )
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument(
        "--target-root",
        default="/",
        help="Restore root path; use '/' for real restore or temp dir for staging",
    )
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        default=[],
        help="Optional subset of original source paths to restore (repeatable)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply restore. Without this flag, command is dry-run only.",
    )
    parser.add_argument(
        "--write-env-file",
        default=None,
        help="Write captured env vars from snapshot to shell script path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        result = restore_snapshot(
            snapshot_dir=args.snapshot_dir,
            target_root=args.target_root,
            apply=args.apply,
            include_source_paths=args.paths or None,
        )

        env_file = None
        if args.write_env_file:
            env_file = write_env_restore_file(
                snapshot_dir=args.snapshot_dir,
                output_path=args.write_env_file,
                shell="sh",
            )

    except BackupError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "mode": "apply" if args.apply else "dry_run",
                "snapshot_dir": str(result.snapshot_dir),
                "actions": [
                    {
                        "source": str(action.source),
                        "destination": str(action.destination),
                        "kind": action.kind,
                        "applied": action.applied,
                    }
                    for action in result.actions
                ],
                "env_restore_file": str(env_file) if env_file else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
