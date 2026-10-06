from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..store.db import get_engine
from .ledger import normalize_entity_key, record_decision


def supersede_decision(
    old_decision_id: str,
    brand_id: str,
    decision: str,
    value: Dict[str, Any],
    decided_by: str,
    reason: str,
    engine: Optional[Engine] = None,
) -> str:
    """
    Supersede an earlier decision with a new decision (append-only ledger).
    Mandates a non-empty reason.
    Returns the new decision_id.
    """
    if engine is None:
        engine = get_engine()

    if not reason or not reason.strip():
        raise ValueError("A reason is strictly required when superseding a decision.")

    # Fetch entity information from old decision
    with engine.connect() as conn:
        old_row = conn.execute(
            text("SELECT entity_type, entity_key FROM decision_ledger WHERE decision_id = :id AND brand_id = :b"),
            {"id": old_decision_id, "b": brand_id}
        ).fetchone()

    if not old_row:
        raise ValueError(f"Old decision with ID '{old_decision_id}' not found for brand '{brand_id}'.")

    entity_type, entity_key = old_row[0], old_row[1]

    new_id = record_decision(
        brand_id=brand_id,
        entity_type=entity_type,
        entity_key=entity_key,
        decision=decision,
        value=value,
        decided_by=decided_by,
        reason=reason,
        supersedes=old_decision_id,
        engine=engine,
    )
    return new_id


def get_decision_history(
    brand_id: str,
    entity_type: str,
    entity_key: str,
    engine: Optional[Engine] = None,
) -> List[Dict[str, Any]]:
    """Retrieve full revision history for an entity from oldest to newest."""
    if engine is None:
        engine = get_engine()

    norm_key = normalize_entity_key(entity_key)

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT decision_id, decision, value, reason, supersedes, decided_by, decided_at
                FROM decision_ledger
                WHERE brand_id = :brand_id AND entity_type = :entity_type AND entity_key = :entity_key
                ORDER BY decided_at ASC
            """),
            {"brand_id": brand_id, "entity_type": entity_type, "entity_key": norm_key}
        ).fetchall()

        history = []
        for r in rows:
            val = r[2]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    pass
            history.append({
                "decision_id": r[0],
                "decision": r[1],
                "value": val,
                "reason": r[3],
                "supersedes": r[4],
                "decided_by": r[5],
                "decided_at": str(r[6]),
            })
        return history


def get_brand_audit_trail(
    brand_id: str,
    limit: int = 50,
    engine: Optional[Engine] = None,
) -> List[Dict[str, Any]]:
    """Retrieve recent decisions across all entities for the brand."""
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT decision_id, entity_type, entity_key, decision, value, reason, supersedes, decided_by, decided_at
                FROM decision_ledger
                WHERE brand_id = :brand_id
                ORDER BY decided_at DESC
                LIMIT :limit
            """),
            {"brand_id": brand_id, "limit": limit}
        ).fetchall()

        audit = []
        for r in rows:
            val = r[4]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    pass
            audit.append({
                "decision_id": r[0],
                "entity_type": r[1],
                "entity_key": r[2],
                "decision": r[3],
                "value": val,
                "reason": r[5],
                "supersedes": r[6],
                "decided_by": r[7],
                "decided_at": str(r[8]),
            })
        return audit
