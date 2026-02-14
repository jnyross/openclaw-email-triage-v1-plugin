from dataclasses import dataclass, field

from openclaw_email_triage_v1_plugin.plugin import PluginRegistrationError, register


@dataclass
class FakeRegistry:
    commands: dict[str, object] = field(default_factory=dict)

    def register_command(self, name: str, handler):  # noqa: ANN001
        self.commands[name] = handler


@dataclass
class FakeContext:
    openclaw_version: str
    config: dict[str, object]


def test_register_success(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_TRIAGE_API_KEY", "token")
    registry = FakeRegistry()
    context = FakeContext(
        openclaw_version="1.8.2",
        config={"inference_base_url": "https://triage.internal"},
    )

    command = register(registry, context)

    assert "email.triage.v1" in registry.commands
    assert command.config.inference_base_url == "https://triage.internal"


def test_register_blocks_unsupported_openclaw_version() -> None:
    registry = FakeRegistry()
    context = FakeContext(
        openclaw_version="2.1.0",
        config={"inference_base_url": "https://triage.internal"},
    )

    try:
        register(registry, context)
        assert False, "Expected PluginRegistrationError"
    except PluginRegistrationError:
        pass
