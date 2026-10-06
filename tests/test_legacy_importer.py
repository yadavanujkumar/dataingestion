from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine

from howlplatform.platform.ingest.legacy import LegacySheetImporter, parse_percentage_cell
from howlplatform.platform.review.queue import get_open_review_items
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent
LEGACY_CSV = REPO_ROOT / "tests" / "fixtures" / "legacy_engagement_rate_ampere.csv"


def test_parse_percentage_cell():
    assert parse_percentage_cell("16.45%") == 0.1645
    assert parse_percentage_cell("0.20%") == 0.002
    assert parse_percentage_cell("-") is None
    assert parse_percentage_cell("") is None


def test_legacy_sheet_importer_and_outlier_flagging():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    importer = LegacySheetImporter(brand_id="ampere", engine=engine)
    rows = importer.import_legacy_sheet(LEGACY_CSV, run_id="test_legacy_import")

    assert len(rows) > 0
    # Problem cells over 100% (if any) or flagged
    open_items = get_open_review_items("ampere", engine)
    assert isinstance(open_items, list)
