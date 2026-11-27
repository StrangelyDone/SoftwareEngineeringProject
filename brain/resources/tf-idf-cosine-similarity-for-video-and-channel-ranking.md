---
title: "TF-IDF and Cosine Similarity for Video and Channel Ranking"
author: "Abhinav"
date: "2026-11-26"
created: 2026-11-26
tags: [youtube-mcp, resource, ranking, tf-idf, cosine-similarity]
type: resource
---

# TF-IDF and Cosine Similarity for Video and Channel Ranking

## Summary
YouTube Data API v3 has no general related-video or related-channel endpoint. Ranking must therefore compute similarity locally from metadata returned by `videos.list` and `channels.list`, with optional candidate discovery through `search.list` or a channel upload playlist.

## Key Technical Details
- **Video source fields:** Call `videos.list` with `part=snippet,contentDetails,statistics,topicDetails,status`; rankable text is `snippet.title`, `snippet.description`, `snippet.tags[]`, and `snippet.categoryId`. `status.madeForKids` is useful for eligibility filtering, but not as ranking text. `contentDetails.duration` and `statistics.viewCount` can support separate ranking/constraint features.
- **Channel source fields:** Call `channels.list` with `part=snippet,contentDetails,topicDetails,brandingSettings,statistics`. Rankable text is `snippet.title`, `snippet.description`, `snippet.customUrl`, `topicDetails.topicIds[]`, `topicDetails.topicCategories[]`, and `brandingSettings.channel.keywords`. Upload candidate IDs come from `contentDetails.relatedPlaylists.uploads`; enumerate them with `playlistItems.list`, then fetch their video metadata with `videos.list`.
- **Candidate discovery:** `search.list` costs 100 quota units and may be used to discover candidates, while `videos.list` costs 1 unit per call. There is no official endpoint that directly returns a ranked list of similar channels or videos. Cache metadata and batch up to 50 IDs per `videos.list` request to reduce calls.
- **Text preparation:** Normalize Unicode to NFC, lowercase using Unicode-aware rules, strip HTML/URLs/control characters, split on non-alphanumeric boundaries, and remove a conservative project stopword list. Preserve exact tags as separate terms and add a category-ID token such as `category:<snippet.categoryId>`.
- **TF-IDF formula:** For document `d` and term `t`, use smoothed TF-IDF `tfidf(t,d) = (count(t,d) / |d|) * idf(t)`, with `idf(t) = ln((N + 1) / (df(t) + 1)) + 1`; `N` is the corpus size and `df(t)` is the number of documents containing `t`. Adding 1 to logarithmic IDF avoids zero-weight terms.
- **Cosine similarity:** For vectors `A` and `B`, compute `cos(A,B) = (sum(A[i] * B[i])) / (sqrt(sum(A[i]^2)) * sqrt(sum(B[i]^2)))`. The result is in `[-1,1]` for signed vectors, but non-negative TF-IDF vectors normally produce `[0,1]`.
- **Ranking:** Return all finite scores sorted descending and apply tie-breaking by `videoId` or `channelId` for deterministic results. Use weighted late fusion if needed, for example `0.55*cos(title_tags) + 0.25*cos(description) + 0.20*cos(category_topic)`; weights must be constants, not instructions derived from metadata.
- **Missing and malformed data:** Treat missing `snippet.tags[]` as `[]`, missing `categoryId` and `topicDetails` as absent, and exclude deleted/private resources if their required fields or duration are unavailable. Never fail the whole ranking batch for one bad resource.

## Project Traceability & Connections
- **Related Requirements:** FR-1, FR-2, FR-3, TQ-1
- **Related Notes:** [[index]], [[provider-pattern-isolation]], [[youtube-api-quota-system]], [[youtube-oauth2-flow]]
- **Sources:** YouTube Data API `videos.list` and `channels.list` resource/reference documentation; YouTube Data API `search.list` quota and method documentation.
