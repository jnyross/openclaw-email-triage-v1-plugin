from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class ConfigError(ValueError):
    """Raised when plugin configuration is invalid."""


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class PluginConfig:
    inference_base_url: str
    inference_api_key_env: str = "OPENCLAW_TRIAGE_API_KEY"
    inference_timeout_ms: int = 1500
    inference_retries: int = 2
    inference_backoff_ms: int = 200
    model_version: str = "v1"
    archive_confidence_threshold: float = 0.995

    email_triage_engine: str = "v1"
    email_triage_archive_enabled: bool = True
    email_triage_fail_open: bool = True
    email_triage_blocklist_enabled: bool = True
    email_triage_legacy_rules_enabled: bool = False

    shadow_mode: bool = False
    canary_percent: float = 100.0
    supported_openclaw_versions: str = ">=1.8.0,<2.0.0"

    telemetry_jsonl_path: str | None = None
    idempotency_sqlite_path: str | None = None

    mtls_ca_file: str | None = None
    mtls_client_cert_file: str | None = None
    mtls_client_key_file: str | None = None

    @classmethod
    def from_sources(
        cls,
        config: dict[str, Any] | None,
        environ: dict[str, str] | None = None,
    ) -> "PluginConfig":
        conf = dict(config or {})
        env = environ or os.environ

        inference_base_url = conf.get("inference_base_url") or env.get("EMAIL_TRIAGE_INFERENCE_BASE_URL")
        if not inference_base_url:
            raise ConfigError("inference_base_url is required")

        canary_percent = _parse_float(conf.get("canary_percent"), 100.0)
        canary_percent = max(0.0, min(100.0, canary_percent))

        return cls(
            inference_base_url=inference_base_url,
            inference_api_key_env=str(conf.get("inference_api_key_env", "OPENCLAW_TRIAGE_API_KEY")),
            inference_timeout_ms=_parse_int(conf.get("inference_timeout_ms"), 1500),
            inference_retries=_parse_int(conf.get("inference_retries"), 2),
            inference_backoff_ms=_parse_int(conf.get("inference_backoff_ms"), 200),
            model_version=str(conf.get("model_version", "v1")),
            archive_confidence_threshold=_parse_float(conf.get("archive_confidence_threshold"), 0.995),
            email_triage_engine=str(env.get("EMAIL_TRIAGE_ENGINE", conf.get("email_triage_engine", "v1"))),
            email_triage_archive_enabled=_parse_bool(
                env.get("EMAIL_TRIAGE_ARCHIVE_ENABLED", conf.get("email_triage_archive_enabled")),
                True,
            ),
            email_triage_fail_open=_parse_bool(
                env.get("EMAIL_TRIAGE_FAIL_OPEN", conf.get("email_triage_fail_open")),
                True,
            ),
            email_triage_blocklist_enabled=_parse_bool(
                env.get("EMAIL_TRIAGE_BLOCKLIST_ENABLED", conf.get("email_triage_blocklist_enabled")),
                True,
            ),
            email_triage_legacy_rules_enabled=_parse_bool(
                env.get("EMAIL_TRIAGE_LEGACY_RULES_ENABLED", conf.get("email_triage_legacy_rules_enabled")),
                False,
            ),
            shadow_mode=_parse_bool(conf.get("shadow_mode"), False),
            canary_percent=canary_percent,
            supported_openclaw_versions=str(conf.get("supported_openclaw_versions", ">=1.8.0,<2.0.0")),
            telemetry_jsonl_path=conf.get("telemetry_jsonl_path"),
            idempotency_sqlite_path=conf.get("idempotency_sqlite_path"),
            mtls_ca_file=conf.get("mtls_ca_file"),
            mtls_client_cert_file=conf.get("mtls_client_cert_file"),
            mtls_client_key_file=conf.get("mtls_client_key_file"),
        )

    def inference_api_key(self, environ: dict[str, str] | None = None) -> str | None:
        env = environ or os.environ
        return env.get(self.inference_api_key_env)
