"""Offline unit and performance tests for SimilarityService (M3.2 / M3.5 / FR-1 / FR-2)."""

from __future__ import annotations

import ast
import math
import time
from pathlib import Path

import pytest

from youtube_mcp.exceptions import InvalidVideoIdentifierError, QuotaBudgetExceededError
from youtube_mcp.models import ChannelMetadata, VideoMetadata
from youtube_mcp.providers.mock import FixtureMockProvider
from youtube_mcp.quota_guard import QuotaGuard
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.services.similarity import (
    DEFAULT_W_CATEGORY,
    DEFAULT_W_TAGS,
    DEFAULT_W_TFIDF,
    SimilarityService,
    normalize_and_tokenize,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _make_service(
    tmp_path: Path, *, daily_budget: int = 10_000
) -> tuple[SimilarityService, SQLiteRepository]:
    repo = SQLiteRepository(tmp_path / "sim.db")
    repo.initialize_schema()
    guard = QuotaGuard(repo, daily_quota_budget=daily_budget)
    provider = FixtureMockProvider(FIXTURES)
    service = SimilarityService(provider=provider, quota_guard=guard, repo=repo)
    return service, repo


def test_zero_external_http_imports_in_services_package() -> None:
    """Enforce SE-6: domain services never import googleapiclient or httpx."""
    services_dir = Path(__file__).resolve().parents[1] / "src" / "youtube_mcp" / "services"
    forbidden = {"googleapiclient", "httpx", "requests", "urllib3"}

    for py_file in services_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden


def test_nfc_normalization_and_2x_title_weighting() -> None:
    # Decomposed "e\u0301" vs composed "\u00e9" must normalize identically.
    assert normalize_and_tokenize("Siste\u0301mas Distributed!") == [
        "sistémas",
        "distributed",
    ]

    service = SimilarityService()
    seed = VideoMetadata(
        video_id="vidSEED0001",
        title="Asyncio",
        description="cooking",
        tags=["python"],
        category_id="28",
    )
    title_match = VideoMetadata(
        video_id="vidTITLE001",
        title="Asyncio",
        description="pasta",
        tags=["python"],
        category_id="28",
    )
    desc_match = VideoMetadata(
        video_id="vidDESC0001",
        title="Pasta",
        description="asyncio",
        tags=["python"],
        category_id="28",
    )
    ranked = service.rank_videos(seed, [desc_match, title_match], limit=5)
    assert [item.video_id for item in ranked] == ["vidTITLE001", "vidDESC0001"]
    assert ranked[0].score_breakdown.tfidf > ranked[1].score_breakdown.tfidf


def test_composite_weights_exact_math() -> None:
    service = SimilarityService(
        w_tfidf=DEFAULT_W_TFIDF, w_tags=DEFAULT_W_TAGS, w_category=DEFAULT_W_CATEGORY
    )
    seed = VideoMetadata(
        video_id="vidA0000001",
        title="Python Asyncio",
        description="Structured concurrency",
        tags=["python", "asyncio"],
        category_id="28",
    )
    candidate = VideoMetadata(
        video_id="vidB0000002",
        title="Python Asyncio",
        description="Structured concurrency",
        tags=["python", "testing"],
        category_id="28",
    )
    score = service.compute_composite_score(seed, candidate)
    # Identical title+description -> tfidf = 1.0; tags Jaccard = 1/3; category = 1.0
    expected = (0.65 * 1.0) + (0.25 * (1.0 / 3.0)) + (0.10 * 1.0)
    assert math.isclose(score.composite_score, expected, rel_tol=1e-6)
    assert score.breakdown.effective_weights == (0.65, 0.25, 0.10)
    assert "python" in score.matching_terms


def test_missing_tags_dynamic_reweighting_fallback() -> None:
    service = SimilarityService()
    seed = VideoMetadata(
        video_id="vidSEED0001",
        title="SQLite WAL Internals",
        description="Checkpoints and concurrency",
        tags=["sqlite", "wal"],
        category_id="28",
    )
    untagged_same_cat = VideoMetadata(
        video_id="vidUNTAG001",
        title="SQLite WAL Internals",
        description="Checkpoints and concurrency",
        tags=[],
        category_id="28",
    )
    score = service.compute_composite_score(seed, untagged_same_cat)
    assert score.breakdown.tags == 0.0
    assert score.breakdown.effective_weights == (0.8667, 0.0, 0.1333)
    assert math.isclose(score.composite_score, 1.0, rel_tol=1e-6)

    untagged_no_cat = VideoMetadata(
        video_id="vidUNTAG002",
        title="SQLite WAL Internals",
        description="Checkpoints and concurrency",
        tags=[],
        category_id=None,
    )
    score_no_cat = service.compute_composite_score(seed, untagged_no_cat)
    assert score_no_cat.breakdown.effective_weights == (1.0, 0.0, 0.0)
    assert math.isclose(score_no_cat.composite_score, 1.0, rel_tol=1e-6)


def test_rank_videos_excludes_seed_and_uses_deterministic_tie_breaking() -> None:
    service = SimilarityService()
    seed = VideoMetadata(
        video_id="vidSEED0001",
        title="Distributed Systems",
        description="Consensus notes",
        tags=["systems"],
        category_id="28",
    )
    cand_b = VideoMetadata(
        video_id="vidCAND0002",
        title="Distributed Systems",
        description="Consensus notes",
        tags=["systems"],
        category_id="28",
    )
    cand_a = VideoMetadata(
        video_id="vidCAND0001",
        title="Distributed Systems",
        description="Consensus notes",
        tags=["systems"],
        category_id="28",
    )

    ranked = service.rank_videos(seed, [seed, cand_b, cand_a], limit=10)
    assert [item.video_id for item in ranked] == ["vidCAND0001", "vidCAND0002"]
    assert all(item.untrusted_metadata is True for item in ranked)


def test_rank_channels_aggregates_metadata_and_recent_uploads() -> None:
    service = SimilarityService()
    seed = ChannelMetadata(
        channel_id="UCsynthetic001",
        title="Systems Lab",
        description="Lessons on distributed systems",
        handle="@systems-lab",
        keywords=["distributed systems", "reliability"],
        topic_categories=["Technology", "Science"],
    )
    related_ch = ChannelMetadata(
        channel_id="UCsynthetic003",
        title="Database Desk",
        description="Storage engine internals",
        handle="@database-desk",
        keywords=["sqlite", "storage"],
        topic_categories=["Technology", "Computing"],
    )
    unrelated_ch = ChannelMetadata(
        channel_id="UCsynthetic004",
        title="Test Kitchen",
        description="Cooking recipes and pasta timing",
        handle="@test-kitchen",
        keywords=["cooking", "pasta"],
        topic_categories=["Lifestyle", "Food"],
    )
    uploads = {
        "UCsynthetic001": [
            VideoMetadata(
                video_id="v1",
                title="Raft Consensus Protocol",
                tags=["distributed", "consensus"],
                duration_seconds=900,
            )
        ],
        "UCsynthetic003": [
            VideoMetadata(
                video_id="v2",
                title="Distributed Transaction Consensus",
                tags=["consensus", "storage"],
                duration_seconds=920,
            )
        ],
        "UCsynthetic004": [
            VideoMetadata(
                video_id="v3",
                title="Boil Pasta Faster",
                tags=["cooking"],
                duration_seconds=300,
            )
        ],
    }

    ranked = service.rank_channels(
        seed,
        [unrelated_ch, related_ch, seed],
        seed_uploads=uploads["UCsynthetic001"],
        candidate_uploads=uploads,
        limit=5,
    )
    assert [item.channel_id for item in ranked] == ["UCsynthetic003", "UCsynthetic004"]
    assert "technology" in ranked[0].matching_topics
    assert ranked[0].shared_topics == ranked[0].matching_topics
    assert ranked[0].avg_upload_duration_seconds == 920
    assert ranked[0].untrusted_metadata is True


def test_find_similar_videos_integrates_cache_quota_and_provider(tmp_path: Path) -> None:
    service, repo = _make_service(tmp_path)

    with pytest.raises(InvalidVideoIdentifierError):
        service.find_similar_videos("not-valid-id")
    assert repo.get_used_quota() == 0

    first = service.find_similar_videos("https://youtu.be/vidPY000002", limit=5)
    assert first.seed_video_id == "vidPY000002"
    assert first.quota_used > 0
    assert any(item.video_id == "vidPY000012" for item in first.results)

    # Seed is now cached: passing pre-cached candidates incurs 0 extra quota.
    cached_map = repo.get_cached_videos(["vidPY000002", "vidPY000012", "vidCOOK0006"])
    cached_candidates = [VideoMetadata.model_validate(v) for v in cached_map.values()]
    second = service.find_similar_videos("vidPY000002", candidates=cached_candidates)
    assert second.quota_used == 0


def test_find_similar_videos_respects_preflight_quota_block(tmp_path: Path) -> None:
    service, repo = _make_service(tmp_path, daily_budget=10_000)
    repo.record_quota_usage("search.list", 9_950, "exhaust")

    with pytest.raises(QuotaBudgetExceededError):
        service.find_similar_videos("vidPY000002")
    assert repo.get_used_quota() == 9_950


def test_find_similar_channels_validates_and_ranks_with_handle(tmp_path: Path) -> None:
    service, repo = _make_service(tmp_path)
    candidates = [
        ChannelMetadata(
            channel_id="UCsynthetic002",
            title="Python Studio",
            description="Asyncio and systems tutorials",
            handle="@python-studio",
            keywords=["python", "systems"],
            topic_categories=["Technology", "Software"],
        ),
        ChannelMetadata(
            channel_id="UCsynthetic004",
            title="Test Kitchen",
            description="Cooking recipes",
            handle="@test-kitchen",
            keywords=["cooking"],
            topic_categories=["Lifestyle", "Food"],
        ),
    ]
    res = service.find_similar_channels(
        "https://www.youtube.com/@systems-lab",
        candidates=candidates,
        channel_videos={"UCsynthetic002": [], "UCsynthetic004": []},
    )
    assert res.seed_channel_id == "UCsynthetic001"
    assert [item.channel_id for item in res.results] == ["UCsynthetic002", "UCsynthetic004"]
    assert repo.get_used_quota() > 0


def test_rank_200_cached_videos_under_500ms_nfr_perf_2() -> None:
    """NFR-PERF-2: Ranking 200 cached videos must complete in under 500 ms."""
    service = SimilarityService()
    seed = VideoMetadata(
        video_id="vidSEED0000",
        title="Distributed Consensus and Python Asyncio Architecture",
        description=(
            "Deep dive into Raft consensus, WAL persistence, event loops, and backpressure."
        ),
        tags=["distributed", "python", "asyncio", "raft", "sqlite"],
        category_id="28",
        duration_seconds=1200,
    )
    candidates = [
        VideoMetadata(
            video_id=f"vidCAND{i:04d}",
            title=f"Synthetic Engineering Talk {i} on Asyncio and Consensus",
            description=(
                f"Episode {i} exploring queues, fault tolerance, WAL logs, and Python tasks."
            ),
            tags=["python", "asyncio", f"topic{i % 15}"],
            category_id="28" if i % 2 == 0 else "27",
            duration_seconds=600 + (i * 5),
        )
        for i in range(200)
    ]

    start = time.perf_counter()
    ranked = service.rank_videos(seed, candidates, limit=25)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert len(ranked) == 25
    assert elapsed_ms < 500.0, f"Ranking 200 videos took {elapsed_ms:.2f} ms (>= 500 ms)"
