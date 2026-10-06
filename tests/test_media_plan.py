from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

from howlplatform.platform.adapters.media_plan import MediaPlanAdapter, calculate_planned_vs_actual
from howlplatform.platform.manifest.loader import load_manifest
from howlplatform.platform.review.queue import get_open_review_items
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "manifests" / "ampere.json"
PLAN_CSV = REPO_ROOT / "tests" / "fixtures" / "media_plan_ampere_2026.csv"


def test_media_plan_ingestion_and_naming_validation():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    manifest = load_manifest(MANIFEST_PATH)
    adapter = MediaPlanAdapter(manifest, engine=engine)

    rows, stats = adapter.process_file(
        file_path=PLAN_CSV,
        plan_id="q3_2026",
        run_id="run_test_plan",
    )

    assert stats["total_rows"] == 3
    assert stats["total_planned_spend"] == 450000.0
    assert stats["naming_violations"] == 1

    # Verify review item was created for the invalid campaign name
    open_items = get_open_review_items("ampere", engine=engine)
    assert len(open_items) == 1
    assert open_items[0]["entity_type"] == "naming_convention"
    assert "invalid campaign name" in open_items[0]["entity_key"].lower()

    # Verify canonical_plan table contains the records
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM canonical_plan WHERE brand_id = 'ampere'")).scalar()
        assert count == 3


def test_calculate_planned_vs_actual():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    # Insert planned data
    manifest = load_manifest(MANIFEST_PATH)
    adapter = MediaPlanAdapter(manifest, engine=engine)
    adapter.process_file(PLAN_CSV, plan_id="q3_2026", run_id="run_test_plan")

    # Insert mock actual paid data matching one of the campaigns
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO canonical_paid (
                    brand_id, date, channel, campaign, adset, ad,
                    spend, currency, impressions, reach, clicks,
                    conversions, source_id, run_id
                ) VALUES (
                    'ampere', '2026-08-15', 'meta', 'AMPERE_META_CONV_MAGNUS_PANINDIA', 'AdSet_1', 'Ad_1',
                    220000.0, 'INR', 1100000, 800000, 24000,
                    180.0, 'ampere-meta', 'run_test_paid'
                )
            """)
        )

    res = calculate_planned_vs_actual("ampere", "2026-08", plan_id="q3_2026", engine=engine)
    assert res["brand_id"] == "ampere"
    assert res["total_planned_spend"] == 450000.0
    assert res["total_actual_spend"] == 220000.0
    assert res["spend_variance"] == (220000.0 - 450000.0)

    # Check campaign-level comparison
    magnus_comp = next((c for c in res["campaigns"] if "MAGNUS" in c["campaign"]), None)
    assert magnus_comp is not None
    assert magnus_comp["planned_spend"] == 250000.0
    assert magnus_comp["actual_spend"] == 220000.0
    assert round(magnus_comp["spend_pacing_pct"], 1) == 88.0
