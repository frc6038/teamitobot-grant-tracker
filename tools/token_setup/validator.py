"""Telegram bot token validation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

import requests

TELEGRAM_BOT_TOKEN_ENV: Final = "TELEGRAM_BOT_TOKEN"
TELEGRAM_API_BASE_URL: Final = "https://api.telegram.org"
TELEGRAM_REQUEST_TIMEOUT_SECONDS: Final = 10

TEST_ENVIRONMENT: Final = "test"
TEST_RESPONSE_ENV: Final = "TOKEN_SETUP_TEST_RESPONSE"

TOKEN_PATTERN: Final = re.compile(r"^\d+:[A-Za-z0-9_-]+$")

def has_valid_token_format(token: str) -> bool:
    """Return whether the token has a recognizable Telegram format."""
    return isinstance(token, str) and bool(TOKEN_PATTERN.fullmatch(token))


class ValidationStatus(str, Enum):
    """Possible token validation results."""

    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result returned by token validation."""

    status: ValidationStatus


def _get_me_url(token: str) -> str:
    """Build the Telegram getMe endpoint URL.

    The token is used only to construct the request URL.
    It must never be logged or included in an error message.
    """
    return f"{TELEGRAM_API_BASE_URL}/bot{token}/getMe"


def _is_valid_telegram_user(result: object) -> bool:
    """Validate the bot user object returned by Telegram."""
    if not isinstance(result, dict):
        return False

    user_id = result.get("id")

    if isinstance(user_id, bool) or not isinstance(user_id, int):
        return False

    if user_id <= 0:
        return False

    if result.get("is_bot") is not True:
        return False

    first_name = result.get("first_name")

    if not isinstance(first_name, str) or not first_name.strip():
        return False

    if "username" in result:
        username = result["username"]

        if not isinstance(username, str) or not username.strip():
            return False

    return True


def _is_successful_get_me_response(response: requests.Response) -> bool:
    """Validate a successful Telegram getMe response."""
    if response.status_code != 200:
        return False

    try:
        payload = response.json()
    except (ValueError, TypeError):
        return False

    if not isinstance(payload, dict):
        return False

    if payload.get("ok") is not True:
        return False

    return _is_valid_telegram_user(payload.get("result"))


def _get_test_response() -> ValidationResult | None:
    """Return a configured fake result only in the test environment."""
    if os.getenv("ENVIRONMENT") != TEST_ENVIRONMENT:
        return None

    mode = os.getenv(TEST_RESPONSE_ENV)

    if mode is None:
        return None

    if mode == "valid":
        return ValidationResult(ValidationStatus.VALID)

    if mode == "unauthorized":
        return ValidationResult(ValidationStatus.INVALID)

    if mode in {
        "network",
        "rate-limited",
        "server-error",
        "malformed",
    }:
        return ValidationResult(ValidationStatus.UNAVAILABLE)

    return ValidationResult(ValidationStatus.UNAVAILABLE)


def validate_token(token: str) -> ValidationResult:
    """Validate a Telegram bot token using the getMe endpoint."""
    if not isinstance(token, str):
        return ValidationResult(ValidationStatus.INVALID)

    normalized_token = token.strip()

    if not normalized_token:
        return ValidationResult(ValidationStatus.INVALID)

    if not has_valid_token_format(normalized_token):
        return ValidationResult(ValidationStatus.INVALID)

    test_result = _get_test_response()

    if test_result is not None:
        return test_result

    try:
        response = requests.get(
            _get_me_url(normalized_token),
            timeout=TELEGRAM_REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException:
        return ValidationResult(ValidationStatus.UNAVAILABLE)

    if response.status_code == 401:
        return ValidationResult(ValidationStatus.INVALID)

    if response.status_code != 200:
        return ValidationResult(ValidationStatus.UNAVAILABLE)

    if _is_successful_get_me_response(response):
        return ValidationResult(ValidationStatus.VALID)

    return ValidationResult(ValidationStatus.UNAVAILABLE)
