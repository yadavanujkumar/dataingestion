from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

from howlplatform.platform.store.db import (
    run_migrations,
    check_tables_exist,
    all_required_tables_exist,
    REQUIRED_TABLES,
)
from howlplatform.platform.store.sync import sync_brand_manifest
from howlplatform.platform.manifest.loader import load_manifest

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def test_engine():
    """Create in-memory SQLite engine for tests."""
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    return engine


def test_migrations_create_all_tables(test_engine):
    status = check_tables_exist(test_engine)
    assert all_required_tables_exist(test_engine)
    for table_name in REQUIRED_TABLES:
        assert status[table_name] is True, f"Table {table_name} missing from db"


def test_sync_brand_manifest(test_engine):
    manifest_path = REPO_ROOT / "manifests" / "ampere.json"
    manifest = load_manifest(manifest_path)
    
    sync_brand_manifest(manifest, test_engine)

    with test_engine.connect() as conn:
        res = conn.execute(text("SELECT brand_id, manifest_version FROM brands WHERE brand_id = 'ampere'")).fetchone()
        assert res is not None
        assert res[0] == "ampere"
        assert res[1] == 1

        sources = conn.execute(text("SELECT source_id, channel FROM sources WHERE brand_id = 'ampere'")).fetchall()
        assert len(sources) == len(manifest["sources"])
        source_ids = [s[0] for s in sources]
        assert "ampere-gsc" in source_ids
