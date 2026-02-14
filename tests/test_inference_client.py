import json
from types import SimpleNamespace
from urllib import request

from openclaw_email_triage_v1_plugin.contracts import EmailTriageRequest
from openclaw_email_triage_v1_plugin.inference_client import (
    InferenceClientError,
    InferenceHTTPClient,
)


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _request() -> EmailTriageRequest:
    return EmailTriageRequest.from_dict(
        {
            "request_id": "r1",
            "message_id": "m1",
            "thread_id": "t1",
            "sender": "promo@example.com",
            "to": "me@example.com",
            "subject": "Sale",
            "date": "2026-02-14T12:00:00Z",
            "body_text": "Discount",
            "gmail_labels": ["Category Promotions"],
            "gmail_category": "Promotions",
            "references": [],
            "sent_message_ids": [],
            "is_starred": False,
            "is_read": False,
        }
    )


def test_classify_success(monkeypatch) -> None:
    def fake_urlopen(req, timeout, context=None):  # noqa: ANN001
        auth = req.headers.get("Authorization")
        assert auth == "Bearer token"
        return _FakeHTTPResponse(
            {
                "decision": "archive",
                "confidence": 0.999,
                "source": "v1",
                "reasoning": "safe",
                "rule": None,
                "model_version": "v1",
                "threshold_used": 0.995,
                "latency_ms": 12,
            }
        )

    monkeypatch.setattr(request, "urlopen", fake_urlopen)
    client = InferenceHTTPClient(base_url="https://triage.internal", api_key="token")
    response = client.classify(_request())
    assert response.decision == "archive"


def test_classify_schema_error(monkeypatch) -> None:
    def fake_urlopen(req, timeout, context=None):  # noqa: ANN001
        return _FakeHTTPResponse({"unexpected": "payload"})

    monkeypatch.setattr(request, "urlopen", fake_urlopen)
    client = InferenceHTTPClient(base_url="https://triage.internal")

    try:
        client.classify(_request())
        assert False, "Expected InferenceClientError"
    except InferenceClientError:
        pass
