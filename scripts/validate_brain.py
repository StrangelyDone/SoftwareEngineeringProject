"""Validate Second Brain PARA notes for YAML frontmatter schema and broken [[wikilinks]]."""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

BRAIN_ROOT = Path("brain")
PARA_FOLDERS = {"inbox", "projects", "areas", "resources", "archive"}
ROOT_STRUCTURAL_FILES = ("index.md", "log.md")
REQUIRED_SCHEMA_KEYS = {"title", "author", "created", "tags", "type"}
ALLOWED_NOTE_TYPES = {
    "inbox",
    "project",
    "area",
    "resource",
    "archive",
    "ai-session",
    "review",
}

# Single-pass tokenizer so comments and code blocks/spans never interfere with each other
IGNORED_BLOCKS_RE = re.compile(
    r"(?P<fenced_bt>^[ \t>]*(?:(?:[-*+]|\d+[.)])[ \t]+)?(?P<bt>`{3,})[^`\r\n]*\r?\n"
    r".*?(?:^[ \t>]*(?P=bt)`*[ \t]*(?:\r?\n|$)|\Z))"
    r"|(?P<fenced_tilde>^[ \t>]*(?:(?:[-*+]|\d+[.)])[ \t]+)?(?P<tl>~{3,})[^\r\n]*\r?\n"
    r".*?(?:^[ \t>]*(?P=tl)~*[ \t]*(?:\r?\n|$)|\Z))"
    r"|(?P<html_comment><!--.*?-->)"
    r"|(?P<obsidian_comment>%%.*?%%)"
    r"|(?P<md_ref_comment>^[ \t]*\[//\]:[ \t]*#[^\r\n]*)"
    r"|(?P<inline_code>(?P<ic>`+)(?!`)(?:(?!\r?\n\r?\n).)+?(?<!`)(?P=ic)(?!`))",
    re.DOTALL | re.MULTILINE,
)

# Matches [[target]] without spanning lines or matching escaped \[[target]]
WIKILINK_RE = re.compile(r"(?<!\\)\[\[([^\[\]\r\n]+)\]\]")


def is_hidden(path: Path, root: Path) -> bool:
    """Return True if any path segment under root starts with '.' (e.g. .obsidian, .trash)."""
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def split_frontmatter(content: str) -> tuple[str | None, str, int]:
    """Split leading YAML frontmatter without regex backtracking across horizontal rules.

    Returns (frontmatter_text_or_None, body_text, body_start_line_offset).
    """
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, content, 0

    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "".join(lines[1:idx]), "".join(lines[idx + 1 :]), idx + 1

    # Opening --- was never closed
    return None, content, 0


def build_valid_targets(all_files: list[Path]) -> set[str]:
    """Collect valid Obsidian link targets (case-folded, including non-Markdown attachments)."""
    targets: set[str] = set()
    for path in all_files:
        rel_from_brain = path.relative_to(BRAIN_ROOT).as_posix()
        rel_from_repo = path.as_posix()

        candidates = {path.name, rel_from_brain, rel_from_repo}
        if path.suffix.lower() == ".md":
            candidates.update(
                {
                    path.stem,
                    rel_from_brain[:-3],
                    rel_from_repo[:-3],
                }
            )

        targets.update(c.casefold() for c in candidates)
    return targets


def normalize_wikilink(raw_link: str) -> str:
    """Strip alias (| or \| in tables), heading (#...), OS slashes, and leading ./ or /."""
    target = re.split(r"\\?\|", raw_link, maxsplit=1)[0]
    target = target.split("#", 1)[0]
    target = target.strip().replace("\\", "/")
    while target.startswith("./"):
        target = target[2:]
    return target.lstrip("/")


def strip_ignored_blocks(body: str) -> str:
    """Replace comments and code blocks with newlines so original line numbers stay exact."""
    return IGNORED_BLOCKS_RE.sub(lambda m: "\n" * m.group(0).count("\n"), body)


def is_valid_date(value: object) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    if isinstance(value, str):
        try:
            date.fromisoformat(value.strip())
            return True
        except ValueError:
            return False
    return False


def validate_frontmatter(path: Path, metadata: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(metadata, dict):
        return [f"{path}: frontmatter must be a non-empty YAML mapping."]

    missing = REQUIRED_SCHEMA_KEYS - set(metadata.keys())
    if missing:
        errors.append(f"{path}: missing required schema keys: {sorted(missing)}.")
        return errors

    for field in ("title", "author"):
        val = metadata.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{path}: frontmatter '{field}' must be a non-empty string.")

    if not is_valid_date(metadata.get("created")):
        errors.append(f"{path}: frontmatter 'created' must be a valid YYYY-MM-DD date.")

    tags = metadata.get("tags")
    if (
        not isinstance(tags, list)
        or not tags
        or not all(isinstance(t, str) and t.strip() for t in tags)
    ):
        errors.append(f"{path}: frontmatter 'tags' must be a non-empty list of strings.")

    note_type = metadata.get("type")
    if not isinstance(note_type, str) or note_type.strip().lower() not in ALLOWED_NOTE_TYPES:
        allowed = sorted(ALLOWED_NOTE_TYPES)
        errors.append(f"{path}: frontmatter 'type' must be one of {allowed}.")

    return errors


def validate_note(path: Path, valid_targets: set[str]) -> list[str]:
    errors: list[str] = []
    content = path.read_text(encoding="utf-8-sig")
    rel_parts = path.relative_to(BRAIN_ROOT).parts

    fm_text, body, body_line_offset = split_frontmatter(content)

    # 1. Schema validation (enforced for all notes inside PARA folders)
    is_para_note = len(rel_parts) >= 2 and rel_parts[0] in PARA_FOLDERS
    if is_para_note:
        if fm_text is None:
            errors.append(f"{path}: missing or malformed YAML frontmatter (--- ... ---).")
        else:
            try:
                metadata = yaml.safe_load(fm_text)
            except yaml.YAMLError as exc:
                errors.append(f"{path}: invalid YAML frontmatter ({exc}).")
            else:
                errors.extend(validate_frontmatter(path, metadata))

    # 2. Broken [[wikilink]] validation (ignores comments, code blocks, and frontmatter)
    cleaned_body = strip_ignored_blocks(body)
    for link_match in WIKILINK_RE.finditer(cleaned_body):
        raw_link = link_match.group(1)
        target = normalize_wikilink(raw_link)
        if not target:
            continue  # Same-file heading anchor like [[#Section]]

        if target.casefold() not in valid_targets:
            line_no = body_line_offset + cleaned_body[: link_match.start()].count("\n") + 1
            errors.append(
                f"{path}:{line_no}: broken wikilink '[[{raw_link}]]' "
                f"(target '{target}' not found)."
            )

    return errors


def main() -> int:
    if not BRAIN_ROOT.exists():
        print(f"[WARN] {BRAIN_ROOT} does not exist yet. Skipping brain validation.")
        return 0

    all_files = sorted(
        p for p in BRAIN_ROOT.rglob("*") if p.is_file() and not is_hidden(p, BRAIN_ROOT)
    )
    md_files = [p for p in all_files if p.suffix.lower() == ".md"]

    if not md_files:
        print(f"[WARN] No Markdown files found inside {BRAIN_ROOT}.")
        return 0

    all_errors: list[str] = []

    for required_file in ROOT_STRUCTURAL_FILES:
        if not (BRAIN_ROOT / required_file).is_file():
            all_errors.append(f"{BRAIN_ROOT / required_file}: required vault entry file missing.")

    valid_targets = build_valid_targets(all_files)
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