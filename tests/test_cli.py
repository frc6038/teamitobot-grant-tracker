"""
Token setup CLI için birim testleri.
"""

from __future__ import annotations

from unittest.mock import patch

from tools.token_setup import cli
from tools.token_setup.validator import (
    ValidationResult,
    ValidationStatus,
)

SECRET_TOKEN = "123456789:SuperSecret_Test-Token"


def test_missing_token_returns_invalid(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(cli.sys, "argv", ["tools.token_setup"])

    result = cli.main()

    captured = capsys.readouterr()

    assert result == cli.EXIT_INVALID
    assert (
        "TELEGRAM_BOT_TOKEN is not set in the environment."
        in captured.err
    )
    assert SECRET_TOKEN not in captured.out + captured.err


def test_empty_token_returns_invalid(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(cli.sys, "argv", ["tools.token_setup"])

    result = cli.main()

    captured = capsys.readouterr()

    assert result == cli.EXIT_INVALID
    assert (
        "TELEGRAM_BOT_TOKEN is not set in the environment."
        in captured.err
    )


def test_whitespace_token_returns_invalid(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "   ")
    monkeypatch.setattr(cli.sys, "argv", ["tools.token_setup"])

    result = cli.main()

    captured = capsys.readouterr()

    assert result == cli.EXIT_INVALID
    assert (
        "TELEGRAM_BOT_TOKEN is not set in the environment."
        in captured.err
    )


def test_invalid_format_returns_invalid(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "not-a-valid-token")
    monkeypatch.setattr(cli.sys, "argv", ["tools.token_setup"])

    with patch.object(cli, "validate_token") as mocked_validate:
        result = cli.main()

    captured = capsys.readouterr()

    assert result == cli.EXIT_INVALID
    assert captured.err == f"{cli.MESSAGE_FORMAT}\n"
    mocked_validate.assert_not_called()


def test_command_line_arguments_are_rejected(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "tools.token_setup",
            SECRET_TOKEN,
        ],
    )

    with patch.object(cli, "validate_token") as mocked_validate:
        result = cli.main()

    captured = capsys.readouterr()

    assert result == cli.EXIT_INVALID
    assert captured.err == f"{cli.MESSAGE_ARGUMENTS}\n"
    assert SECRET_TOKEN not in captured.out + captured.err
    mocked_validate.assert_not_called()


def test_valid_token_returns_zero(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr(cli.sys, "argv", ["tools.token_setup"])

    with patch.object(
        cli,
        "validate_token",
        return_value=ValidationResult(ValidationStatus.VALID),
    ) as mocked_validate:
        result = cli.main()

    captured = capsys.readouterr()

    assert result == cli.EXIT_VALID
    assert "Telegram bot token is valid." in captured.out
    assert SECRET_TOKEN not in captured.out + captured.err
    mocked_validate.assert_called_once_with(SECRET_TOKEN)


def test_invalid_token_returns_one(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr(cli.sys, "argv", ["tools.token_setup"])

    with patch.object(
        cli,
        "validate_token",
        return_value=ValidationResult(ValidationStatus.INVALID),
    ) as mocked_validate:
        result = cli.main()

    captured = capsys.readouterr()

    assert result == cli.EXIT_INVALID
    assert "Telegram bot token is invalid." in captured.err
    assert SECRET_TOKEN not in captured.out + captured.err
    mocked_validate.assert_called_once_with(SECRET_TOKEN)


def test_unavailable_token_returns_two(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr(cli.sys, "argv", ["tools.token_setup"])

    with patch.object(
        cli,
        "validate_token",
        return_value=ValidationResult(ValidationStatus.UNAVAILABLE),
    ) as mocked_validate:
        result = cli.main()

    captured = capsys.readouterr()

    assert result == cli.EXIT_UNAVAILABLE
    assert "currently unavailable" in captured.err
    assert SECRET_TOKEN not in captured.out + captured.err
    mocked_validate.assert_called_once_with(SECRET_TOKEN)


def test_token_is_stripped_before_validation(monkeypatch):
    monkeypatch.setenv(
        "TELEGRAM_BOT_TOKEN",
        f"  {SECRET_TOKEN}  ",
    )
    monkeypatch.setattr(cli.sys, "argv", ["tools.token_setup"])

    with patch.object(
        cli,
        "validate_token",
        return_value=ValidationResult(ValidationStatus.VALID),
    ) as mocked_validate:
        result = cli.main()

    assert result == cli.EXIT_VALID
    mocked_validate.assert_called_once_with(SECRET_TOKEN)


def test_cli_does_not_write_token_to_disk(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr(cli.sys, "argv", ["tools.token_setup"])

    with patch.object(
        cli,
        "validate_token",
        return_value=ValidationResult(ValidationStatus.VALID),
    ):
        result = cli.main()

    assert result == cli.EXIT_VALID
    assert list(tmp_path.iterdir()) == []