"""Deterministic metadata similarity service for FR-1 and FR-2 (`ADR-004`, `TBD-02`)."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from youtube_mcp.exceptions import VideoUnavailableError
from youtube_mcp.models import ChannelMetadata, VideoMetadata
from youtube_mcp.providers.base import YouTubeProvider
from youtube_mcp.quota_guard import QuotaGuard, QuotaOperation
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.sanitizer import InputValidator, MetadataSanitizer

DEFAULT_W_TFIDF = 0.65
DEFAULT_W_TAGS = 0.25
DEFAULT_W_CATEGORY = 0.10

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "these",
        "those",
        "to",
        "was",
        "were",
        "will",
        "with",
        "you",
        "your",
    }
)


class ScoreBreakdown(BaseModel):
    """Per-signal breakdown for composite video/channel similarity."""

    tfidf: float
    tags: float
    category: float
    effective_weights: tuple[float, float, float]


class SimilarityScore(BaseModel):
    """Pairwise composite similarity score and matching explanations."""

    composite_score: float
    breakdown: ScoreBreakdown
    matching_terms: list[str] = Field(default_factory=list)


class SimilarVideoItem(BaseModel):
    """Ranked similar video item (`docs/architecture.md` §6.1)."""

    video_id: str
    title: str
    channel_title: str = ""
    duration_seconds: int | None = None
    similarity_score: float
    score_breakdown: ScoreBreakdown
    matching_terms: list[str] = Field(default_factory=list)
    untrusted_metadata: Literal[True] = True


class SimilarVideosResponse(BaseModel):
    """Output schema for `find_similar_videos` (`FR-1`)."""

    seed_video_id: str
    results: list[SimilarVideoItem] = Field(default_factory=list)
    quota_used: int = 0
    remaining_daily_quota: int
    quota_warning: str | None = None


class SimilarChannelItem(BaseModel):
    """Ranked similar channel item (`docs/architecture.md` §6.1 / `REQ-FR2-5`)."""

    channel_id: str
    title: str
    handle: str | None = None
    subscriber_count: int | None = None
    similarity_score: float
    matching_topics: list[str] = Field(default_factory=list)
    avg_upload_duration_seconds: int | None = None
    untrusted_metadata: Literal[True] = True

    @property
    def shared_topics(self) -> list[str]:
        """Compatibility alias matching `REQ-FR2-5` terminology."""
        return self.matching_topics


class SimilarChannelsResponse(BaseModel):
    """Output schema for `find_similar_channels` (`FR-2`)."""

    seed_channel_id: str
    results: list[SimilarChannelItem] = Field(default_factory=list)
    quota_used: int = 0
    remaining_daily_quota: int
    quota_warning: str | None = None


def normalize_and_tokenize(text: str) -> list[str]:
    """Normalize text to Unicode NFC, strip URLs/HTML, lowercase, and tokenize."""
    if not text:
        return []
    cleaned = unicodedata.normalize("NFC", text)
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = cleaned.casefold()
    tokens = _TOKEN_RE.findall(cleaned)
    return [tok for tok in tokens if tok not in _STOPWORDS]


def _normalize_terms(terms: list[str]) -> set[str]:
    normalized: set[str] = set()
    for term in terms:
        cleaned = unicodedata.normalize("NFC", term).casefold().strip()
        if cleaned:
            normalized.add(cleaned)
    return normalized


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _weighted_video_counts(video: VideoMetadata) -> Counter[str]:
    """Build term counts with 2x weight on title and 1x weight on description (`REQ-FR1-4`)."""
    counts: Counter[str] = Counter()
    for token in normalize_and_tokenize(video.title):
        counts[token] += 2
    for token in normalize_and_tokenize(video.description):
        counts[token] += 1
    return counts


def _weighted_channel_counts(
    channel: ChannelMetadata,
    uploads: list[VideoMetadata] | None = None,
) -> Counter[str]:
    """Build aggregated channel document counts (`REQ-FR2-3`)."""
    counts: Counter[str] = Counter()
    for token in normalize_and_tokenize(channel.title):
        counts[token] += 2
    for token in normalize_and_tokenize(channel.description):
        counts[token] += 1
    for keyword in channel.keywords:
        for token in normalize_and_tokenize(keyword):
            counts[token] += 1
    for topic in channel.topic_categories:
        for token in normalize_and_tokenize(topic):
            counts[token] += 1
    if uploads:
        for video in uploads:
            for token in normalize_and_tokenize(video.title):
                counts[token] += 1
            for tag in video.tags:
                for token in normalize_and_tokenize(tag):
                    counts[token] += 1
    return counts


def _compute_idf(doc_counts: list[Counter[str]]) -> dict[str, float]:
    """Compute smoothed IDF: `ln((N + 1) / (df(t) + 1)) + 1` (`ADR-004`)."""
    total_docs = len(doc_counts)
    df: Counter[str] = Counter()
    for counts in doc_counts:
        for term in counts:
            df[term] += 1
    return {
        term: math.log((total_docs + 1.0) / (term_df + 1.0)) + 1.0
        for term, term_df in df.items()
    }


def _to_l2_tfidf_vector(counts: Counter[str], idf: dict[str, float]) -> dict[str, float]:
    """Convert weighted term counts to an L2-normalized TF-IDF vector."""
    total_terms = sum(counts.values())
    if total_terms == 0:
        return {}
    raw: dict[str, float] = {}
    norm_sq = 0.0
    for term, count in counts.items():
        weight = (count / total_terms) * idf.get(term, 1.0)
        raw[term] = weight
        norm_sq += weight * weight
    if norm_sq <= 0.0:
        return {}
    inv_norm = 1.0 / math.sqrt(norm_sq)
    return {term: val * inv_norm for term, val in raw.items()}


def _cosine_and_overlap(
    vec_a: dict[str, float],
    vec_b: dict[str, float],
) -> tuple[float, list[str]]:
    if not vec_a or not vec_b:
        return 0.0, []
    if len(vec_a) > len(vec_b):
        smaller, larger = vec_b, vec_a
    else:
        smaller, larger = vec_a, vec_b

    dot = 0.0
    shared: list[tuple[float, str]] = []
    for term, val_s in smaller.items():
        val_l = larger.get(term)
        if val_l is not None:
            contrib = val_s * val_l
            dot += contrib
            shared.append((contrib, term))

    shared.sort(key=lambda item: (-item[0], item[1]))
    clamped = min(1.0, max(0.0, dot))
    return clamped, [term for _, term in shared]


def _resolve_weights(
    base_weights: tuple[float, float, float],
    *,
    has_second_signal: bool,
    has_third_signal: bool,
) -> tuple[float, float, float]:
    """Dynamically re-normalize weights when tags or secondary signals are missing (`TQ-4`)."""
    w1, w2, w3 = base_weights
    eff_w1 = w1
    eff_w2 = w2 if has_second_signal else 0.0
    eff_w3 = w3 if has_third_signal else 0.0
    total = eff_w1 + eff_w2 + eff_w3
    if total <= 0.0:
        return (1.0, 0.0, 0.0)
    return (eff_w1 / total, eff_w2 / total, eff_w3 / total)


def _average_upload_duration(uploads: list[VideoMetadata] | None) -> int | None:
    if not uploads:
        return None
    durations = [
        video.duration_seconds
        for video in uploads
        if video.duration_seconds is not None and video.duration_seconds > 0
    ]
    if not durations:
        return None
    return round(sum(durations) / len(durations))


class SimilarityService:
    """Computes deterministic metadata similarity for `FR-1` and `FR-2` (`ADR-004`)."""

    def __init__(
        self,
        provider: YouTubeProvider | None = None,
        quota_guard: QuotaGuard | None = None,
        repo: SQLiteRepository | None = None,
        sanitizer: MetadataSanitizer | None = None,
        *,
        w_tfidf: float = DEFAULT_W_TFIDF,
        w_tags: float = DEFAULT_W_TAGS,
        w_category: float = DEFAULT_W_CATEGORY,
    ) -> None:
        if min(w_tfidf, w_tags, w_category) < 0.0:
            raise ValueError("Similarity weights must be non-negative.")
        weight_sum = w_tfidf + w_tags + w_category
        if not math.isclose(weight_sum, 1.0, rel_tol=1e-6, abs_tol=1e-6):
            raise ValueError(f"Similarity weights must sum to 1.0 (got {weight_sum}).")

        self.provider = provider
        self.quota_guard = quota_guard
        self.repo = repo
        self.sanitizer = sanitizer or MetadataSanitizer()
        self.w_tfidf = w_tfidf
        self.w_tags = w_tags
        self.w_category = w_category

    def compute_composite_score(
        self,
        seed: VideoMetadata,
        candidate: VideoMetadata,
        *,
        idf_map: dict[str, float] | None = None,
    ) -> SimilarityScore:
        """Compute composite similarity between two videos using smoothed TF-IDF + tags + cat."""
        counts_a = _weighted_video_counts(seed)
        counts_b = _weighted_video_counts(candidate)
        idf = idf_map if idf_map is not None else _compute_idf([counts_a, counts_b])
        vec_a = _to_l2_tfidf_vector(counts_a, idf)
        vec_b = _to_l2_tfidf_vector(counts_b, idf)
        return self._score_video_vectors(seed, vec_a, candidate, vec_b)

    def rank_videos(
        self,
        seed: VideoMetadata,
        candidates: list[VideoMetadata],
        *,
        limit: int = 10,
    ) -> list[SimilarVideoItem]:
        """Rank candidate videos against `seed`, excluding seed itself (`FR-1`, `NFR-PERF-2`)."""
        if limit <= 0:
            return []

        deduped: list[VideoMetadata] = []
        seen_ids = {seed.video_id}
        for cand in candidates:
            if cand.video_id in seen_ids:
                continue
            seen_ids.add(cand.video_id)
            deduped.append(cand)

        if not deduped:
            return []

        doc_counts = [_weighted_video_counts(seed)]
        doc_counts.extend(_weighted_video_counts(cand) for cand in deduped)
        idf = _compute_idf(doc_counts)
        seed_vec = _to_l2_tfidf_vector(doc_counts[0], idf)

        scored: list[SimilarVideoItem] = []
        for cand, cand_counts in zip(deduped, doc_counts[1:], strict=True):
            cand_vec = _to_l2_tfidf_vector(cand_counts, idf)
            sim = self._score_video_vectors(seed, seed_vec, cand, cand_vec)
            sanitized = self.sanitizer.sanitize_video(cand)
            scored.append(
                SimilarVideoItem(
                    video_id=sanitized.video_id,
                    title=sanitized.title,
                    channel_title=sanitized.channel_title,
                    duration_seconds=sanitized.duration_seconds,
                    similarity_score=round(sim.composite_score, 6),
                    score_breakdown=sim.breakdown,
                    matching_terms=sim.matching_terms,
                    untrusted_metadata=True,
                )
            )

        scored.sort(key=lambda item: (-item.similarity_score, item.video_id))
        return scored[:limit]

    def rank_channels(
        self,
        seed: ChannelMetadata,
        candidates: list[ChannelMetadata],
        *,
        seed_uploads: list[VideoMetadata] | None = None,
        candidate_uploads: dict[str, list[VideoMetadata]] | None = None,
        limit: int = 10,
    ) -> list[SimilarChannelItem]:
        """Rank candidate channels against `seed`, excluding seed itself (`FR-2`)."""
        if limit <= 0:
            return []

        uploads_map = candidate_uploads or {}
        deduped: list[ChannelMetadata] = []
        seen_ids = {seed.channel_id}
        for cand in candidates:
            if cand.channel_id in seen_ids:
                continue
            seen_ids.add(cand.channel_id)
            deduped.append(cand)

        if not deduped:
            return []

        doc_counts = [_weighted_channel_counts(seed, seed_uploads)]
        doc_counts.extend(
            _weighted_channel_counts(cand, uploads_map.get(cand.channel_id)) for cand in deduped
        )
        idf = _compute_idf(doc_counts)
        seed_vec = _to_l2_tfidf_vector(doc_counts[0], idf)
        seed_topics = _normalize_terms([*seed.topic_categories, *seed.keywords])
        seed_avg_dur = _average_upload_duration(seed_uploads)

        scored: list[SimilarChannelItem] = []
        for cand, cand_counts in zip(deduped, doc_counts[1:], strict=True):
            cand_vec = _to_l2_tfidf_vector(cand_counts, idf)
            s_tfidf, shared_tokens = _cosine_and_overlap(seed_vec, cand_vec)

            cand_topics = _normalize_terms([*cand.topic_categories, *cand.keywords])
            has_topics = bool(seed_topics and cand_topics)
            s_topics = _jaccard_similarity(seed_topics, cand_topics) if has_topics else 0.0

            cand_avg_dur = _average_upload_duration(uploads_map.get(cand.channel_id))
            has_durations = seed_avg_dur is not None and cand_avg_dur is not None
            if has_durations:
                assert seed_avg_dur is not None and cand_avg_dur is not None
                denom_dur = max(seed_avg_dur, cand_avg_dur, 1)
                s_duration = 1.0 - min(1.0, abs(seed_avg_dur - cand_avg_dur) / denom_dur)
            else:
                s_duration = 0.0

            w1, w2, w3 = _resolve_weights(
                (self.w_tfidf, self.w_tags, self.w_category),
                has_second_signal=has_topics,
                has_third_signal=has_durations,
            )
            composite = (w1 * s_tfidf) + (w2 * s_topics) + (w3 * s_duration)

            shared_topic_terms = sorted(seed_topics & cand_topics)
            merged_topics = list(dict.fromkeys([*shared_topic_terms, *shared_tokens]))[:10]

            sanitized = self.sanitizer.sanitize_channel(cand)
            scored.append(
                SimilarChannelItem(
                    channel_id=sanitized.channel_id,
                    title=sanitized.title,
                    handle=sanitized.handle,
                    subscriber_count=sanitized.subscriber_count,
                    similarity_score=round(composite, 6),
                    matching_topics=merged_topics,
                    avg_upload_duration_seconds=cand_avg_dur,
                    untrusted_metadata=True,
                )
            )

        scored.sort(key=lambda item: (-item.similarity_score, item.channel_id))
        return scored[:limit]

    def find_similar_videos(
        self,
        video_ref: str,
        limit: int = 10,
        *,
        candidates: list[VideoMetadata] | None = None,
    ) -> SimilarVideosResponse:
        """Validate identifier, enforce cache & `QuotaGuard`, and rank similar videos (`FR-1`)."""
        seed_id = InputValidator.extract_video_id(video_ref)
        bounded_limit = max(1, min(limit, 25))
        provider = self._require_provider()
        quota_guard = self._require_quota_guard()
        repo = self._require_repo()

        cached_seed = repo.get_cached_videos([seed_id])
        seed_is_cached = seed_id in cached_seed

        planned_ops: list[QuotaOperation] = [
            QuotaOperation("videos.list", count=1, cached=seed_is_cached),
        ]
        if candidates is None:
            planned_ops.extend(
                [
                    QuotaOperation("search.list", count=1, cached=False),
                    QuotaOperation("videos.list", count=1, cached=False),
                ]
            )

        estimated_cost = quota_guard.estimate_cost(planned_ops)
        decision = quota_guard.preflight_check(estimated_cost, "FR-1:find_similar_videos")
        quota_used = 0

        if seed_is_cached:
            seed_video = VideoMetadata.model_validate(cached_seed[seed_id])
        else:
            fetched_seeds = provider.get_videos([seed_id])
            quota_guard.commit_usage("videos.list", 1, "FR-1:find_similar_videos")
            quota_used += 1
            if not fetched_seeds:
                raise VideoUnavailableError(f"Video {seed_id!r} was not found.")
            seed_video = fetched_seeds[0]
            repo.upsert_cached_videos({seed_video.video_id: seed_video.model_dump()})

        if candidates is not None:
            candidate_pool = candidates
        else:
            search_query = self._build_video_search_query(seed_video)
            search_page = provider.search_videos(search_query, max_results=25)
            quota_guard.commit_usage("search.list", 100, "FR-1:find_similar_videos")
            quota_used += 100

            candidate_ids = [vid for vid in search_page.video_ids if vid != seed_id]
            candidate_pool, fetch_cost = self._load_videos_with_cache(
                candidate_ids, workflow_context="FR-1:find_similar_videos"
            )
            quota_used += fetch_cost

        ranked = self.rank_videos(seed_video, candidate_pool, limit=bounded_limit)
        return SimilarVideosResponse(
            seed_video_id=seed_id,
            results=ranked,
            quota_used=quota_used,
            remaining_daily_quota=quota_guard.remaining_budget(),
            quota_warning=decision.quota_warning,
        )

    def find_similar_channels(
        self,
        channel_ref: str,
        limit: int = 10,
        *,
        candidates: list[ChannelMetadata] | None = None,
        channel_videos: dict[str, list[VideoMetadata]] | None = None,
    ) -> SimilarChannelsResponse:
        """Validate channel ref, enforce cache & `QuotaGuard`, and rank similar channels (`FR-2`)."""
        ref = InputValidator.parse_channel_identifier(channel_ref)
        bounded_limit = max(1, min(limit, 20))
        provider = self._require_provider()
        quota_guard = self._require_quota_guard()
        repo = self._require_repo()

        cached_seed = (
            repo.get_cached_channels([ref.channel_id]) if ref.channel_id is not None else {}
        )
        seed_is_cached = ref.channel_id is not None and ref.channel_id in cached_seed

        planned_ops: list[QuotaOperation] = [
            QuotaOperation("channels.list", count=1, cached=seed_is_cached),
        ]
        if channel_videos is None:
            planned_ops.extend(
                [
                    QuotaOperation("playlistItems.list", count=1, cached=False),
                    QuotaOperation("videos.list", count=1, cached=False),
                ]
            )
        if candidates is None:
            planned_ops.extend(
                [
                    QuotaOperation("search.list", count=1, cached=False),
                    QuotaOperation("videos.list", count=1, cached=False),
                    QuotaOperation("channels.list", count=1, cached=False),
                ]
            )

        estimated_cost = quota_guard.estimate_cost(planned_ops)
        decision = quota_guard.preflight_check(estimated_cost, "FR-2:find_similar_channels")
        quota_used = 0

        if seed_is_cached and ref.channel_id is not None:
            seed_channel = ChannelMetadata.model_validate(cached_seed[ref.channel_id])
        else:
            fetched_channels = provider.get_channels(
                channel_ids=[ref.channel_id] if ref.channel_id else None,
                handle=ref.handle,
            )
            quota_guard.commit_usage("channels.list", 1, "FR-2:find_similar_channels")
            quota_used += 1
            if not fetched_channels:
                raise VideoUnavailableError("Requested YouTube channel was not found.")
            seed_channel = fetched_channels[0]
            repo.upsert_cached_channels({seed_channel.channel_id: seed_channel.model_dump()})

        uploads_map: dict[str, list[VideoMetadata]] = dict(channel_videos or {})
        if seed_channel.channel_id not in uploads_map and seed_channel.uploads_playlist_id:
            seed_uploads, upload_cost = self._load_channel_uploads(
                seed_channel.uploads_playlist_id, workflow_context="FR-2:find_similar_channels"
            )
            uploads_map[seed_channel.channel_id] = seed_uploads
            quota_used += upload_cost

        if candidates is not None:
            candidate_channels = candidates
        else:
            search_query = self._build_channel_search_query(seed_channel)
            search_page = provider.search_videos(search_query, max_results=25)
            quota_guard.commit_usage("search.list", 100, "FR-2:find_similar_channels")
            quota_used += 100

            discovered_videos, vid_cost = self._load_videos_with_cache(
                search_page.video_ids, workflow_context="FR-2:find_similar_channels"
            )
            quota_used += vid_cost

            cand_channel_ids = list(
                dict.fromkeys(
                    video.channel_id
                    for video in discovered_videos
                    if video.channel_id and video.channel_id != seed_channel.channel_id
                )
            )
            candidate_channels, ch_cost = self._load_channels_with_cache(
                cand_channel_ids, workflow_context="FR-2:find_similar_channels"
            )
            quota_used += ch_cost

            for video in discovered_videos:
                if video.channel_id:
                    uploads_map.setdefault(video.channel_id, []).append(video)

        ranked = self.rank_channels(
            seed_channel,
            candidate_channels,
            seed_uploads=uploads_map.get(seed_channel.channel_id),
            candidate_uploads=uploads_map,
            limit=bounded_limit,
        )
        return SimilarChannelsResponse(
            seed_channel_id=seed_channel.channel_id,
            results=ranked,
            quota_used=quota_used,
            remaining_daily_quota=quota_guard.remaining_budget(),
            quota_warning=decision.quota_warning,
        )

    def _score_video_vectors(
        self,
        seed: VideoMetadata,
        seed_vec: dict[str, float],
        candidate: VideoMetadata,
        cand_vec: dict[str, float],
    ) -> SimilarityScore:
        s_tfidf, shared_tokens = _cosine_and_overlap(seed_vec, cand_vec)

        tags_a = _normalize_terms(seed.tags)
        tags_b = _normalize_terms(candidate.tags)
        has_tags = bool(tags_a and tags_b)
        s_tags = _jaccard_similarity(tags_a, tags_b) if has_tags else 0.0

        has_category = bool(seed.category_id and candidate.category_id)
        s_cat = 1.0 if (has_category and seed.category_id == candidate.category_id) else 0.0

        w1, w2, w3 = _resolve_weights(
            (self.w_tfidf, self.w_tags, self.w_category),
            has_second_signal=has_tags,
            has_third_signal=has_category,
        )
        composite = (w1 * s_tfidf) + (w2 * s_tags) + (w3 * s_cat)

        shared_tags = sorted(tags_a & tags_b)
        matching_terms = list(dict.fromkeys([*shared_tags, *shared_tokens]))[:10]
        return SimilarityScore(
            composite_score=composite,
            breakdown=ScoreBreakdown(
                tfidf=round(s_tfidf, 6),
                tags=round(s_tags, 6),
                category=round(s_cat, 6),
                effective_weights=(round(w1, 4), round(w2, 4), round(w3, 4)),
            ),
            matching_terms=matching_terms,
        )

    def _load_videos_with_cache(
        self,
        video_ids: list[str],
        *,
        workflow_context: str,
    ) -> tuple[list[VideoMetadata], int]:
        if not video_ids:
            return [], 0
        provider = self._require_provider()
        quota_guard = self._require_quota_guard()
        repo = self._require_repo()

        cached = repo.get_cached_videos(video_ids)
        uncached_ids = [vid for vid in video_ids if vid not in cached]
        fetched: dict[str, VideoMetadata] = {}
        cost = 0

        for idx in range(0, len(uncached_ids), 50):
            batch = uncached_ids[idx : idx + 50]
            batch_videos = provider.get_videos(batch)
            quota_guard.commit_usage("videos.list", 1, workflow_context)
            cost += 1
            for vid in batch_videos:
                fetched[vid.video_id] = vid

        if fetched:
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

    def _load_channels_with_cache(
        self,
        channel_ids: list[str],
        *,
        workflow_context: str,
    ) -> tuple[list[ChannelMetadata], int]:
        if not channel_ids:
            return [], 0
        provider = self._require_provider()
        quota_guard = self._require_quota_guard()
        repo = self._require_repo()

        cached = repo.get_cached_channels(channel_ids)
        uncached_ids = [cid for cid in channel_ids if cid not in cached]
        fetched: dict[str, ChannelMetadata] = {}
        cost = 0

        if uncached_ids:
            for idx in range(0, len(uncached_ids), 50):
                batch = uncached_ids[idx : idx + 50]
                batch_channels = provider.get_channels(channel_ids=batch)
                quota_guard.commit_usage("channels.list", 1, workflow_context)
                cost += 1
                for ch in batch_channels:
                    fetched[ch.channel_id] = ch

            if fetched:
                repo.upsert_cached_channels(
                    {cid: model.model_dump() for cid, model in fetched.items()}
                )

        ordered: list[ChannelMetadata] = []
        for cid in channel_ids:
            if cid in cached:
                ordered.append(ChannelMetadata.model_validate(cached[cid]))
            elif cid in fetched:
                ordered.append(fetched[cid])
        return ordered, cost

    def _load_channel_uploads(
        self,
        uploads_playlist_id: str,
        *,
        workflow_context: str,
    ) -> tuple[list[VideoMetadata], int]:
        provider = self._require_provider()
        quota_guard = self._require_quota_guard()
        item_ids = provider.get_playlist_items(uploads_playlist_id, max_results=20)
        quota_guard.commit_usage("playlistItems.list", 1, workflow_context)
        videos, vid_cost = self._load_videos_with_cache(
            item_ids, workflow_context=workflow_context
        )
        return videos, 1 + vid_cost

    def _build_video_search_query(self, seed: VideoMetadata) -> str:
        if seed.tags:
            sanitized_tag = self.sanitizer.sanitize_text(
                seed.tags[0], max_length=60, preserve_newlines=False
            )
            if sanitized_tag:
                return sanitized_tag
        sanitized_title = self.sanitizer.sanitize_text(
            seed.title, max_length=100, preserve_newlines=False
        )
        tokens = normalize_and_tokenize(sanitized_title)
        if tokens:
            return " ".join(tokens[:2])
        return "tutorial"

    def _build_channel_search_query(self, seed: ChannelMetadata) -> str:
        if seed.keywords:
            return self.sanitizer.sanitize_text(
                seed.keywords[0], max_length=60, preserve_newlines=False
            )
        tokens = normalize_and_tokenize(
            self.sanitizer.sanitize_text(seed.title, max_length=100, preserve_newlines=False)
        )
        return " ".join(tokens[:3]) if tokens else "technology"

    def _require_provider(self) -> YouTubeProvider:
        if self.provider is None:
            raise RuntimeError("SimilarityService requires a YouTubeProvider instance.")
        return self.provider

    def _require_quota_guard(self) -> QuotaGuard:
        if self.quota_guard is None:
            raise RuntimeError("SimilarityService requires a QuotaGuard instance.")
        return self.quota_guard

    def _require_repo(self) -> SQLiteRepository:
        if self.repo is None:
            raise RuntimeError("SimilarityService requires a SQLiteRepository instance.")
        return self.repo
