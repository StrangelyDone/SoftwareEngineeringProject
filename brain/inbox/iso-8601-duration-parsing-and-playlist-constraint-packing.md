---
title: "ISO 8601 Duration Parsing and Playlist Constraint Packing"
author: "Abhinav"
date: "2026-11-26"
created: 2026-11-26
tags: [youtube-mcp, resource, duration, iso-8601, playlist]
type: resource
---

# ISO 8601 Duration Parsing and Playlist Constraint Packing

## Summary
YouTube video durations are returned in ISO 8601 format in `videos.contentDetails.duration`. The value must be parsed and converted to whole seconds before analyzing engagement duration preferences or enforcing playlist total-duration, per-video, and language constraints.

## Key Technical Details
- **API field:** Call `videos.list?part=snippet,contentDetails` and read `items[].snippet` plus `items[].contentDetails.duration`. Example values include `PT15M33S` (933 seconds) and `PT1H2M3S` (3723 seconds). YouTube duration strings are not calendar durations and must use hours, minutes, and seconds rather than locale formatting.
- **Strict parser pattern:** Accept `P[nD][T[nH][nM][nS]]` and require at least one value-bearing component. A portable pattern is `^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:[.,]\d+)?)S)?)?$`; use named capture groups where supported, but preserve the same component constraints. `PT0S` is valid; a bare `P` or `PT` is invalid.
- **Portability-safe parser:** Prefer an explicit pattern such as `^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:[.,]\d+)?)S)?)?$`, then reject strings for which every capture is absent. Compute `total_seconds = 86400*d + 3600*h + 60*m + float(seconds)` and reject negative values, values containing only `P`, missing time units, or decimal fractions with more precision than the application's policy.
- **Integer policy:** Convert the result to integer milliseconds or an exact rational if sub-second precision can occur; for video playlist constraints, compare integer seconds so `PT15M33S` is exactly 933. `PT0S` is valid for unavailable/live edge cases; missing or malformed duration must be excluded rather than silently treated as zero.
- **Duration preferences:** For FR-4, calculate medians and histograms of successfully parsed durations by period (for example 30/90-day cohorts) and report bucket counts such as under 4 minutes, 4-10 minutes, 10-20 minutes, and over 20 minutes. Store the parsing status separately from the measured value.
- **Constraint packing:** Filter first to `duration_seconds <= max_video_length_seconds`, then language-match against `snippet.defaultLanguage` or `snippet.defaultAudioLanguage` when a language constraint is supplied. For a target total `T`, require `T - tolerance <= sum(selected durations) <= T`, or define exact-equality mode when no overflow is permitted.
- **Selection algorithms:** Use dynamic programming for exact subset sums with integer seconds; complexity is O(n*T) memory/time. For large targets or weighted ranking, use branch-and-bound or a bounded knapsack: rank eligible candidates by similarity/relevance, enforce per-video and total limits, and never exceed the requested total. Greedy longest-first can fail to find a valid total.
- **Preview before mutation:** Return video IDs, title, duration, language, and cumulative seconds for preview. Only `playlists.insert` and `playlistItems.insert` mutate YouTube state, and mutation is allowed only after the explicit confirmation step. These calls cost 50 and 50 quota units respectively.

## Project Traceability & Connections
- **Related Requirements:** FR-4, FR-5, TQ-1
- **Related Notes:** [[index]], [[youtube-api-quota-system]], [[youtube-oauth2-flow]], [[provider-pattern-isolation]]
- **Source:** YouTube Data API `videos.list` resource documentation; ISO 8601 duration syntax; project FR-4/FR-5 requirements.
