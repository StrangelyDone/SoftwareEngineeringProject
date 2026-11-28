"""Strict ISO-8601 duration parsing shared by AnalyticsService and PlaylistService."""

from __future__ import annotations

import re

from youtube_mcp.models import VideoMetadata

# Matches YouTube API ISO-8601 durations like PT15M33S, PT1H2M3S, PT0S, P1DT2H.
# Rejects bare "P", bare "PT", trailing "T" with no time unit, negative signs, and decimals.
_ISO_8601_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?=\d+[HMS])(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso8601_duration(duration_iso: str) -> int:
    """Parse a YouTube ISO-8601 duration string into non-negative whole seconds.

    Raises `ValueError` for missing, negative, fractional, or malformed strings.
    """
    if not isinstance(duration_iso, str):
        raise TypeError("Duration must be a string.")

    cleaned = duration_iso.strip()
    if not cleaned:
        raise ValueError("Duration string cannot be empty.")

    match = _ISO_8601_DURATION_RE.fullmatch(cleaned)
    if match is None:
        raise ValueError(f"Malformed ISO-8601 duration: {duration_iso!r}")

    groups = match.groupdict()
    if all(groups[key] is None for key in ("days", "hours", "minutes", "seconds")):
        raise ValueError(f"ISO-8601 duration has no numeric components: {duration_iso!r}")

    days = int(groups["days"] or 0)
    hours = int(groups["hours"] or 0)
    minutes = int(groups["minutes"] or 0)
    seconds = int(groups["seconds"] or 0)
    return (days * 86_400) + (hours * 3_600) + (minutes * 60) + seconds


def try_parse_iso8601_duration(duration_iso: str | None) -> int | None:
    """Safely parse an ISO-8601 duration string, returning `None` on invalid input."""
    if duration_iso is None:
        return None
    try:
        return parse_iso8601_duration(duration_iso)
    except (TypeError, ValueError):
        return None


def resolve_video_duration_seconds(video: VideoMetadata) -> int | None:
    """Resolve a video's duration in seconds using strict ISO-8601 validation first.

    If `duration_iso` is present, it is strictly parsed (`not-an-iso-duration` -> `None`).
    Only when `duration_iso` is `None` does this fall back to a non-negative `duration_seconds`.
    """
    if video.duration_iso is not None:
        return try_parse_iso8601_duration(video.duration_iso)
    if video.duration_seconds is not None and video.duration_seconds >= 0:
        return int(video.duration_seconds)
    return None
