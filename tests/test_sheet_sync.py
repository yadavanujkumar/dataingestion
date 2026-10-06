from __future__ import annotations

import csv
from pathlib import Path
import pytest
from sqlalchemy import create_engine

from howlplatform.platform.review.queue import create_review_item, get_open_review_items
from howlplatform.platform.review.sheet_sync import export_review_sheet, import_review_sheet
from howlplatform.platform.store.db import run_migrations


def test_review_sheet_export_and_import(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    # 1. Create a review item
    item_id = create_review_item(
        brand_id="ampere",
        run_id="run_test",
        entity_type="query",
        entity_key="scooter financing emi options",
        impact=40.0,
        reason="Unknown theme",
        engine=engine,
    )

    # 2. Export to CSV
    export_csv = tmp_path / "review_queue.csv"
    export_review_sheet("ampere", output_path=export_csv, engine=engine)
    assert export_csv.is_file()

    # 3. Simulate analyst filling in response
    rows = []
    with open(export_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["item_id"] == item_id:
                r["action"] = "reclassify"
                r["value"] = "generic_theme=finance"
                r["analyst_notes"] = "Financing query"
            rows.append(r)

    with open(export_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # 4. Import from CSV
    res = import_review_sheet("ampere", input_path=export_csv, engine=engine)
    assert res["resolved_count"] == 1

    # Verify queue is empty
    open_items = get_open_review_items("ampere", engine)
    assert len(open_items) == 0
