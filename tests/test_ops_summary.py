from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from howlplatform.platform.orchestrator.ops_summary import (
    generate_ops_summary,
    format_ops_summary_text,
)
from howlplatform.platform.store.db import run_migrations


def test_generate_ops_summary():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    with engine.begin() as conn:
        # Insert a run
        conn.execute(
            text("""
                INSERT INTO brands (brand_id, manifest, manifest_version)
                VALUES ('test_brand', '{}', 1)
            """)
        )
        conn.execute(
            text("""
                INSERT INTO runs (run_id, brand_id, deliverable, period, status, stage)
                VALUES ('run_test_1', 'test_brand', 'gsc_organic_report', '2026-08', 'delivered', 'delivered')
            """)
        )
        # Insert an open review item
        conn.execute(
            text("""
                INSERT INTO review_items (item_id, brand_id, entity_type, entity_key, impact, reason, status)
                VALUES ('item_1', 'test_brand', 'query', 'electric scooter price', 150.0, 'unclassified', 'open')
            """)
        )

    summary = generate_ops_summary(engine=engine)
    assert summary["runs"]["total"] == 1
    assert summary["runs"]["delivered"] == 1
    assert summary["review_queue"]["open_count"] == 1
    assert summary["review_queue"]["total_open_impact"] == 150.0
    assert summary["health_status"] in ["HEALTHY", "ATTENTION_NEEDED"]

    report_text = format_ops_summary_text(summary)
    assert "DAILY OPERATIONAL SUMMARY" in report_text
    assert "electric scooter price" in report_text
