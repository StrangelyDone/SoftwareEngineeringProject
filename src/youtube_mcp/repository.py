"""Transactional SQLite 3 WAL repository extending `youtube_mcp.db` (M1.1)."""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from youtube_mcp.db import (
    SQLiteRepository as BaseSQLiteRepository,
)
from youtube_mcp.db import (
    get_connection,
    utc_today_str,
)
from youtube_mcp.exceptions import ConfirmationRequiredError

VIDEO_CACHE_TTL_SECONDS = 86_400       # 24 hours (ADR-002 / TBD-03)
CHANNEL_CACHE_TTL_SECONDS = 604_800    # 7 days   (ADR-002 / TBD-03)
PLAYLIST_DRAFT_TTL_SECONDS = 900       # 15 mins  (ADR-005)
VALID_TERMINAL_STATUSES = {"COMPLETED", "EXPIRED", "FAILED"}


def utc_date_str(now: datetime | None = None) -> str:
    """Return `YYYY-MM-DD` in UTC, delegating to `db.utc_today_str` by default."""
    if now is None:
        return utc_today_str()
    return now.astimezone(UTC).strftime("%Y-%m-%d")


def format_utc(now: datetime | None = None) -> str:
    """Format a UTC datetime as fixed-width ISO-8601 for SQLite comparisons."""
    current = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    return current.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class PendingPlaylistDraft:
    """Typed representation of a row in `pending_playlists`."""

    confirmation_token: str
    topic: str
    constraints: dict[str, Any]
    selected_video_ids: list[str]
    total_duration_seconds: int
    estimated_quota_cost: int
    status: str
    created_at: str
    expires_at: str


class SQLiteRepository(BaseSQLiteRepository):
    """Full ACID repository built directly on top of `youtube_mcp.db`."""

    @contextmanager
    def write_transaction(self) -> Iterator[sqlite3.Connection]:
        """Acquire an explicit `BEGIN IMMEDIATE` write lock with atomic rollback."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 1. quota_ledger (REQ-DB-2)
    # ------------------------------------------------------------------
    def record_quota_usage(
        self,
        endpoint: str,
        units_cost: int,
        workflow_context: str,
        *,
        date_utc: str | None = None,
        now: datetime | None = None,
    ) -> None:
        """Atomically insert an endpoint cost row into `quota_ledger`."""
        if units_cost < 0:
            raise ValueError("units_cost must be non-negative")
        target_date = date_utc or utc_date_str(now)
        created_at = format_utc(now)
        with self.write_transaction() as conn:
            conn.execute(
                """
                INSERT INTO quota_ledger
                    (date_utc, endpoint, units_cost, workflow_context, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (target_date, endpoint, units_cost, workflow_context, created_at),
            )

    # ------------------------------------------------------------------
    # 2. cached_videos (24h TTL) & cached_channels (7d TTL) (REQ-DB-3)
    # ------------------------------------------------------------------
    def get_cached_videos(
        self,
        video_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Return non-expired cached video payloads at 0 quota cost."""
        if not video_ids:
            return {}
        now_iso = format_utc(now)
        placeholders = ",".join("?" for _ in video_ids)
        query = (
            f"SELECT video_id, payload_json FROM cached_videos "
            f"WHERE video_id IN ({placeholders}) AND expires_at > ?;"
        )
        with closing(get_connection(self.db_path)) as conn:
            rows = conn.execute(query, (*video_ids, now_iso)).fetchall()
        return {row["video_id"]: json.loads(row["payload_json"]) for row in rows}

    def upsert_cached_videos(
        self,
        videos: dict[str, dict[str, Any]],
        *,
        ttl_seconds: int = VIDEO_CACHE_TTL_SECONDS,
        now: datetime | None = None,
    ) -> None:
        """Insert or atomically refresh cached video metadata (24h default TTL)."""
        if not videos:
            return
        current = now.astimezone(UTC) if now is not None else datetime.now(UTC)
        fetched_at = format_utc(current)
        expires_at = format_utc(current + timedelta(seconds=ttl_seconds))
        rows = [
            (vid, json.dumps(payload), fetched_at, expires_at)
            for vid, payload in videos.items()
        ]
        with self.write_transaction() as conn:
            conn.executemany(
                """
                INSERT INTO cached_videos
                    (video_id, payload_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at;
                """,
                rows,
            )

    def get_cached_channels(
        self,
        channel_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Return non-expired cached channel payloads at 0 quota cost."""
        if not channel_ids:
            return {}
        now_iso = format_utc(now)
        placeholders = ",".join("?" for _ in channel_ids)
        query = (
            f"SELECT channel_id, payload_json FROM cached_channels "
            f"WHERE channel_id IN ({placeholders}) AND expires_at > ?;"
        )
        with closing(get_connection(self.db_path)) as conn:
            rows = conn.execute(query, (*channel_ids, now_iso)).fetchall()
        return {row["channel_id"]: json.loads(row["payload_json"]) for row in rows}

    def upsert_cached_channels(
        self,
        channels: dict[str, dict[str, Any]],
        *,
        ttl_seconds: int = CHANNEL_CACHE_TTL_SECONDS,
        now: datetime | None = None,
    ) -> None:
        """Insert or atomically refresh cached channel metadata (7d default TTL)."""
        if not channels:
            return
        current = now.astimezone(UTC) if now is not None else datetime.now(UTC)
        fetched_at = format_utc(current)
        expires_at = format_utc(current + timedelta(seconds=ttl_seconds))
        rows = [
            (cid, json.dumps(payload), fetched_at, expires_at)
            for cid, payload in channels.items()
        ]
        with self.write_transaction() as conn:
            conn.executemany(
                """
                INSERT INTO cached_channels
                    (channel_id, payload_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at;
                """,
                rows,
            )

    # ------------------------------------------------------------------
    # 3. pending_playlists (REQ-DB-4 / ADR-005)
    # ------------------------------------------------------------------
    def create_pending_playlist(
        self,
        *,
        topic: str,
        constraints: dict[str, Any],
        selected_video_ids: list[str],
        total_duration_seconds: int,
        ttl_seconds: int = PLAYLIST_DRAFT_TTL_SECONDS,
        now: datetime | None = None,
    ) -> PendingPlaylistDraft:
        """Persist a Phase 1 playlist draft with a 15-minute cryptographic token."""
        current = now.astimezone(UTC) if now is not None else datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        created_at = format_utc(current)
        expires_at = format_utc(current + timedelta(seconds=ttl_seconds))
        estimated_cost = 50 + 50 * len(selected_video_ids)

        with self.write_transaction() as conn:
            conn.execute(
                """
                INSERT INTO pending_playlists (
                    confirmation_token,
                    topic,
                    constraints_json,
                    selected_video_ids_json,
                    total_duration_seconds,
                    estimated_quota_cost,
                    status,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?);
                """,
                (
                    token,
                    topic,
                    json.dumps(constraints),
                    json.dumps(selected_video_ids),
                    total_duration_seconds,
                    estimated_cost,
                    created_at,
                    expires_at,
                ),
            )

        return PendingPlaylistDraft(
            confirmation_token=token,
            topic=topic,
            constraints=constraints,
            selected_video_ids=selected_video_ids,
            total_duration_seconds=total_duration_seconds,
            estimated_quota_cost=estimated_cost,
            status="PENDING",
            created_at=created_at,
            expires_at=expires_at,
        )

    def get_pending_playlist(self, token: str) -> PendingPlaylistDraft | None:
        """Look up a pending playlist draft by `confirmation_token`."""
        with closing(get_connection(self.db_path)) as conn:
            row = conn.execute(
                "SELECT * FROM pending_playlists WHERE confirmation_token = ?;",
                (token,),
            ).fetchone()
        return self._row_to_draft(row) if row is not None else None

    def transition_pending_playlist(
        self,
        token: str,
        new_status: str,
        *,
        now: datetime | None = None,
    ) -> PendingPlaylistDraft:
        """Enforce one-way `PENDING -> {COMPLETED, EXPIRED, FAILED}` transition."""
        if new_status not in VALID_TERMINAL_STATUSES:
            raise ValueError(f"Invalid target status: {new_status}")

        now_iso = format_utc(now)
        expired_during_check = False
        updated_row: sqlite3.Row | None = None

        with self.write_transaction() as conn:
            row = conn.execute(
                "SELECT * FROM pending_playlists WHERE confirmation_token = ?;",
                (token,),
            ).fetchone()
            if row is None:
                raise ConfirmationRequiredError(
                    "Unknown playlist confirmation token.",
                    remediation=(
                        "Run propose_playlist to generate a valid confirmation token."
                    ),
                )

            current_status = row["status"]
            if current_status != "PENDING":
                raise ConfirmationRequiredError(
                    f"Confirmation token cannot be reused (status={current_status}).",
                    remediation="Run propose_playlist again to create a fresh draft.",
                )

            if row["expires_at"] <= now_iso:
                conn.execute(
                    "UPDATE pending_playlists SET status = 'EXPIRED' "
                    "WHERE confirmation_token = ?;",
                    (token,),
                )
                expired_during_check = True
            else:
                conn.execute(
                    "UPDATE pending_playlists SET status = ? "
                    "WHERE confirmation_token = ?;",
                    (new_status, token),
                )
                updated_row = conn.execute(
                    "SELECT * FROM pending_playlists WHERE confirmation_token = ?;",
                    (token,),
                ).fetchone()

        if expired_during_check:
            raise ConfirmationRequiredError(
                "Playlist confirmation token has expired (>15 minutes).",
                remediation="Run propose_playlist again and confirm within 15 minutes.",
            )

        assert updated_row is not None
        return self._row_to_draft(updated_row)

    @staticmethod
    def _row_to_draft(row: sqlite3.Row) -> PendingPlaylistDraft:
        return PendingPlaylistDraft(
            confirmation_token=row["confirmation_token"],
            topic=row["topic"],
            constraints=json.loads(row["constraints_json"]),
            selected_video_ids=json.loads(row["selected_video_ids_json"]),
            total_duration_seconds=int(row["total_duration_seconds"]),
            estimated_quota_cost=int(row["estimated_quota_cost"]),
            status=row["status"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )
