from pathlib import Path

import pytest

from reelhaven.config import Settings


def test_defaults_never_point_at_slash_config(monkeypatch: pytest.MonkeyPatch) -> None:
    # In code-server /config is the developer's home directory.
    monkeypatch.delenv("REELHAVEN_CONFIG_DIR", raising=False)
    settings = Settings()
    assert settings.config_dir == Path(".dev-config")
    assert settings.port == 7171


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REELHAVEN_CONFIG_DIR", "/config")
    monkeypatch.setenv("REELHAVEN_PORT", "8080")
    monkeypatch.setenv("REELHAVEN_LOG_LEVEL", "debug")
    settings = Settings()
    assert settings.config_dir == Path("/config")
    assert settings.log_dir == Path("/config/logs")
    assert settings.port == 8080
    assert settings.log_level == "debug"


def test_invalid_port_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REELHAVEN_PORT", "70000")
    with pytest.raises(ValueError, match="port"):
        Settings()
