"""Command-line interface for Telegram bot token validation."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Final

from .validator import (
    TELEGRAM_BOT_TOKEN_ENV,
    TOKEN_PATTERN,  # noqa: F401
    ValidationResult,
    ValidationStatus,
    has_valid_token_format,
    validate_token,
)

EXIT_VALID: Final = 0
EXIT_INVALID: Final = 1
EXIT_UNAVAILABLE: Final = 2

MESSAGE_VALID: Final = "Telegram bot token is valid."
MESSAGE_INVALID: Final = "Telegram bot token is invalid."
MESSAGE_UNAVAILABLE: Final = "Telegram Bot API is currently unavailable."
MESSAGE_MISSING: Final = f"{TELEGRAM_BOT_TOKEN_ENV} is not set in the environment."
MESSAGE_FORMAT: Final = (
    f"{TELEGRAM_BOT_TOKEN_ENV} does not have a valid Telegram bot token format."
)

MESSAGE_ARGUMENTS: Final = (
    "Unexpected command-line arguments are not supported; "
    f"set {TELEGRAM_BOT_TOKEN_ENV} in the environment instead."
)

TokenValidator = Callable[[str], ValidationResult]


def _has_valid_format(token: str) -> bool:
    """Backward-compatible wrapper for token format validation."""
    return has_valid_token_format(token)


def _read_token() -> str | None:
    """Read and normalize the token from the process environment."""
    token = os.environ.get(TELEGRAM_BOT_TOKEN_ENV)

    if token is None:
        return None

    return token.strip()


def main(validate_token_func: TokenValidator | None = None) -> int:
    """Run token validation and return the corresponding exit code."""
    if len(sys.argv) != 1:
        print(MESSAGE_ARGUMENTS, file=sys.stderr)
        return EXIT_INVALID

    token = _read_token()

    if not token:
        print(MESSAGE_MISSING, file=sys.stderr)
        return EXIT_INVALID

    if not has_valid_token_format(token):
        print(MESSAGE_FORMAT, file=sys.stderr)
        return EXIT_INVALID

    validator = validate_token if validate_token_func is None else validate_token_func

    try:
        result = validator(token)
    except Exception:
        print(MESSAGE_UNAVAILABLE, file=sys.stderr)
        return EXIT_UNAVAILABLE

    if not isinstance(result, ValidationResult):
        print(MESSAGE_UNAVAILABLE, file=sys.stderr)
        return EXIT_UNAVAILABLE

    if result.status is ValidationStatus.VALID:
        print(MESSAGE_VALID)
        return EXIT_VALID

    if result.status is ValidationStatus.INVALID:
        print(MESSAGE_INVALID, file=sys.stderr)
        return EXIT_INVALID

    print(MESSAGE_UNAVAILABLE, file=sys.stderr)
    return EXIT_UNAVAILABLE


if __name__ == "__main__":
    raise SystemExit(main())
