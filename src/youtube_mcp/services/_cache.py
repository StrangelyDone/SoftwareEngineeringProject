"""Shared provider-plus-SQLite video/channel batch cache loader for domain services."""

from __future__ import annotations

from youtube_mcp.models import VideoMetadata
from youtube_mcp.providers.base import YouTubeProvider
from youtube_mcp.quota_guard import QuotaGuard, QuotaOperation
from youtube_mcp.repository import SQLiteRepository


def load_videos_with_cache(
    video_ids: list[str],
    *,
    provider: YouTubeProvider,
    quota_guard: QuotaGuard,
    repo: SQLiteRepository | None,
    workflow_context: str,
    preflight_batches: bool = True,
) -> tuple[list[VideoMetadata], int]:
    """Load `video_ids` from SQLite cache first, batching misses at 50 IDs per unit."""
    if not video_ids:
        return [], 0

    cached = repo.get_cached_videos(video_ids) if repo is not None else {}
    uncached = [vid for vid in video_ids if vid not in cached]
    fetched: dict[str, VideoMetadata] = {}
    cost = 0

    if uncached:
        if preflight_batches:
            batches = (len(uncached) + 49) // 50
            quota_guard.preflight_check(
                quota_guard.estimate_cost([QuotaOperation("videos.list", count=batches)]),
                workflow_context,
            )

        for idx in range(0, len(uncached), 50):
            batch = uncached[idx : idx + 50]
            for video in provider.get_videos(batch):
                fetched[video.video_id] = video
            quota_guard.commit_usage("videos.list", 1, workflow_context)
            cost += 1

        if repo is not None and fetched:
            repo.upsert_cached_videos(
                {vid: model.model_dump() for vid, model in fetched.items()}
            )

    ordered: list[VideoMetadata] = []
    for vid in video_ids:
        if vid in cached:
            ordered.append(VideoMetadata.model_validate(cached[vid]))
        elif vid in fetched:
            ordered.append(fetched[vid])
    return ordered, cost
