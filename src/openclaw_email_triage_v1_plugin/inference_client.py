from __future__ import annotations

import json
import socket
import ssl
from dataclasses import dataclass
from urllib import error, request

from openclaw_email_triage_v1_plugin.contracts import (
    EmailTriageRequest,
    EmailTriageResponse,
    SchemaError,
)


class InferenceClientError(RuntimeError):
    """Raised when inference endpoint call fails or returns invalid schema."""


@dataclass(frozen=True)
class InferenceHTTPClient:
    base_url: str
    timeout_ms: int = 1500
    api_key: str | None = None
    ca_file: str | None = None
    client_cert_file: str | None = None
    client_key_file: str | None = None

    def classify(self, triage_request: EmailTriageRequest) -> EmailTriageResponse:
        payload = json.dumps(triage_request.to_dict()).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(
            url=f"{self.base_url.rstrip('/')}/v1/classify/email",
            data=payload,
            method="POST",
            headers=headers,
        )

        timeout_seconds = self.timeout_ms / 1000.0
        context = self._ssl_context()
        try:
            with request.urlopen(req, timeout=timeout_seconds, context=context) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raise InferenceClientError(f"Inference API HTTP error: {exc.code}") from exc
        except (error.URLError, TimeoutError, socket.timeout) as exc:
            raise InferenceClientError(f"Inference API unavailable: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InferenceClientError("Inference API returned malformed JSON") from exc

        if not isinstance(parsed, dict):
            raise InferenceClientError("Inference API returned non-object JSON")

        try:
            return EmailTriageResponse.from_dict(parsed)
        except SchemaError as exc:
            raise InferenceClientError(f"Inference API schema error: {exc}") from exc

    def _ssl_context(self) -> ssl.SSLContext | None:
        if not self.ca_file and not self.client_cert_file:
            return None

        context = ssl.create_default_context(cafile=self.ca_file)
        if self.client_cert_file:
            context.load_cert_chain(
                certfile=self.client_cert_file,
                keyfile=self.client_key_file,
            )
        return context
