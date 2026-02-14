from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class SchemaError(ValueError):
    """Raised when an email triage payload is invalid."""


def _require_str(
    data: dict[str, Any],
    key: str,
    *,
    allow_empty: bool = True,
    default: str | None = None,
) -> str:
    value = data.get(key, default)
    if value is None:
        raise SchemaError(f"Missing required field: {key}")
    if not isinstance(value, str):
        raise SchemaError(f"Field {key} must be a string")
    if not allow_empty and not value.strip():
        raise SchemaError(f"Field {key} must not be empty")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SchemaError(f"Field {key} must be a string")
    return value


def _list_of_str(data: dict[str, Any], key: str, default: list[str] | None = None) -> list[str]:
    value = data.get(key)
    if value is None:
        return list(default or [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaError(f"Field {key} must be an array of strings")
    return list(value)


def _parse_bool(data: dict[str, Any], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    raise SchemaError(f"Field {key} must be a boolean")


def _parse_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise SchemaError(f"Field {field_name} must be an ISO datetime string")

    normalized = value
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SchemaError(f"Field {field_name} is not a valid ISO datetime") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


@dataclass(frozen=True)
class EmailTriageRequest:
    request_id: str
    message_id: str
    thread_id: str | None
    sender: str
    to: str
    subject: str
    date: datetime
    body_text: str
    body_html: str | None = None
    gmail_labels: list[str] = field(default_factory=list)
    gmail_category: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    sent_message_ids: list[str] = field(default_factory=list)
    is_starred: bool = False
    is_read: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmailTriageRequest":
        return cls(
            request_id=_require_str(data, "request_id", allow_empty=False),
            message_id=_require_str(data, "message_id", allow_empty=False),
            thread_id=_optional_str(data, "thread_id"),
            sender=_require_str(data, "sender", allow_empty=False),
            to=_require_str(data, "to", allow_empty=False),
            subject=_require_str(data, "subject", default=""),
            date=_parse_datetime(data.get("date"), "date"),
            body_text=_require_str(data, "body_text", default=""),
            body_html=_optional_str(data, "body_html"),
            gmail_labels=_list_of_str(data, "gmail_labels"),
            gmail_category=_optional_str(data, "gmail_category"),
            in_reply_to=_optional_str(data, "in_reply_to"),
            references=_list_of_str(data, "references"),
            sent_message_ids=_list_of_str(data, "sent_message_ids"),
            is_starred=_parse_bool(data, "is_starred", default=False),
            is_read=_parse_bool(data, "is_read", default=False),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "sender": self.sender,
            "to": self.to,
            "subject": self.subject,
            "date": _iso(self.date),
            "body_text": self.body_text,
            "body_html": self.body_html,
            "gmail_labels": self.gmail_labels,
            "gmail_category": self.gmail_category,
            "in_reply_to": self.in_reply_to,
            "references": self.references,
            "sent_message_ids": self.sent_message_ids,
            "is_starred": self.is_starred,
            "is_read": self.is_read,
        }


@dataclass(frozen=True)
class EmailTriageResponse:
    decision: str
    confidence: float
    source: str
    reasoning: str
    rule: str | None
    model_version: str
    threshold_used: float
    latency_ms: int

    def __post_init__(self) -> None:
        if self.decision not in {"archive", "needs_attention"}:
            raise SchemaError("decision must be one of: archive, needs_attention")
        if not 0.0 <= self.confidence <= 1.0:
            raise SchemaError("confidence must be between 0.0 and 1.0")
        if self.latency_ms < 0:
            raise SchemaError("latency_ms must be >= 0")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmailTriageResponse":
        try:
            confidence = float(data.get("confidence", 0.0))
            threshold_used = float(data.get("threshold_used", 0.0))
            latency_ms = int(data.get("latency_ms", 0))
        except (TypeError, ValueError) as exc:
            raise SchemaError("Invalid numeric fields in response payload") from exc

        return cls(
            decision=_require_str(data, "decision", allow_empty=False),
            confidence=confidence,
            source=_require_str(data, "source", allow_empty=False),
            reasoning=_require_str(data, "reasoning", default=""),
            rule=_optional_str(data, "rule"),
            model_version=_require_str(data, "model_version", allow_empty=False),
            threshold_used=threshold_used,
            latency_ms=latency_ms,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "source": self.source,
            "reasoning": self.reasoning,
            "rule": self.rule,
            "model_version": self.model_version,
            "threshold_used": self.threshold_used,
            "latency_ms": self.latency_ms,
        }
