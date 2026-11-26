"""Offline unit tests for scripts/validate_adrs.py (SB-3 ADR citation enforcement)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_validate_adrs():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "validate_adrs.py"
    spec = importlib.util.spec_from_file_location("validate_adrs", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_adrs"] = module
    spec.loader.exec_module(module)
    return module


validate_adrs = _load_validate_adrs().validate_adrs


def _seed_brain(tmp_path: Path) -> Path:
    brain_root = tmp_path / "brain"
    (brain_root / "resources").mkdir(parents=True)
    (brain_root / "areas").mkdir(parents=True)
    (brain_root / "inbox").mkdir(parents=True)
    (brain_root / "index.md").write_text("# Index\n", encoding="utf-8")
    (brain_root / "log.md").write_text("# Log\n", encoding="utf-8")
    (brain_root / "resources" / "sqlite-wal-mode.md").write_text(
        "# SQLite WAL\n", encoding="utf-8"
    )
    (brain_root / "areas" / "security-policy.md").write_text(
        "# Security Policy\n", encoding="utf-8"
    )
    (brain_root / "inbox" / "rough-draft.md").write_text(
        "# Rough Draft\n", encoding="utf-8"
    )
    return brain_root


def test_missing_adr_directory_warns_and_passes(tmp_path: Path) -> None:
    brain_root = _seed_brain(tmp_path)
    exit_code, messages = validate_adrs(tmp_path / "docs" / "adr", brain_root)
    assert exit_code == 0
    assert messages[0].startswith("[WARN]")


def test_valid_adr_with_resource_citation_passes(tmp_path: Path) -> None:
    brain_root = _seed_brain(tmp_path)
    adr_root = tmp_path / "docs" / "adr"
    adr_root.mkdir(parents=True)
    (adr_root / "001-sqlite-storage.md").write_text(
        "# ADR-001\n\n## Citations (SB-3)\n- [[sqlite-wal-mode]]\n",
        encoding="utf-8",
    )

    exit_code, messages = validate_adrs(adr_root, brain_root)
    assert exit_code == 0
    assert "PASSED (1 numbered ADR(s) checked)" in messages[0]


def test_adr_with_zero_or_commented_citations_fails(tmp_path: Path) -> None:
    brain_root = _seed_brain(tmp_path)
    adr_root = tmp_path / "docs" / "adr"
    adr_root.mkdir(parents=True)
    (adr_root / "001-no-citations.md").write_text(
        "# ADR-001\n\n## Context\nNo links here.\n",
        encoding="utf-8",
    )
    (adr_root / "002-commented-only.md").write_text(
        "# ADR-002\n\n"
        "<!-- [[sqlite-wal-mode]] -->\n"
        "%% [[sqlite-wal-mode]] %%\n"
        "`[[sqlite-wal-mode]]`\n"
        "```markdown\n[[sqlite-wal-mode]]\n```\n"
        "## Citations (SB-3)\n"
        "- [[index]]\n",
        encoding="utf-8",
    )

    exit_code, errors = validate_adrs(adr_root, brain_root)
    assert exit_code == 1
    assert len(errors) == 2
    assert "001-no-citations.md:1:" in errors[0]
    assert "SB-3" in errors[0]
    assert "002-commented-only.md:9:" in errors[1]
    assert "SB-3" in errors[1]


def test_adr_with_broken_wikilink_fails_with_file_line(tmp_path: Path) -> None:
    brain_root = _seed_brain(tmp_path)
    adr_root = tmp_path / "docs" / "adr"
    adr_root.mkdir(parents=True)
    (adr_root / "001-broken-link.md").write_text(
        "# ADR-001\n\n## Citations (SB-3)\n- [[sqlite-wal-mode]]\n- [[does-not-exist]]\n",
        encoding="utf-8",
    )

    exit_code, errors = validate_adrs(adr_root, brain_root)
    assert exit_code == 1
    assert len(errors) == 1
    assert "001-broken-link.md:5:" in errors[0]
    assert "does-not-exist" in errors[0]


def test_template_and_readme_are_ignored(tmp_path: Path) -> None:
    brain_root = _seed_brain(tmp_path)
    adr_root = tmp_path / "docs" / "adr"
    adr_root.mkdir(parents=True)
    (adr_root / "template.md").write_text(
        "# ADR-NNN\n\n- [[placeholder-note]]\n",
        encoding="utf-8",
    )
    (adr_root / "README.md").write_text(
        "# ADR Index\n\nNo wikilinks needed.\n",
        encoding="utf-8",
    )

    exit_code, messages = validate_adrs(adr_root, brain_root)
    assert exit_code == 0
    assert messages[0].startswith("[WARN]")
