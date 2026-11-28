"""Permanent regression tests for resolved defects (`TQ-8`)."""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from youtube_mcp.db import check_wal_health, get_connection, init_db, utc_today_str


def test_regression_issue_58_check_wal_health_clamping_and_utc_day_rollover(
    tmp_path: Path,
) -> None:
    """Regression test for Issue #58 (DEF-001).

    Verifies:
    1. `check_wal_health()` clamps `remaining_quota` to 0 when today's UTC usage
       exceeds `daily_quota_budget` (using dynamic `utc_today_str()`).
    2. Previous-day quota rows (e.g. yesterday's `date_utc` with 12000 units)
       do not leak into today's `used_today` or `remaining_quota` across UTC rollover.
    """
    db_path = tmp_path / "regression_58.db"
    init_db(db_path)

    today_dt = datetime.now(UTC)
    today_utc = utc_today_str()
    yesterday_utc = (today_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_utc = (today_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    with closing(get_connection(db_path)) as conn, conn:
        # Previous day exceeded daily quota; must never pollute today's budget.
        conn.execute(
            """
            INSERT INTO quota_ledger
                (date_utc, endpoint, units_cost, workflow_context, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (yesterday_utc, "search.list", 12000, "yesterday-seed", f"{yesterday_utc}T23:59:00Z"),
        )

    # On today's UTC date, yesterday's 12000-unit row must not leak into used_today.
    clean_today = check_wal_health(10000, db_path)
    assert clean_today == {
        "journal_mode": "wal",
        "daily_quota_budget": 10000,
        "used_today": 0,
        "remaining_quota": 10000,
    }

    # Explicit date_utc override still reads yesterday's row and clamps remaining_quota to 0.
    yesterday_health = check_wal_health(10000, db_path, date_utc=yesterday_utc)
    assert yesterday_health == {
        "journal_mode": "wal",
        "daily_quota_budget": 10000,
        "used_today": 12000,
        "remaining_quota": 0,
    }

    # Seed today's UTC date above budget and verify clamping + next-day rollover isolation.
    with closing(get_connection(db_path)) as conn, conn:
        conn.execute(
            """
            INSERT INTO quota_ledger
                (date_utc, endpoint, units_cost, workflow_context, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (today_utc, "search.list", 12000, "today-overage", f"{today_utc}T00:05:00Z"),
        )

    over_today = check_wal_health(10000, db_path)
    assert over_today == {
        "journal_mode": "wal",
        "daily_quota_budget": 10000,
        "used_today": 12000,
        "remaining_quota": 0,
    }

    # Next UTC day starts fresh at 0 used / full budget.
    rolled_over = check_wal_health(10000, db_path, date_utc=tomorrow_utc)
    assert rolled_over == {
        "journal_mode": "wal",
        "daily_quota_budget": 10000,
        "used_today": 0,
        "remaining_quota": 10000,
    }
