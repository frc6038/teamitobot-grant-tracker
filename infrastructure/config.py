"""Typed, immutable application configuration contract.

The module is intentionally environment- and dotenv-agnostic. Bootstrap code
passes an ordinary mapping to :func:`settings_from_mapping`; domain and
application code receive typed values instead of reading process state.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TypeVar
from urllib.parse import urlsplit

DEFAULT_GRANT_URL = (
    "https://www.firstinspires.org/programs/team-grant-opportunities"
)
_TELEGRAM_BOT_TOKEN_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]+$")
_RELEASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z")
_EnumT = TypeVar("_EnumT", bound=Enum)


class Environment(str, Enum):
    """Supported deployment modes."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    """Supported standard-library logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class PollingBacklogPolicy(str, Enum):
    """Telegram updates to retain when polling starts."""

    PROCESS = "process"
    DISCARD = "discard"


@dataclass(frozen=True, slots=True)
class ConfigurationProblem:
    """One value-free configuration validation problem."""

    variable: str
    reason: str


class ConfigurationError(ValueError):
    """Raised with variable names and reasons, never supplied values."""

    def __init__(self, *problems: ConfigurationProblem) -> None:
        if not problems:
            raise ValueError("ConfigurationError requires at least one problem")
        self.problems = problems
        detail = "; ".join(
            f"{problem.variable}: {problem.reason}" for problem in problems
        )
        super().__init__(f"Invalid configuration: {detail}")


@dataclass(frozen=True, slots=True)
class LegacySmtpEnvironment:
    """Temporary pass-through for the best-effort SMTP adapter.

    SMTP validation remains at its existing optional adapter boundary so a
    partially configured email channel cannot prevent the Telegram bot from
    starting. These values still share the canonical source/precedence path.
    """

    host: str | None = None
    port: str | None = None
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    sender: str | None = None
    recipients: str | None = None
    security: str = "STARTTLS"
    timeout: str = "10"


@dataclass(frozen=True, slots=True)
class Settings:
    """Canonical validated settings constructed once during bootstrap."""

    telegram_bot_token: str = field(repr=False)
    database_url: str = field(repr=False)
    environment: Environment = Environment.DEVELOPMENT
    release_id: str = "local"
    check_interval_seconds: int = 900
    health_port: int = 8080
    log_level: LogLevel = LogLevel.INFO
    grant_url: str = DEFAULT_GRANT_URL
    provider_timeout_seconds: float = 15.0
    telegram_timeout_seconds: float = 30.0
    database_timeout_seconds: float = 10.0
    polling_backlog_policy: PollingBacklogPolicy = PollingBacklogPolicy.PROCESS
    outbox_max_attempts: int = 5
    outbox_base_backoff_seconds: float = 30.0
    outbox_max_backoff_seconds: float = 3600.0
    outbox_lease_seconds: float = 120.0
    smtp: LegacySmtpEnvironment = field(default_factory=LegacySmtpEnvironment)

    def __post_init__(self) -> None:
        problems: list[ConfigurationProblem] = []
        _validate_telegram_bot_token(problems, self.telegram_bot_token)
        _validate_secret(problems, "DATABASE_URL", self.database_url)
        _validate_database_url(problems, self.database_url)

        if not isinstance(self.environment, Environment):
            problems.append(
                ConfigurationProblem("ENVIRONMENT", "must be a supported mode")
            )
        if not isinstance(self.log_level, LogLevel):
            problems.append(
                ConfigurationProblem("LOG_LEVEL", "must be a supported level")
            )
        if not isinstance(self.polling_backlog_policy, PollingBacklogPolicy):
            problems.append(
                ConfigurationProblem(
                    "POLLING_BACKLOG_POLICY",
                    "must be 'process' or 'discard'",
                )
            )
        if not isinstance(self.release_id, str) or not _RELEASE_ID.fullmatch(
            self.release_id
        ):
            problems.append(
                ConfigurationProblem(
                    "RELEASE_ID",
                    "must be 1-128 safe identifier characters",
                )
            )

        _validate_int_range(
            problems,
            "CHECK_INTERVAL",
            self.check_interval_seconds,
            minimum=1,
            maximum=86_400,
        )
        minimum_port = 0 if self.environment is Environment.TEST else 1
        _validate_int_range(
            problems,
            "PORT",
            self.health_port,
            minimum=minimum_port,
            maximum=65_535,
        )
        _validate_http_url(problems, "GRANT_URL", self.grant_url)
        _validate_float_range(
            problems,
            "PROVIDER_TIMEOUT",
            self.provider_timeout_seconds,
            minimum=0.1,
            maximum=300.0,
        )
        _validate_float_range(
            problems,
            "TELEGRAM_TIMEOUT",
            self.telegram_timeout_seconds,
            minimum=0.1,
            maximum=300.0,
        )
        _validate_float_range(
            problems,
            "DATABASE_TIMEOUT",
            self.database_timeout_seconds,
            minimum=0.1,
            maximum=300.0,
        )
        _validate_int_range(
            problems,
            "OUTBOX_MAX_ATTEMPTS",
            self.outbox_max_attempts,
            minimum=1,
            maximum=100,
        )
        _validate_float_range(
            problems,
            "OUTBOX_BASE_BACKOFF",
            self.outbox_base_backoff_seconds,
            minimum=0.1,
            maximum=86_400.0,
        )
        _validate_float_range(
            problems,
            "OUTBOX_MAX_BACKOFF",
            self.outbox_max_backoff_seconds,
            minimum=0.1,
            maximum=604_800.0,
        )
        _validate_float_range(
            problems,
            "OUTBOX_LEASE_SECONDS",
            self.outbox_lease_seconds,
            minimum=1.0,
            maximum=86_400.0,
        )
        if _is_number(self.outbox_max_backoff_seconds) and _is_number(
            self.outbox_base_backoff_seconds
        ) and self.outbox_max_backoff_seconds < self.outbox_base_backoff_seconds:
            problems.append(
                ConfigurationProblem(
                    "OUTBOX_MAX_BACKOFF",
                    "must be greater than or equal to OUTBOX_BASE_BACKOFF",
                )
            )
        if _is_number(self.outbox_lease_seconds) and _is_number(
            self.telegram_timeout_seconds
        ) and self.outbox_lease_seconds <= self.telegram_timeout_seconds:
            problems.append(
                ConfigurationProblem(
                    "OUTBOX_LEASE_SECONDS",
                    "must be greater than TELEGRAM_TIMEOUT",
                )
            )
        if not isinstance(self.smtp, LegacySmtpEnvironment):
            problems.append(
                ConfigurationProblem("SMTP_*", "must use LegacySmtpEnvironment")
            )

        if problems:
            raise ConfigurationError(*problems)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> Settings:
        """Construct from an environment-shaped mapping without reading globals."""
        return settings_from_mapping(values)

    def redacted_summary(self) -> Mapping[str, object]:
        """Return immutable startup-safe fields with secret presence only."""
        return MappingProxyType(
            {
                "telegram_bot_token": "[set]",
                "database_url": "[set]",
                "environment": self.environment.value,
                "release_id": self.release_id,
                "check_interval_seconds": self.check_interval_seconds,
                "health_port": self.health_port,
                "log_level": self.log_level.value,
                "polling_backlog_policy": self.polling_backlog_policy.value,
            }
        )


def _validate_telegram_bot_token(
    problems: list[ConfigurationProblem],
    value: object,
) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        problems.append(
            ConfigurationProblem(
                "TELEGRAM_BOT_TOKEN",
                "is required",
            )
        )
        return

    if not _TELEGRAM_BOT_TOKEN_PATTERN.fullmatch(value):
        problems.append(
            ConfigurationProblem(
                "TELEGRAM_BOT_TOKEN",
                "has an invalid format",
            )
        )


def _validate_secret(
    problems: list[ConfigurationProblem],
    variable: str,
    value: object,
) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        problems.append(ConfigurationProblem(variable, "is required"))


def _validate_database_url(
    problems: list[ConfigurationProblem],
    value: object,
) -> None:
    if not isinstance(value, str) or not value:
        return
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        problems.append(ConfigurationProblem("DATABASE_URL", "must be a valid URL"))
        return
    scheme_parts = parsed.scheme.split("+", maxsplit=1)
    if scheme_parts[0] != "postgresql" or (
        len(scheme_parts) == 2 and not scheme_parts[1]
    ):
        problems.append(ConfigurationProblem("DATABASE_URL", "must use PostgreSQL"))
    if not parsed.hostname or not parsed.path.strip("/"):
        problems.append(
            ConfigurationProblem(
                "DATABASE_URL",
                "must include a host and database name",
            )
        )


def _validate_http_url(
    problems: list[ConfigurationProblem],
    variable: str,
    value: object,
) -> None:
    if not isinstance(value, str):
        problems.append(ConfigurationProblem(variable, "must be an HTTP(S) URL"))
        return
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        problems.append(ConfigurationProblem(variable, "must be an HTTP(S) URL"))
        return
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        problems.append(ConfigurationProblem(variable, "must be an HTTP(S) URL"))


def _validate_int_range(
    problems: list[ConfigurationProblem],
    variable: str,
    value: object,
    *,
    minimum: int,
    maximum: int,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(ConfigurationProblem(variable, "must be an integer"))
    elif not minimum <= value <= maximum:
        problems.append(
            ConfigurationProblem(variable, f"must be between {minimum} and {maximum}")
        )


def _validate_float_range(
    problems: list[ConfigurationProblem],
    variable: str,
    value: object,
    *,
    minimum: float,
    maximum: float,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append(ConfigurationProblem(variable, "must be a number"))
    elif not minimum <= value <= maximum:
        problems.append(
            ConfigurationProblem(variable, f"must be between {minimum} and {maximum}")
        )


def _is_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _required(
    values: Mapping[str, str],
    variable: str,
    problems: list[ConfigurationProblem],
) -> str:
    value = values.get(variable)
    if not isinstance(value, str) or not value or value != value.strip():
        problems.append(ConfigurationProblem(variable, "is required"))
        return ""
    return value


def _parse_int(
    values: Mapping[str, str],
    variable: str,
    default: int,
    problems: list[ConfigurationProblem],
) -> int:
    raw_value = values.get(variable, str(default))
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        problems.append(ConfigurationProblem(variable, "must be an integer"))
        return default


def _parse_float(
    values: Mapping[str, str],
    variable: str,
    default: float,
    problems: list[ConfigurationProblem],
) -> float:
    raw_value = values.get(variable, str(default))
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        problems.append(ConfigurationProblem(variable, "must be a number"))
        return default


def _parse_enum(
    enum_type: type[_EnumT],
    values: Mapping[str, str],
    variable: str,
    default: _EnumT,
    problems: list[ConfigurationProblem],
) -> _EnumT:
    raw_value = values.get(variable, str(default.value))
    if not isinstance(raw_value, str):
        problems.append(ConfigurationProblem(variable, "has an unsupported value"))
        return default
    normalized = raw_value.strip()
    if enum_type is Environment or enum_type is PollingBacklogPolicy:
        normalized = normalized.casefold()
    elif enum_type is LogLevel:
        normalized = normalized.upper()
    try:
        return enum_type(normalized)
    except ValueError:
        problems.append(ConfigurationProblem(variable, "has an unsupported value"))
        return default


def _optional(values: Mapping[str, str], variable: str) -> str | None:
    value = values.get(variable)
    return value if isinstance(value, str) and value else None


def settings_from_mapping(values: Mapping[str, str]) -> Settings:
    """Parse the canonical environment contract with redacted failures."""
    problems: list[ConfigurationProblem] = []
    telegram_bot_token = _required(values, "TELEGRAM_BOT_TOKEN", problems)
    database_url = _required(values, "DATABASE_URL", problems)
    environment = _parse_enum(
        Environment,
        values,
        "ENVIRONMENT",
        Environment.DEVELOPMENT,
        problems,
    )
    log_level = _parse_enum(
        LogLevel,
        values,
        "LOG_LEVEL",
        LogLevel.INFO,
        problems,
    )
    backlog_policy = _parse_enum(
        PollingBacklogPolicy,
        values,
        "POLLING_BACKLOG_POLICY",
        PollingBacklogPolicy.PROCESS,
        problems,
    )
    check_interval = _parse_int(values, "CHECK_INTERVAL", 900, problems)
    health_port = _parse_int(values, "PORT", 8080, problems)
    provider_timeout = _parse_float(values, "PROVIDER_TIMEOUT", 15.0, problems)
    telegram_timeout = _parse_float(values, "TELEGRAM_TIMEOUT", 30.0, problems)
    database_timeout = _parse_float(values, "DATABASE_TIMEOUT", 10.0, problems)
    outbox_max_attempts = _parse_int(values, "OUTBOX_MAX_ATTEMPTS", 5, problems)
    outbox_base_backoff = _parse_float(
        values,
        "OUTBOX_BASE_BACKOFF",
        30.0,
        problems,
    )
    outbox_max_backoff = _parse_float(
        values,
        "OUTBOX_MAX_BACKOFF",
        3600.0,
        problems,
    )
    outbox_lease = _parse_float(
        values,
        "OUTBOX_LEASE_SECONDS",
        120.0,
        problems,
    )
    if problems:
        raise ConfigurationError(*problems)

    return Settings(
        telegram_bot_token=telegram_bot_token,
        database_url=database_url,
        environment=environment,
        release_id=values.get("RELEASE_ID", "local"),
        check_interval_seconds=check_interval,
        health_port=health_port,
        log_level=log_level,
        grant_url=values.get("GRANT_URL", DEFAULT_GRANT_URL),
        provider_timeout_seconds=provider_timeout,
        telegram_timeout_seconds=telegram_timeout,
        database_timeout_seconds=database_timeout,
        polling_backlog_policy=backlog_policy,
        outbox_max_attempts=outbox_max_attempts,
        outbox_base_backoff_seconds=outbox_base_backoff,
        outbox_max_backoff_seconds=outbox_max_backoff,
        outbox_lease_seconds=outbox_lease,
        smtp=LegacySmtpEnvironment(
            host=_optional(values, "SMTP_HOST"),
            port=_optional(values, "SMTP_PORT"),
            username=_optional(values, "SMTP_USERNAME"),
            password=_optional(values, "SMTP_PASSWORD"),
            sender=_optional(values, "SMTP_FROM"),
            recipients=_optional(values, "SMTP_TO"),
            security=values.get("SMTP_SECURITY", "STARTTLS"),
            timeout=values.get("SMTP_TIMEOUT", "10"),
        ),
    )
