"""Run the offline Stage 2 local-check workflow with clean process teardown."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SERVER_READY_TIMEOUT_SECONDS = 5.0


def run_command(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    """Run a command and preserve a concise captured result."""
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _first_error(result: subprocess.CompletedProcess[str]) -> str:
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    return (stderr or stdout or f"exit status {result.returncode}").splitlines()[0]


def find_free_loopback_port() -> int:
    """Reserve a loopback port briefly and return it for the server process."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def terminate_process(process: subprocess.Popen[bytes] | None) -> None:
    """Terminate only the supplied child process and wait for it to exit."""
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def validate_health_payload(payload: object) -> bool:
    """Validate the read-only health response fields used by local-check."""
    if not isinstance(payload, dict):
        return False
    return (
        payload.get("status") == "ok"
        and payload.get("journal_mode") == "wal"
        and isinstance(payload.get("service"), str)
        and bool(payload.get("service"))
        and "remaining_quota" in payload
    )


def wait_for_health(
    base_url: str,
    timeout_seconds: float = SERVER_READY_TIMEOUT_SECONDS,
) -> tuple[int | None, dict[str, object] | None]:
    """Wait briefly for the local health endpoint and return its response."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=1.0) as client:
                health_response = client.get(f"{base_url}/api/v1/health")
                if health_response.status_code == 200:
                    try:
                        payload = health_response.json()
                    except ValueError as exc:
                        last_error = exc
                    else:
                        if validate_health_payload(payload):
                            return health_response.status_code, payload
                        last_error = RuntimeError("health payload validation failed")
                else:
                    last_error = RuntimeError(
                        f"health returned HTTP {health_response.status_code}"
                    )
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.1)
    if last_error is not None:
        raise RuntimeError(str(last_error))
    raise RuntimeError("local server readiness timed out")


def print_status_rows(statuses: Iterable[tuple[bool, str]]) -> bool:
    """Print the five-step table and overall verdict."""
    all_passed = True
    for passed, label in statuses:
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
        all_passed = all_passed and passed
    print(f"local-check: {'PASS' if all_passed else 'FAIL'}")
    return all_passed


def main() -> int:
    statuses: list[tuple[bool, str]] = []
    process: subprocess.Popen[bytes] | None = None
    saved_database_url = os.environ.get("DATABASE_URL")

    python_ok = sys.version_info >= (3, 11)
    statuses.append(
        (python_ok, f"Python 3.11+ ({sys.version.split()[0]} at {sys.executable})")
    )
    if not python_ok:
        print_status_rows(statuses)
        return 1

    dependency_result = run_command(
        [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
    )
    dependencies_ok = dependency_result.returncode == 0
    statuses.append((dependencies_ok, "Dependencies installed"))
    if not dependencies_ok:
        statuses.extend(
            [
                (False, "Offline tests and validators passed"),
                (False, "Local server started"),
                (False, "Health/OpenAPI passed and server stopped"),
            ]
        )
        print_status_rows(statuses)
        print(f"FAIL: Dependency installation: {_first_error(dependency_result)}")
        return 1

    validation_commands = [
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "pytest", "-v"],
        [sys.executable, "scripts/validate_skills.py"],
        [sys.executable, "scripts/check_brain.py"],
        [sys.executable, "scripts/validate_adrs.py"],
    ]
    validation_ok = True
    validation_error = ""
    for command in validation_commands:
        result = run_command(command)
        if result.returncode != 0:
            validation_ok = False
            validation_error = _first_error(result)
            break
    statuses.append((validation_ok, "Offline tests and validators passed"))
    if not validation_ok:
        statuses.extend(
            [
                (False, "Local server started"),
                (False, "Health/OpenAPI passed and server stopped"),
            ]
        )
        print_status_rows(statuses)
        print(f"FAIL: Validation: {validation_error}")
        return 1

    health_ok = False
    server_started = False
    teardown_ok = True
    temp_directory: tempfile.TemporaryDirectory[str] | None = None
    try:
        temp_directory = tempfile.TemporaryDirectory(prefix="youtube-mcp-local-check-")
        temp_path = Path(temp_directory.name)
        database_path = temp_path / "youtube_mcp.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

        port = find_free_loopback_port()
        server_log = temp_path / "uvicorn.log"
        with server_log.open("wb") as log_file:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "youtube_mcp.server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )

        base_url = f"http://127.0.0.1:{port}"
        try:
            _status_code, _payload = wait_for_health(base_url)
            server_started = True
        except RuntimeError as exc:
            server_started = False
            health_error = str(exc)
            server_log = temp_path / "uvicorn.log"
            if server_log.exists():
                log_lines = server_log.read_text(encoding="utf-8", errors="replace").strip()
                if log_lines:
                    health_error = log_lines.splitlines()[-1]

            statuses.extend(
                [
                    (False, "Local server started"),
                    (False, "Health/OpenAPI passed and server stopped"),
                ]
            )
            print_status_rows(statuses)
            print(f"FAIL: Server startup or health check: {health_error}")
            health_ok = False
        else:
            statuses.append((True, "Local server started"))
            try:
                with httpx.Client(timeout=2.0) as client:
                    openapi_response = client.get(f"{base_url}/openapi.json")
                health_ok = openapi_response.status_code == 200
                if not health_ok:
                    health_error = f"OpenAPI returned HTTP {openapi_response.status_code}"
            except httpx.HTTPError as exc:
                health_error = str(exc)
                health_ok = False
    except (OSError, RuntimeError) as exc:
        if not server_started:
            statuses.extend(
                [
                    (False, "Local server started"),
                    (False, "Health/OpenAPI passed and server stopped"),
                ]
            )
            print_status_rows(statuses)
            print(f"FAIL: Server startup: {exc}")
            return 1
    finally:
        terminate_process(process)
        if process is not None and process.poll() is not None:
            teardown_ok = True
        elif process is not None:
            teardown_ok = False

        if saved_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = saved_database_url

        if temp_directory is not None:
            try:
                temp_directory.cleanup()
                if temp_directory.name and Path(temp_directory.name).exists():
                    shutil.rmtree(temp_directory.name)
            except OSError:
                teardown_ok = False

    if server_started:
        statuses.append(
            (
                health_ok and teardown_ok,
                "Health/OpenAPI passed and server stopped",
            )
        )
        if not health_ok:
            print_status_rows(statuses)
            print(f"FAIL: Health/OpenAPI: {locals().get('health_error', 'validation failed')}")
        elif not teardown_ok:
            print_status_rows(statuses)
            print("FAIL: Server teardown")
        else:
            print_status_rows(statuses)

        return 0 if health_ok and teardown_ok else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
