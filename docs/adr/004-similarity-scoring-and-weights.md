# ADR-004: Metadata Similarity Scoring and Feature Weight Calibration

- **ADR ID:** ADR-004
- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** YouTube MCP Team
- **Related Requirements:** SE-3, SB-3, FR-1, FR-2, REQ-FR1-4, REQ-FR1-5, REQ-FR2-3, REQ-FR2-4, TQ-1, TQ-4, NFR-PERF-2, TBD-02
- **Related Issue:** #20

## Context
YouTube Data API v3 provides no general related-video or related-channel similarity endpoint (`FR-1`, `FR-2`), and `CON-2` prohibits scraping or downloading third-party captions. Similarity ranking must therefore operate strictly over official metadata (`snippet`, `topicDetails`, `brandingSettings`, `contentDetails`).

Per `REQ-FR1-4` and `REQ-FR1-5` in `docs/srs.pdf`, video similarity combines:
- $S_{\text{tfidf}}(A, B) \in [0.0, 1.0]$: L2-normalized TF-IDF cosine similarity over normalized `snippet.title` ($2\times$ weight) and `snippet.description` ($1\times$ weight).
- $S_{\text{tags}}(A, B) = \frac{|T_A \cap T_B|}{|T_A \cup T_B|}$: Jaccard overlap over normalized `snippet.tags[]`.
- $S_{\text{cat}}(A, B) \in \{0, 1\}$: exact match on `snippet.categoryId`.

SRS `TBD-02` deferred calibrating the exact default composite weights $(w_1, w_2, w_3)$ to Stage 2, and `TQ-4` requires graceful handling when `snippet.tags` is missing or empty without raising a division-by-zero error.

## Options Considered
- **Option A — Dense Neural Embeddings (`sentence-transformers` / External LLM Embedding APIs):**
  - *Pros:* Captures semantic synonyms beyond lexical overlap.
  - *Cons:* Introduces large model weights or extra network/API cost and latency, risks exceeding the `<500 ms` local latency budget for 200 cached videos (`NFR-PERF-2`), and complicates deterministic offline CI tests (`TQ-1`, `TQ-5`).
- **Option B — Unweighted Pure Bag-of-Words Cosine Similarity:**
  - *Pros:* Minimal code.
  - *Cons:* Ignores explicit creator tags (`snippet.tags[]`) and YouTube taxonomy (`snippet.categoryId`), degrading precision when descriptions are sparse or SEO-stuffed.
- **Option C — Deterministic Smoothed TF-IDF Cosine + Tag Jaccard + Category Match with Calibrated Weights and Dynamic Re-Weighting:**
  - *Pros:* Pure Python / lightweight math runs well under 500 ms for 200 videos (`NFR-PERF-2`), yields explainable `matching_terms` (`REQ-FR1-6`), stays 100% deterministic for `TQ-1` unit tests, and handles missing tags cleanly (`TQ-4`).
  - *Cons:* Lexical matching cannot equate unseen synonyms unless captured in tags or category metadata.

## Decision
Adopt deterministic **TF-IDF cosine + tag Jaccard + category match** scoring for `FR-1` and `FR-2`, and **close `TBD-02`** with calibrated default weights $(w_1 = 0.65,\; w_2 = 0.25,\; w_3 = 0.10)$:
1. **Text Normalization & Smoothed TF-IDF (`REQ-FR1-4`):** Normalize Unicode to NFC, lowercase, strip URLs/HTML/control sequences, tokenize on alphanumeric boundaries, and drop conservative stopwords. Weight `snippet.title` tokens $2\times$ and `snippet.description` tokens $1\times$. Compute smoothed TF-IDF ($\text{idf}(t) = \ln((N + 1) / (\text{df}(t) + 1)) + 1$) and L2-normalized cosine similarity $S_{\text{tfidf}} \in [0.0, 1.0]$.
2. **Calibrated Default Weights (Closes `TBD-02`):**
   $$S_{\text{composite}}(A, B) = 0.65\, S_{\text{tfidf}}(A, B) + 0.25\, S_{\text{tags}}(A, B) + 0.10\, S_{\text{cat}}(A, B)$$
   - `0.65` prioritizes rich title/description topical overlap across all videos (including untagged uploads).
   - `0.25` rewards shared creator tags without letting sparse or noisy tag lists dominate.
   - `0.10` acts as a domain-alignment signal for matching `categoryId`.
   - Weights are stored as server-side constants/configuration, never derived from untrusted metadata.
3. **Missing-Tag Dynamic Re-Weighting (`REQ-FR1-5`, `TQ-4`):** Whenever either video has missing or empty `snippet.tags[]` (meaning $|T_A \cup T_B| = 0$), skip $S_{\text{tags}}$ without dividing by zero and re-normalize $w_1$ and $w_3$ proportionally:
   $$w_1' = \frac{w_1}{w_1 + w_3} = \frac{0.65}{0.75} \approx 0.8667, \qquad w_3' = \frac{w_3}{w_1 + w_3} = \frac{0.10}{0.75} \approx 0.1333$$
   If `categoryId` is also missing on either item, fall back cleanly to $w_1'' = 1.0$ ($S_{\text{tfidf}}$ only).
4. **Channel Similarity (`FR-2`, `REQ-FR2-3`, `REQ-FR2-4`):** Build an aggregated channel document from `snippet.description`, `brandingSettings.channel.keywords`, `topicDetails.topicCategories`, and recent upload titles/tags (`relatedPlaylists.uploads`), then apply the same deterministic TF-IDF cosine + topic-category Jaccard overlap + upload duration profile similarity, breaking score ties deterministically by `video_id` / `channel_id`.

## Consequences
- **Positive:**
  - Closes `TBD-02` with clear, tunable constants ($w_1=0.65, w_2=0.25, w_3=0.10$) and safe missing-field fallbacks (`TQ-4`).
  - Easily executes in `<500 ms` for 200 cached videos (`NFR-PERF-2`) with fully deterministic outputs and `matching_terms` rationales (`TQ-1`).
- **Negative / Trade-offs:**
  - Purely lexical TF-IDF does not capture deep cross-lingual or zero-overlap semantic paraphrases; future calibration can adjust $(w_1, w_2, w_3)$ via offline fixture benchmarks without changing the scoring contract.

## Citations (SB-3)
- [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] (`brain/inbox/tf-idf-cosine-similarity-for-video-and-channel-ranking.md`)
- [[youtube-api-quota-system]] (`brain/resources/youtube-api-quota-system.md`)
- [[youtube-engagement-library-analytics]] (`brain/resources/youtube-engagement-library-analytics.md`)
- [[srs-requirements-index]] (`brain/projects/srs-requirements-index.md`)
