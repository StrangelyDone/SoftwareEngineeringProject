---
title: "YouTube Engagement and Library Analytics Metrics"
author: "@StrangelyDone"
created: 2026-11-26
tags: [youtube-mcp, resource, analytics, engagement]
type: resource
---

# YouTube Engagement and Library Analytics Metrics

## Summary
The project’s FR-4 analyzes a user's liked videos, subscriptions, and playlists to report channel and category distributions, temporal trends, duration preferences, and period-over-period changes. Implement the metrics over clearly defined cohorts using metadata from the official YouTube Data API v3, and keep source counts and denominators explicit. In particular, a video's publication timestamp is not the time the user engaged with it, so trends must state which event timestamp they measure.

## Key Technical Details
- **Channel and category distributions:** For each defined library cohort, count videos by stable uploader `channelId` (with `channelTitle` for display) and by `snippet.categoryId`; compute share as `count / total eligible items in that cohort * 100`. Rank channels by count and include both count and percentage. `videoCategories.list(part="snippet", ...)` can map category IDs to titles; keep the ID as the key because category titles are display labels. State whether totals use unique video IDs or membership occurrences, and don't mix subscribed-channel entities directly into video denominators.
- **Video metadata:** `videos.list` returns `snippet.categoryId`, `snippet.channelId`, `snippet.publishedAt`, and `contentDetails.duration` when the corresponding `part` values are requested. These fields support classification, grouping, and duration analysis; missing or unavailable video metadata should be excluded from a metric's eligible denominator and reported rather than silently treated as a value.
- **Duration parsing and statistics:** Parse YouTube's ISO-8601 duration strings such as `PT15M33S` and `PT1H2M3S` into integer seconds: `seconds = 3600 * hours + 60 * minutes + seconds`. Compute mean, median, minimum, maximum, and a histogram over successfully parsed durations. Treat missing or malformed durations as invalid data, not zero; test exact bucket boundaries.
- **Duration buckets:** Use non-overlapping integer-second ranges: Short `<300`; Medium `300–1199`; Long `1200–3600`; Deep-Dive `>3600`. Thus exactly 5 minutes is Medium, exactly 20 minutes is Long, and exactly 60 minutes remains Long.
- **Monthly and quarterly trends:** Parse the chosen source timestamp as an ISO-8601 datetime, normalize to UTC, and group by calendar month (`YYYY-MM`) or calendar quarter (`YYYY-Qn`, where Q1 is Jan–Mar). Aggregate counts and category/channel shares per bucket to compare changes in dominant topics. Preserve the timestamp's meaning: `video.snippet.publishedAt` is when the video was published, `playlistItem.snippet.publishedAt` is when it was added to that playlist, and a liked-video result does not provide the time the user liked it. Do not label publication-time trends as user activity trends.
- **Period-over-period deltas:** For a metric with values `A` and `B`, absolute change is `B - A`; when `A != 0`, percentage change is `((B - A) / A) * 100`. When `A == 0`, the percentage is undefined: report it as `N/A`/“new from zero” alongside the absolute change, including when both periods are zero. Never divide by zero or substitute a misleading percentage. For top-channel/category comparisons, align metric keys across both windows and explicitly represent absent keys as zero.
- **Testing (TQ-1, TQ-4):** Use deterministic fixtures to test numerator/denominator and percentage calculations, UTC month/quarter boundaries, each duration boundary (299/300, 1199/1200, 3600/3601 seconds), malformed or missing durations, missing categories/channel IDs, and zero-baseline deltas. Keep malformed records from corrupting an entire aggregate and make exclusions observable.

## Project Traceability & Connections
- **Related Requirements:** FR-4, TQ-1, TQ-4
- **Related Notes:** [[index]], [[iso-8601-duration-parsing-and-playlist-constraint-packing]], [[youtube-api-quota-system]], [[provider-pattern-isolation]]
- **Source:**
  - Project requirements: `SE_SRS.pdf`, REQ-FR4-1 through REQ-FR4-4 and TQ-1/TQ-4.
  - [YouTube Data API v3 video resource](https://developers.google.com/youtube/data/reference/rest/v3/videos)
  - [YouTube Data API v3 videos.list](https://developers.google.com/youtube/data/reference/rest/v3/videos/list)
  - [YouTube Data API v3 videoCategories.list](https://developers.google.com/youtube/data/reference/rest/v3/videoCategories/list)
  - [YouTube Data API v3 playlist item resource](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems)
