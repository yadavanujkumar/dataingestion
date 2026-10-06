from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.engine import Engine

from .pipeline import PipelineRun
from ..store.db import get_engine


def run_control_sheet(
    sheet_path: Path | str,
    engine: Optional[Engine] = None,
) -> Dict[str, Any]:
    """
    Parses a control sheet CSV, identifies triggered report execution requests,
    executes them through the PipelineRun state machine, and updates the sheet.
    """
    p = Path(sheet_path)
    if not p.is_file():
        raise FileNotFoundError(f"Control sheet file not found: {p}")

    rows: List[Dict[str, str]] = []
    fieldnames: List[str] = []

    with open(p, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for r in reader:
            rows.append(dict(r))

    # Ensure required tracking columns exist
    for col in ["status", "trigger", "last_run_id", "last_run_at"]:
        if col not in fieldnames:
            fieldnames.append(col)

    results: List[Dict[str, Any]] = []
    triggered_count = 0

    for row in rows:
        trigger_val = (row.get("trigger") or "").strip().upper()
        if trigger_val in ["RUN", "TRUE", "1", "YES", "TRIGGER"]:
            triggered_count += 1
            brand_id = row.get("brand_id", "").strip()
            deliverable = row.get("deliverable", "").strip()
            period = row.get("period", "").strip()
            input_file = row.get("input_file", "").strip() or None

            try:
                pipeline = PipelineRun(
                    brand_id=brand_id,
                    deliverable=deliverable,
                    period=period,
                    input_file=input_file,
                    engine=engine,
                )
                res = pipeline.execute()
                run_id = res.get("run_id", "")
                final_status = res.get("status", "unknown").upper()

                row["status"] = final_status
                row["trigger"] = "DONE"
                row["last_run_id"] = run_id
                row["last_run_at"] = datetime.now(timezone.utc).isoformat()

                results.append({
                    "brand_id": brand_id,
                    "deliverable": deliverable,
                    "period": period,
                    "status": final_status,
                    "run_id": run_id,
                    "error": None,
                })
            except Exception as e:
                err_msg = str(e)
                row["status"] = "FAILED"
                row["trigger"] = "ERROR"
                row["last_run_at"] = datetime.now(timezone.utc).isoformat()
                results.append({
                    "brand_id": brand_id,
                    "deliverable": deliverable,
                    "period": period,
                    "status": "FAILED",
                    "error": err_msg,
                })

    # Save updated control sheet
    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "sheet_path": str(p.resolve()),
        "total_rows": len(rows),
        "triggered_count": triggered_count,
        "runs": results,
    }
