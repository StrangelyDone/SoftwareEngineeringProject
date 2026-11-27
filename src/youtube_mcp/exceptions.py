"""Safe domain exceptions shared by YouTube MCP providers and tool handlers."""

from __future__ import annotations


class YouTubeMCPError(Exception):
    """Base exception carrying only fields that are safe to return to MCP clients."""

    error_code = "YOUTUBE_MCP_ERROR"
    default_message = "A YouTube MCP operation could not be completed."
    default_remediation = "Verify your request parameters and try again."

    def __init__(
        self,
        message: str | None = None,
        remediation: str | None = None,
    ) -> None:
        resolved_message = message if message is not None else self.default_message
        resolved_remediation = (
            remediation if remediation is not None else self.default_remediation
        )
        super().__init__(resolved_message)
        self.error_code = self.error_code
        self.message = resolved_message
        self.remediation = resolved_remediation

    def to_error_payload(self) -> dict[str, str]:
        """Return a structured, stack-free error payload."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "remediation": self.remediation,
        }

    def to_payload(self) -> dict[str, str]:
        """Compatibility alias for existing provider callers."""
        return self.to_error_payload()


class InvalidVideoIdentifierError(YouTubeMCPError):
    error_code = "INVALID_IDENTIFIER"
    default_message = "The supplied YouTube video or channel identifier is invalid."
    default_remediation = (
        "Provide a valid YouTube URL, 11-char video ID, @handle, or UC... channel ID."
    )


class VideoUnavailableError(YouTubeMCPError):
    error_code = "VIDEO_UNAVAILABLE"
    default_message = "The requested YouTube video or channel is unavailable."
    default_remediation = "Verify the video is public/accessible and retry with another ID."


class QuotaBudgetExceededError(YouTubeMCPError):
    error_code = "QUOTA_BUDGET_EXCEEDED"
    default_message = "The YouTube API quota budget is insufficient."
    default_remediation = (
        "Wait for UTC midnight quota reset, reduce result scope, or rely on cached entries."
    )


class ConfirmationRequiredError(YouTubeMCPError):
    error_code = "CONFIRMATION_REQUIRED"
    default_message = "Explicit playlist confirmation is required."
    default_remediation = (
        "Re-run propose_playlist and obtain explicit human confirmation before "
        "calling confirm_playlist."
    )


class OAuthReauthorizationRequiredError(YouTubeMCPError):
    error_code = "OAUTH_REAUTH_REQUIRED"
    default_message = "YouTube OAuth authorization must be renewed."
    default_remediation = (
        "Re-run the local OAuth 2.0 authorization flow to issue a fresh refresh token."
    )


class YouTubeSignupRequiredError(YouTubeMCPError):
    error_code = "YOUTUBE_SIGNUP_REQUIRED"
    default_message = "The authenticated Google account has no initialized YouTube channel."
    default_remediation = (
        "Create a YouTube channel on the authenticated Google account before creating playlists."
    )
