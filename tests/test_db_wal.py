"""Offline unit tests for SQLite WAL initialization and quota queries."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from youtube_mcp.db import (
    SQLiteRepository,
    check_wal_health,
    get_connection,
    get_remaining_quota,
    get_used_quota,
    init_db,
    utc_today_str,
)

TABLE_NAMES = {
    "quota_ledger",
    "cached_videos",
    "cached_channels",
    "pending_playlists",
}


def _table_names(db_path: Path) -> set[str]:
    with closing(get_connection(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {str(row["name"]) for row in rows}


def test_init_db_creates_tables_and_enables_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "wal.db"

    result = init_db(db_path)

    assert result == db_path
    assert TABLE_NAMES.issubset(_table_names(db_path))
    with closing(get_connection(db_path)) as conn:
        assert str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
        assert int(conn.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
        assert int(conn.execute("PRAGMA busy_timeout").fetchone()[0]) == 5000
        assert int(conn.execute("PRAGMA synchronous").fetchone()[0]) == 1


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "idempotent.db"

    init_db(db_path)
    init_db(db_path)

    with closing(get_connection(db_path)) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    assert len(tables) == len(TABLE_NAMES)
    assert len(indexes) == 4


def test_pending_playlist_status_constraint_rejects_invalid_status(tmp_path: Path) -> None:
    db_path = tmp_path / "status_constraint.db"
    init_db(db_path)

    with closing(get_connection(db_path)) as conn:
        columns = conn.execute("PRAGMA table_info(pending_playlists)").fetchall()
        column_names = {str(row["name"]) for row in columns}
        assert {
            "confirmation_token",
            "topic",
            "constraints_json",
            "selected_video_ids_json",
            "total_duration_seconds",
            "estimated_quota_cost",
            "status",
            "created_at",
            "expires_at",
        }.issubset(column_names)
        try:
            conn.execute(
                """
                INSERT INTO pending_playlists (
                    confirmation_token, topic, constraints_json,
                    selected_video_ids_json, total_duration_seconds,
                    estimated_quota_cost, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("token", "topic", "{}", "[]", 0, 0, "INVALID", "now", "later"),
            )
            conn.commit()
            raise AssertionError("Invalid pending playlist status was accepted")
        except sqlite3.IntegrityError:
            conn.rollback()


def test_quota_queries_filter_by_utc_date(tmp_path: Path) -> None:
    db_path = tmp_path / "quota.db"
    init_db(db_path)

    with closing(get_connection(db_path)) as conn, conn:
        conn.executemany(
            """
            INSERT INTO quota_ledger
                (date_utc, endpoint, units_cost, workflow_context, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("2026-11-27", "search.list", 100, "test", "2026-11-27T00:00:00Z"),
                ("2026-11-27", "videos.list", 50, "test", "2026-11-27T01:00:00Z"),
                ("2026-11-26", "search.list", 900, "test", "2026-11-26T00:00:00Z"),
            ],
        )

    assert get_used_quota(db_path, "2026-11-27") == 150
    assert get_used_quota(db_path, "2026-11-26") == 900
    assert get_used_quota(db_path, "2026-11-25") == 0
    assert get_remaining_quota(200, db_path, "2026-11-27") == 50
    assert get_remaining_quota(100, db_path, "2026-11-27") == 0


def test_quota_queries_never_return_negative_remaining_quota(tmp_path: Path) -> None:
    db_path = tmp_path / "over_quota.db"
    init_db(db_path)
    today_utc = utc_today_str()

    with closing(get_connection(db_path)) as conn, conn:
        conn.execute(
            """
            INSERT INTO quota_ledger
                (date_utc, endpoint, units_cost, workflow_context, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (today_utc, "search.list", 12000, "test", f"{today_utc}T00:00:00Z"),
        )

    assert get_remaining_quota(10000, db_path, today_utc) == 0
    health = check_wal_health(10000, db_path)
    assert health == {
        "journal_mode": "wal",
        "daily_quota_budget": 10000,
        "used_today": 12000,
        "remaining_quota": 0,
    }


def test_sqlite_repository_exposes_schema_health_and_quota(tmp_path: Path) -> None:
    db_path = tmp_path / "repository.db"
    repository = SQLiteRepository(db_path)

    repository.initialize_schema()

    assert TABLE_NAMES.issubset(_table_names(db_path))
    assert repository.get_used_quota("2026-11-27") == 0
    assert repository.check_wal_health(1000) == {
        "journal_mode": "wal",
        "daily_quota_budget": 1000,
        "used_today": 0,
        "remaining_quota": 1000,
    }
