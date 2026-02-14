from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


def run_with_retries(
    func: Callable[[], T],
    *,
    max_retries: int,
    base_backoff_ms: int,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= max_retries:
                break
            backoff = (base_backoff_ms / 1000.0) * (2**attempt)
            sleep_fn(backoff)

    assert last_error is not None
    raise last_error
