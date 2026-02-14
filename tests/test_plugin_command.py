from dataclasses import dataclass, field

from openclaw_email_triage_v1_plugin.config import PluginConfig
from openclaw_email_triage_v1_plugin.contracts import EmailTriageResponse
from openclaw_email_triage_v1_plugin.idempotency import InMemoryIdempotencyStore
from openclaw_email_triage_v1_plugin.inference_client import InferenceClientError
from openclaw_email_triage_v1_plugin.plugin import EmailTriageCommand
from openclaw_email_triage_v1_plugin.telemetry import NullDecisionSink


@dataclass
class FakeInferenceClient:
    outcome: EmailTriageResponse | Exception

    def classify(self, triage_request):  # noqa: ANN001
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@dataclass
class FakeRuntime:
    archived: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)

    def archive_email(self, message_id: str) -> None:
        self.archived.append(message_id)

    def keep_in_inbox(self, message_id: str) -> None:
        self.kept.append(message_id)


def _event(message_id: str = "m1") -> dict[str, object]:
    return {
        "request_id": f"r-{message_id}",
        "message_id": message_id,
        "thread_id": "t1",
        "sender": "promo@example.com",
        "to": "me@example.com",
        "subject": "Sale",
        "date": "2026-02-14T12:00:00Z",
        "body_text": "discount",
        "gmail_labels": ["Category Promotions"],
        "gmail_category": "Promotions",
        "references": [],
        "sent_message_ids": [],
        "is_starred": False,
        "is_read": False,
    }


def _base_config(**overrides):  # noqa: ANN001
    conf = PluginConfig(
        inference_base_url="https://triage.internal",
        shadow_mode=False,
        canary_percent=100,
        telemetry_jsonl_path=None,
        idempotency_sqlite_path=None,
    )
    data = conf.__dict__.copy()
    data.update(overrides)
    return PluginConfig(**data)


def test_archives_when_decision_is_archive() -> None:
    command = EmailTriageCommand(
        config=_base_config(),
        inference_client=FakeInferenceClient(
            EmailTriageResponse(
                decision="archive",
                confidence=0.999,
                source="v1",
                reasoning="safe",
                rule=None,
                model_version="v1",
                threshold_used=0.995,
                latency_ms=10,
            )
        ),
        idempotency_store=InMemoryIdempotencyStore(),
        decision_sink=NullDecisionSink(),
    )
    runtime = FakeRuntime()

    result = command.execute(_event(), runtime)

    assert result["action_status"] == "archived"
    assert runtime.archived == ["m1"]


def test_shadow_mode_keeps_inbox() -> None:
    command = EmailTriageCommand(
        config=_base_config(shadow_mode=True),
        inference_client=FakeInferenceClient(
            EmailTriageResponse(
                decision="archive",
                confidence=0.999,
                source="v1",
                reasoning="safe",
                rule=None,
                model_version="v1",
                threshold_used=0.995,
                latency_ms=10,
            )
        ),
        idempotency_store=InMemoryIdempotencyStore(),
        decision_sink=NullDecisionSink(),
    )
    runtime = FakeRuntime()

    result = command.execute(_event(), runtime)

    assert result["action_status"] == "shadow_kept"
    assert runtime.archived == []
    assert runtime.kept == ["m1"]


def test_fail_open_on_inference_error() -> None:
    command = EmailTriageCommand(
        config=_base_config(email_triage_fail_open=True),
        inference_client=FakeInferenceClient(InferenceClientError("down")),
        idempotency_store=InMemoryIdempotencyStore(),
        decision_sink=NullDecisionSink(),
    )
    runtime = FakeRuntime()

    result = command.execute(_event(), runtime)

    assert result["decision"] == "needs_attention"
    assert result["action_status"] == "kept_in_inbox"
    assert runtime.kept == ["m1"]


def test_duplicate_skipped_by_idempotency() -> None:
    store = InMemoryIdempotencyStore()
    command = EmailTriageCommand(
        config=_base_config(),
        inference_client=FakeInferenceClient(
            EmailTriageResponse(
                decision="archive",
                confidence=0.999,
                source="v1",
                reasoning="safe",
                rule=None,
                model_version="v1",
                threshold_used=0.995,
                latency_ms=10,
            )
        ),
        idempotency_store=store,
        decision_sink=NullDecisionSink(),
    )
    runtime = FakeRuntime()

    first = command.execute(_event("m2"), runtime)
    second = command.execute(_event("m2"), runtime)

    assert first["action_status"] == "archived"
    assert second["action_status"] == "duplicate_skipped"
    assert runtime.archived == ["m2"]
