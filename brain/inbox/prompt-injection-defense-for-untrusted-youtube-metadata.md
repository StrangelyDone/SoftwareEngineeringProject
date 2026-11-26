---
title: "Prompt Injection Defense for Untrusted YouTube Metadata"
author: "Abhinav"
date: "2026-11-26"
created: 2026-11-26
tags: [youtube-mcp, resource, security, prompt-injection, confirmation]
type: resource
---

# Prompt Injection Defense for Untrusted YouTube Metadata

## Summary
YouTube titles, descriptions, tags, channel names, and channel descriptions are untrusted text. Any downstream prompt or parser must isolate these values as data; they must never create instructions that change tool access, constraint interpretation, OAuth scopes, or the explicit confirmation required by FR-5.

## Key Technical Details
- **Threat boundary:** Metadata fields including `snippet.title`, `snippet.description`, `snippet.tags[]`, `channels.snippet.title`, `channels.snippet.description`, `brandingSettings.channel.keywords`, and playlist item text can contain direct-instruction payloads such as "ignore previous instructions", tool names, hidden HTML, or deceptive confirmation text.
- **Data-only handling:** Keep metadata in typed fields and encode it into a dedicated untrusted-data structure; never concatenate it directly into system/developer instructions or shell, SQL, URL, HTML, or command strings. A retrieved title is not a policy document or a user-authenticated command.
- **Sanitization limits:** Strip/normalize control characters, reject or escape NUL and bidi/control sequences, remove active markup before HTML rendering, and HTML-escape text if it is displayed in HTML. Escaping is presentation hygiene, not authorization: do not use sanitization as the sole guard because adversarial text can remain meaningful.
- **Delimiters and labels:** If metadata must enter an LLM context, place it in clearly separated fields with fixed labels and tell the model that field contents are evidence only. Do not rely on delimiters alone, because they do not prevent instruction interpretation.
- **No metadata-driven side effects:** A server-side allowlist must decide all tool calls and mutation parameters. Never parse text as natural-language confirmation, role/identity data, tool selection, or OAuth scope elevation; confirmations must come from an authenticated, unambiguous explicit user action.
- **FR-5 confirmation invariant:** Preview playlist title/description, video IDs, titles, durations, and cumulative seconds. The `playlists.insert` and `playlistItems.insert` calls may execute only after a distinct confirmation step. Metadata cannot auto-confirm, mark a confirmation complete, rewrite constraints after preview, or expand the preview set.
- **Provider isolation:** Fetch and normalize metadata behind provider interfaces and preserve provenance, for example `source=api`, `resource_type`, and `untrusted=true`. Recorded fixtures must include malicious payloads but must contain no secrets or real PII.
- **Negative/security tests:** Test titles/descriptions/tags containing instruction overrides, fake confirmation phrases, HTML/Markdown/script payloads, ANSI/bidi controls, excessively long text, and attempts to trigger `playlists.insert` or `playlistItems.insert`. Verify no mutation tool is called before confirmation and that malformed/hostile metadata cannot alter the allowlisted scope or constraints.
- **Failure behavior:** Reject or safely omit malformed fields, enforce maximum text lengths, and return structured errors. Never send raw exception text or untrusted metadata to privileged prompts or logs without redaction and fixed escaping.

## Project Traceability & Connections
- **Related Requirements:** FR-5, TQ-4, Security Testing
- **Related Notes:** [[index]], [[provider-pattern-isolation]], [[youtube-oauth2-flow]], [[youtube-api-quota-system]], [[tf-idf-cosine-similarity-for-video-and-channel-ranking]], [[iso-8601-duration-parsing-and-playlist-constraint-packing]]
- **Source:** Project prompt-injection and explicit-confirmation guardrails in `AGENTS.md`; YouTube Data API resource field documentation.
