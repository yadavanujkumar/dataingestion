from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
from ..store.db import get_engine
from ..ledger.ledger import normalize_entity_key, record_decision


def create_review_item(
    brand_id: str,
    run_id: str,
    entity_type: str,
    entity_key: str,
    impact: float,
    reason: str,
    suggestion: Optional[Dict[str, Any]] = None,
    engine: Optional[Engine] = None,
) -> str:
    """Create a new item in review_items if not already existing as open."""
    if engine is None:
        engine = get_engine()

    norm_key = normalize_entity_key(entity_key)
    sugg_json = json.dumps(suggestion) if suggestion else None

    # Check if this exact entity is already open for this brand
    with engine.connect() as conn:
        existing = conn.execute(
            text("""
                SELECT item_id FROM review_items
                WHERE brand_id = :brand_id AND entity_type = :entity_type
                  AND entity_key = :entity_key AND status = 'open'
            """),
            {"brand_id": brand_id, "entity_type": entity_type, "entity_key": norm_key}
        ).fetchone()

        if existing:
            return existing[0]

    item_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO review_items (
                    item_id, brand_id, run_id, entity_type, entity_key,
                    impact, reason, suggestion, status, created_at
                ) VALUES (
                    :item_id, :brand_id, :run_id, :entity_type, :entity_key,
                    :impact, :reason, :suggestion, 'open', CURRENT_TIMESTAMP
                )
            """),
            {
                "item_id": item_id,
                "brand_id": brand_id,
                "run_id": run_id,
                "entity_type": entity_type,
                "entity_key": norm_key,
                "impact": impact,
                "reason": reason,
                "suggestion": sugg_json,
            }
        )

    return item_id


def get_open_review_items(brand_id: str, engine: Optional[Engine] = None) -> List[Dict[str, Any]]:
    """Retrieve all open review items for a brand ranked by impact descending."""
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT item_id, run_id, entity_type, entity_key, impact, reason, suggestion, created_at
                FROM review_items
                WHERE brand_id = :brand_id AND status = 'open'
                ORDER BY impact DESC
            """),
            {"brand_id": brand_id}
        ).fetchall()

        items = []
        for r in rows:
            sugg = r[6]
            if isinstance(sugg, str):
                try:
                    sugg = json.loads(sugg)
                except Exception:
                    pass
            items.append({
                "item_id": r[0],
                "run_id": r[1],
                "entity_type": r[2],
                "entity_key": r[3],
                "impact": float(r[4]),
                "reason": r[5],
                "suggestion": sugg,
                "created_at": r[7],
            })
        return items


def resolve_review_item(
    item_id: str,
    action: str,  # 'reclassify', 'fix', 'exclude', 'ignore'
    value: Dict[str, Any],
    decided_by: str,
    reason: Optional[str] = None,
    engine: Optional[Engine] = None,
) -> Optional[str]:
    """
    Resolve an open review item: records the decision in the decision ledger
    and marks the review item as resolved.
    """
    if engine is None:
        engine = get_engine()

    # Fetch review item details
    with engine.connect() as conn:
        item = conn.execute(
            text("SELECT brand_id, entity_type, entity_key FROM review_items WHERE item_id = :item_id"),
            {"item_id": item_id}
        ).fetchone()

    if not item:
        return None

    brand_id, entity_type, entity_key = item[0], item[1], item[2]

    # Write to ledger
    decision_id = record_decision(
        brand_id=brand_id,
        entity_type=entity_type,
        entity_key=entity_key,
        decision=action,
        value=value,
        decided_by=decided_by,
        reason=reason,
        engine=engine,
    )

    # Mark review item resolved
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE review_items
                SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
                WHERE item_id = :item_id
            """),
            {"item_id": item_id}
        )

    return decision_id


def evaluate_review_gate(
    brand_id: str,
    total_impact: float,
    blocking_share: float = 0.02,
    engine: Optional[Engine] = None,
) -> Dict[str, Any]:
    """
    Check if unresolved review items exceed the deliverable's blocking threshold.
    Returns:
      blocked: bool
      unresolved_impact: float
      unresolved_share: float
      items_count: int
    """
    items = get_open_review_items(brand_id, engine)
    unresolved_impact = sum(item["impact"] for item in items)
    unresolved_share = (unresolved_impact / total_impact) if total_impact > 0 else 0.0

    blocked = unresolved_share > blocking_share
    return {
        "blocked": blocked,
        "unresolved_impact": unresolved_impact,
        "total_impact": total_impact,
        "unresolved_share": unresolved_share,
        "blocking_share": blocking_share,
        "items_count": len(items),
        "items": items,
    }
