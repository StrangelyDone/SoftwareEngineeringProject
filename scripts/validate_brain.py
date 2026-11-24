"""Validate Second Brain PARA notes for YAML frontmatter schema and broken [[wikilinks]]."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

BRAIN_ROOT = Path("brain")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# Notes inside PARA folders must include these frontmatter keys
PARA_FOLDERS = {"inbox", "projects", "areas", "resources", "archive"}
REQUIRED_SCHEMA_KEYS = {"title", "author", "created", "tags", "type"}
ROOT_STRUCTURAL_FILES = {"index.md", "log.md"}


def build_valid_targets(md_files: list[Path]) -> set[str]:
    """Collect all valid Obsidian link targets (by stem and by relative path)."""
    targets: set[str] = set()
    for path in md_files:
        rel_from_brain = path.relative_to(BRAIN_ROOT).as_posix()  # e.g. resources/sqlite-wal.md
        rel_from_repo = path.as_posix()                            # e.g. brain/resources/sqlite-wal.md
        targets.add(path.stem)
        targets.add(rel_from_brain)
        targets.add(rel_from_brain.removesuffix(".md"))
        targets.add(rel_from_repo)
        targets.add(rel_from_repo.removesuffix(".md"))
    return targets


def normalize_wikilink(raw_link: str) -> str:
    """Handle Obsidian aliases ([[note|Alias]]) and heading anchors ([[note#Section]])."""
    target = raw_link.split("|", 1)[0]
    target = target.split("#", 1)[0]
    return target.strip()


def validate_note(path: Path, valid_targets: set[str]) -> list[str]:
    errors: list[str] = []
    content = path.read_text(encoding="utf-8")
    rel_parts = path.relative_to(BRAIN_ROOT).parts

    # 1. Schema validation (enforced for all notes inside PARA folders)
    is_para_note = len(rel_parts) >= 2 and rel_parts[0] in PARA_FOLDERS
    if is_para_note:
        match = FRONTMATTER_RE.match(content)
        if not match:
            errors.append(f"{path}: missing or malformed YAML frontmatter.")
        else:
            try:
                metadata = yaml.safe_load(match.group(1))
            except yaml.YAMLError as exc:
                errors.append(f"{path}: invalid YAML frontmatter ({exc}).")
                metadata = None

            if isinstance(metadata, dict):
                missing = REQUIRED_SCHEMA_KEYS - set(metadata.keys())
                if missing:
                    errors.append(f"{path}: missing required schema keys: {sorted(missing)}.")
            elif metadata is not None:
                errors.append(f"{path}: frontmatter must be a YAML mapping.")

    # 2. Broken [[wikilink]] validation (enforced across all files in brain/)
    for raw_link in WIKILINK_RE.findall(content):
        target = normalize_wikilink(raw_link)
        if not target:
            continue
        if target not in valid_targets:
            errors.append(f"{path}: broken wikilink '[[{raw_link}]]' (target '{target}' not found).")

    return errors


def main() -> int:
    if not BRAIN_ROOT.exists():
        print(f"[WARN] {BRAIN_ROOT} does not exist yet. Skipping brain validation during bootstrap.")
        return 0

    md_files = sorted(BRAIN_ROOT.rglob("*.md"))
    if not md_files:
        print(f"[WARN] No Markdown files found inside {BRAIN_ROOT}.")
        return 0

    valid_targets = build_valid_targets(md_files)
    all_errors: list[str] = []

    for md_file in md_files:
        all_errors.extend(validate_note(md_file, valid_targets))

    if all_errors:
        print("Second Brain validation FAILED:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(f"Second Brain validation PASSED ({len(md_files)} markdown file(s) checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())