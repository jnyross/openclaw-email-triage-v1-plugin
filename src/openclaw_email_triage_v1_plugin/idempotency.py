from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
import threading


class IdempotencyStore:
    def is_applied(self, message_id: str, decision_version: str) -> bool:
        raise NotImplementedError

    def mark_applied(self, message_id: str, decision_version: str) -> None:
        raise NotImplementedError


@dataclass
class InMemoryIdempotencyStore(IdempotencyStore):
    _seen: set[tuple[str, str]] = field(default_factory=set)

    def is_applied(self, message_id: str, decision_version: str) -> bool:
        return (message_id, decision_version) in self._seen

    def mark_applied(self, message_id: str, decision_version: str) -> None:
        self._seen.add((message_id, decision_version))


@dataclass
class SQLiteIdempotencyStore(IdempotencyStore):
    db_path: str
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS triage_applied_actions (
                    message_id TEXT NOT NULL,
                    decision_version TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    PRIMARY KEY (message_id, decision_version)
                )
                """
            )
            conn.commit()

    def is_applied(self, message_id: str, decision_version: str) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM triage_applied_actions
                WHERE message_id = ? AND decision_version = ?
                """,
                (message_id, decision_version),
            ).fetchone()
            return row is not None

    def mark_applied(self, message_id: str, decision_version: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO triage_applied_actions
                (message_id, decision_version, applied_at)
                VALUES (?, ?, ?)
                """,
                (message_id, decision_version, datetime.now(UTC).isoformat()),
            )
            conn.commit()
