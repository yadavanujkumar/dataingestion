from __future__ import annotations

import json
from pathlib import Path
import pytest

from howlplatform.platform.manifest.loader import (
    load_manifest,
    validate_manifest,
    ManifestValidationError,
)

REPO_ROOT = Path(__file__).parent.parent


def test_ampere_manifest_loads_and_validates():
    manifest_path = REPO_ROOT / "manifests" / "ampere.json"
    manifest = load_manifest(manifest_path)
    assert manifest["brand_id"] == "ampere"
    assert manifest["manifest_version"] == 1
    assert "google_search_console" in [s["channel"] for s in manifest["sources"]]
    assert "gsc_organic_report" in manifest["deliverables"]


def test_manifest_missing_required_fields_fails():
    invalid_data = {
        "brand_id": "test_brand",
        # missing manifest_version, identity, sources, deliverables, review
    }
    errors = validate_manifest(invalid_data)
    assert len(errors) > 0
    assert any("manifest_version" in e for e in errors)
    assert any("identity" in e for e in errors)


def test_manifest_duplicate_source_id_fails():
    with open(REPO_ROOT / "manifests" / "ampere.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Duplicate first source
    data["sources"].append(dict(data["sources"][0]))
    errors = validate_manifest(data)
    assert any("Duplicate source_id" in e for e in errors)


def test_manifest_empty_deliverables_fails():
    with open(REPO_ROOT / "manifests" / "ampere.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data["deliverables"] = []
    errors = validate_manifest(data)
    assert any("deliverable" in e.lower() for e in errors)
