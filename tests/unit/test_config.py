from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from config import Config, load_settings
from infrastructure.config import (
    ConfigurationError,
    Environment,
    LogLevel,
    PollingBacklogPolicy,
    Settings,
    settings_from_mapping,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOKEN = "123456789:secret-token-not-real"
DATABASE_URL = "postgresql://itobot:database-secret@db.invalid:5432/grants"


def valid_environment(**overrides: str) -> dict[str, str]:
    values = {
        "TELEGRAM_BOT_TOKEN": TOKEN,
        "DATABASE_URL": DATABASE_URL,
        "ENVIRONMENT": "test",
        "PORT": "0",
    }
    values.update(overrides)
    return values


def test_settings_can_be_constructed_directly_without_environment() -> None:
    settings = Settings(
        telegram_bot_token=TOKEN,
        database_url=DATABASE_URL,
        environment=Environment.TEST,
        health_port=0,
    )

    assert settings.check_interval_seconds == 900
    assert settings.log_level is LogLevel.INFO
    assert settings.polling_backlog_policy is PollingBacklogPolicy.PROCESS
    with pytest.raises(FrozenInstanceError):
        settings.health_port = 8080  # type: ignore[misc]


def test_mapping_parses_all_typed_fields() -> None:
    settings = settings_from_mapping(
        valid_environment(
            ENVIRONMENT="STAGING",
            PORT="8443",
            RELEASE_ID="git/abc-123",
            CHECK_INTERVAL="60",
            LOG_LEVEL="warning",
            GRANT_URL="https://provider.invalid/grants",
            PROVIDER_TIMEOUT="1.5",
            TELEGRAM_TIMEOUT="2.5",
            DATABASE_TIMEOUT="3.5",
            POLLING_BACKLOG_POLICY="discard",
            OUTBOX_MAX_ATTEMPTS="7",
            OUTBOX_BASE_BACKOFF="4.5",
            OUTBOX_MAX_BACKOFF="45",
            OUTBOX_LEASE_SECONDS="30",
        )
    )

    assert settings.environment is Environment.STAGING
    assert settings.health_port == 8443
    assert settings.release_id == "git/abc-123"
    assert settings.check_interval_seconds == 60
    assert settings.log_level is LogLevel.WARNING
    assert settings.provider_timeout_seconds == 1.5
    assert settings.telegram_timeout_seconds == 2.5
    assert settings.database_timeout_seconds == 3.5
    assert settings.polling_backlog_policy is PollingBacklogPolicy.DISCARD
    assert settings.outbox_max_attempts == 7
    assert settings.outbox_base_backoff_seconds == 4.5
    assert settings.outbox_max_backoff_seconds == 45
    assert settings.outbox_lease_seconds == 30


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("ENVIRONMENT", "preview"),
        ("RELEASE_ID", "contains spaces"),
        ("CHECK_INTERVAL", "not-an-int"),
        ("CHECK_INTERVAL", "0"),
        ("CHECK_INTERVAL", "86401"),
        ("PORT", "-1"),
        ("PORT", "65536"),
        ("LOG_LEVEL", "TRACE"),
        ("GRANT_URL", "file:///tmp/grants"),
        ("PROVIDER_TIMEOUT", "0"),
        ("TELEGRAM_TIMEOUT", "301"),
        ("DATABASE_TIMEOUT", "NaN"),
        ("POLLING_BACKLOG_POLICY", "sometimes"),
        ("OUTBOX_MAX_ATTEMPTS", "0"),
        ("OUTBOX_BASE_BACKOFF", "-1"),
        ("OUTBOX_MAX_BACKOFF", "604801"),
        ("OUTBOX_LEASE_SECONDS", "0"),
    ],
)
def test_field_type_and_range_matrix(variable: str, value: str) -> None:
    with pytest.raises(ConfigurationError) as captured:
        settings_from_mapping(valid_environment(**{variable: value}))

    assert variable in str(captured.value)


@pytest.mark.parametrize("missing", ["TELEGRAM_BOT_TOKEN", "DATABASE_URL"])
def test_required_secrets_are_reported_by_name_only(missing: str) -> None:
    values = valid_environment()
    secret_values = tuple(values.values())
    values.pop(missing)

    with pytest.raises(ConfigurationError) as captured:
        settings_from_mapping(values)

    message = str(captured.value)
    assert missing in message
    assert all(secret not in message for secret in secret_values)


def test_database_validation_never_discloses_credentials() -> None:
    invalid_url = "mysql://private-user:private-password@db.invalid/app"

    with pytest.raises(ConfigurationError) as captured:
        settings_from_mapping(valid_environment(DATABASE_URL=invalid_url))

    message = str(captured.value)
    assert "DATABASE_URL" in message
    assert "private-user" not in message
    assert "private-password" not in message
    assert invalid_url not in message


def test_repr_and_summary_redact_all_secrets() -> None:
    settings = settings_from_mapping(
        valid_environment(
            SMTP_PASSWORD="smtp-secret",
            SMTP_HOST="smtp.invalid",
        )
    )
    compatibility = Config(settings)
    rendered = repr(settings) + repr(settings.smtp) + repr(compatibility)

    assert TOKEN not in rendered
    assert DATABASE_URL not in rendered
    assert "smtp-secret" not in rendered
    assert settings.redacted_summary()["telegram_bot_token"] == "[set]"


def test_cross_field_backoff_and_lease_constraints() -> None:
    with pytest.raises(ConfigurationError) as captured:
        settings_from_mapping(
            valid_environment(
                TELEGRAM_TIMEOUT="30",
                OUTBOX_BASE_BACKOFF="60",
                OUTBOX_MAX_BACKOFF="30",
                OUTBOX_LEASE_SECONDS="30",
            )
        )

    message = str(captured.value)
    assert "OUTBOX_MAX_BACKOFF" in message
    assert "OUTBOX_LEASE_SECONDS" in message


def test_environment_overrides_local_dotenv(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "TELEGRAM_BOT_TOKEN=123456789:file-token\n"
        "DATABASE_URL=postgresql://file:file@file.invalid/file\n"
        "CHECK_INTERVAL=120\n",
        encoding="utf-8",
    )

    settings = load_settings(
        valid_environment(
            ENVIRONMENT="development",
            PORT="8080",
            CHECK_INTERVAL="45",
        ),
        dotenv_path=dotenv_path,
    )

    assert settings.telegram_bot_token == TOKEN
    assert settings.database_url == DATABASE_URL
    assert settings.check_interval_seconds == 45


def test_local_dotenv_fills_missing_development_values(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "TELEGRAM_BOT_TOKEN=123456789:file-token\n"
        "DATABASE_URL=postgresql://file:file@file.invalid/file\n",
        encoding="utf-8",
    )

    settings = load_settings(
        {"ENVIRONMENT": "development"},
        dotenv_path=dotenv_path,
    )

    assert settings.telegram_bot_token == "123456789:file-token"
    assert settings.database_url.endswith("@file.invalid/file")


@pytest.mark.parametrize("mode", ["test", "staging", "production"])
def test_non_development_modes_never_read_dotenv(
    tmp_path: Path,
    mode: str,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "TELEGRAM_BOT_TOKEN=file-token\n"
        "DATABASE_URL=postgresql://file:file@file.invalid/file\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as captured:
        load_settings(
            {"ENVIRONMENT": mode},
            dotenv_path=dotenv_path,
        )

    assert "TELEGRAM_BOT_TOKEN" in str(captured.value)
    assert "DATABASE_URL" in str(captured.value)
    assert "file-token" not in str(captured.value)


def test_compatibility_facade_preserves_current_callers_and_test_overrides() -> None:
    settings = settings_from_mapping(valid_environment(CHECK_INTERVAL="33"))
    compatibility = Config(settings)

    assert compatibility.BOT_TOKEN == TOKEN
    assert compatibility.DATABASE_URL == DATABASE_URL
    assert compatibility.CHECK_INTERVAL == 33
    assert compatibility.PORT == 0
    assert compatibility.PROVIDER_TIMEOUT == 15.0
    assert compatibility.POLLING_BACKLOG_POLICY == "process"
    assert compatibility.OUTBOX_MAX_ATTEMPTS == 5
    compatibility.CHECK_INTERVAL = 0
    assert compatibility.CHECK_INTERVAL == 0
    del compatibility.CHECK_INTERVAL
    assert compatibility.CHECK_INTERVAL == 33
    assert compatibility.validate()


def test_inner_modules_import_without_live_secrets(tmp_path: Path) -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"TELEGRAM_BOT_TOKEN", "DATABASE_URL"}
    }
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import domain; import infrastructure.config; print('imports-ok')",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "imports-ok"
