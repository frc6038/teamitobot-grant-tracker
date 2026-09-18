"""Module entry point for the Telegram token setup CLI."""

from __future__ import annotations

from . import cli
from .validator import validate_token

EXIT_INVALID = cli.EXIT_INVALID
EXIT_UNAVAILABLE = cli.EXIT_UNAVAILABLE
EXIT_VALID = cli.EXIT_VALID

MESSAGE_ARGUMENTS = cli.MESSAGE_ARGUMENTS
MESSAGE_FORMAT = cli.MESSAGE_FORMAT
MESSAGE_INVALID = cli.MESSAGE_INVALID
MESSAGE_MISSING = cli.MESSAGE_MISSING
MESSAGE_UNAVAILABLE = cli.MESSAGE_UNAVAILABLE
MESSAGE_VALID = cli.MESSAGE_VALID
TOKEN_PATTERN = cli.TOKEN_PATTERN

_has_valid_format = cli._has_valid_format
_read_token = cli._read_token


def main() -> int:
    """Run the CLI using this module's validator reference."""
    return cli.main(validate_token_func=validate_token)


__all__ = [
    "EXIT_INVALID",
    "EXIT_UNAVAILABLE",
    "EXIT_VALID",
    "MESSAGE_ARGUMENTS",
    "MESSAGE_FORMAT",
    "MESSAGE_INVALID",
    "MESSAGE_MISSING",
    "MESSAGE_UNAVAILABLE",
    "MESSAGE_VALID",
    "TOKEN_PATTERN",
    "_has_valid_format",
    "_read_token",
    "main",
    "validate_token",
]


if __name__ == "__main__":
    raise SystemExit(main())
