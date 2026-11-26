"""Validate numbered Architecture Decision Records (docs/adr/NNN-*.md) for SB-3 citations."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

try:
    from scripts import validate_brain
except ImportError:  # Executed directly or loaded without repo root on sys.path
    _vb_path = Path(__file__).resolve().with_name("validate_brain.py")
    _vb_spec = importlib.util.spec_from_file_location("validate_brain", _vb_path)
    if _vb_spec is None or _vb_spec.loader is None:
        raise ImportError(f"Cannot load validate_brain from {_vb_path}")
    validate_brain = importlib.util.module_from_spec(_vb_spec)
    _vb_spec.loader.exec_module(validate_brain)

ADR_ROOT = Path("docs/adr")
BRAIN_ROOT = Path("brain")
DISTILLED_FOLDERS = {"resources", "areas"}
NUMBERED_ADR_RE = re.compile(r"^\d{3}-.*\.md$")
CITATION_HEADING_RE = re.compile(r"^#{1,6}\s+.*(?:citation|reference)", re.IGNORECASE | re.MULTILINE)


def build_brain_targets(brain_root: Path) -> tuple[set[str], set[str]]:
    """Return (all_valid_targets, distilled_note_targets) inside brain_root (case-folded)."""
    all_valid_targets: set[str] = set()
    distilled_targets: set[str] = set()

    if not brain_root.exists():
        return all_valid_targets, distilled_targets

    for path in sorted(brain_root.rglob("*")):
        if not path.is_file() or validate_brain.is_hidden(path, brain_root):
            continue

        rel_parts = path.relative_to(brain_root).parts
        rel_from_brain = path.relative_to(brain_root).as_posix()
        candidates = {path.name, rel_from_brain, f"brain/{rel_from_brain}"}
        if path.suffix.lower() == ".md":
            candidates.update(
                {
                    path.stem,
                    rel_from_brain[:-3],
                    f"brain/{rel_from_brain[:-3]}",
                }
            )

        folded = {c.casefold() for c in candidates}
        all_valid_targets.update(folded)

        is_distilled_note = (
            path.suffix.lower() == ".md"
            and len(rel_parts) >= 2
            and rel_parts[0] in DISTILLED_FOLDERS
        )
        if is_distilled_note:
            distilled_targets.update(folded)

    return all_valid_targets, distilled_targets


def find_citation_line(cleaned_body: str, body_line_offset: int) -> int:
    """Return a sensible 1-based line number for missing-citation errors."""
    match = CITATION_HEADING_RE.search(cleaned_body)
    if match:
        return body_line_offset + cleaned_body[: match.start()].count("\n") + 1
    return body_line_offset + 1


def validate_adr_file(
    adr_path: Path,
    all_valid_targets: set[str],
    distilled_targets: set[str],
    brain_root: Path = BRAIN_ROOT,
) -> list[str]:
    """Validate a single numbered ADR for SB-3 distilled citations and broken wikilinks."""
    errors: list[str] = []
    content = adr_path.read_text(encoding="utf-8-sig")
    _, body, body_line_offset = validate_brain.split_frontmatter(content)
    cleaned_body = validate_brain.strip_ignored_blocks(body)

    distilled_count = 0
    for link_match in validate_brain.WIKILINK_RE.finditer(cleaned_body):
        raw_link = link_match.group(1)
        target = validate_brain.normalize_wikilink(raw_link)
        if not target:
            continue

        line_no = body_line_offset + cleaned_body[: link_match.start()].count("\n") + 1
        folded = target.casefold()
        if folded not in all_valid_targets:
            errors.append(
                f"{adr_path}:{line_no}: broken wikilink '[[{raw_link}]]' "
                f"(target '{target}' not found in {brain_root}/)."
            )
        elif folded in distilled_targets:
            distilled_count += 1

    if distilled_count == 0:
        citation_line = find_citation_line(cleaned_body, body_line_offset)
        errors.append(
            f"{adr_path}:{citation_line}: missing required Second Brain citation (SB-3): "
            f"numbered ADRs must cite at least one existing distilled note in "
            f"'{brain_root}/resources/' or '{brain_root}/areas/' using [[wikilinks]]."
        )

    return errors


def validate_adrs(adr_root: Path = ADR_ROOT, brain_root: Path = BRAIN_ROOT) -> tuple[int, list[str]]:
    """Validate all numbered ADRs under adr_root against notes in brain_root.

    Returns (exit_code, messages).
    """
    if not adr_root.exists():
        return 0, [f"[WARN] {adr_root} does not exist yet. Skipping ADR validation."]

    adr_files = sorted(
        path
        for path in adr_root.iterdir()
        if path.is_file() and NUMBERED_ADR_RE.match(path.name)
    )
    if not adr_files:
        return 0, [f"[WARN] No numbered ADRs found inside {adr_root}. Skipping ADR validation."]

    all_valid_targets, distilled_targets = build_brain_targets(brain_root)
    all_errors: list[str] = []
    for adr_path in adr_files:
        all_errors.extend(
            validate_adr_file(adr_path, all_valid_targets, distilled_targets, brain_root=brain_root)
        )

    if all_errors:
        return 1, all_errors

    return 0, [f"ADR validation PASSED ({len(adr_files)} numbered ADR(s) checked)."]


def main() -> int:
    exit_code, messages = validate_adrs()
    if exit_code != 0:
        print("ADR citation validation FAILED:")
        for msg in messages:
            print(f"  - {msg}")
        return exit_code

    for msg in messages:
        print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
