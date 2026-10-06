from __future__ import annotations

import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

from howlplatform.platform.orchestrator.pipeline import (
    PipelineRun,
    resume_run,
    list_runs,
    load_canonical_data_from_db,
)
from howlplatform.platform.review.queue import create_review_item, resolve_review_item
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "gsc_ampere_2026_08.csv"


def test_list_runs():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO brands (brand_id, manifest, manifest_version)
                VALUES ('ampere', '{}', 1)
            """)
        )
        conn.execute(
            text("""
                INSERT INTO runs (run_id, brand_id, deliverable, period, status, stage, started_at)
                VALUES ('run_1', 'ampere', 'gsc_organic_report', '2026-08', 'delivered', 'delivered', '2026-08-01 10:00:00'),
                       ('run_2', 'ampere', 'paid_social_report', '2026-08', 'awaiting_review', 'review_gate', '2026-08-01 11:00:00')
            """)
        )

    runs = list_runs(brand_id="ampere", engine=engine)
    assert len(runs) == 2
    assert runs[0]["run_id"] == "run_2"
    assert runs[1]["run_id"] == "run_1"


def test_resume_run_validation_errors():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    # 1. Non-existent run
    with pytest.raises(ValueError, match="not found"):
        resume_run("non_existent_run", engine=engine)

    # 2. Run not in awaiting_review
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO brands (brand_id, manifest, manifest_version)
                VALUES ('ampere', '{}', 1)
            """)
        )
        conn.execute(
            text("""
                INSERT INTO runs (run_id, brand_id, deliverable, period, status, stage)
                VALUES ('run_delivered', 'ampere', 'gsc_organic_report', '2026-08', 'delivered', 'delivered')
            """)
        )

    with pytest.raises(ValueError, match="Only runs in 'awaiting_review'"):
        resume_run("run_delivered", engine=engine)


def test_resume_run_end_to_end(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    # 1. Run pipeline on GSC CSV
    run = PipelineRun(
        brand_id="ampere",
        deliverable="gsc_organic_report",
        period="2026-08",
        input_file=SAMPLE_CSV,
        engine=engine,
    )
    result = run.execute()
    assert result["status"] == "delivered"
    total_impact = result["stats"]["total_impact"]

    # 2. Simulate a run paused at awaiting_review with high impact open review item (> 2% threshold)
    paused_run_id = "run_paused_gate"
    blocking_impact = total_impact * 0.05  # 5% of impact, well above the 2% threshold
    item_id = create_review_item(
        brand_id="ampere",
        run_id=paused_run_id,
        entity_type="query",
        entity_key="unclassified query with huge volume",
        impact=blocking_impact,
        reason="unclassified query",
        engine=engine,
    )

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO runs (run_id, brand_id, deliverable, period, status, stage, row_counts)
                VALUES (:run_id, 'ampere', 'gsc_organic_report', '2026-08', 'awaiting_review', 'review_gate', :row_counts)
            """),
            {
                "run_id": paused_run_id,
                "row_counts": json.dumps({"total_impact": total_impact}),
            },
        )

    # 3. Attempt to resume while gate is still blocked
    res_halted = resume_run(paused_run_id, engine=engine)
    assert res_halted["status"] == "awaiting_review"
    assert res_halted["gate_status"]["blocked"] is True

    # 4. Resolve the blocking review item
    resolve_review_item(
        item_id=item_id,
        action="reclassify",
        value={"generic_theme": "intent"},
        decided_by="analyst@howl.internal",
        engine=engine,
    )

    # 5. Resume run again - now it should unblock and deliver!
    res_completed = resume_run(paused_run_id, engine=engine)
    assert res_completed["status"] == "delivered"
    assert len(res_completed["delivered_files"]) > 0

    # 6. Verify runs table was updated to delivered
    with engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM runs WHERE run_id = :run_id"),
            {"run_id": paused_run_id},
        ).scalar()
        assert status == "delivered"
