"""Constraint-based playlist curation and two-phase confirmation gate (`FR-5`, `ADR-005`)."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from youtube_mcp.exceptions import (
    ConfirmationRequiredError,
    YouTubeSignupRequiredError,
)
from youtube_mcp.models import VideoMetadata
from youtube_mcp.providers.base import YouTubeProvider
from youtube_mcp.quota_guard import QuotaGuard, QuotaOperation
from youtube_mcp.repository import SQLiteRepository, format_utc
from youtube_mcp.sanitizer import InputValidator, MetadataSanitizer
from youtube_mcp.services._cache import load_videos_with_cache
from youtube_mcp.services.duration import resolve_video_duration_seconds
from youtube_mcp.services.similarity import (
    _compute_idf,
    _cosine_and_overlap,
    _to_l2_tfidf_vector,
    _weighted_video_counts,
    normalize_and_tokenize,
)

MAX_PLAYLIST_TITLE_LENGTH = 150
MAX_PLAYLIST_DESCRIPTION_LENGTH = 5000


class ProposedVideoItem(BaseModel):
    """Sanitized candidate video included in a Phase 1 playlist proposal."""

    video_id: str
    title: str
    channel_title: str = ""
    duration_seconds: int
    language: str | None = None
    relevance_score: float
    untrusted_metadata: Literal[True] = True


class PlaylistProposalRequest(BaseModel):
    """Input constraints for Phase 1 `propose_playlist` (`FR-5`)."""

    topic: str = Field(min_length=1)
    max_total_duration_minutes: int = Field(ge=1, le=600)
    max_video_duration_minutes: int | None = Field(default=None, ge=1, le=240)
    language: str | None = None


class PlaylistProposalResponse(BaseModel):
    """Phase 1 proposal response persisted in `pending_playlists` (zero writes)."""

    confirmation_token: str
    expires_at: str
    topic: str
    proposed_videos: list[ProposedVideoItem] = Field(default_factory=list)
    total_duration_seconds: int
    estimated_write_quota_cost: int
    requires_explicit_user_confirmation: Literal[True] = True
    quota_used: int = 0
    remaining_daily_quota: int = 0
    quota_warning: str | None = None


class PlaylistCreatedResponse(BaseModel):
    """Phase 2 execution response after explicit user confirmation (`FR-5`)."""

    status: Literal["COMPLETED"] = "COMPLETED"
    playlist_id: str
    playlist_url: str
    title: str
    privacy_status: str
    items_added: int
    quota_used: int
    remaining_daily_quota: int
    quota_warning: str | None = None


def _video_matches_language(video: VideoMetadata, lang_code: str) -> bool:
    for candidate_lang in (video.default_audio_language, video.default_language):
        if candidate_lang and candidate_lang.strip():
            primary = candidate_lang.strip().split("-", 1)[0].split("_", 1)[0].lower()
            if primary == lang_code:
                return True
    return False


class PlaylistService:
    """Implements constrained knapsack packing and the `FR-5` two-phase confirmation gate.

    Exposes only non-destructive `propose_playlist` and `confirm_playlist` operations (`NFR-SAFE-2`).
    """

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

    @staticmethod
    def filter_candidates(
        candidates: list[VideoMetadata],
        *,
        max_video_seconds: int | None = None,
        language: str | None = None,
    ) -> list[tuple[VideoMetadata, int]]:
        """Filter videos by strict ISO-8601 duration, per-video cap, and ISO 639-1 language."""
        normalized_lang = (
            InputValidator.validate_language_code(language)
            if language is not None and language.strip()
            else None
        )

        eligible: list[tuple[VideoMetadata, int]] = []
        seen_ids: set[str] = set()
        for video in candidates:
            if video.video_id in seen_ids:
                continue
            seen_ids.add(video.video_id)

            duration_sec = resolve_video_duration_seconds(video)
            if duration_sec is None or duration_sec <= 0:
                continue
            if max_video_seconds is not None and duration_sec > max_video_seconds:
                continue
            if normalized_lang is not None and not _video_matches_language(video, normalized_lang):
                continue

            eligible.append((video, duration_sec))
        return eligible

    @staticmethod
    def pack_videos_knapsack(
        scored_candidates: list[tuple[VideoMetadata, int, float]],
        *,
        max_total_seconds: int,
    ) -> list[tuple[VideoMetadata, int, float]]:
        """Select optimal subset maximizing cumulative score with `sum(duration) <= max_total_seconds`.

        Uses exact 0/1 dynamic programming (GCD-scaled when possible, or bounded ceiling
        discretization for very large budgets so the total duration limit is never exceeded).
        """
        if max_total_seconds <= 0 or not scored_candidates:
            return []

        items = [
            (video, dur, max(0.0, float(score)))
            for video, dur, score in scored_candidates
            if 0 < dur <= max_total_seconds
        ]
        if not items:
            return []

        # Deterministic ordering before DP so equal-score subsets break ties predictably.
        items.sort(key=lambda item: (-item[2], item[1], item[0].video_id))

        gcd_val = math.gcd(max_total_seconds, *(dur for _, dur, _ in items))
        scaled_capacity = max_total_seconds // gcd_val
        step_multiplier = 1
        if scaled_capacity > 2_500:
            step_multiplier = math.ceil(scaled_capacity / 2_500)
        unit_seconds = gcd_val * step_multiplier

        dp_capacity = max_total_seconds // unit_seconds
        if dp_capacity <= 0:
            return []

        weights = [math.ceil(dur / unit_seconds) for _, dur, _ in items]

        # Track DP values alongside chosen item indices per weight bucket.
        dp_scores: list[float] = [-1.0] * (dp_capacity + 1)
        dp_choices: list[list[int]] = [[] for _ in range(dp_capacity + 1)]
        dp_scores[0] = 0.0

        for idx, ((_, _, score), weight) in enumerate(zip(items, weights, strict=True)):
            if weight > dp_capacity:
                continue
            for cap in range(dp_capacity, weight - 1, -1):
                prev_score = dp_scores[cap - weight]
                if prev_score < 0.0:
                    continue
                candidate_score = prev_score + score
                if candidate_score > dp_scores[cap] + 1e-12:
                    dp_scores[cap] = candidate_score
                    dp_choices[cap] = [*dp_choices[cap - weight], idx]

        best_cap = max(range(dp_capacity + 1), key=lambda cap: (dp_scores[cap], -cap))
        selected_indices = dp_choices[best_cap]
        selected = [items[idx] for idx in selected_indices]

        # Defensive guard: strictly enforce actual seconds <= max_total_seconds.
        assert sum(dur for _, dur, _ in selected) <= max_total_seconds
        return selected

    def propose_playlist(
        self,
        request: PlaylistProposalRequest,
        *,
        candidates: list[VideoMetadata] | None = None,
        candidate_scores: dict[str, float] | None = None,
        now: datetime | None = None,
    ) -> PlaylistProposalResponse:
        """Phase 1 (`FR-5`): filter, pack via 0/1 knapsack, sanitize, and persist PENDING draft.

        Makes ZERO write calls (`playlists.insert` / `playlistItems.insert`) to YouTube.
        """
        topic = self.sanitizer.sanitize_text(
            request.topic, max_length=150, preserve_newlines=False
        )
        if not topic:
            raise ValueError("Playlist topic cannot be empty.")

        normalized_lang = (
            InputValidator.validate_language_code(request.language)
            if request.language is not None and request.language.strip()
            else None
        )
        max_total_seconds = request.max_total_duration_minutes * 60
        max_video_seconds = (
            request.max_video_duration_minutes * 60
            if request.max_video_duration_minutes is not None
            else None
        )

        quota_guard = self._require_quota_guard()
        repo = self._require_repo()
        quota_used = 0
        quota_warning: str | None = None

        if candidates is not None:
            raw_candidates = candidates
        else:
            provider = self._require_provider()
            planned = [
                QuotaOperation("search.list", count=1, cached=False),
                QuotaOperation("videos.list", count=1, cached=False),
            ]
            decision = quota_guard.preflight_check(
                quota_guard.estimate_cost(planned), "FR-5:propose_playlist"
            )
            quota_warning = decision.quota_warning

            search_page = provider.search_videos(
                topic, max_results=25, language=normalized_lang
            )
            quota_guard.commit_usage("search.list", 100, "FR-5:propose_playlist", now=now)
            quota_used += 100

            raw_candidates, vid_cost = load_videos_with_cache(
                search_page.video_ids,
                provider=provider,
                quota_guard=quota_guard,
                repo=repo,
                workflow_context="FR-5:propose_playlist",
            )
            quota_used += vid_cost

        eligible = self.filter_candidates(
            raw_candidates,
            max_video_seconds=max_video_seconds,
            language=normalized_lang,
        )
        scored = self._score_candidates_for_topic(
            topic, eligible, explicit_scores=candidate_scores
        )
        selected = self.pack_videos_knapsack(scored, max_total_seconds=max_total_seconds)

        proposed_items: list[ProposedVideoItem] = []
        selected_ids: list[str] = []
        total_duration_seconds = 0

        for video, dur_sec, score in selected:
            sanitized = self.sanitizer.sanitize_video(video)
            selected_ids.append(sanitized.video_id)
            total_duration_seconds += dur_sec
            proposed_items.append(
                ProposedVideoItem(
                    video_id=sanitized.video_id,
                    title=sanitized.title,
                    channel_title=sanitized.channel_title,
                    duration_seconds=dur_sec,
                    language=video.default_audio_language or video.default_language,
                    relevance_score=round(score, 6),
                    untrusted_metadata=True,
                )
            )

        draft = repo.create_pending_playlist(
            topic=topic,
            constraints={
                "max_total_duration_minutes": request.max_total_duration_minutes,
                "max_video_duration_minutes": request.max_video_duration_minutes,
                "language": normalized_lang,
            },
            selected_video_ids=selected_ids,
            total_duration_seconds=total_duration_seconds,
            now=now,
        )

        return PlaylistProposalResponse(
            confirmation_token=draft.confirmation_token,
            expires_at=draft.expires_at,
            topic=topic,
            proposed_videos=proposed_items,
            total_duration_seconds=total_duration_seconds,
            estimated_write_quota_cost=draft.estimated_quota_cost,
            requires_explicit_user_confirmation=True,
            quota_used=quota_used,
            remaining_daily_quota=quota_guard.remaining_budget(),
            quota_warning=quota_warning,
        )

    def confirm_playlist(
        self,
        *,
        confirmation_token: str,
        user_confirmed: bool,
        playlist_title: str,
        playlist_description: str = "",
        privacy_status: Literal["private", "unlisted", "public"] = "private",
        now: datetime | None = None,
    ) -> PlaylistCreatedResponse:
        """Phase 2 (`FR-5`): verify explicit confirmation, token TTL/replay, and `50 + 50N` quota."""
        if user_confirmed is not True:
            raise ConfirmationRequiredError(
                "Explicit user_confirmed=True is required before creating a YouTube playlist."
            )
        if not isinstance(confirmation_token, str) or not confirmation_token.strip():
            raise ConfirmationRequiredError("A valid playlist confirmation_token is required.")

        repo = self._require_repo()
        quota_guard = self._require_quota_guard()
        provider = self._require_provider()
        token = confirmation_token.strip()

        draft = repo.get_pending_playlist(token)
        if draft is None:
            raise ConfirmationRequiredError(
                "Unknown playlist confirmation token.",
                remediation="Run propose_playlist to generate a valid confirmation token.",
            )
        if draft.status != "PENDING":
            raise ConfirmationRequiredError(
                f"Confirmation token cannot be reused (status={draft.status}).",
                remediation="Run propose_playlist again to create a fresh draft.",
            )

        now_iso = format_utc(now)
        if draft.expires_at <= now_iso:
            # Transition atomically to EXPIRED and reject.
            repo.transition_pending_playlist(token, "EXPIRED", now=now)
            raise ConfirmationRequiredError(
                "Playlist confirmation token has expired (>15 minutes).",
                remediation="Run propose_playlist again and confirm within 15 minutes.",
            )

        required_write_cost = quota_guard.estimate_playlist_write_cost(
            len(draft.selected_video_ids)
        )
        decision = quota_guard.preflight_check(
            required_write_cost, "FR-5:confirm_playlist"
        )

        # Atomically claim the single-use PENDING token before performing external writes so
        # concurrent invocations cannot replay the same token.
        repo.transition_pending_playlist(token, "COMPLETED", now=now)

        safe_title = self.sanitizer.sanitize_text(
            playlist_title, max_length=MAX_PLAYLIST_TITLE_LENGTH, preserve_newlines=False
        )
        if not safe_title:
            safe_title = draft.topic[:MAX_PLAYLIST_TITLE_LENGTH]
        safe_description = self.sanitizer.sanitize_text(
            playlist_description,
            max_length=MAX_PLAYLIST_DESCRIPTION_LENGTH,
            preserve_newlines=True,
        )

        current_utc = now.astimezone(UTC) if now is not None else datetime.now(UTC)
        quota_used = 0
        try:
            created = provider.create_playlist(
                title=safe_title,
                description=safe_description,
                privacy_status=privacy_status,
            )
            quota_guard.commit_usage(
                "playlists.insert", 50, "FR-5:confirm_playlist", now=current_utc
            )
            quota_used += 50

            for video_id in draft.selected_video_ids:
                provider.add_playlist_item(created.playlist_id, video_id)
                quota_guard.commit_usage(
                    "playlistItems.insert", 50, "FR-5:confirm_playlist", now=current_utc
                )
                quota_used += 50
        except YouTubeSignupRequiredError:
            self._mark_failed_best_effort(token)
            raise

        return PlaylistCreatedResponse(
            status="COMPLETED",
            playlist_id=created.playlist_id,
            playlist_url=created.url,
            title=safe_title,
            privacy_status=created.privacy_status,
            items_added=len(draft.selected_video_ids),
            quota_used=quota_used,
            remaining_daily_quota=quota_guard.remaining_budget(),
            quota_warning=decision.quota_warning,
        )

    def _mark_failed_best_effort(self, token: str) -> None:
        if self.repo is None:
            return
        with self.repo.write_transaction() as conn:
            conn.execute(
                "UPDATE pending_playlists SET status = 'FAILED' WHERE confirmation_token = ?;",
                (token,),
            )

    @staticmethod
    def _score_candidates_for_topic(
        topic: str,
        eligible: list[tuple[VideoMetadata, int]],
        *,
        explicit_scores: dict[str, float] | None,
    ) -> list[tuple[VideoMetadata, int, float]]:
        if not eligible:
            return []
        if explicit_scores is not None:
            return [
                (video, dur, float(explicit_scores.get(video.video_id, 0.5)))
                for video, dur in eligible
            ]

        topic_tokens = normalize_and_tokenize(topic)
        if not topic_tokens:
            return [(video, dur, 1.0) for video, dur in eligible]

        from collections import Counter

        topic_counts = Counter(topic_tokens)
        doc_counts = [topic_counts] + [_weighted_video_counts(video) for video, _ in eligible]
        idf = _compute_idf(doc_counts)
        topic_vec = _to_l2_tfidf_vector(topic_counts, idf)

        scored: list[tuple[VideoMetadata, int, float]] = []
        for (video, dur), counts in zip(eligible, doc_counts[1:], strict=True):
            cand_vec = _to_l2_tfidf_vector(counts, idf)
            sim, _ = _cosine_and_overlap(topic_vec, cand_vec)
            # Keep every eligible video positively weighted so packing still fills target duration.
            scored.append((video, dur, max(0.05, sim)))
        return scored

    def _require_provider(self) -> YouTubeProvider:
        if self.provider is None:
            raise RuntimeError("PlaylistService requires a YouTubeProvider instance.")
        return self.provider

    def _require_quota_guard(self) -> QuotaGuard:
        if self.quota_guard is None:
            raise RuntimeError("PlaylistService requires a QuotaGuard instance.")
        return self.quota_guard

    def _require_repo(self) -> SQLiteRepository:
        if self.repo is None:
            raise RuntimeError("PlaylistService requires a SQLiteRepository instance.")
        return self.repo
