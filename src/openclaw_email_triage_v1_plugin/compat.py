from __future__ import annotations

import re
from dataclasses import dataclass


class CompatibilityError(RuntimeError):
    """Raised when plugin is loaded on an unsupported OpenClaw version."""


_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        match = _VERSION_RE.match(value.strip())
        if not match:
            raise CompatibilityError(f"Invalid semantic version: {value}")
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _compare(left: SemVer, right: SemVer) -> int:
    if (left.major, left.minor, left.patch) < (right.major, right.minor, right.patch):
        return -1
    if (left.major, left.minor, left.patch) > (right.major, right.minor, right.patch):
        return 1
    return 0


def _satisfies_token(version: SemVer, token: str) -> bool:
    token = token.strip()
    if not token:
        return True

    operators = [">=", "<=", "==", ">", "<"]
    for op in operators:
        if token.startswith(op):
            rhs = SemVer.parse(token[len(op) :].strip())
            cmp = _compare(version, rhs)
            if op == ">=":
                return cmp >= 0
            if op == "<=":
                return cmp <= 0
            if op == "==":
                return cmp == 0
            if op == ">":
                return cmp > 0
            if op == "<":
                return cmp < 0

    raise CompatibilityError(f"Unsupported spec token: {token}")


def is_supported_version(openclaw_version: str, spec: str) -> bool:
    version = SemVer.parse(openclaw_version)
    tokens = [part.strip() for part in spec.split(",") if part.strip()]
    return all(_satisfies_token(version, token) for token in tokens)


def assert_supported_version(openclaw_version: str, spec: str) -> None:
    if not is_supported_version(openclaw_version, spec):
        raise CompatibilityError(
            f"OpenClaw version {openclaw_version} is not supported by this plugin "
            f"(required: {spec})."
        )
