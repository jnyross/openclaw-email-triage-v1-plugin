#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from dataclasses import dataclass
from urllib import error, request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from openclaw_email_triage_v1_plugin.compat import CompatibilityError, assert_supported_version


@dataclass(frozen=True)
class EndpointCheck:
    name: str
    url: str
    ok: bool
    status: int | None
    error: str | None
    body: dict[str, object] | None


def check_json_endpoint(url: str, timeout_seconds: float) -> EndpointCheck:
    name = url.rsplit("/", 1)[-1]
    try:
        with request.urlopen(url, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return EndpointCheck(name, url, False, resp.status, "response is not a JSON object", None)
            return EndpointCheck(name, url, True, resp.status, None, parsed)
    except error.HTTPError as exc:
        return EndpointCheck(name, url, False, exc.code, f"HTTP {exc.code}", None)
    except Exception as exc:  # noqa: BLE001
        return EndpointCheck(name, url, False, None, str(exc), None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenClaw email-triage plugin preflight checks")
    parser.add_argument("--openclaw-version", required=True)
    parser.add_argument("--supported-spec", default=">=1.8.0,<2.0.0")
    parser.add_argument("--inference-base-url", required=True)
    parser.add_argument("--timeout-ms", type=int, default=1500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timeout_seconds = args.timeout_ms / 1000.0

    checks: list[dict[str, object]] = []
    failures = 0

    try:
        assert_supported_version(args.openclaw_version, args.supported_spec)
        checks.append(
            {
                "name": "openclaw_version",
                "ok": True,
                "detail": f"{args.openclaw_version} matches {args.supported_spec}",
            }
        )
    except CompatibilityError as exc:
        checks.append(
            {
                "name": "openclaw_version",
                "ok": False,
                "detail": str(exc),
            }
        )
        failures += 1

    base = args.inference_base_url.rstrip("/")
    endpoints = [f"{base}/healthz", f"{base}/readyz", f"{base}/v1/model"]
    for endpoint in endpoints:
        result = check_json_endpoint(endpoint, timeout_seconds)
        checks.append(
            {
                "name": f"endpoint:{result.name}",
                "ok": result.ok,
                "status": result.status,
                "detail": result.error or "ok",
                "url": result.url,
                "body": result.body,
            }
        )
        if not result.ok:
            failures += 1

    report = {
        "ok": failures == 0,
        "failures": failures,
        "checks": checks,
    }
    print(json.dumps(report, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
