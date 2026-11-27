"""Pre-flight YouTube Data API v3 quota firewall and soft-warning guard (ADR-006)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from youtube_mcp.config import (
    DEFAULT_DAILY_QUOTA_BUDGET,
    DEFAULT_MAX_SEARCH_PAGES,
    DEFAULT_SOFT_WARNING_THRESHOLD_UNITS,
    Settings,
    load_settings,
)
from youtube_mcp.exceptions import QuotaBudgetExceededError
from youtube_mcp.repository import SQLiteRepository, format_utc, utc_date_str

ENDPOINT_UNIT_COSTS: dict[str, int] = {
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
    "playlists.list": 1,
    "subscriptions.list": 1,
    "playlists.insert": 50,
    "playlistItems.insert": 50,
    "search.list": 100,
}

@dataclass(frozen=True)
class QuotaOperation:
    """Single planned provider operation for worst-case cost estimation."""

    endpoint: str
    count: int = 1
    cached: bool = False


@dataclass(frozen=True)
class QuotaDecision:
    """Outcome of a pre-flight quota check."""

    allowed: bool
    estimated_cost: int
    used_today: int
    remaining_after: int
    quota_warning: str | None = None


class QuotaGuard:
    """Enforces daily 10,000-unit quota ceiling and 300-unit soft warning."""

    def __init__(
        self,
        repo: SQLiteRepository,
        *,
        daily_quota_budget: int = DEFAULT_DAILY_QUOTA_BUDGET,
        soft_warning_threshold: int = DEFAULT_SOFT_WARNING_THRESHOLD,
        max_search_pages: int = DEFAULT_MAX_SEARCH_PAGES,
    ) -> None:
        self.repo = repo
        self.daily_quota_budget = daily_quota_budget
        self.soft_warning_threshold = soft_warning_threshold
        self.max_search_pages = max_search_pages

    def estimate_cost(self, operations: list[QuotaOperation]) -> int:
        """Compute worst-case unit cost after skipping cached hits."""
        total_cost = 0
        uncached_search_pages = 0

        for op in operations:
            if op.count < 0:
                raise ValueError(f"Operation count cannot be negative: {op.count}")
            if op.endpoint not in ENDPOINT_UNIT_COSTS:
                raise ValueError(f"Unknown YouTube API endpoint: {op.endpoint}")
            if op.cached or op.count == 0:
                continue

            if op.endpoint == "search.list":
                uncached_search_pages += op.count
                if uncached_search_pages > self.max_search_pages:
                    raise ValueError(
                        f"Uncached search.list pages ({uncached_search_pages}) "
                        f"exceeds max_search_pages cap ({self.max_search_pages})."
                    )

            total_cost += ENDPOINT_UNIT_COSTS[op.endpoint] * op.count

        return total_cost

    @staticmethod
    def estimate_playlist_write_cost(video_count: int) -> int:
        """FR-5 write cost: 50 (playlists.insert) + 50 * N (playlistItems.insert)."""
        if video_count < 0:
            raise ValueError("video_count must be non-negative")
        return ENDPOINT_UNIT_COSTS["playlists.insert"] + (
            ENDPOINT_UNIT_COSTS["playlistItems.insert"] * video_count
        )

    def remaining_budget(self, *, date_utc: str | None = None) -> int:
        used = self.repo.get_used_quota(date_utc=date_utc)
        return max(0, self.daily_quota_budget - used)

    def preflight_check(
        self,
        estimated_cost: int,
        workflow_context: str,
        *,
        date_utc: str | None = None,
    ) -> QuotaDecision:
        """Block execution before any provider call if budget would be exceeded."""
        if estimated_cost < 0:
            raise ValueError("estimated_cost must be non-negative")

        target_date = date_utc or utc_date_str()
        with self.repo.write_transaction() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(units_cost), 0) AS total "
                "FROM quota_ledger WHERE date_utc = ?;",
                (target_date,),
            ).fetchone()
            used_today = int(row["total"]) if row is not None else 0

        if used_today + estimated_cost > self.daily_quota_budget:
            remaining = max(0, self.daily_quota_budget - used_today)
            raise QuotaBudgetExceededError(
                (
                    f"Workflow '{workflow_context}' requires {estimated_cost} units, "
                    f"but only {remaining} of {self.daily_quota_budget} daily units "
                    "remain."
                ),
                remediation=(
                    "Wait for the UTC midnight quota reset, narrow the request scope, "
                    "or rely on cached metadata."
                ),
            )

        remaining_after = self.daily_quota_budget - (used_today + estimated_cost)
        warning: str | None = None
        if estimated_cost > self.soft_warning_threshold:
            warning = (
                f"High quota workflow ('{workflow_context}'): estimated "
                f"{estimated_cost} units (soft threshold: "
                f"{self.soft_warning_threshold}); {remaining_after} daily units "
                "will remain after execution."
            )

        return QuotaDecision(
            allowed=True,
            estimated_cost=estimated_cost,
            used_today=used_today,
            remaining_after=remaining_after,
            quota_warning=warning,
        )

    def commit_usage(
        self,
        endpoint: str,
        units_cost: int,
        workflow_context: str,
        *,
        date_utc: str | None = None,
        now: datetime | None = None,
    ) -> None:
        """Persist actual endpoint units consumed to `quota_ledger`."""
        self.repo.record_quota_usage(
            endpoint=endpoint,
            units_cost=units_cost,
            workflow_context=workflow_context,
            date_utc=date_utc,
            now=now,
        )

    def mark_quota_exhausted(
        self,
        workflow_context: str = "upstream:quotaExceeded",
        *,
        date_utc: str | None = None,
        now: datetime | None = None,
    ) -> None:
        """Drain remaining local budget if Google returns HTTP 403 quotaExceeded."""
        target_date = date_utc or utc_date_str(now)
        created_at = format_utc(now)
        with self.repo.write_transaction() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(units_cost), 0) AS total "
                "FROM quota_ledger WHERE date_utc = ?;",
                (target_date,),
            ).fetchone()
            used_today = int(row["total"]) if row is not None else 0
            remaining = max(0, self.daily_quota_budget - used_today)
            if remaining > 0:
                conn.execute(
                    """
                    INSERT INTO quota_ledger
                        (date_utc, endpoint, units_cost, workflow_context, created_at)
                    VALUES (?, 'upstream.quotaExceeded', ?, ?, ?);
                    """,
                    (target_date, remaining, workflow_context, created_at),
                )
