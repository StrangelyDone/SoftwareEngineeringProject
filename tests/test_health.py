"""Offline integration tests for the FastAPI health and OpenAPI routes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from youtube_mcp import __version__
from youtube_mcp.config import Settings
from youtube_mcp.providers.mock import FixtureMockProvider
from youtube_mcp.server import create_app


def _settings(tmp_path: Path, budget: int = 10000) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'health.db'}",
        daily_quota_budget=budget,
    )


def test_health_route_returns_ok_in_wal_mode(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(
        settings=settings,
        provider=FixtureMockProvider(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "ok",
        "service": "youtube-video-intelligence-mcp",
        "version": __version__,
        "journal_mode": "wal",
        "daily_quota_budget": 10000,
        "remaining_quota": 10000,
    }


def test_openapi_document_exposes_health_route(tmp_path: Path) -> None:
    app = create_app(
        settings=_settings(tmp_path),
        provider=FixtureMockProvider(),
    )

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["openapi"].startswith("3.")
    assert "/api/v1/health" in document["paths"]
    assert "get" in document["paths"]["/api/v1/health"]


def test_health_route_uses_configured_quota_budget(tmp_path: Path) -> None:
    settings = _settings(tmp_path, budget=2500)
    app = create_app(settings=settings, provider=FixtureMockProvider())

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["daily_quota_budget"] == 2500
    assert payload["remaining_quota"] == 2500


@pytest.mark.parametrize(
    ("wal_status", "expected_status"),
    [
        ({"journal_mode": "delete", "daily_quota_budget": 10000,
          "used_today": 0, "remaining_quota": 10000}, 503),
    ],
)
def test_health_route_reports_non_wal_database_as_degraded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wal_status: dict[str, object],
    expected_status: int,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr("youtube_mcp.server.check_wal_health", lambda **_: wal_status)
    app = create_app(settings=settings, provider=FixtureMockProvider())

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == expected_status
    assert response.json()["status"] == "degraded"
    assert response.json()["journal_mode"] == "delete"


def test_health_route_reports_sqlite_failure_as_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)

    def raise_operational_error(**_: object) -> dict[str, object]:
        raise sqlite3.OperationalError("database unavailable")

    monkeypatch.setattr("youtube_mcp.server.check_wal_health", raise_operational_error)
    app = create_app(settings=settings, provider=FixtureMockProvider())

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["journal_mode"] == "unavailable"
