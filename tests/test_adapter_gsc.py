from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

from howlplatform.platform.adapters.gsc_csv import GSCCSVAdapter
from howlplatform.platform.manifest.loader import load_manifest
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "gsc_ampere_2026_08.csv"


def test_gsc_csv_adapter_processes_and_upserts():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    manifest = load_manifest(REPO_ROOT / "manifests" / "ampere.json")

    adapter = GSCCSVAdapter(manifest, engine=engine)
    rows, stats = adapter.process_file(SAMPLE_CSV, period="2026-08", run_id="test_run_gsc")

    assert len(rows) > 0
    assert stats["total_clicks"] > 0
    assert stats["branded_count"] > 0

    with engine.connect() as conn:
        db_count = conn.execute(text("SELECT COUNT(*) FROM canonical_search WHERE period = '2026-08'")).scalar()
        assert db_count == len(rows)

    # Re-running same file upserts without duplication
    rows2, _ = adapter.process_file(SAMPLE_CSV, period="2026-08", run_id="test_run_gsc_2")
    with engine.connect() as conn:
        db_count_after = conn.execute(text("SELECT COUNT(*) FROM canonical_search WHERE period = '2026-08'")).scalar()
        assert db_count_after == len(rows)
