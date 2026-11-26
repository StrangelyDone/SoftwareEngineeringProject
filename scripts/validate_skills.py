"""Validate all Agent Skills under .agents/skills/*/SKILL.md."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

SKILLS_ROOT = Path(".agents/skills")
IGNORED_DIRS = {"__pycache__"}
KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_FIELDS = {"name", "description"}
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
CITATION_RE = re.compile(r"(\[\[[^\[\]\r\n]+\]\]|brain/)")


def split_frontmatter(content: str) -> tuple[str | None, str]:
    """Split leading YAML frontmatter without regex backtracking across horizontal rules."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, content

    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "".join(lines[1:idx]), "".join(lines[idx + 1 :])

    return None, content


def has_exact_skill_md(skill_dir: Path) -> bool:
    """Verify exact uppercase 'SKILL.md' filename (catches casing bugs on macOS/Windows)."""
    return any(entry.is_file() and entry.name == "SKILL.md" for entry in skill_dir.iterdir())


def validate_skill_file(skill_dir: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    dir_name = skill_dir.name

    if not KEBAB_CASE_RE.match(dir_name):
        errors.append(f"{skill_dir}: folder name '{dir_name}' must be lowercase kebab-case.")

    if not has_exact_skill_md(skill_dir):
        errors.append(f"{skill_dir}: missing required 'SKILL.md' file (exact uppercase name).")
        return errors, warnings

    skill_file = skill_dir / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8-sig")
    fm_text, body = split_frontmatter(content)
    if fm_text is None:
        errors.append(f"{skill_file}: missing or malformed YAML frontmatter (--- ... ---).")
        return errors, warnings

    try:
        metadata = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        errors.append(f"{skill_file}: invalid YAML syntax in frontmatter ({exc}).")
        return errors, warnings

    if not isinstance(metadata, dict):
        errors.append(f"{skill_file}: frontmatter must be a non-empty YAML mapping.")
        return errors, warnings

    missing = REQUIRED_FIELDS - set(metadata.keys())
    if missing:
        errors.append(f"{skill_file}: missing required frontmatter fields: {sorted(missing)}.")

    name = metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{skill_file}: frontmatter 'name' must be a non-empty string.")
    else:
        if not KEBAB_CASE_RE.match(name):
            errors.append(f"{skill_file}: frontmatter name '{name}' must be lowercase kebab-case.")
        if len(name) > MAX_NAME_LENGTH:
            errors.append(f"{skill_file}: frontmatter 'name' exceeds {MAX_NAME_LENGTH} chars.")
        if name != dir_name:
            errors.append(
                f"{skill_file}: frontmatter name '{name}' does not match folder '{dir_name}'."
            )

    desc = metadata.get("description")
    if not isinstance(desc, str) or not desc.strip():
        errors.append(f"{skill_file}: frontmatter 'description' must be a non-empty string.")
    elif len(desc) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"{skill_file}: frontmatter 'description' exceeds {MAX_DESCRIPTION_LENGTH} chars."
        )

    if not body.strip():
        errors.append(f"{skill_file}: skill body is empty; add instructions below frontmatter.")

    # SB-3 reminder: every skill should cite at least one distilled note in brain/
    if not CITATION_RE.search(content):
        warnings.append(
            f"{skill_file}: no Second Brain note citation ([[...]] or brain/...) found (SB-3)."
        )

    return errors, warnings


def main() -> int:
    if not SKILLS_ROOT.exists():
        print(f"[WARN] {SKILLS_ROOT} does not exist yet. Skipping skill validation.")
        return 0

    all_errors: list[str] = []
    all_warnings: list[str] = []

    # Catch skills mistakenly placed directly under .agents/skills/<name>.md
    for entry in sorted(SKILLS_ROOT.iterdir()):
        if entry.is_file() and entry.suffix.lower() == ".md" and entry.name.lower() != "readme.md":
            all_errors.append(
                f"{entry}: skills must live in a subfolder as "
                f"'{SKILLS_ROOT / entry.stem / 'SKILL.md'}'."
            )

    skill_dirs = sorted(
        p
        for p in SKILLS_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in IGNORED_DIRS
    )
    if not skill_dirs and not all_errors:
        print(f"[WARN] No skill folders found inside {SKILLS_ROOT}.")
        return 0

    for skill_dir in skill_dirs:
        errs, warns = validate_skill_file(skill_dir)
        all_errors.extend(errs)
        all_warnings.extend(warns)

    for warn in all_warnings:
        print(f"[WARN] {warn}")

    if all_errors:
        print("SKILL.md validation FAILED:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(f"SKILL.md validation PASSED ({len(skill_dirs)} skill(s) checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())