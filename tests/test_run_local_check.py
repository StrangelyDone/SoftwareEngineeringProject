"""Focused tests for the M0.4 local-check helper."""

from __future__ import annotations

import subprocess
import sys
import time

from scripts.run_local_check import (
    find_free_loopback_port,
    terminate_process,
    validate_health_payload,
)


def test_find_free_loopback_port_returns_valid_port() -> None:
    port = find_free_loopback_port()
    assert 1 <= port <= 65535


def test_validate_health_payload_requires_safe_fields() -> None:
    assert validate_health_payload(
        {
            "status": "ok",
            "journal_mode": "wal",
            "service": "youtube-video-intelligence-mcp",
            "remaining_quota": 10000,
        }
    )
    assert not validate_health_payload(
        {"status": "ok", "journal_mode": "delete", "service": "server"}
    )
    assert not validate_health_payload(None)


def test_terminate_process_stops_exact_child() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.1)

    terminate_process(process)

    assert process.poll() is not None
