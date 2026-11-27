# Stage 2 TQ-7 Skill Evaluation Results

- **Issue:** #29
- **Branch:** `docs/29-stage2-skill-evals`
- **Run date:** 2026-11-27
- **Machine 1:** Abhinav — Ubuntu 24.04.3 LTS
- **Python:** 3.12.3

These are execution results, not simulated outputs. Vault queries were answered from `brain/`; gaps are stated where the vault does not specify enough detail.

## SK-1 — brain-ingest

**Input:** Verify existing Stage 1/2 ingested notes and audit entries in `brain/` and `brain/log.md`; validate the vault.

**Command:**

```text
/usr/bin/python3 scripts/check_brain.py
```

**Observed output:**

```text
Second Brain validation PASSED (18 markdown file(s) checked).
```

The vault contained Stage 1/2 notes, including `youtube-oauth2-flow`, `sqlite-wal-mode`, `provider-pattern-isolation`, `mcp-architecture`, `agent-skills-format-specification`, `fastmcp-python-sdk`, and the three Abhinav-authored technical notes evaluated under SK-2. Corresponding Stage 1/2 ingests were present in `brain/log.md`.

**Verdict: PASS.** Existing notes and audit entries were present, and schema/link validation passed.

## SK-2 — brain-refine

**Input:** Audit PARA placement, note frontmatter, links, index coverage, and audit history.

**Initial validator command and output:**

```text
/usr/bin/python3 scripts/check_brain.py
Second Brain validation PASSED (18 markdown file(s) checked).
```

The validator confirmed schema and wikilink integrity but does not check whether every note appears in the index. The manual index audit found three distilled notes in `brain/inbox/` with `type: resource`, plus existing `ai-session-2026-11-24` and `stage-1-review` notes missing from `brain/index.md`.

**Refinement performed:** Moved the following notes into `brain/resources/` without changing their content:

- `iso-8601-duration-parsing-and-playlist-constraint-packing.md`
- `prompt-injection-defense-for-untrusted-youtube-metadata.md`
- `tf-idf-cosine-similarity-for-video-and-channel-ranking.md`

Added the three resources and the two omitted existing notes to their matching index sections, and removed `.gitkeep` files from `inbox/`, `projects/`, and `resources/`, which now contain Markdown notes.

**Post-refinement command and observed output:**

```text
/usr/bin/python3 scripts/check_brain.py
Second Brain validation PASSED (18 markdown file(s) checked).
```

**Verdict: PASS.** Manual index coverage was synchronized and the post-refinement schema/link check passed. The existing brain-ingest audit rows for the three technical notes were preserved.

## SK-3 — brain-query

Queries were issued against `brain/` after reading `brain/index.md`; each answer cites its source wikilink and path.

### Query (a)

**Exact input:** “Which ADRs justify SQLite WAL mode, cache TTLs, and our pre-flight quota guard?”

**Search command:**

```text
rg -n 'WAL|TTL|24-hour|7-day|pre-flight|300|quota' brain/index.md brain/resources brain/inbox/ai-session-2026-11-26.md
```

**Cited answer:** The vault's session record maps the 24-hour `cached_videos` and 7-day `cached_channels` TTLs to ADR-002, and the 300-unit soft-warning threshold plus `max_search_pages = 2` to ADR-006. The quota resource requires tracking quota in local storage and rejecting over-budget workflows before an outbound API call. The SQLite resource supports WAL for local quota/cache storage and atomic quota-ledger updates. The vault does **not** explicitly map the WAL decision itself to an ADR number, so that part cannot be named from vault evidence alone.

**Cited notes:** [[sqlite-wal-mode]] (`brain/resources/sqlite-wal-mode.md`); [[youtube-api-quota-system]] (`brain/resources/youtube-api-quota-system.md`); [[ai-session-2026-11-26]] (`brain/inbox/ai-session-2026-11-26.md`).

**Verdict: PASS — gap explicitly reported.** ADR-002 and ADR-006 mappings were grounded in the session note; the missing WAL-to-ADR mapping was not guessed.

### Query (b)

**Exact input:** “How do we prevent untrusted YouTube metadata from triggering unauthorized playlist writes?”

**Search command:**

```text
rg -n 'untrusted|explicit user action|confirmation|playlists.insert|playlistItems.insert' brain/resources/prompt-injection-defense-for-untrusted-youtube-metadata.md
```

**Cited answer:** Keep metadata in typed, explicitly untrusted data fields; do not treat it as instructions, a user-authenticated command, or confirmation. A server-side allowlist controls tool calls and mutation parameters. Show a preview, then allow `playlists.insert` and `playlistItems.insert` only after a distinct, authenticated explicit confirmation. Metadata cannot auto-confirm, change constraints after preview, or expand the approved set.

**Cited note:** [[prompt-injection-defense-for-untrusted-youtube-metadata]] (`brain/resources/prompt-injection-defense-for-untrusted-youtube-metadata.md`).

**Verdict: PASS.** The answer was directly supported by the vault.

### Query (c)

**Exact input:** “How is similarity scoring calculated when a video has missing tags?”

**Search command:**

```text
rg -n 'Missing and malformed|TF-IDF formula|Cosine similarity|dynamic missing-tag|0\.65|0\.25|0\.10' brain/resources/tf-idf-cosine-similarity-for-video-and-channel-ranking.md brain/inbox/ai-session-2026-11-26.md
```

**Cited answer:** Treat missing `snippet.tags[]` as `[]`; missing category/topic data is absent, and one bad resource must not fail the whole ranking batch. The remaining metadata signals can still be scored using smoothed TF-IDF and cosine similarity. The session log records ADR-004's weights (`0.65`, `0.25`, `0.10`) and dynamic missing-tag reweighting, but the vault does not specify the exact per-feature mapping or normalization formula. The resource's `0.55 / 0.25 / 0.20` late-fusion formula is explicitly an example, not the ADR-004 weights.

**Cited notes:** [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] (`brain/resources/tf-idf-cosine-similarity-for-video-and-channel-ranking.md`); [[ai-session-2026-11-26]] (`brain/inbox/ai-session-2026-11-26.md`).

**Verdict: PASS — gap explicitly reported.** The missing-tag policy and recorded weights were cited; unspecified normalization details were not invented.

## SK-4 — local-check

### Machine 1 — Abhinav (Ubuntu Linux)

**Input:** Run the full offline local-check with Python 3.11+, editable development dependencies, validators/tests, a loopback-only server, temporary SQLite, health/OpenAPI checks, cleanup, and no live YouTube credentials.

The first attempt used `/usr/bin/python3` and failed because the system interpreter is externally managed. It stopped before server startup:

```text
PASS: Python 3.11+ (3.12.3 at /usr/bin/python3)
FAIL: Dependencies installed
FAIL: Offline tests and validators passed
FAIL: Local server started
FAIL: Health/OpenAPI passed and server stopped
local-check: FAIL
FAIL: Dependency installation: error: externally-managed-environment
```

The workflow script imports `httpx` before it installs project dependencies. A bare temporary virtual environment therefore also initially failed with `ModuleNotFoundError: No module named 'httpx'`. Recovery used a temporary venv and installed the project before rerunning:

```text
/tmp/m05-local-check-venv/bin/python -m pip install -e ".[dev]"
exit code: 0
```

**Successful command** (the credential and token-path variables were explicitly empty for this run):

```text
env YOUTUBE_API_KEY= YOUTUBE_OAUTH_CLIENT_ID= YOUTUBE_OAUTH_CLIENT_SECRET= YOUTUBE_OAUTH_TOKEN_PATH= /tmp/m05-local-check-venv/bin/python scripts/run_local_check.py
```

**Observed five-step output:**

```text
PASS: Python 3.11+ (3.12.3 at /tmp/m05-local-check-venv/bin/python)
PASS: Dependencies installed
PASS: Offline tests and validators passed
PASS: Local server started
PASS: Health/OpenAPI passed and server stopped
local-check: PASS
```

The script checked HTTP 200 for health and OpenAPI, and validated health fields `status: "ok"`, `journal_mode: "wal"`, a non-empty service name, and `remaining_quota`. It terminated its exact child process and cleaned the temporary database directory. Afterward, `ss -ltnp 'sport = :8000'` showed only the column header and no listener.

| Step | Result | Observed |
|---|---|---|
| 1. Python version | PASS | Python 3.12.3 at `/tmp/m05-local-check-venv/bin/python` |
| 2. Dependencies | PASS | Editable project and dev dependencies installed |
| 3. Offline tests and validators | PASS | `ruff`, `pytest`, skill, brain, and ADR checks passed |
| 4. Local server | PASS | Started by the script on loopback |
| 5. Health/OpenAPI and cleanup | PASS | Required health fields and OpenAPI passed; process stopped and temporary DB cleaned |

### Machine 2 — Teammate

**TODO: Paste Teammate Machine 2 Output**

| Step | Result | Observed |
|---|---|---|
| 1. Python version | TODO | Paste teammate output |
| 2. Dependencies | TODO | Paste teammate output |
| 3. Offline tests and validators | TODO | Paste teammate output |
| 4. Local server | TODO | Paste teammate output |
| 5. Health/OpenAPI and cleanup | TODO | Paste teammate output |

## Final Repository Validation

**Command sequence** (using the temporary venv first on `PATH`):

```text
export PATH=/tmp/m05-local-check-venv/bin:$PATH; ruff check . && pytest -v && python scripts/validate_skills.py && python scripts/check_brain.py && python scripts/validate_adrs.py
```

**Observed results:**

```text
All checks passed!
======================== 21 passed, 1 warning in 1.05s ========================
[WARN] .agents/skills/video-to-playlist/SKILL.md: no Second Brain note citation ([[...]] or brain/...) found (SB-3).
SKILL.md validation PASSED (5 skill(s) checked).
Second Brain validation PASSED (19 markdown file(s) checked).
ADR validation PASSED (6 numbered ADR(s) checked).
```

All five commands exited 0. The two warnings were non-failing: a Starlette `TestClient` deprecation warning during pytest and the pre-existing SB-3 citation warning for the Stage 3 placeholder skill.
