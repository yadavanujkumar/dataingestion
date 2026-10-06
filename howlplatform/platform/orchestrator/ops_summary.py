from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..store.db import get_engine


def generate_ops_summary(
    brand_id: Optional[str] = None,
    hours: int = 24,
    engine: Optional[Engine] = None,
) -> Dict[str, Any]:
    """
    Generates a consolidated operational summary of platform health and activity:
    - Runs in the last N hours (completed, paused, failed)
    - Review queue backlog and stale items
    - Raw file ingestion freshness
    - Outputs delivered
    """
    if engine is None:
        engine = get_engine()

    since_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    since_str = since_dt.isoformat()

    summary: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": hours,
        "brand_filter": brand_id or "all",
        "runs": {
            "total": 0,
            "delivered": 0,
            "awaiting_review": 0,
            "failed": 0,
            "other": 0,
            "items": [],
        },
        "review_queue": {
            "open_count": 0,
            "total_open_impact": 0.0,
            "stale_count_48h": 0,
            "top_unresolved": [],
        },
        "raw_files": {
            "total_received": 0,
            "recent_files": [],
        },
        "outputs": {
            "total_delivered": 0,
            "recent_outputs": [],
        },
        "health_status": "HEALTHY",
    }

    with engine.connect() as conn:
        # 1. Runs Query
        run_query = """
            SELECT run_id, brand_id, deliverable, period, status, stage, started_at, completed_at, error_message
            FROM runs
            WHERE started_at >= :since
        """
        params: Dict[str, Any] = {"since": since_str}
        if brand_id:
            run_query += " AND brand_id = :brand_id"
            params["brand_id"] = brand_id
        run_query += " ORDER BY started_at DESC"

        run_rows = conn.execute(text(run_query), params).mappings().fetchall()
        summary["runs"]["total"] = len(run_rows)
        for r in run_rows:
            st = (r["status"] or "").lower()
            if st == "delivered":
                summary["runs"]["delivered"] += 1
            elif st == "awaiting_review":
                summary["runs"]["awaiting_review"] += 1
            elif st == "failed":
                summary["runs"]["failed"] += 1
            else:
                summary["runs"]["other"] += 1

            summary["runs"]["items"].append({
                "run_id": r["run_id"],
                "brand_id": r["brand_id"],
                "deliverable": r["deliverable"],
                "period": r["period"],
                "status": r["status"],
                "stage": r["stage"],
                "started_at": str(r["started_at"]),
                "error_message": r["error_message"],
            })

        # 2. Review Items Query
        rev_query = """
            SELECT item_id, brand_id, run_id, entity_type, entity_key, impact, reason, status, created_at
            FROM review_items
            WHERE status = 'open'
        """
        rev_params: Dict[str, Any] = {}
        if brand_id:
            rev_query += " AND brand_id = :brand_id"
            rev_params["brand_id"] = brand_id
        rev_query += " ORDER BY impact DESC"

        rev_rows = conn.execute(text(rev_query), rev_params).mappings().fetchall()
        summary["review_queue"]["open_count"] = len(rev_rows)

        stale_threshold = datetime.now(timezone.utc) - timedelta(hours=48)
        for r in rev_rows:
            summary["review_queue"]["total_open_impact"] += float(r["impact"] or 0.0)
            created_at_dt = r["created_at"]
            if created_at_dt and isinstance(created_at_dt, str):
                try:
                    created_at_dt = datetime.fromisoformat(created_at_dt)
                except Exception:
                    created_at_dt = None
            if created_at_dt and created_at_dt.tzinfo is None:
                created_at_dt = created_at_dt.replace(tzinfo=timezone.utc)
            if created_at_dt and created_at_dt < stale_threshold:
                summary["review_queue"]["stale_count_48h"] += 1

        summary["review_queue"]["top_unresolved"] = [
            {
                "item_id": r["item_id"],
                "brand_id": r["brand_id"],
                "entity_key": r["entity_key"],
                "impact": float(r["impact"] or 0.0),
                "reason": r["reason"],
            }
            for r in rev_rows[:5]
        ]

        # 3. Raw Files Query
        raw_query = """
            SELECT file_id, source_id, run_id, sha256, storage_ref, received_at
            FROM raw_files
            WHERE received_at >= :since
            ORDER BY received_at DESC
        """
        raw_rows = conn.execute(text(raw_query), {"since": since_str}).mappings().fetchall()
        summary["raw_files"]["total_received"] = len(raw_rows)
        summary["raw_files"]["recent_files"] = [
            {
                "file_id": r["file_id"],
                "source_id": r["source_id"],
                "storage_ref": r["storage_ref"],
                "received_at": str(r["received_at"]),
            }
            for r in raw_rows[:5]
        ]

        # 4. Outputs Query
        out_query = """
            SELECT output_id, run_id, generator, generator_version, file_ref, delivered_to, created_at
            FROM outputs
            WHERE created_at >= :since
            ORDER BY created_at DESC
        """
        out_rows = conn.execute(text(out_query), {"since": since_str}).mappings().fetchall()
        summary["outputs"]["total_delivered"] = len(out_rows)
        summary["outputs"]["recent_outputs"] = [
            {
                "output_id": r["output_id"],
                "run_id": r["run_id"],
                "generator": r["generator"],
                "delivered_to": r["delivered_to"],
                "created_at": str(r["created_at"]),
            }
            for r in out_rows[:5]
        ]

    # Health evaluation
    if summary["runs"]["failed"] > 0:
        summary["health_status"] = "DEGRADED"
    elif summary["runs"]["awaiting_review"] > 0 or summary["review_queue"]["stale_count_48h"] > 0:
        summary["health_status"] = "ATTENTION_NEEDED"
    else:
        summary["health_status"] = "HEALTHY"

    return summary


def format_ops_summary_text(summary: Dict[str, Any]) -> str:
    """Formats an ops summary dictionary into an executive terminal/markdown report."""
    lines = []
    lines.append("================================================================================")
    lines.append(f" HOWL PLATFORM - DAILY OPERATIONAL SUMMARY (Last {summary['window_hours']} Hours)")
    lines.append(f" Generated: {summary['generated_at']} | Brand: {summary['brand_filter'].upper()}")
    lines.append(f" Overall Status: [{summary['health_status']}]")
    lines.append("================================================================================")
    lines.append("")

    runs = summary["runs"]
    lines.append(f"[RUNS & PIPELINE] Total: {runs['total']}")
    lines.append(f"  - Completed/Delivered: {runs['delivered']}")
    lines.append(f"  - Awaiting Review:     {runs['awaiting_review']}")
    lines.append(f"  - Failed:              {runs['failed']}")
    if runs["items"]:
        lines.append("  Recent Runs:")
        for r in runs["items"][:5]:
            err = f" (Error: {r['error_message']})" if r["error_message"] else ""
            lines.append(f"    * [{r['status'].upper()}] {r['brand_id']} - {r['deliverable']} ({r['period']}) ID: {r['run_id']}{err}")
    lines.append("")

    rev = summary["review_queue"]
    lines.append(f"[REVIEW QUEUE] Open Items: {rev['open_count']} (Total Impact: {rev['total_open_impact']:,.1f})")
    lines.append(f"  - Stale (>48h) Open Items: {rev['stale_count_48h']}")
    if rev["top_unresolved"]:
        lines.append("  Top Unresolved Items by Impact:")
        for itm in rev["top_unresolved"]:
            lines.append(f"    * [{itm['brand_id']}] '{itm['entity_key']}' (Impact: {itm['impact']:,.1f}) - {itm['reason']}")
    lines.append("")

    raw = summary["raw_files"]
    lines.append(f"[DATA INGESTION] Raw Files Received: {raw['total_received']}")

    out = summary["outputs"]
    lines.append(f"[DELIVERY] Outputs Generated: {out['total_delivered']}")
    if out["recent_outputs"]:
        for o in out["recent_outputs"][:3]:
            lines.append(f"    * {o['generator']} -> {o['delivered_to']}")

    lines.append("================================================================================")
    return "\n".join(lines)
