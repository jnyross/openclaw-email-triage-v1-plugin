from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openclaw_email_triage_v1_plugin.compat import (
    CompatibilityError,
    assert_supported_version,
)
from openclaw_email_triage_v1_plugin.config import ConfigError, PluginConfig
from openclaw_email_triage_v1_plugin.contracts import (
    EmailTriageRequest,
    EmailTriageResponse,
    SchemaError,
)
from openclaw_email_triage_v1_plugin.idempotency import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
    SQLiteIdempotencyStore,
)
from openclaw_email_triage_v1_plugin.inference_client import (
    InferenceClientError,
    InferenceHTTPClient,
)
from openclaw_email_triage_v1_plugin.retry import run_with_retries
from openclaw_email_triage_v1_plugin.runtime import ActionRuntime, ContextAdapter
from openclaw_email_triage_v1_plugin.telemetry import (
    DecisionSink,
    JsonlDecisionSink,
    NullDecisionSink,
    build_decision_event,
)

logger = logging.getLogger(__name__)


class PluginRegistrationError(RuntimeError):
    """Raised when plugin cannot be registered safely."""


@dataclass
class EmailTriageCommand:
    config: PluginConfig
    inference_client: InferenceHTTPClient
    idempotency_store: IdempotencyStore
    decision_sink: DecisionSink

    def execute(self, email_event: dict[str, Any], runtime: ActionRuntime) -> dict[str, Any]:
        request = EmailTriageRequest.from_dict(email_event)

        if self.idempotency_store.is_applied(request.message_id, self.config.model_version):
            duplicate = EmailTriageResponse(
                decision="needs_attention",
                confidence=0.0,
                source="plugin",
                reasoning="duplicate message skipped by idempotency guard",
                rule=None,
                model_version=self.config.model_version,
                threshold_used=self.config.archive_confidence_threshold,
                latency_ms=0,
            )
            self.decision_sink.log(
                build_decision_event(
                    request,
                    duplicate,
                    action_status="duplicate_skipped",
                    timestamp=datetime.now(UTC),
                )
            )
            return {
                "action_status": "duplicate_skipped",
                "decision": "needs_attention",
                "source": "plugin",
                "model_version": self.config.model_version,
            }

        try:
            response = run_with_retries(
                lambda: self.inference_client.classify(request),
                max_retries=self.config.inference_retries,
                base_backoff_ms=self.config.inference_backoff_ms,
            )
        except (InferenceClientError, SchemaError) as exc:
            if not self.config.email_triage_fail_open:
                raise
            response = EmailTriageResponse(
                decision="needs_attention",
                confidence=0.0,
                source="plugin",
                reasoning=f"fail-open due to inference error: {exc}",
                rule=None,
                model_version=self.config.model_version,
                threshold_used=self.config.archive_confidence_threshold,
                latency_ms=0,
            )

        # Defense-in-depth threshold check in plugin layer as well
        if (
            response.decision == "archive"
            and response.confidence < self.config.archive_confidence_threshold
        ):
            response = EmailTriageResponse(
                decision="needs_attention",
                confidence=response.confidence,
                source=response.source,
                reasoning=(
                    f"archive confidence below threshold "
                    f"({response.confidence:.3f} < {self.config.archive_confidence_threshold:.3f})"
                ),
                rule=response.rule,
                model_version=response.model_version,
                threshold_used=self.config.archive_confidence_threshold,
                latency_ms=response.latency_ms,
            )

        action_status = self._apply_action(response, request, runtime)

        self.idempotency_store.mark_applied(request.message_id, self.config.model_version)
        event = build_decision_event(
            request,
            response,
            action_status=action_status,
            timestamp=datetime.now(UTC),
        )
        self.decision_sink.log(event)

        return {
            "action_status": action_status,
            "decision": response.decision,
            "confidence": response.confidence,
            "source": response.source,
            "rule": response.rule,
            "reasoning": response.reasoning,
            "model_version": response.model_version,
            "threshold_used": response.threshold_used,
            "latency_ms": response.latency_ms,
        }

    def _apply_action(
        self,
        response: EmailTriageResponse,
        request: EmailTriageRequest,
        runtime: ActionRuntime,
    ) -> str:
        if self.config.shadow_mode or not self._is_in_canary(request.message_id):
            runtime.keep_in_inbox(request.message_id)
            return "shadow_kept"

        if response.decision != "archive" or not self.config.email_triage_archive_enabled:
            runtime.keep_in_inbox(request.message_id)
            if not self.config.email_triage_archive_enabled and response.decision == "archive":
                return "archive_disabled_kept"
            return "kept_in_inbox"

        try:
            runtime.archive_email(request.message_id)
            return "archived"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Archive action failed for %s: %s", request.message_id, exc)
            runtime.keep_in_inbox(request.message_id)
            return "action_failed"

    def _is_in_canary(self, message_id: str) -> bool:
        if self.config.canary_percent >= 100.0:
            return True
        if self.config.canary_percent <= 0.0:
            return False

        digest = hashlib.sha256(message_id.encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 100
        return bucket < int(self.config.canary_percent)


def register(registry: Any, context: Any) -> EmailTriageCommand:
    """Register command `email.triage.v1` in OpenClaw plugin registry."""
    adapter = ContextAdapter(context)

    try:
        config = PluginConfig.from_sources(adapter.plugin_config(), os.environ)
    except ConfigError as exc:
        raise PluginRegistrationError(str(exc)) from exc

    try:
        assert_supported_version(adapter.openclaw_version(), config.supported_openclaw_versions)
    except CompatibilityError as exc:
        raise PluginRegistrationError(str(exc)) from exc

    inference_client = InferenceHTTPClient(
        base_url=config.inference_base_url,
        timeout_ms=config.inference_timeout_ms,
        api_key=config.inference_api_key(),
        ca_file=config.mtls_ca_file,
        client_cert_file=config.mtls_client_cert_file,
        client_key_file=config.mtls_client_key_file,
    )

    if config.idempotency_sqlite_path:
        idempotency_store: IdempotencyStore = SQLiteIdempotencyStore(config.idempotency_sqlite_path)
    else:
        idempotency_store = InMemoryIdempotencyStore()

    if config.telemetry_jsonl_path:
        sink = JsonlDecisionSink(path=Path(config.telemetry_jsonl_path).expanduser())
    else:
        sink = NullDecisionSink()

    command = EmailTriageCommand(
        config=config,
        inference_client=inference_client,
        idempotency_store=idempotency_store,
        decision_sink=sink,
    )

    registry.register_command("email.triage.v1", command.execute)
    return command
