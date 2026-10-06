from __future__ import annotations

from pathlib import Path
import openpyxl
import pytest

REPO_ROOT = Path(__file__).parent.parent
GOLDEN_FILE = REPO_ROOT / "tests" / "golden" / "ampere_organic_search_report_2026-08.xlsx"


def test_golden_report_file_structure():
    assert GOLDEN_FILE.is_file(), "Golden report file must exist"
    wb = openpyxl.load_workbook(GOLDEN_FILE)
    expected_sheets = {"Summary", "Product Breakdown", "Top Queries", "Notes"}
    assert set(wb.sheetnames) == expected_sheets

    ws_sum = wb["Summary"]
    assert "Ampere - Organic Search Performance Report" in str(ws_sum["A1"].value)
    assert ws_sum["A4"].value == "Total Queries"
