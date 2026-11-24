"""Validate all Agent Skills under .agents/skills/*/SKILL.md."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

SKILLS_ROOT = Path(".agents/skills")
KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
REQUIRED_FIELDS = {"name", "description"}


def validate_skill_file(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    dir_name = skill_dir.name

    if not KEBAB_CASE_RE.match(dir_name):
        errors.append(f"{skill_dir}: folder name '{dir_name}' must be lowercase kebab-case.")

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        errors.append(f"{skill_dir}: missing required SKILL.md file.")
        return errors

    content = skill_file.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    if not match:
        errors.append(f"{skill_file}: missing or malformed YAML frontmatter (--- ... ---).")
        return errors

    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        errors.append(f"{skill_file}: invalid YAML syntax in frontmatter ({exc}).")
        return errors

    if not isinstance(metadata, dict):
        errors.append(f"{skill_file}: frontmatter must be a YAML mapping/dictionary.")
        return errors

    missing = REQUIRED_FIELDS - set(metadata.keys())
    if missing:
        errors.append(f"{skill_file}: missing required frontmatter fields: {sorted(missing)}.")

    name = metadata.get("name")
    if isinstance(name, str) and name != dir_name:
        errors.append(
            f"{skill_file}: frontmatter name '{name}' does not match folder name '{dir_name}'."
        )

    desc = metadata.get("description")
    if not isinstance(desc, str) or not desc.strip():
        errors.append(f"{skill_file}: frontmatter 'description' must be a non-empty string.")

    return errors


def main() -> int:
    if not SKILLS_ROOT.exists():
        print(f"[WARN] {SKILLS_ROOT} does not exist yet. Skipping skill validation during bootstrap.")
        return 0

    skill_dirs = sorted(p for p in SKILLS_ROOT.iterdir() if p.is_dir())
    if not skill_dirs:
        print(f"[WARN] No skill folders found inside {SKILLS_ROOT}.")
        return 0

    all_errors: list[str] = []
    for skill_dir in skill_dirs:
        all_errors.extend(validate_skill_file(skill_dir))

    if all_errors:
        print("SKILL.md validation FAILED:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(f"SKILL.md validation PASSED ({len(skill_dirs)} skill(s) checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())