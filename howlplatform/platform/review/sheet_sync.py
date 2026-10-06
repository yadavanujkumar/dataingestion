from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.engine import Engine

from ..store.db import get_engine
from .queue import get_open_review_items, resolve_review_item


REVIEW_SHEET_HEADERS = [
    "item_id",
    "entity_type",
    "entity_key",
    "impact",
    "reason",
    "ai_suggestion",
    "action",           # Analyst enters: reclassify, fix, exclude, ignore
    "value",            # Analyst enters: e.g. generic_theme=dealership or is_branded=true
    "analyst_notes",    # Analyst enters reason
]


def export_review_sheet(
    brand_id: str,
    output_path: Optional[Path | str] = None,
    engine: Optional[Engine] = None,
) -> Path:
    """
    Exports open review items for an analyst into a CSV/Sheet-compatible file.
    Items are sorted in descending order of impact.
    """
    if engine is None:
        engine = get_engine()

    items = get_open_review_items(brand_id, engine)

    out_file = Path(output_path or Path.cwd() / "review_sheets" / f"{brand_id}_review_queue.csv")
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_SHEET_HEADERS)
        writer.writeheader()

        for it in items:
            sugg_str = json.dumps(it.get("suggestion", {})) if it.get("suggestion") else ""
            writer.writerow({
                "item_id": it["item_id"],
                "entity_type": it["entity_type"],
                "entity_key": it["entity_key"],
                "impact": f"{it['impact']:.1f}",
                "reason": it["reason"],
                "ai_suggestion": sugg_str,
                "action": "",
                "value": "",
                "analyst_notes": "",
            })

    return out_file


def import_review_sheet(
    brand_id: str,
    input_path: Path | str,
    decided_by: str = "analyst@howl.internal",
    engine: Optional[Engine] = None,
) -> Dict[str, Any]:
    """
    Reads decisions entered by an analyst into the Sheet/CSV,
    records them in the decision ledger, and resolves the review items.
    Skips items where 'action' was left empty.
    """
    if engine is None:
        engine = get_engine()

    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError(f"Review sheet file not found: {p}")

    resolved_count = 0
    skipped_count = 0
    errors = []

    with open(p, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_id = row.get("item_id", "").strip()
            action = row.get("action", "").strip().lower()

            if not action:
                skipped_count += 1
                continue

            if action not in ("reclassify", "fix", "exclude", "ignore"):
                errors.append(f"Invalid action '{action}' for item {item_id}")
                continue

            val_raw = row.get("value", "").strip()
            notes = row.get("analyst_notes", "").strip() or f"Analyst action {action}"

            # Parse value (key=val or JSON)
            val_dict: Dict[str, Any] = {}
            if val_raw:
                if "=" in val_raw and not val_raw.startswith("{"):
                    k, v = val_raw.split("=", 1)
                    v_clean = True if v.lower() == "true" else (False if v.lower() == "false" else v)
                    val_dict[k.strip()] = v_clean
                else:
                    try:
                        val_dict = json.loads(val_raw)
                    except Exception:
                        val_dict = {"raw": val_raw}

            dec_id = resolve_review_item(
                item_id=item_id,
                action=action,
                value=val_dict,
                decided_by=decided_by,
                reason=notes,
                engine=engine,
            )
            if dec_id:
                resolved_count += 1

    return {
        "brand_id": brand_id,
        "resolved_count": resolved_count,
        "skipped_count": skipped_count,
        "errors": errors,
    }
