#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


@dataclass(frozen=True)
class DecisionEvent:
    timestamp: datetime
    message_id: str
    action_status: str


@dataclass(frozen=True)
class CorrectionEvent:
    timestamp: datetime
    message_id: str


def _parse_datetime(raw: str) -> datetime:
    normalized = raw
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def load_decisions(path: Path) -> list[DecisionEvent]:
    events: list[DecisionEvent] = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            raw = json.loads(line)
            ts = _parse_datetime(str(raw.get("timestamp")))
            message_id = str(raw.get("message_id", ""))
            action_status = str(raw.get("action_status", ""))
            events.append(DecisionEvent(ts, message_id, action_status))
    return events


def load_corrections(path: Path) -> list[CorrectionEvent]:
    events: list[CorrectionEvent] = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            raw = json.loads(line)
            ts = _parse_datetime(str(raw.get("timestamp")))
            message_id = str(raw.get("message_id", ""))
            events.append(CorrectionEvent(ts, message_id))
    return events


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate FP-based rollback trigger")
    parser.add_argument("--decisions", required=True, help="Path to decision JSONL")
    parser.add_argument("--corrections", required=True, help="Path to confirmed FP correction JSONL")
    parser.add_argument("--rollback-threshold", type=float, default=0.002)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--write-env", default=None, help="Write rollback env overrides to this file if triggered")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    decisions_path = Path(args.decisions)
    corrections_path = Path(args.corrections)

    if not decisions_path.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"decisions file not found: {decisions_path}",
                },
                indent=2,
            )
        )
        return 1

    if not corrections_path.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"corrections file not found: {corrections_path}",
                },
                indent=2,
            )
        )
        return 1

    decisions = load_decisions(decisions_path)
    corrections = load_corrections(corrections_path)

    if not decisions:
        report = {"ok": True, "reason": "no decisions"}
        print(json.dumps(report, indent=2))
        return 0

    now = max(event.timestamp for event in decisions)
    cutoff = now - timedelta(hours=args.window_hours)

    archived = [event for event in decisions if event.timestamp >= cutoff and event.action_status == "archived"]
    archived_ids = {event.message_id for event in archived}

    confirmed_fp = [
        event
        for event in corrections
        if event.timestamp >= cutoff and event.message_id in archived_ids
    ]

    fp_rate = (len(confirmed_fp) / len(archived)) if archived else 0.0
    rollback_triggered = fp_rate > args.rollback_threshold

    action_counts = Counter(event.action_status for event in decisions if event.timestamp >= cutoff)

    report = {
        "ok": True,
        "window_hours": args.window_hours,
        "cutoff": cutoff.isoformat(),
        "total_archived": len(archived),
        "confirmed_fp": len(confirmed_fp),
        "fp_rate": fp_rate,
        "rollback_threshold": args.rollback_threshold,
        "rollback_triggered": rollback_triggered,
        "action_counts": dict(action_counts),
    }

    if rollback_triggered and args.write_env:
        env_lines = [
            "EMAIL_TRIAGE_ARCHIVE_ENABLED=false",
            "EMAIL_TRIAGE_FAIL_OPEN=true",
            "EMAIL_TRIAGE_BLOCKLIST_ENABLED=true",
            "EMAIL_TRIAGE_LEGACY_RULES_ENABLED=false",
            "EMAIL_TRIAGE_ENGINE=v1",
        ]
        Path(args.write_env).write_text("\n".join(env_lines) + "\n")
        report["env_override_written"] = args.write_env

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
