"""Non-persisting Telegram bot token validation.

This module validates a Telegram bot token against the Bot API without
persisting, logging, or exposing the token value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

import requests
from requests import Response
from requests.exceptions import RequestException

TELEGRAM_BOT_TOKEN_ENV: Final = "TELEGRAM_BOT_TOKEN"
TELEGRAM_API_BASE_URL: Final = "https://api.telegram.org"
GET_ME_TIMEOUT_SECONDS: Final = 10.0


class ValidationStatus(str, Enum):
    """Classification of a Telegram bot token validation attempt."""

    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Safe result of a Telegram bot token validation attempt.

    No token, API response body, or exception text is stored in this object.
    """

    status: ValidationStatus


def _get_me_url(token: str) -> str:
    """Build the Telegram getMe endpoint for the supplied token.

    The returned URL contains the secret token and must never be logged,
    displayed, or included in an exception message.
    """
    return f"{TELEGRAM_API_BASE_URL}/bot{token}/getMe"


def _is_successful_get_me_response(response: Response) -> bool:
    """Return whether Telegram explicitly accepted the bot token."""
    if response.status_code != 200:
        return False

    try:
        payload = response.json()
    except ValueError:
        return False

    return (
        isinstance(payload, dict)
        and payload.get("ok") is True
        and isinstance(payload.get("result"), dict)
    )


def validate_token(token: str) -> ValidationResult:
    """Validate a Telegram bot token without persisting or exposing it.

    A successful ``getMe`` response is classified as VALID.

    An explicit HTTP 401 response is classified as INVALID because Telegram
    has rejected the supplied credentials.

    Network failures, timeouts, rate limiting, server errors, malformed
    responses, and other unexpected provider responses are classified as
    UNAVAILABLE because they do not prove that the token itself is invalid.

    The token is never returned, logged, or included in an exception message.
    """
    if not isinstance(token, str) or not token.strip():
        return ValidationResult(ValidationStatus.INVALID)

    try:
        response = requests.get(
            _get_me_url(token),
            timeout=GET_ME_TIMEOUT_SECONDS,
        )
    except RequestException:
        return ValidationResult(ValidationStatus.UNAVAILABLE)

    if response.status_code == 401:
        return ValidationResult(ValidationStatus.INVALID)

    if _is_successful_get_me_response(response):
        return ValidationResult(ValidationStatus.VALID)

    return ValidationResult(ValidationStatus.UNAVAILABLE)
