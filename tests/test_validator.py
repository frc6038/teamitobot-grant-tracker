"""
Telegram token validator için birim testleri.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import requests

from tools.token_setup.validator import (
    TELEGRAM_API_BASE_URL,
    TELEGRAM_REQUEST_TIMEOUT_SECONDS,
    ValidationResult,
    ValidationStatus,
    _is_successful_get_me_response,
    _is_valid_telegram_user,
    validate_token,
)

SECRET_TOKEN = "123456789:SuperSecret_Test-Token"


def _response(status_code: int, payload):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def test_empty_token_is_invalid():
    result = validate_token("")

    assert result.status is ValidationStatus.INVALID


def test_whitespace_token_is_invalid():
    result = validate_token("   ")

    assert result.status is ValidationStatus.INVALID


def test_non_string_token_is_invalid():
    result = validate_token(None)

    assert result.status is ValidationStatus.INVALID


def test_401_response_is_invalid():
    response = _response(
        401,
        {
            "ok": False,
        },
    )

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.INVALID


def test_429_response_is_unavailable():
    response = _response(
        429,
        {
            "ok": False,
        },
    )

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_500_response_is_unavailable():
    response = _response(
        500,
        {
            "ok": False,
        },
    )

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_503_response_is_unavailable():
    response = _response(
        503,
        {
            "ok": False,
        },
    )

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_network_error_is_unavailable():
    with patch(
        "tools.token_setup.validator.requests.get",
        side_effect=requests.RequestException("simulated failure"),
    ):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_malformed_json_is_unavailable():
    response = Mock()
    response.status_code = 200
    response.json.side_effect = ValueError("malformed json")

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_non_dictionary_payload_is_unavailable():
    response = _response(200, [])

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_ok_false_payload_is_unavailable():
    response = _response(
        200,
        {
            "ok": False,
        },
    )

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_missing_result_is_unavailable():
    response = _response(
        200,
        {
            "ok": True,
        },
    )

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE


def test_valid_response_is_valid():
    response = _response(
        200,
        {
            "ok": True,
            "result": {
                "id": 123456789,
                "is_bot": True,
                "first_name": "Test Bot",
                "username": "test_bot",
            },
        },
    )

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.VALID


def test_valid_response_without_username_is_valid():
    response = _response(
        200,
        {
            "ok": True,
            "result": {
                "id": 123456789,
                "is_bot": True,
                "first_name": "Test Bot",
            },
        },
    )

    with patch("tools.token_setup.validator.requests.get", return_value=response):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.VALID


def test_token_is_stripped_before_request():
    response = _response(
        200,
        {
            "ok": True,
            "result": {
                "id": 123456789,
                "is_bot": True,
                "first_name": "Test Bot",
            },
        },
    )

    with patch(
        "tools.token_setup.validator.requests.get",
        return_value=response,
    ) as mocked_get:
        result = validate_token(f"  {SECRET_TOKEN}  ")

    assert result.status is ValidationStatus.VALID

    requested_url = mocked_get.call_args.args[0]

    assert requested_url == (f"{TELEGRAM_API_BASE_URL}/bot{SECRET_TOKEN}/getMe")


def test_timeout_is_set():
    response = _response(
        200,
        {
            "ok": True,
            "result": {
                "id": 123456789,
                "is_bot": True,
                "first_name": "Test Bot",
            },
        },
    )

    with patch(
        "tools.token_setup.validator.requests.get",
        return_value=response,
    ) as mocked_get:
        validate_token(SECRET_TOKEN)

    assert mocked_get.call_args.kwargs["timeout"] == (TELEGRAM_REQUEST_TIMEOUT_SECONDS)


def test_request_does_not_disable_tls_verification():
    response = _response(
        200,
        {
            "ok": True,
            "result": {
                "id": 123456789,
                "is_bot": True,
                "first_name": "Test Bot",
            },
        },
    )

    with patch(
        "tools.token_setup.validator.requests.get",
        return_value=response,
    ) as mocked_get:
        validate_token(SECRET_TOKEN)

    assert mocked_get.call_args.kwargs.get("verify", True) is True


def test_validation_result_does_not_contain_token():
    result = ValidationResult(ValidationStatus.VALID)

    assert SECRET_TOKEN not in repr(result)


def test_valid_user_requires_positive_integer_id():
    assert not _is_valid_telegram_user(
        {
            "id": 0,
            "is_bot": True,
            "first_name": "Bot",
        }
    )

    assert not _is_valid_telegram_user(
        {
            "id": -1,
            "is_bot": True,
            "first_name": "Bot",
        }
    )

    assert not _is_valid_telegram_user(
        {
            "id": True,
            "is_bot": True,
            "first_name": "Bot",
        }
    )


def test_valid_user_requires_is_bot_true():
    assert not _is_valid_telegram_user(
        {
            "id": 123,
            "is_bot": False,
            "first_name": "Bot",
        }
    )

    assert not _is_valid_telegram_user(
        {
            "id": 123,
            "is_bot": 1,
            "first_name": "Bot",
        }
    )


def test_valid_user_requires_non_empty_first_name():
    assert not _is_valid_telegram_user(
        {
            "id": 123,
            "is_bot": True,
            "first_name": "",
        }
    )

    assert not _is_valid_telegram_user(
        {
            "id": 123,
            "is_bot": True,
            "first_name": "   ",
        }
    )


def test_optional_username_must_not_be_empty():
    assert not _is_valid_telegram_user(
        {
            "id": 123,
            "is_bot": True,
            "first_name": "Bot",
            "username": "",
        }
    )

    assert not _is_valid_telegram_user(
        {
            "id": 123,
            "is_bot": True,
            "first_name": "Bot",
            "username": "   ",
        }
    )


def test_successful_response_requires_status_200():
    response = _response(
        201,
        {
            "ok": True,
            "result": {
                "id": 123,
                "is_bot": True,
                "first_name": "Bot",
            },
        },
    )

    assert not _is_successful_get_me_response(response)


def test_unknown_test_mode_does_not_make_real_request(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv(
        "TOKEN_SETUP_TEST_RESPONSE",
        "unknown-mode",
    )

    with patch(
        "tools.token_setup.validator.requests.get",
    ) as mocked_get:
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.UNAVAILABLE
    mocked_get.assert_not_called()


def test_test_hook_is_ignored_outside_test_environment(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "TOKEN_SETUP_TEST_RESPONSE",
        "valid",
    )

    response = _response(
        401,
        {
            "ok": False,
        },
    )

    with patch(
        "tools.token_setup.validator.requests.get",
        return_value=response,
    ):
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.INVALID


def test_request_does_not_follow_redirects():
    response = _response(
        200,
        {
            "ok": True,
            "result": {
                "id": 123456789,
                "is_bot": True,
                "first_name": "Test Bot",
            },
        },
    )

    with patch(
        "tools.token_setup.validator.requests.get",
        return_value=response,
    ) as mocked_get:
        result = validate_token(SECRET_TOKEN)

    assert result.status is ValidationStatus.VALID
    assert mocked_get.call_args.kwargs["allow_redirects"] is False
