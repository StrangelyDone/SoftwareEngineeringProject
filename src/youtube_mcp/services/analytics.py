"""User engagement and library analytics service (`FR-4`, `REQ-FR4-1`..`5`)."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from youtube_mcp.models import ChannelMetadata, PlaylistSummary, VideoMetadata
from youtube_mcp.providers.base import YouTubeProvider
from youtube_mcp.quota_guard import QuotaGuard, QuotaOperation
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.sanitizer import MetadataSanitizer
from youtube_mcp.services._cache import load_videos_with_cache
from youtube_mcp.services.duration import resolve_video_duration_seconds


class ChannelDistributionEntry(BaseModel):
    """Frequency and percentage share for a single channel in the video cohort."""

    channel_id: str
    channel_title: str = ""
    count: int
    percentage: float
    untrusted_metadata: Literal[True] = True


class CategoryDistributionEntry(BaseModel):
    """Frequency and percentage share for a single YouTube `categoryId`."""

    category_id: str
    count: int
    percentage: float


class TrendBucket(BaseModel):
    """Monthly (`YYYY-MM`) or quarterly (`YYYY-Qn`) publication-time bucket."""

    period: str
    video_count: int
    top_category_id: str | None = None
    category_counts: dict[str, int] = Field(default_factory=dict)


class DurationBuckets(BaseModel):
    """Non-overlapping integer-second duration histogram buckets (`FR-4`)."""

    short_lt_5m: int = 0
    medium_5m_20m: int = 0
    long_20m_60m: int = 0
    deep_dive_gt_60m: int = 0


class DurationPreferences(BaseModel):
    """Summary duration statistics and bucket counts over valid parsed durations."""

    valid_video_count: int = 0
    invalid_duration_count: int = 0
    mean_seconds: float = 0.0
    median_seconds: float = 0.0
    min_seconds: int = 0
    max_seconds: int = 0
    buckets: DurationBuckets = Field(default_factory=DurationBuckets)


class KeyDelta(BaseModel):
    """Period-over-period delta for a specific channel or category key."""

    key: str
    period_a_count: int
    period_b_count: int
    absolute_delta: int
    percentage_delta: float | None = None
    percentage_delta_display: str


class PeriodSummary(BaseModel):
    """Aggregate summary for one comparison window."""

    start_utc: str
    end_utc: str
    video_count: int = 0
    avg_duration_seconds: float = 0.0
    top_categories: dict[str, int] = Field(default_factory=dict)
    top_channels: dict[str, int] = Field(default_factory=dict)


class PeriodComparison(BaseModel):
    """Period A vs. Period B comparison with zero-division-safe deltas."""

    period_a: PeriodSummary
    period_b: PeriodSummary
    volume_absolute_delta: int = 0
    volume_percentage_delta: float | None = None
    volume_percentage_delta_display: str = "N/A (new from zero)"
    avg_duration_absolute_delta: float = 0.0
    avg_duration_percentage_delta: float | None = None
    avg_duration_percentage_delta_display: str = "N/A (new from zero)"
    category_deltas: list[KeyDelta] = Field(default_factory=list)
    channel_deltas: list[KeyDelta] = Field(default_factory=list)


class EngagementReport(BaseModel):
    """Complete `FR-4` engagement analysis report across user library cohorts."""

    liked_video_count: int = 0
    subscription_count: int = 0
    playlist_count: int = 0
    unique_video_count: int = 0
    missing_category_count: int = 0
    timestamp_source: str = "video.snippet.publishedAt"
    top_channels: list[ChannelDistributionEntry] = Field(default_factory=list)
    top_categories: list[CategoryDistributionEntry] = Field(default_factory=list)
    trends_over_time: list[TrendBucket] = Field(default_factory=list)
    duration_preferences: DurationPreferences = Field(default_factory=DurationPreferences)
    period_comparison: PeriodComparison | None = None
    quota_used: int = 0
    remaining_daily_quota: int = 0
    quota_warning: str | None = None


def _parse_utc_datetime(raw: str | None, *, end_of_day_if_date_only: bool = False) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    is_date_only = len(cleaned) == 10 and cleaned[4] == "-" and cleaned[7] == "-"
    if cleaned.endswith("Z"):
        cleaned = f"{cleaned[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    if is_date_only and end_of_day_if_date_only:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _compute_pct_delta(val_a: float, val_b: float) -> tuple[float | None, str]:
    if val_a == 0:
        return None, "N/A (new from zero)"
    pct = round(((val_b - val_a) / val_a) * 100.0, 2)
    return pct, f"{pct:+.2f}%"


def _bucket_label(dt: datetime, granularity: Literal["month", "quarter"]) -> str:
    if granularity == "quarter":
        quarter = ((dt.month - 1) // 3) + 1
        return f"{dt.year}-Q{quarter}"
    return f"{dt.year:04d}-{dt.month:02d}"


class AnalyticsService:
    """Computes `FR-4` library distributions, trends, duration profiles, and deltas."""

    def __init__(
        self,
        provider: YouTubeProvider | None = None,
        quota_guard: QuotaGuard | None = None,
        repo: SQLiteRepository | None = None,
        sanitizer: MetadataSanitizer | None = None,
    ) -> None:
        self.provider = provider
        self.quota_guard = quota_guard
        self.repo = repo
        self.sanitizer = sanitizer or MetadataSanitizer()

    def build_report(
        self,
        *,
        liked_videos: list[VideoMetadata] | None = None,
        subscriptions: list[ChannelMetadata] | None = None,
        playlists: list[PlaylistSummary] | None = None,
        playlist_videos: list[VideoMetadata] | None = None,
        granularity: Literal["month", "quarter"] = "month",
        period_a_start: str | None = None,
        period_a_end: str | None = None,
        period_b_start: str | None = None,
        period_b_end: str | None = None,
        period_days: int = 30,
        compare_previous: bool = True,
        now_utc: datetime | None = None,
    ) -> EngagementReport:
        """Compute all four `FR-4` dimensions cleanly from supplied library collections."""
        likes = liked_videos or []
        subs = subscriptions or []
        user_playlists = playlists or []
        pl_videos = playlist_videos or []

        # Deduplicate video cohort by video_id; subscriptions remain separate from video counts.
        cohort_by_id: dict[str, VideoMetadata] = {}
        for video in [*likes, *pl_videos]:
            cohort_by_id.setdefault(video.video_id, video)
        cohort = list(cohort_by_id.values())

        top_channels = self._compute_top_channels(cohort)
        top_categories, missing_cat_count = self._compute_top_categories(cohort)
        trends = self._compute_trends(cohort, granularity=granularity)
        duration_prefs = self._compute_duration_preferences(cohort)

        comparison: PeriodComparison | None = None
        if compare_previous or all(
            v is not None for v in (period_a_start, period_a_end, period_b_start, period_b_end)
        ):
            comparison = self._compute_period_comparison(
                cohort,
                period_a_start=period_a_start,
                period_a_end=period_a_end,
                period_b_start=period_b_start,
                period_b_end=period_b_end,
                period_days=period_days,
                now_utc=now_utc,
            )

        return EngagementReport(
            liked_video_count=len(likes),
            subscription_count=len(subs),
            playlist_count=len(user_playlists),
            unique_video_count=len(cohort),
            missing_category_count=missing_cat_count,
            top_channels=top_channels,
            top_categories=top_categories,
            trends_over_time=trends,
            duration_preferences=duration_prefs,
            period_comparison=comparison,
        )

    def analyze_engagement(
        self,
        *,
        period_days: int = 30,
        compare_previous: bool = True,
        granularity: Literal["month", "quarter"] = "month",
        period_a_start: str | None = None,
        period_a_end: str | None = None,
        period_b_start: str | None = None,
        period_b_end: str | None = None,
        max_library_items: int = 50,
    ) -> EngagementReport:
        """Fetch user library via `YouTubeProvider` under `QuotaGuard` and build `FR-4` report."""
        provider = self._require_provider()
        quota_guard = self._require_quota_guard()

        bounded_items = max(1, min(max_library_items, 50))
        planned_ops = [
            QuotaOperation("videos.list", count=1, cached=False),
            QuotaOperation("subscriptions.list", count=1, cached=False),
            QuotaOperation("playlists.list", count=1, cached=False),
        ]
        estimated_cost = quota_guard.estimate_cost(planned_ops)
        decision = quota_guard.preflight_check(estimated_cost, "FR-4:analyze_user_engagement")
        quota_used = 0

        liked_videos = provider.get_user_likes(max_results=bounded_items)
        quota_guard.commit_usage("videos.list", 1, "FR-4:analyze_user_engagement")
        quota_used += 1

        subscriptions = provider.get_user_subscriptions(max_results=bounded_items)
        quota_guard.commit_usage("subscriptions.list", 1, "FR-4:analyze_user_engagement")
        quota_used += 1

        playlists = provider.get_user_playlists(max_results=bounded_items)
        quota_guard.commit_usage("playlists.list", 1, "FR-4:analyze_user_engagement")
        quota_used += 1

        if self.repo is not None and liked_videos:
            self.repo.upsert_cached_videos(
                {v.video_id: v.model_dump() for v in liked_videos}
            )

        playlist_video_ids: list[str] = []
        if playlists:
            extra_ops = [QuotaOperation("playlistItems.list", count=len(playlists), cached=False)]
            quota_guard.preflight_check(
                quota_guard.estimate_cost(extra_ops), "FR-4:analyze_user_engagement:playlists"
            )
            for pl in playlists:
                item_ids = provider.get_playlist_items(pl.playlist_id, max_results=bounded_items)
                quota_guard.commit_usage(
                    "playlistItems.list", 1, "FR-4:analyze_user_engagement"
                )
                quota_used += 1
                playlist_video_ids.extend(item_ids)

        known_ids = {v.video_id for v in liked_videos}
        needed_ids = list(dict.fromkeys(vid for vid in playlist_video_ids if vid not in known_ids))
        playlist_videos, fetch_cost = load_videos_with_cache(
            needed_ids,
            provider=provider,
            quota_guard=quota_guard,
            repo=self.repo,
            workflow_context="FR-4:analyze_user_engagement",
        )
        quota_used += fetch_cost

        report = self.build_report(
            liked_videos=liked_videos,
            subscriptions=subscriptions,
            playlists=playlists,
            playlist_videos=playlist_videos,
            granularity=granularity,
            period_a_start=period_a_start,
            period_a_end=period_a_end,
            period_b_start=period_b_start,
            period_b_end=period_b_end,
            period_days=period_days,
            compare_previous=compare_previous,
        )
        return report.model_copy(
            update={
                "quota_used": quota_used,
                "remaining_daily_quota": quota_guard.remaining_budget(),
                "quota_warning": decision.quota_warning,
            }
        )

    def _compute_top_channels(
        self, videos: list[VideoMetadata]
    ) -> list[ChannelDistributionEntry]:
        eligible = [v for v in videos if v.channel_id]
        if not eligible:
            return []
        counts: Counter[str] = Counter()
        titles: dict[str, str] = {}
        for video in eligible:
            counts[video.channel_id] += 1
            if video.channel_id not in titles and video.channel_title:
                titles[video.channel_id] = self.sanitizer.sanitize_text(
                    video.channel_title, max_length=150, preserve_newlines=False
                )

        total = len(eligible)
        entries = [
            ChannelDistributionEntry(
                channel_id=cid,
                channel_title=titles.get(cid, ""),
                count=count,
                percentage=round((count / total) * 100.0, 2),
                untrusted_metadata=True,
            )
            for cid, count in counts.items()
        ]
        entries.sort(key=lambda item: (-item.count, item.channel_id))
        return entries

    @staticmethod
    def _compute_top_categories(
        videos: list[VideoMetadata],
    ) -> tuple[list[CategoryDistributionEntry], int]:
        counts: Counter[str] = Counter()
        missing = 0
        for video in videos:
            if video.category_id and video.category_id.strip():
                counts[video.category_id.strip()] += 1
            else:
                missing += 1

        eligible_total = sum(counts.values())
        if eligible_total == 0:
            return [], missing

        entries = [
            CategoryDistributionEntry(
                category_id=cat_id,
                count=count,
                percentage=round((count / eligible_total) * 100.0, 2),
            )
            for cat_id, count in counts.items()
        ]
        entries.sort(key=lambda item: (-item.count, item.category_id))
        return entries, missing

    @staticmethod
    def _compute_trends(
        videos: list[VideoMetadata],
        *,
        granularity: Literal["month", "quarter"],
    ) -> list[TrendBucket]:
        bucket_counts: Counter[str] = Counter()
        bucket_cats: dict[str, Counter[str]] = defaultdict(Counter)

        for video in videos:
            dt = _parse_utc_datetime(video.published_at)
            if dt is None:
                continue
            label = _bucket_label(dt, granularity)
            bucket_counts[label] += 1
            if video.category_id and video.category_id.strip():
                bucket_cats[label][video.category_id.strip()] += 1

        buckets: list[TrendBucket] = []
        for label in sorted(bucket_counts):
            cat_counter = bucket_cats[label]
            top_cat = (
                min(cat_counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]
                if cat_counter
                else None
            )
            buckets.append(
                TrendBucket(
                    period=label,
                    video_count=bucket_counts[label],
                    top_category_id=top_cat,
                    category_counts=dict(sorted(cat_counter.items())),
                )
            )
        return buckets

    @staticmethod
    def _compute_duration_preferences(videos: list[VideoMetadata]) -> DurationPreferences:
        valid_durations: list[int] = []
        invalid_count = 0
        buckets = DurationBuckets()

        for video in videos:
            seconds = resolve_video_duration_seconds(video)
            if seconds is None:
                invalid_count += 1
                continue
            valid_durations.append(seconds)
            if seconds < 300:
                buckets.short_lt_5m += 1
            elif seconds <= 1199:
                buckets.medium_5m_20m += 1
            elif seconds <= 3600:
                buckets.long_20m_60m += 1
            else:
                buckets.deep_dive_gt_60m += 1

        if not valid_durations:
            return DurationPreferences(
                valid_video_count=0,
                invalid_duration_count=invalid_count,
                buckets=buckets,
            )

        return DurationPreferences(
            valid_video_count=len(valid_durations),
            invalid_duration_count=invalid_count,
            mean_seconds=round(statistics.mean(valid_durations), 2),
            median_seconds=round(float(statistics.median(valid_durations)), 2),
            min_seconds=min(valid_durations),
            max_seconds=max(valid_durations),
            buckets=buckets,
        )

    @staticmethod
    def _compute_period_comparison(
        videos: list[VideoMetadata],
        *,
        period_a_start: str | None,
        period_a_end: str | None,
        period_b_start: str | None,
        period_b_end: str | None,
        period_days: int,
        now_utc: datetime | None,
    ) -> PeriodComparison:
        current = now_utc.astimezone(UTC) if now_utc is not None else datetime.now(UTC)
        a_start = _parse_utc_datetime(period_a_start)
        a_end = _parse_utc_datetime(period_a_end, end_of_day_if_date_only=True)
        b_start = _parse_utc_datetime(period_b_start)
        b_end = _parse_utc_datetime(period_b_end, end_of_day_if_date_only=True)

        if not all(v is not None for v in (a_start, a_end, b_start, b_end)):
            b_end = current
            b_start = current - timedelta(days=period_days)
            a_end = b_start - timedelta(microseconds=1)
            a_start = a_end - timedelta(days=period_days)

        assert a_start is not None and a_end is not None
        assert b_start is not None and b_end is not None

        def summarize(start: datetime, end: datetime) -> PeriodSummary:
            matched: list[VideoMetadata] = []
            for video in videos:
                dt = _parse_utc_datetime(video.published_at)
                if dt is not None and start <= dt <= end:
                    matched.append(video)

            cat_counts = Counter(
                v.category_id.strip()
                for v in matched
                if v.category_id and v.category_id.strip()
            )
            ch_counts = Counter(v.channel_id for v in matched if v.channel_id)
            durations = [
                sec
                for sec in (resolve_video_duration_seconds(v) for v in matched)
                if sec is not None
            ]
            avg_dur = round(statistics.mean(durations), 2) if durations else 0.0
            return PeriodSummary(
                start_utc=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                end_utc=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                video_count=len(matched),
                avg_duration_seconds=avg_dur,
                top_categories=dict(sorted(cat_counts.items())),
                top_channels=dict(sorted(ch_counts.items())),
            )

        summary_a = summarize(a_start, a_end)
        summary_b = summarize(b_start, b_end)

        vol_abs = summary_b.video_count - summary_a.video_count
        vol_pct, vol_display = _compute_pct_delta(summary_a.video_count, summary_b.video_count)

        dur_abs = round(summary_b.avg_duration_seconds - summary_a.avg_duration_seconds, 2)
        dur_pct, dur_display = _compute_pct_delta(
            summary_a.avg_duration_seconds, summary_b.avg_duration_seconds
        )

        def build_key_deltas(
            counts_a: dict[str, int], counts_b: dict[str, int]
        ) -> list[KeyDelta]:
            all_keys = sorted(set(counts_a) | set(counts_b))
            deltas: list[KeyDelta] = []
            for key in all_keys:
                a_val = counts_a.get(key, 0)
                b_val = counts_b.get(key, 0)
                pct, display = _compute_pct_delta(a_val, b_val)
                deltas.append(
                    KeyDelta(
                        key=key,
                        period_a_count=a_val,
                        period_b_count=b_val,
                        absolute_delta=b_val - a_val,
                        percentage_delta=pct,
                        percentage_delta_display=display,
                    )
                )
            return deltas

        return PeriodComparison(
            period_a=summary_a,
            period_b=summary_b,
            volume_absolute_delta=vol_abs,
            volume_percentage_delta=vol_pct,
            volume_percentage_delta_display=vol_display,
            avg_duration_absolute_delta=dur_abs,
            avg_duration_percentage_delta=dur_pct,
            avg_duration_percentage_delta_display=dur_display,
            category_deltas=build_key_deltas(summary_a.top_categories, summary_b.top_categories),
            channel_deltas=build_key_deltas(summary_a.top_channels, summary_b.top_channels),
        )

    def _require_provider(self) -> YouTubeProvider:
        if self.provider is None:
            raise RuntimeError("AnalyticsService requires a YouTubeProvider instance.")
        return self.provider

    def _require_quota_guard(self) -> QuotaGuard:
        if self.quota_guard is None:
            raise RuntimeError("AnalyticsService requires a QuotaGuard instance.")
        return self.quota_guard
