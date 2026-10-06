from __future__ import annotations

import json
from pathlib import Path
import pytest

from howlplatform.platform.delivery.notifications import (
    send_slack_message,
    create_email_draft,
    notify_review_gate_blocked,
    notify_run_completed,
    notify_run_failed,
)


def test_send_slack_message(tmp_path):
    res = send_slack_message(
        text="Test slack notification",
        channel="#test-channel",
    )
    assert res["sent"] is True
    assert res["mock"] is True
    assert res["channel"] == "#test-channel"

    # Verify audit file was written
    history_file = Path.cwd() / "outputs" / "notifications" / "slack_history.jsonl"
    assert history_file.is_file()
    with open(history_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) > 0
        last = json.loads(lines[-1])
        assert "Test slack notification" in last["text"]


def test_create_email_draft(tmp_path):
    # Create sample dummy report file
    dummy_report = tmp_path / "sample_report.xlsx"
    dummy_report.write_text("dummy binary content")

    res = create_email_draft(
        brand_id="ampere",
        subject="Monthly Performance Report - 2026-08",
        body_text="Hi Team, please find attached the monthly report.",
        recipients=["client-team@howl.internal"],
        attachments=[dummy_report],
    )

    assert res["brand_id"] == "ampere"
    assert Path(res["eml_path"]).is_file()
    assert len(res["attachments"]) == 1

    # Verify .eml content
    eml_content = Path(res["eml_path"]).read_bytes()
    assert b"Monthly Performance Report" in eml_content
    assert b"sample_report.xlsx" in eml_content


def test_specialized_notifications():
    # 1. Gate blocked
    res_gate = notify_review_gate_blocked(
        brand_id="ampere",
        run_id="run_test_123",
        deliverable="gsc_organic_report",
        period="2026-08",
        gate_status={"unresolved_share": 0.05, "blocking_share": 0.02, "unresolved_count": 3},
    )
    assert res_gate["sent"] is True
    assert "review-list" in res_gate["text"]

    # 2. Run completed
    res_done = notify_run_completed(
        brand_id="ampere",
        run_id="run_test_123",
        deliverable="gsc_organic_report",
        period="2026-08",
        delivered_files=[{"file_name": "test.xlsx", "delivered_to": "/tmp/test.xlsx"}],
    )
    assert res_done["slack"]["sent"] is True
    assert res_done["email_draft"]["brand_id"] == "ampere"

    # 3. Run failed
    res_fail = notify_run_failed(
        brand_id="ampere",
        run_id="run_test_123",
        deliverable="gsc_organic_report",
        period="2026-08",
        error_message="Test database connection error",
    )
    assert res_fail["sent"] is True
    assert "Test database connection error" in res_fail["text"]
