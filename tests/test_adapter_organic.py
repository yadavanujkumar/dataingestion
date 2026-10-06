from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

from howlplatform.platform.adapters.organic_social import OrganicSocialAdapter
from howlplatform.platform.manifest.loader import load_manifest
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_ORGANIC = REPO_ROOT / "tests" / "fixtures" / "organic_social_ampere_2026_08.csv"


def test_organic_social_adapter_processes_and_upserts():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    manifest = load_manifest(REPO_ROOT / "manifests" / "ampere.json")

    adapter = OrganicSocialAdapter(manifest, engine=engine)
    rows, stats = adapter.process_file(SAMPLE_ORGANIC, period="2026-08", run_id="test_run_organic")

    assert len(rows) > 0
    assert stats["total_impressions"] > 0
    assert stats["total_engagements"] > 0

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM canonical_organic")).scalar()
        assert count == len(rows)
