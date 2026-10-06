from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import jsonschema


class ManifestValidationError(Exception):
    """Raised when a brand manifest fails schema validation or semantic checks."""
    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or [message]


def get_schema_path() -> Path:
    return Path(__file__).parent / "manifest.schema.json"


def load_manifest_schema() -> Dict[str, Any]:
    schema_path = get_schema_path()
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_manifest(data: Dict[str, Any]) -> List[str]:
    """
    Validate manifest data against the JSON Schema and semantic rules.
    Returns a list of error strings if invalid, or empty list if valid.
    """
    schema = load_manifest_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors: List[str] = []

    for err in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.path]):
        loc = ".".join(str(p) for p in err.path) if err.path else "root"
        errors.append(f"[{loc}] {err.message}")

    # Semantic cross-field validations:
    # 1. Unique source_ids
    source_ids = [s.get("source_id") for s in data.get("sources", []) if isinstance(s, dict)]
    if len(source_ids) != len(set(source_ids)):
        duplicates = [sid for sid in set(source_ids) if source_ids.count(sid) > 1]
        errors.append(f"[sources] Duplicate source_id found: {duplicates}")

    # 2. Check deliverable list non-empty
    if not data.get("deliverables"):
        errors.append("[deliverables] Brand manifest must declare at least one deliverable.")

    return errors


def load_manifest(path: Union[Path, str]) -> Dict[str, Any]:
    """
    Load and validate a brand manifest from a JSON file path.
    Raises ManifestValidationError on any syntax or schema failure.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Manifest file not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ManifestValidationError(f"Invalid JSON in manifest {file_path}: {e}")

    errors = validate_manifest(data)
    if errors:
        error_summary = "\n  - " + "\n  - ".join(errors)
        raise ManifestValidationError(
            f"Manifest validation failed for {file_path.name}:{error_summary}",
            errors=errors
        )

    return data
