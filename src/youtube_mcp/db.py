"""SQLite 3 WAL-mode connection management, schema initialization, and health queries."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from youtube_mcp.config import DEFAULT_DAILY_QUOTA_BUDGET, load_settings

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS quota_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_utc TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        units_cost INTEGER NOT NULL CHECK (units_cost >= 0),
        workflow_context TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_quota_ledger_date_utc
        ON quota_ledger (date_utc);
    """,
    """
    CREATE TABLE IF NOT EXISTS cached_videos (
        video_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cached_videos_expires_at
        ON cached_videos (expires_at);
    """,
    """
    CREATE TABLE IF NOT EXISTS cached_channels (
        channel_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cached_channels_expires_at
        ON cached_channels (expires_at);
    """,
    """
    CREATE TABLE IF NOT EXISTS pending_playlists (
        confirmation_token TEXT PRIMARY KEY,
        topic TEXT NOT NULL,
        constraints_json TEXT NOT NULL,
        selected_video_ids_json TEXT NOT NULL,
        total_duration_seconds INTEGER NOT NULL CHECK (total_duration_seconds >= 0),
        estimated_quota_cost INTEGER NOT NULL CHECK (estimated_quota_cost >= 0),
        status TEXT NOT NULL CHECK (status IN ('PENDING', 'COMPLETED', 'EXPIRED', 'FAILED')),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pending_playlists_expires_at
        ON pending_playlists (expires_at);
    """,
)


def utc_today_str() -> str:
    """Return the current UTC date formatted as `YYYY-MM-DD`."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _resolve_target_path(db_path: Path | str | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return load_settings().db_path


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a SQLite 3 connection configured with WAL mode and safety pragmas."""
    resolved_path = _resolve_target_path(db_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(resolved_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db(db_path: Path | str | None = None) -> Path:
    """Idempotently create all Stage 2 SQLite tables and indexes."""
    resolved_path = _resolve_target_path(db_path)
    with closing(get_connection(resolved_path)) as conn, conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
    return resolved_path


def get_journal_mode(db_path: Path | str | None = None) -> str:
    """Return the active SQLite `journal_mode` pragma value in lowercase."""
    with closing(get_connection(db_path)) as conn:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
    if row is None:
        return "unknown"
    return str(row[0]).lower()


def get_used_quota(
    db_path: Path | str | None = None,
    date_utc: str | None = None,
) -> int:
    """Return total quota units consumed for `date_utc` (defaults to today UTC)."""
    target_date = date_utc or utc_today_str()
    with closing(get_connection(db_path)) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(units_cost), 0) FROM quota_ledger WHERE date_utc = ?;",
            (target_date,),
        ).fetchone()
    return int(row[0]) if row is not None else 0


def get_remaining_quota(
    daily_quota_budget: int = DEFAULT_DAILY_QUOTA_BUDGET,
    db_path: Path | str | None = None,
    date_utc: str | None = None,
) -> int:
    """Compute remaining daily quota (`DAILY_QUOTA_BUDGET - today_utc_usage`)."""
    used = get_used_quota(db_path=db_path, date_utc=date_utc)
    return max(0, daily_quota_budget - used)


def check_wal_health(
    daily_quota_budget: int = DEFAULT_DAILY_QUOTA_BUDGET,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Perform a read-only WAL mode check and remaining quota query for health checks."""
    target_date = utc_today_str()
    with closing(get_connection(db_path)) as conn:
        mode_row = conn.execute("PRAGMA journal_mode;").fetchone()
        journal_mode = str(mode_row[0]).lower() if mode_row is not None else "unknown"
        usage_row = conn.execute(
            "SELECT COALESCE(SUM(units_cost), 0) FROM quota_ledger WHERE date_utc = ?;",
            (target_date,),
        ).fetchone()
        used_today = int(usage_row[0]) if usage_row is not None else 0

    return {
        "journal_mode": journal_mode,
        "daily_quota_budget": daily_quota_budget,
        "used_today": used_today,
        "remaining_quota": max(0, daily_quota_budget - used_today),
    }


class SQLiteRepository:
    """Repository facade matching the Stage 2 `SQLiteRepository` architecture contract."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = _resolve_target_path(db_path)

    def initialize_schema(self) -> None:
        """Create all tables and indexes idempotently."""
        init_db(self.db_path)

    def get_used_quota(self, date_utc: str | None = None) -> int:
        """Return total quota units logged for `date_utc` (default today UTC)."""
        return get_used_quota(db_path=self.db_path, date_utc=date_utc)

    def check_wal_health(
        self, daily_quota_budget: int = DEFAULT_DAILY_QUOTA_BUDGET
    ) -> dict[str, Any]:
        """Return active SQLite WAL status and remaining daily quota."""
        return check_wal_health(
            daily_quota_budget=daily_quota_budget, db_path=self.db_path
        )
