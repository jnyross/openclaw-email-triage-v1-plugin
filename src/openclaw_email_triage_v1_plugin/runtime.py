from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ActionRuntime(Protocol):
    def archive_email(self, message_id: str) -> None:
        """Archive message in provider (GoG/Gmail)."""

    def keep_in_inbox(self, message_id: str) -> None:
        """Leave message in inbox."""


class PluginRegistry(Protocol):
    def register_command(self, name: str, handler: Any) -> None:
        """Register plugin command handler."""


@dataclass(frozen=True)
class ContextAdapter:
    raw: Any

    def openclaw_version(self) -> str:
        value = getattr(self.raw, "openclaw_version", None)
        if value:
            return str(value)
        value = getattr(self.raw, "version", None)
        if value:
            return str(value)
        raise RuntimeError("Could not determine OpenClaw version from plugin context")

    def plugin_config(self) -> dict[str, Any]:
        value = getattr(self.raw, "config", None)
        if isinstance(value, dict):
            return value
        getter = getattr(self.raw, "get_config", None)
        if callable(getter):
            conf = getter()
            if isinstance(conf, dict):
                return conf
        return {}
