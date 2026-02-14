from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from openclaw_email_triage_v1_plugin.contracts import EmailTriageRequest, EmailTriageResponse


_EMAIL_PATTERN = re.compile(r"\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b")
_LONG_NUMBER_PATTERN = re.compile(r"\\b\\d{4,}\\b")


def _sha256_hex(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _sender_domain(sender: str) -> str:
    _, addr = parseaddr(sender)
    if "@" not in addr:
        return ""
    return addr.rsplit("@", 1)[-1].lower()


def redact_snippet(text: str, max_chars: int = 180) -> str:
    snippet = (text or "")[:max_chars]
    snippet = _EMAIL_PATTERN.sub("[email]", snippet)
    snippet = _LONG_NUMBER_PATTERN.sub("[number]", snippet)
    return snippet


@dataclass(frozen=True)
class DecisionEvent:
    timestamp: str
    request_id: str
    message_id: str
    thread_id_hash: str
    sender_domain: str
    subject_hash: str
    snippet_redacted: str
    decision: str
    confidence: float
    source: str
    rule: str | None
    model_version: str
    latency_ms: int
    action_status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "message_id": self.message_id,
            "thread_id_hash": self.thread_id_hash,
            "sender_domain": self.sender_domain,
            "subject_hash": self.subject_hash,
            "snippet_redacted": self.snippet_redacted,
            "decision": self.decision,
            "confidence": self.confidence,
            "source": self.source,
            "rule": self.rule,
            "model_version": self.model_version,
            "latency_ms": self.latency_ms,
            "action_status": self.action_status,
        }


class DecisionSink(Protocol):
    def log(self, event: DecisionEvent) -> None:
        """Persist a decision event."""


@dataclass
class JsonlDecisionSink:
    path: Path

    def log(self, event: DecisionEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(event.to_dict()) + "\\n")


@dataclass
class NullDecisionSink:
    def log(self, event: DecisionEvent) -> None:  # noqa: ARG002
        return


def build_decision_event(
    triage_request: EmailTriageRequest,
    response: EmailTriageResponse,
    *,
    action_status: str,
    timestamp: datetime | None = None,
) -> DecisionEvent:
    now = timestamp or datetime.now(UTC)
    return DecisionEvent(
        timestamp=now.isoformat(),
        request_id=triage_request.request_id,
        message_id=triage_request.message_id,
        thread_id_hash=_sha256_hex(triage_request.thread_id or ""),
        sender_domain=_sender_domain(triage_request.sender),
        subject_hash=_sha256_hex(triage_request.subject),
        snippet_redacted=redact_snippet(triage_request.body_text),
        decision=response.decision,
        confidence=response.confidence,
        source=response.source,
        rule=response.rule,
        model_version=response.model_version,
        latency_ms=response.latency_ms,
        action_status=action_status,
    )
