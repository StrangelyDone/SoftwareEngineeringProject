"""Core domain services for YouTube MCP (`SE-6`: zero external HTTP/API imports)."""

from youtube_mcp.services.similarity import (
    DEFAULT_W_CATEGORY,
    DEFAULT_W_TAGS,
    DEFAULT_W_TFIDF,
    ScoreBreakdown,
    SimilarChannelItem,
    SimilarChannelsResponse,
    SimilarityScore,
    SimilarityService,
    SimilarVideoItem,
    SimilarVideosResponse,
)

__all__ = [
    "DEFAULT_W_CATEGORY",
    "DEFAULT_W_TAGS",
    "DEFAULT_W_TFIDF",
    "ScoreBreakdown",
    "SimilarChannelItem",
    "SimilarChannelsResponse",
    "SimilarVideoItem",
    "SimilarVideosResponse",
    "SimilarityScore",
    "SimilarityService",
]
