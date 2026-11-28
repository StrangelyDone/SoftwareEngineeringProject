"""Personalized recommendation engine (`FR-3`, `REQ-FR3-1`..`5`)."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from youtube_mcp.models import ChannelMetadata, VideoMetadata
from youtube_mcp.providers.base import YouTubeProvider
from youtube_mcp.quota_guard import QuotaGuard, QuotaOperation
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.sanitizer import MetadataSanitizer
from youtube_mcp.services._cache import load_videos_with_cache
from youtube_mcp.services.duration import resolve_video_duration_seconds
from youtube_mcp.services.similarity import (
    SimilarityService,
    _compute_idf,
    _cosine_and_overlap,
    _to_l2_tfidf_vector,
    _weighted_video_counts,
    normalize_and_tokenize,
)


class ProfileSummary(BaseModel):
    """Summary of the computed User Interest Profile."""

    top_topics: list[str] = Field(default_factory=list)
    preferred_categories: list[str] = Field(default_factory=list)
    preferred_median_duration_seconds: int | None = None
    source_counts: dict[str, int] = Field(default_factory=dict)


class RecommendationItem(BaseModel):
    """Single unseen recommended video with human-readable explanation (`FR-3`)."""

    video_id: str
    title: str
    channel_id: str = ""
    channel_title: str = ""
    duration_seconds: int | None = None
    relevance_score: float
    matching_terms: list[str] = Field(default_factory=list)
    explanation: str
    untrusted_metadata: Literal[True] = True


class RecommendationsResponse(BaseModel):
    """Output schema for `get_recommendations` (`docs/architecture.md` §6.1)."""

    profile_summary: ProfileSummary
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    quota_used: int = 0
    remaining_daily_quota: int = 0
    quota_warning: str | None = None


class UserInterestProfile(BaseModel):
    """Recency-weighted user interest vector and library metadata preferences."""

    tfidf_centroid: dict[str, float] = Field(default_factory=dict)
    idf_map: dict[str, float] = Field(default_factory=dict)
    preferred_categories: dict[str, float] = Field(default_factory=dict)
    subscribed_channel_ids: set[str] = Field(default_factory=set)
    subscribed_channel_titles: dict[str, str] = Field(default_factory=dict)
    seen_video_ids: set[str] = Field(default_factory=set)
    median_duration_seconds: int | None = None
    top_topics: list[str] = Field(default_factory=list)


class RecommendationService:
    """Recommends unseen videos aligned with a user's likes, subscriptions, and playlists."""

    def __init__(
        self,
        provider: YouTubeProvider | None = None,
        quota_guard: QuotaGuard | None = None,
        repo: SQLiteRepository | None = None,
        similarity: SimilarityService | None = None,
        sanitizer: MetadataSanitizer | None = None,
    ) -> None:
        self.provider = provider
        self.quota_guard = quota_guard
        self.repo = repo
        self.similarity = similarity or SimilarityService(
            provider=provider, quota_guard=quota_guard, repo=repo, sanitizer=sanitizer
        )
        self.sanitizer = sanitizer or MetadataSanitizer()

    def build_interest_profile(
        self,
        *,
        liked_videos: list[VideoMetadata] | None = None,
        subscriptions: list[ChannelMetadata] | None = None,
        playlist_videos: list[VideoMetadata] | None = None,
    ) -> UserInterestProfile:
        """Build a recency-weighted TF-IDF centroid, category weights, and duration preference."""
        likes = liked_videos or []
        subs = subscriptions or []
        pl_vids = playlist_videos or []

        seen_ids = {v.video_id for v in likes} | {v.video_id for v in pl_vids}

        # Deduplicate profile source videos, keeping newest published_at first for recency weights.
        source_by_id: dict[str, VideoMetadata] = {}
        for video in [*likes, *pl_vids]:
            source_by_id.setdefault(video.video_id, video)

        ordered_sources = sorted(
            source_by_id.values(),
            key=lambda v: v.published_at or "",
            reverse=True,
        )

        centroid: dict[str, float] = {}
        idf_map: dict[str, float] = {}
        cat_weights: Counter[str] = Counter()
        durations: list[int] = []

        if ordered_sources:
            doc_counts = [_weighted_video_counts(video) for video in ordered_sources]
            idf_map = _compute_idf(doc_counts)
            accum: dict[str, float] = {}

            for rank_idx, (video, counts) in enumerate(
                zip(ordered_sources, doc_counts, strict=True)
            ):
                recency_weight = 1.0 / (1.0 + (0.15 * rank_idx))
                vec = _to_l2_tfidf_vector(counts, idf_map)
                for term, val in vec.items():
                    accum[term] = accum.get(term, 0.0) + (recency_weight * val)

                if video.category_id and video.category_id.strip():
                    cat_weights[video.category_id.strip()] += recency_weight  # type: ignore[assignment]

                dur = resolve_video_duration_seconds(video)
                if dur is not None and dur > 0:
                    durations.append(dur)

            norm_sq = sum(val * val for val in accum.values())
            if norm_sq > 0.0:
                inv_norm = 1.0 / math.sqrt(norm_sq)
                centroid = {term: val * inv_norm for term, val in accum.items()}

        total_cat_weight = sum(cat_weights.values())
        preferred_categories = (
            {cat: round(w / total_cat_weight, 4) for cat, w in cat_weights.items()}
            if total_cat_weight > 0
            else {}
        )

        top_topics = [
            term
            for term, _ in sorted(centroid.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        ]

        sub_ids = {ch.channel_id for ch in subs if ch.channel_id}
        sub_titles = {
            ch.channel_id: self.sanitizer.sanitize_text(
                ch.title, max_length=150, preserve_newlines=False
            )
            for ch in subs
            if ch.channel_id
        }
        median_dur = round(float(statistics.median(durations))) if durations else None

        return UserInterestProfile(
            tfidf_centroid=centroid,
            idf_map=idf_map,
            preferred_categories=preferred_categories,
            subscribed_channel_ids=sub_ids,
            subscribed_channel_titles=sub_titles,
            seen_video_ids=seen_ids,
            median_duration_seconds=median_dur,
            top_topics=top_topics,
        )

    def rank_recommendations(
        self,
        profile: UserInterestProfile,
        candidates: list[VideoMetadata],
        *,
        limit: int = 10,
        focus_topic: str | None = None,
    ) -> list[RecommendationItem]:
        """Exclude seen videos and rank unseen candidates against the User Interest Profile."""
        if limit <= 0:
            return []

        focus_tokens = (
            set(normalize_and_tokenize(focus_topic)) if focus_topic and focus_topic.strip() else set()
        )

        unseen: list[VideoMetadata] = []
        seen_cand_ids: set[str] = set()
        for cand in candidates:
            if cand.video_id in profile.seen_video_ids or cand.video_id in seen_cand_ids:
                continue
            seen_cand_ids.add(cand.video_id)

            if focus_tokens:
                cand_text_tokens = set(
                    normalize_and_tokenize(
                        f"{cand.title} {cand.description} {' '.join(cand.tags)} {cand.channel_title}"
                    )
                )
                if not (focus_tokens & cand_text_tokens):
                    continue

            unseen.append(cand)

        if not unseen:
            return []

        cand_counts = [_weighted_video_counts(cand) for cand in unseen]
        local_idf = _compute_idf(cand_counts)
        merged_idf = {**local_idf, **profile.idf_map}

        focus_vec: dict[str, float] = {}
        if focus_tokens:
            focus_counts = Counter(focus_tokens)
            focus_vec = _to_l2_tfidf_vector(focus_counts, merged_idf)

        scored: list[RecommendationItem] = []
        for cand, counts in zip(unseen, cand_counts, strict=True):
            cand_vec = _to_l2_tfidf_vector(counts, merged_idf)
            profile_sim, matching_terms = _cosine_and_overlap(profile.tfidf_centroid, cand_vec)

            if focus_vec:
                focus_sim, focus_shared = _cosine_and_overlap(focus_vec, cand_vec)
                text_score = (0.7 * profile_sim) + (0.3 * focus_sim)
                matching_terms = list(dict.fromkeys([*focus_shared, *matching_terms]))[:8]
            else:
                text_score = profile_sim

            cat_score = (
                profile.preferred_categories.get(cand.category_id, 0.0)
                if cand.category_id
                else 0.0
            )
            sub_boost = 1.0 if cand.channel_id in profile.subscribed_channel_ids else 0.0

            dur_seconds = resolve_video_duration_seconds(cand)
            dur_fit = 0.0
            if (
                profile.median_duration_seconds is not None
                and dur_seconds is not None
                and dur_seconds > 0
            ):
                denom = max(profile.median_duration_seconds, dur_seconds, 1)
                dur_fit = 1.0 - min(1.0, abs(profile.median_duration_seconds - dur_seconds) / denom)

            relevance = (0.60 * text_score) + (0.15 * cat_score) + (0.15 * sub_boost) + (0.10 * dur_fit)

            sanitized = self.sanitizer.sanitize_video(cand)
            explanation = self._build_explanation(
                profile=profile,
                sanitized_channel_title=sanitized.channel_title,
                channel_id=cand.channel_id,
                category_id=cand.category_id,
                dur_seconds=dur_seconds,
                dur_fit=dur_fit,
                matching_terms=matching_terms,
                focus_topic=focus_topic,
            )

            scored.append(
                RecommendationItem(
                    video_id=sanitized.video_id,
                    title=sanitized.title,
                    channel_id=sanitized.channel_id,
                    channel_title=sanitized.channel_title,
                    duration_seconds=dur_seconds,
                    relevance_score=round(relevance, 6),
                    matching_terms=matching_terms[:8],
                    explanation=explanation,
                    untrusted_metadata=True,
                )
            )

        scored.sort(key=lambda item: (-item.relevance_score, item.video_id))
        return scored[:limit]

    def recommend_for_user(
        self,
        limit: int = 10,
        *,
        focus_topic: str | None = None,
        candidates: list[VideoMetadata] | None = None,
        max_library_items: int = 50,
    ) -> RecommendationsResponse:
        """Fetch user library under `QuotaGuard`, build interest profile, and rank unseen videos."""
        provider = self._require_provider()
        quota_guard = self._require_quota_guard()

        bounded_limit = max(1, min(limit, 25))
        bounded_lib = max(1, min(max_library_items, 50))

        planned_ops: list[QuotaOperation] = [
            QuotaOperation("videos.list", count=1, cached=False),
            QuotaOperation("subscriptions.list", count=1, cached=False),
            QuotaOperation("playlists.list", count=1, cached=False),
        ]
        if candidates is None:
            planned_ops.append(QuotaOperation("search.list", count=1, cached=False))

        decision = quota_guard.preflight_check(
            quota_guard.estimate_cost(planned_ops), "FR-3:get_recommendations"
        )
        quota_used = 0

        liked_videos = provider.get_user_likes(max_results=bounded_lib)
        quota_guard.commit_usage("videos.list", 1, "FR-3:get_recommendations")
        quota_used += 1

        subscriptions = provider.get_user_subscriptions(max_results=bounded_lib)
        quota_guard.commit_usage("subscriptions.list", 1, "FR-3:get_recommendations")
        quota_used += 1

        playlists = provider.get_user_playlists(max_results=bounded_lib)
        quota_guard.commit_usage("playlists.list", 1, "FR-3:get_recommendations")
        quota_used += 1

        if self.repo is not None and liked_videos:
            self.repo.upsert_cached_videos(
                {v.video_id: v.model_dump() for v in liked_videos}
            )

        playlist_video_ids: list[str] = []
        if playlists:
            pl_ops = [QuotaOperation("playlistItems.list", count=len(playlists))]
            quota_guard.preflight_check(
                quota_guard.estimate_cost(pl_ops), "FR-3:get_recommendations:playlists"
            )
            for pl in playlists:
                item_ids = provider.get_playlist_items(pl.playlist_id, max_results=bounded_lib)
                quota_guard.commit_usage("playlistItems.list", 1, "FR-3:get_recommendations")
                quota_used += 1
                playlist_video_ids.extend(item_ids)

        known_by_id = {v.video_id: v for v in liked_videos}
        needed_pl_ids = list(
            dict.fromkeys(vid for vid in playlist_video_ids if vid not in known_by_id)
        )
        playlist_videos, pl_vid_cost = load_videos_with_cache(
            needed_pl_ids,
            provider=provider,
            quota_guard=quota_guard,
            repo=self.repo,
            workflow_context="FR-3:get_recommendations",
        )
        quota_used += pl_vid_cost

        profile = self.build_interest_profile(
            liked_videos=liked_videos,
            subscriptions=subscriptions,
            playlist_videos=playlist_videos,
        )

        if candidates is not None:
            candidate_pool = candidates
        else:
            candidate_ids: list[str] = []
            for ch in subscriptions:
                if ch.uploads_playlist_id:
                    quota_guard.preflight_check(
                        quota_guard.estimate_cost([QuotaOperation("playlistItems.list", count=1)]),
                        "FR-3:get_recommendations:sub_uploads",
                    )
                    up_ids = provider.get_playlist_items(ch.uploads_playlist_id, max_results=10)
                    quota_guard.commit_usage(
                        "playlistItems.list", 1, "FR-3:get_recommendations"
                    )
                    quota_used += 1
                    candidate_ids.extend(up_ids)

            query = (
                focus_topic.strip()
                if focus_topic and focus_topic.strip()
                else (" ".join(profile.top_topics[:2]) if profile.top_topics else "technology")
            )
            search_page = provider.search_videos(query, max_results=25)
            quota_guard.commit_usage("search.list", 100, "FR-3:get_recommendations")
            quota_used += 1
            candidate_ids.extend(search_page.video_ids)

            unseen_cand_ids = list(
                dict.fromkeys(vid for vid in candidate_ids if vid not in profile.seen_video_ids)
            )
            candidate_pool, cand_cost = load_videos_with_cache(
                unseen_cand_ids,
                provider=provider,
                quota_guard=quota_guard,
                repo=self.repo,
                workflow_context="FR-3:get_recommendations",
            )
            quota_used += cand_cost

        ranked = self.rank_recommendations(
            profile,
            candidate_pool,
            limit=bounded_limit,
            focus_topic=focus_topic,
        )
        summary = ProfileSummary(
            top_topics=profile.top_topics,
            preferred_categories=list(
                dict(
                    sorted(profile.preferred_categories.items(), key=lambda kv: (-kv[1], kv[0]))
                ).keys()
            ),
            preferred_median_duration_seconds=profile.median_duration_seconds,
            source_counts={
                "likes": len(liked_videos),
                "subscriptions": len(subscriptions),
                "playlists": len(playlists),
            },
        )
        return RecommendationsResponse(
            profile_summary=summary,
            recommendations=ranked,
            quota_used=quota_used,
            remaining_daily_quota=quota_guard.remaining_budget(),
            quota_warning=decision.quota_warning,
        )

    @staticmethod
    def _build_explanation(
        *,
        profile: UserInterestProfile,
        sanitized_channel_title: str,
        channel_id: str,
        category_id: str | None,
        dur_seconds: int | None,
        dur_fit: float,
        matching_terms: list[str],
        focus_topic: str | None,
    ) -> str:
        reasons: list[str] = []
        if matching_terms:
            reasons.append(f"matches interest topics ({', '.join(matching_terms[:4])})")
        if focus_topic and focus_topic.strip():
            reasons.append(f"aligns with focus topic '{focus_topic.strip()}'")
        if channel_id in profile.subscribed_channel_ids:
            ch_label = (
                profile.subscribed_channel_titles.get(channel_id)
                or sanitized_channel_title
                or channel_id
            )
            reasons.append(f"from subscribed channel '{ch_label}'")
        if category_id and category_id in profile.preferred_categories:
            reasons.append(f"fits preferred category {category_id}")
        if dur_seconds is not None and dur_fit >= 0.6 and profile.median_duration_seconds:
            reasons.append(
                f"duration ({dur_seconds}s) matches typical length (~{profile.median_duration_seconds}s)"
            )
        if not reasons:
            return "Recommended as an unseen candidate aligned with your overall library profile."
        return "Recommended because it " + "; ".join(reasons) + "."

    def _require_provider(self) -> YouTubeProvider:
        if self.provider is None:
            raise RuntimeError("RecommendationService requires a YouTubeProvider instance.")
        return self.provider

    def _require_quota_guard(self) -> QuotaGuard:
        if self.quota_guard is None:
            raise RuntimeError("RecommendationService requires a QuotaGuard instance.")
        return self.quota_guard
