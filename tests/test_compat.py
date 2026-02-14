from openclaw_email_triage_v1_plugin.compat import (
    CompatibilityError,
    assert_supported_version,
    is_supported_version,
)


def test_supported_version_range() -> None:
    assert is_supported_version("1.8.0", ">=1.8.0,<2.0.0") is True
    assert is_supported_version("1.9.5", ">=1.8.0,<2.0.0") is True
    assert is_supported_version("2.0.0", ">=1.8.0,<2.0.0") is False


def test_assert_supported_version_raises() -> None:
    try:
        assert_supported_version("2.1.0", ">=1.8.0,<2.0.0")
        assert False, "Expected CompatibilityError"
    except CompatibilityError:
        pass
