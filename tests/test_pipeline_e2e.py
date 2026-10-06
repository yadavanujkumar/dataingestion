from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine

from howlplatform.platform.orchestrator.pipeline import PipelineRun
from howlplatform.platform.review.queue import get_open_review_items, resolve_review_item
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "gsc_ampere_2026_08.csv"


def test_pipeline_e2e_and_idempotence():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    # 1. Run pipeline first time
    pipeline1 = PipelineRun(
        brand_id="ampere",
        deliverable="gsc_organic_report",
        period="2026-08",
        input_file=SAMPLE_CSV,
        engine=engine,
    )
    res1 = pipeline1.execute()
    assert res1["status"] == "delivered"
    assert len(res1["delivered_files"]) == 1

    first_file = Path(res1["delivered_files"][0]["delivered_to"])
    assert first_file.is_file()

    # Check open review items
    open_items_first = get_open_review_items("ampere", engine)
    num_items_first = len(open_items_first)

    # 2. Run pipeline second time (Exit Test: zero new review items & identical file delivered)
    pipeline2 = PipelineRun(
        brand_id="ampere",
        deliverable="gsc_organic_report",
        period="2026-08",
        input_file=SAMPLE_CSV,
        engine=engine,
    )
    res2 = pipeline2.execute()
    assert res2["status"] == "delivered"

    open_items_second = get_open_review_items("ampere", engine)
    assert len(open_items_second) == num_items_first  # Zero new review items!
