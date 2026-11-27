"""Compatibility entrypoint for the repository's Second Brain validator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_validate_brain_module():
    validator_path = Path(__file__).resolve().with_name("validate_brain.py")
    spec = importlib.util.spec_from_file_location("validate_brain", validator_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load validator from {validator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    return _load_validate_brain_module().main()


if __name__ == "__main__":
    sys.exit(main())
