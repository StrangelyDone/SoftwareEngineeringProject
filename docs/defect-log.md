# Defect Log (`TQ-8`)

**Project:** YouTube Video Intelligence MCP Server  
**Policy:** Every significant defect resolved in the repository is logged here with its GitHub Issue, root cause, fix summary, and permanent regression test in `tests/test_regressions.py` (`TQ-8`).

| Defect ID | GitHub Issue | Date | Affected Files | Root Cause | Fix Summary | Regression Test |
|---|---|---|---|---|---|---|
| `DEF-001` | `#58` | 2026-11-28 | `tests/test_db_wal.py`, `src/youtube_mcp/db.py` | `test_quota_queries_never_return_negative_remaining_quota` seeded `quota_ledger` with hardcoded `date_utc="2026-11-27"`, while `check_wal_health()` queried `utc_today_str()` (`2026-11-28`), causing `used_today == 0` and `remaining_quota == 10000` after UTC midnight rollover. | Added optional `date_utc: str \| None = None` (defaulting to `utc_today_str()`) to `check_wal_health()` and `SQLiteRepository.check_wal_health()`, and updated `tests/test_db_wal.py` to seed using `utc_today_str()`. | `tests/test_regressions.py::test_regression_issue_58_check_wal_health_clamping_and_utc_day_rollover` |
