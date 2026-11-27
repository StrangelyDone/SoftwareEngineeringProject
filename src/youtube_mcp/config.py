"""Typed application configuration for the YouTube Video Intelligence MCP Server.

Loads environment variables safely with offline-safe defaults and optional `.env`
support without requiring API keys or OAuth secrets to boot in offline/CI mode.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

DEFAULT_DATABASE_URL = "sqlite:///data/youtube_mcp.db"
DEFAULT_DAILY_QUOTA_BUDGET = 10_000
DEFAULT_SOFT_WARNING_THRESHOLD_UNITS = 300
DEFAULT_MAX_SEARCH_PAGES = 2
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_LIVE_MAX_RETRIES = 3


def resolve_db_path(database_url: str) -> Path:
    """Convert a SQLite URL (`sqlite:///...`) or plain path into a local `Path`."""
    cleaned = database_url.strip()
    if cleaned.startswith("sqlite:///"):
        raw_path = cleaned[len("sqlite:///") :]
        if not raw_path:
            raise ValueError("DATABASE_URL with sqlite:/// scheme must include a file path.")
        return Path(raw_path)
    if cleaned.startswith("sqlite://"):
        raise ValueError("Unsupported SQLite URL format; use sqlite:///relative/or//abs/path.db.")
    return Path(cleaned)


def _parse_dotenv_file(env_path: Path) -> dict[str, str]:
    """Parse key=value pairs from a `.env` file without mutating `os.environ`."""
    parsed: dict[str, str] = {}
    if not env_path.is_file():
        return parsed

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        parsed[key] = value
    return parsed


class Settings(BaseModel):
    """Immutable application settings validated via Pydantic."""

    model_config = ConfigDict(frozen=True)

    daily_quota_budget: int = Field(default=DEFAULT_DAILY_QUOTA_BUDGET, ge=1)
    soft_warning_threshold_units: int = Field(
        default=DEFAULT_SOFT_WARNING_THRESHOLD_UNITS, ge=0
    )
    max_search_pages: int = Field(default=DEFAULT_MAX_SEARCH_PAGES, ge=1)
    database_url: str = Field(default=DEFAULT_DATABASE_URL)
    log_level: str = Field(default=DEFAULT_LOG_LEVEL)
    host: str = Field(default=DEFAULT_HOST)
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    live_max_retries: int = Field(default=DEFAULT_LIVE_MAX_RETRIES, ge=0)

    youtube_api_key: SecretStr | None = Field(default=None)
    youtube_oauth_client_id: str | None = Field(default=None)
    youtube_oauth_client_secret: SecretStr | None = Field(default=None)
    youtube_oauth_token_path: Path | None = Field(default=None)

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if normalized not in valid_levels:
            raise ValueError(f"Unsupported LOG_LEVEL: {value!r}")
        return normalized

    @property
    def db_path(self) -> Path:
        """Resolved local filesystem path for the SQLite WAL database."""
        return resolve_db_path(self.database_url)


def _optional_nonempty(env: dict[str, str], key: str) -> str | None:
    value = env.get(key)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def load_settings(env_file: Path | str | None = Path(".env")) -> Settings:
    """Load settings from `os.environ` with optional `.env` fallback.

    Explicit environment variables always take precedence over `.env` entries.
    Missing API keys and OAuth secrets remain `None` so offline and CI runs boot cleanly.
    """
    merged_env: dict[str, str] = {}
    if env_file is not None:
        merged_env.update(_parse_dotenv_file(Path(env_file)))
    merged_env.update(os.environ)

    token_path_raw = _optional_nonempty(merged_env, "YOUTUBE_OAUTH_TOKEN_PATH")
    api_key_raw = _optional_nonempty(merged_env, "YOUTUBE_API_KEY")
    client_secret_raw = _optional_nonempty(merged_env, "YOUTUBE_OAUTH_CLIENT_SECRET")

    return Settings(
        daily_quota_budget=int(
            merged_env.get("DAILY_QUOTA_BUDGET", DEFAULT_DAILY_QUOTA_BUDGET)
        ),
        soft_warning_threshold_units=int(
            merged_env.get(
                "SOFT_WARNING_THRESHOLD_UNITS", DEFAULT_SOFT_WARNING_THRESHOLD_UNITS
            )
        ),
        max_search_pages=int(merged_env.get("MAX_SEARCH_PAGES", DEFAULT_MAX_SEARCH_PAGES)),
        database_url=merged_env.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        log_level=merged_env.get("LOG_LEVEL", DEFAULT_LOG_LEVEL),
        host=merged_env.get("HOST", DEFAULT_HOST),
        port=int(merged_env.get("PORT", DEFAULT_PORT)),
        live_max_retries=int(
            merged_env.get("LIVE_MAX_RETRIES", DEFAULT_LIVE_MAX_RETRIES)
        ),
        youtube_api_key=SecretStr(api_key_raw) if api_key_raw is not None else None,
        youtube_oauth_client_id=_optional_nonempty(merged_env, "YOUTUBE_OAUTH_CLIENT_ID"),
        youtube_oauth_client_secret=(
            SecretStr(client_secret_raw) if client_secret_raw is not None else None
        ),
        youtube_oauth_token_path=Path(token_path_raw) if token_path_raw is not None else None,
    )
