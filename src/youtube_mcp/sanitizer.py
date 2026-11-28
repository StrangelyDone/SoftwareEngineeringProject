"""Input identifier validation and untrusted YouTube metadata sanitization (M3.1)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field

from youtube_mcp.exceptions import InvalidVideoIdentifierError
from youtube_mcp.models import ChannelMetadata, VideoMetadata

VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
CHANNEL_ID_RE = re.compile(r"^UC[a-zA-Z0-9_-]{22}$")
HANDLE_RE = re.compile(r"^@[A-Za-z0-9._-]{3,30}$")
ISO_639_1_RE = re.compile(r"^[a-zA-Z]{2}$")

_ALLOWED_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_ALLOWED_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_VIDEO_PATH_PREFIXES = {"shorts", "embed", "live", "v"}

# ANSI CSI, OSC, and 2-byte ESC sequences.
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[@-Z\\-_]"
)

# Unicode directional formatting / override / isolate codepoints (CVE-2021-42574 class).
_BIDI_CHARS = frozenset(
    {
        "\u061c",  # Arabic Letter Mark
        "\u200e",  # Left-to-Right Mark
        "\u200f",  # Right-to-Left Mark
        "\u202a",  # Left-to-Right Embedding
        "\u202b",  # Right-to-Left Embedding
        "\u202c",  # Pop Directional Formatting
        "\u202d",  # Left-to-Right Override
        "\u202e",  # Right-to-Left Override
        "\u2066",  # Left-to-Right Isolate
        "\u2067",  # Right-to-Left Isolate
        "\u2068",  # First Strong Isolate
        "\u2069",  # Pop Directional Isolate
    }
)

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_CHANNEL_TITLE_LENGTH = 150
MAX_TAG_LENGTH = 100
MAX_TAGS_COUNT = 50
MAX_KEYWORD_LENGTH = 100
MAX_KEYWORDS_COUNT = 50


@dataclass(frozen=True)
class ChannelReference:
    """Validated channel identifier resolved to either a `UC...` ID or `@handle`."""

    channel_id: str | None = None
    handle: str | None = None


class SanitizedVideo(BaseModel):
    """Sanitized video metadata explicitly flagged as untrusted external data (`ADR-005`)."""

    video_id: str
    title: str
    description: str = ""
    channel_id: str = ""
    channel_title: str = ""
    tags: list[str] = Field(default_factory=list)
    category_id: str | None = None
    duration_iso: str | None = None
    duration_seconds: int | None = None
    default_language: str | None = None
    default_audio_language: str | None = None
    published_at: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    untrusted_metadata: Literal[True] = True


class SanitizedChannel(BaseModel):
    """Sanitized channel metadata explicitly flagged as untrusted external data (`ADR-005`)."""

    channel_id: str
    title: str
    description: str = ""
    handle: str | None = None
    keywords: list[str] = Field(default_factory=list)
    topic_categories: list[str] = Field(default_factory=list)
    uploads_playlist_id: str | None = None
    subscriber_count: int | None = None
    video_count: int | None = None
    country: str | None = None
    untrusted_metadata: Literal[True] = True


class InputValidator:
    """Validates YouTube video IDs/URLs, channel IDs/handles/URLs, and language codes."""

    @staticmethod
    def extract_video_id(video_ref: str) -> str:
        """Extract and validate an 11-character YouTube video ID from a URL or raw ID."""
        if not isinstance(video_ref, str):
            raise InvalidVideoIdentifierError("Video identifier must be a string.")

        candidate = video_ref.strip()
        if not candidate:
            raise InvalidVideoIdentifierError("Video identifier cannot be empty.")

        if VIDEO_ID_RE.fullmatch(candidate):
            return candidate

        parsed = InputValidator._parse_youtube_url(candidate)
        if parsed is None:
            raise InvalidVideoIdentifierError(
                f"Malformed YouTube video identifier or URL: {candidate!r}."
            )

        host = (parsed.hostname or "").lower()
        segments = [seg for seg in parsed.path.split("/") if seg]

        video_id: str | None = None
        if host in _ALLOWED_SHORT_HOSTS:
            if len(segments) == 1:
                video_id = segments[0]
        elif host in _ALLOWED_YOUTUBE_HOSTS:
            if parsed.path in {"/watch", "/watch/"}:
                values = parse_qs(parsed.query).get("v", [])
                if len(values) == 1:
                    video_id = values[0].strip()
            elif len(segments) == 2 and segments[0] in _VIDEO_PATH_PREFIXES:
                video_id = segments[1]

        if video_id and VIDEO_ID_RE.fullmatch(video_id):
            return video_id

        raise InvalidVideoIdentifierError(
            f"Malformed YouTube video identifier or URL: {candidate!r}."
        )

    @staticmethod
    def parse_channel_identifier(channel_ref: str) -> ChannelReference:
        """Parse and validate a 24-char `UC...` ID, `@handle`, or YouTube channel URL."""
        if not isinstance(channel_ref, str):
            raise InvalidVideoIdentifierError("Channel identifier must be a string.")

        candidate = channel_ref.strip()
        if not candidate:
            raise InvalidVideoIdentifierError("Channel identifier cannot be empty.")

        if CHANNEL_ID_RE.fullmatch(candidate):
            return ChannelReference(channel_id=candidate)

        if InputValidator._is_valid_handle(candidate):
            return ChannelReference(handle=candidate)

        parsed = InputValidator._parse_youtube_url(candidate)
        if parsed is None:
            raise InvalidVideoIdentifierError(
                f"Malformed YouTube channel identifier or URL: {candidate!r}."
            )

        host = (parsed.hostname or "").lower()
        if host not in _ALLOWED_YOUTUBE_HOSTS:
            raise InvalidVideoIdentifierError(
                f"Unsupported YouTube channel host in URL: {candidate!r}."
            )

        segments = [seg for seg in parsed.path.split("/") if seg]
        if len(segments) == 2 and segments[0] == "channel" and CHANNEL_ID_RE.fullmatch(segments[1]):
            return ChannelReference(channel_id=segments[1])

        if len(segments) == 1 and InputValidator._is_valid_handle(segments[0]):
            return ChannelReference(handle=segments[0])

        raise InvalidVideoIdentifierError(
            f"Malformed YouTube channel identifier or URL: {candidate!r}."
        )

    @staticmethod
    def validate_language_code(language: str) -> str:
        """Validate and normalize an ISO 639-1 two-letter language code (e.g. `'en'`)."""
        if not isinstance(language, str):
            raise InvalidVideoIdentifierError("Language code must be a two-letter string.")
        cleaned = language.strip()
        if not ISO_639_1_RE.fullmatch(cleaned):
            raise InvalidVideoIdentifierError(
                f"Invalid ISO 639-1 language code: {language!r}.",
                remediation="Provide a two-letter ISO 639-1 code such as 'en', 'es', or 'de'.",
            )
        return cleaned.lower()

    @staticmethod
    def _is_valid_handle(value: str) -> bool:
        if not HANDLE_RE.fullmatch(value):
            return False
        body = value[1:]
        return not (body.startswith(".") or body.endswith(".") or ".." in body)

    @staticmethod
    def _parse_youtube_url(candidate: str):
        url_str = candidate
        if "://" not in candidate:
            lowered = candidate.lower()
            if any(
                lowered.startswith(prefix)
                for prefix in ("youtube.com/", "www.youtube.com/", "m.youtube.com/", "youtu.be/")
            ):
                url_str = f"https://{candidate}"
            else:
                return None

        parsed = urlparse(url_str)
        if parsed.scheme not in {"http", "https"}:
            return None
        host = (parsed.hostname or "").lower()
        if host not in _ALLOWED_YOUTUBE_HOSTS and host not in _ALLOWED_SHORT_HOSTS:
            return None
        return parsed


class MetadataSanitizer:
    """Strips dangerous control sequences and bounds untrusted YouTube metadata (`ADR-005`)."""

    @staticmethod
    def sanitize_text(
        raw: str | None,
        *,
        max_length: int = MAX_DESCRIPTION_LENGTH,
        preserve_newlines: bool = True,
    ) -> str:
        """Strip NUL, ANSI escapes, bidi overrides, and non-printable chars with length cap."""
        if not raw:
            return ""
        if max_length < 0:
            raise ValueError("max_length must be non-negative")

        text = unicodedata.normalize("NFC", raw)
        text = text.replace("\x00", "")
        text = _ANSI_ESCAPE_RE.sub("", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        cleaned_chars: list[str] = []
        for ch in text:
            if ch in _BIDI_CHARS:
                continue
            if ch == "\n":
                cleaned_chars.append("\n" if preserve_newlines else " ")
                continue
            if ch == "\t":
                cleaned_chars.append("\t" if preserve_newlines else " ")
                continue
            code = ord(ch)
            if code < 0x20 or 0x7F <= code <= 0x9F:
                continue
            if unicodedata.category(ch) in {"Cc", "Cf"}:
                continue
            cleaned_chars.append(ch)

        cleaned = "".join(cleaned_chars).strip()
        if max_length == 0:
            return ""
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length].rstrip()
        return cleaned

    def sanitize_video(self, video: VideoMetadata) -> SanitizedVideo:
        """Return a length-bounded, control-stripped `SanitizedVideo` (`untrusted_metadata=True`)."""
        sanitized_tags: list[str] = []
        for tag in video.tags[:MAX_TAGS_COUNT]:
            cleaned_tag = self.sanitize_text(
                tag, max_length=MAX_TAG_LENGTH, preserve_newlines=False
            )
            if cleaned_tag:
                sanitized_tags.append(cleaned_tag)

        return SanitizedVideo(
            video_id=video.video_id,
            title=self.sanitize_text(
                video.title, max_length=MAX_TITLE_LENGTH, preserve_newlines=False
            ),
            description=self.sanitize_text(
                video.description, max_length=MAX_DESCRIPTION_LENGTH, preserve_newlines=True
            ),
            channel_id=self.sanitize_text(
                video.channel_id, max_length=64, preserve_newlines=False
            ),
            channel_title=self.sanitize_text(
                video.channel_title, max_length=MAX_CHANNEL_TITLE_LENGTH, preserve_newlines=False
            ),
            tags=sanitized_tags,
            category_id=video.category_id,
            duration_iso=video.duration_iso,
            duration_seconds=video.duration_seconds,
            default_language=video.default_language,
            default_audio_language=video.default_audio_language,
            published_at=video.published_at,
            view_count=video.view_count,
            like_count=video.like_count,
            untrusted_metadata=True,
        )

    def sanitize_channel(self, channel: ChannelMetadata) -> SanitizedChannel:
        """Return a sanitized `SanitizedChannel` flagged with `untrusted_metadata=True`."""
        sanitized_keywords: list[str] = []
        for kw in channel.keywords[:MAX_KEYWORDS_COUNT]:
            cleaned_kw = self.sanitize_text(
                kw, max_length=MAX_KEYWORD_LENGTH, preserve_newlines=False
            )
            if cleaned_kw:
                sanitized_keywords.append(cleaned_kw)

        sanitized_topics: list[str] = []
        for topic in channel.topic_categories[:MAX_KEYWORDS_COUNT]:
            cleaned_topic = self.sanitize_text(
                topic, max_length=MAX_KEYWORD_LENGTH, preserve_newlines=False
            )
            if cleaned_topic:
                sanitized_topics.append(cleaned_topic)

        return SanitizedChannel(
            channel_id=channel.channel_id,
            title=self.sanitize_text(
                channel.title, max_length=MAX_CHANNEL_TITLE_LENGTH, preserve_newlines=False
            ),
            description=self.sanitize_text(
                channel.description, max_length=MAX_DESCRIPTION_LENGTH, preserve_newlines=True
            ),
            handle=self.sanitize_text(channel.handle, max_length=64, preserve_newlines=False)
            if channel.handle
            else None,
            keywords=sanitized_keywords,
            topic_categories=sanitized_topics,
            uploads_playlist_id=channel.uploads_playlist_id,
            subscriber_count=channel.subscriber_count,
            video_count=channel.video_count,
            country=channel.country,
            untrusted_metadata=True,
        )
