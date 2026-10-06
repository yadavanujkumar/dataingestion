from __future__ import annotations

import csv
import shutil
from pathlib import Path
import pytest
from sqlalchemy import create_engine

from howlplatform.platform.orchestrator.control_sheet import run_control_sheet
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent
FIXTURE_SHEET = REPO_ROOT / "tests" / "fixtures" / "control_sheet_sample.csv"


def test_control_sheet_trigger_and_execution(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    test_sheet = tmp_path / "control_sheet.csv"
    shutil.copy2(FIXTURE_SHEET, test_sheet)

    res = run_control_sheet(test_sheet, engine=engine)
    assert res["total_rows"] == 2
    assert res["triggered_count"] == 1
    assert len(res["runs"]) == 1
    assert res["runs"][0]["status"] == "DELIVERED"

    # Read back sheet to check updated columns
    with open(test_sheet, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 2

        # First row was triggered
        row1 = reader[0]
        assert row1["status"] == "DELIVERED"
        assert row1["trigger"] == "DONE"
        assert row1["last_run_id"] != ""
        assert row1["last_run_at"] != ""

        # Second row remained idle
        row2 = reader[1]
        assert row2["status"] == "IDLE"
        assert row2["trigger"] == "IDLE"
