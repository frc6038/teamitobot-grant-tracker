"""Tests for the non-persisting Telegram token setup CLI."""

from __future__ import annotations

import sys
from unittest.mock import Mock

import pytest
import requests

from tools.token_setup import __main__ as cli
from tools.token_setup import validator
from tools.token_setup.validator import (
    ValidationStatus,
    validate_token,
)

VALID_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456789"
INVALID_TOKEN = "123456789:INVALIDTOKEN123456789"
SECRET_SENTINEL = "987654321:SUPER_SECRET_TOKEN_DO_NOT_EXPOSE"


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external_request(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tests must not make external network requests.")

    monkeypatch.setattr(requests, "get", fail_external_request)


def test_validate_token_returns_valid_for_successful_get_me(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": {
            "id": 123456789,
            "is_bot": True,
            "first_name": "Ä°TOBOT",
            "username": "itobot_bot",
        },
    }

    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)

    result = validate_token(VALID_TOKEN)

    assert result.status is ValidationStatus.VALID
    get.assert_called_once()


def test_validate_token_returns_invalid_for_http_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.status_code = 401

    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)

    result = validate_token(INVALID_TOKEN)

    assert result.status is ValidationStatus.INVALID


def test_validate_token_returns_unavailable_for_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get = Mock(side_effect=requests.RequestException("network failure"))
    monkeypatch.setattr(requests, "get", get)

    result = validate_token(VALID_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_validate_token_returns_unavailable_for_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.status_code = 500

    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)

    result = validate_token(VALID_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_validate_token_returns_unavailable_for_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.status_code = 429

    get = Mock(return_value=response)
    monkeypatch.setattr(validator.requests, "get", get)

    result = validate_token(VALID_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_validate_token_returns_unavailable_for_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.status_code = 200
    response.json.side_effect = ValueError("invalid json")

    get = Mock(return_value=response)
    monkeypatch.setattr(validator.requests, "get", get)

    result = validate_token(VALID_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_validate_token_returns_unavailable_when_success_payload_has_no_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"ok": True}

    get = Mock(return_value=response)
    monkeypatch.setattr(validator.requests, "get", get)

    result = validate_token(VALID_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE

def test_validate_token_returns_unavailable_for_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": {},
    }

    get = Mock(return_value=response)
    monkeypatch.setattr(validator.requests, "get", get)

    result = validate_token(VALID_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE

@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        "not-a-user",
        {"is_bot": True},
        {"id": 123456789, "is_bot": True},
        {"id": 123456789, "first_name": "Ä°TOBOT"},
        {
            "id": 123456789,
            "is_bot": False,
            "first_name": "Ä°TOBOT",
        },
        {
            "id": 123456789,
            "is_bot": True,
            "first_name": "",
        },
        {
            "id": 123456789,
            "is_bot": True,
            "first_name": "Ä°TOBOT",
            "username": 12345,
        },
    ],
)
def test_validate_token_returns_unavailable_for_malformed_telegram_user(
    monkeypatch: pytest.MonkeyPatch,
    result: object,
) -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": result,
    }

    get = Mock(return_value=response)
    monkeypatch.setattr(validator.requests, "get", get)

    validation_result = validate_token(VALID_TOKEN)

    assert validation_result.status is ValidationStatus.UNAVAILABLE


def test_validate_token_returns_unavailable_for_unsuccessful_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"ok": False}

    get = Mock(return_value=response)
    monkeypatch.setattr(validator.requests, "get", get)

    result = validate_token(VALID_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_validate_token_does_not_store_token_in_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": {
            "id": 123456789,
            "is_bot": True,
            "first_name": "Ä°TOBOT",
            "username": "itobot_bot",
        },
    }

    monkeypatch.setattr(requests, "get", Mock(return_value=response))

    result = validate_token(SECRET_SENTINEL)

    assert result.status is ValidationStatus.VALID
    assert SECRET_SENTINEL not in repr(result)
    assert SECRET_SENTINEL not in str(result)


def test_validate_token_does_not_include_token_in_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_get(*args: object, **kwargs: object) -> None:
        raise requests.RequestException("request failed")

    monkeypatch.setattr(requests, "get", failing_get)

    result = validate_token(SECRET_SENTINEL)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_cli_reports_missing_environment_variable_without_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["token_setup"])

    result = cli.main()
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "TELEGRAM_BOT_TOKEN is not set in the environment." in captured.err
    assert SECRET_SENTINEL not in captured.out + captured.err


def test_cli_rejects_invalid_token_format(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "not-a-valid-token")
    monkeypatch.setattr(sys, "argv", ["token_setup"])

    result = cli.main()
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert (
        "TELEGRAM_BOT_TOKEN does not have a valid Telegram bot token format."
        in captured.err
    )


def test_cli_validates_environment_token_without_echoing_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_SENTINEL)
    monkeypatch.setattr(sys, "argv", ["token_setup"])

    validate = Mock(return_value=validator.ValidationResult(ValidationStatus.VALID))

    monkeypatch.setattr(cli, "validate_token", validate)

    result = cli.main()
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == "Telegram bot token is valid.\n"
    assert captured.err == ""
    assert SECRET_SENTINEL not in captured.out + captured.err
    validate.assert_called_once_with(SECRET_SENTINEL)


def test_cli_rejects_unexpected_argument_without_reading_environment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", VALID_TOKEN)
    monkeypatch.setattr(
        sys,
        "argv",
        ["token_setup", SECRET_SENTINEL],
    )

    validate = Mock()
    monkeypatch.setattr(cli, "validate_token", validate)

    result = cli.main()
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (
        "Unexpected command-line arguments are not supported; "
        "set TELEGRAM_BOT_TOKEN in the environment instead.\n"
    )
    assert SECRET_SENTINEL not in captured.out + captured.err
    validate.assert_not_called()
