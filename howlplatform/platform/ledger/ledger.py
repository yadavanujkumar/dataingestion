from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
from ..store.db import get_engine


def normalize_entity_key(key: str) -> str:
    """Normalize entity key: lower-case, trimmed, collapse consecutive whitespace."""
    if not key:
        return ""
    return re.sub(r"\s+", " ", key.strip().lower())


def record_decision(
    brand_id: str,
    entity_type: str,
    entity_key: str,
    decision: str,
    value: Dict[str, Any],
    decided_by: str,
    reason: Optional[str] = None,
    supersedes: Optional[str] = None,
    engine: Optional[Engine] = None,
) -> str:
    """
    Append a new decision to the decision_ledger.
    Returns the generated decision_id (uuid string).
    """
    if engine is None:
        engine = get_engine()

    decision_id = str(uuid.uuid4())
    norm_key = normalize_entity_key(entity_key)
    val_json = json.dumps(value)

    is_sqlite = engine.dialect.name == "sqlite"
    sql = """
        INSERT INTO decision_ledger (
            decision_id, brand_id, entity_type, entity_key,
            decision, value, reason, supersedes, decided_by, decided_at
        ) VALUES (
            :decision_id, :brand_id, :entity_type, :entity_key,
            :decision, :value, :reason, :supersedes, :decided_by, CURRENT_TIMESTAMP
        )
    """

    with engine.begin() as conn:
        conn.execute(
            text(sql),
            {
                "decision_id": decision_id,
                "brand_id": brand_id,
                "entity_type": entity_type,
                "entity_key": norm_key,
                "decision": decision,
                "value": val_json,
                "reason": reason or "",
                "supersedes": supersedes,
                "decided_by": decided_by,
            }
        )

    return decision_id


def get_active_decision(
    brand_id: str,
    entity_type: str,
    entity_key: str,
    engine: Optional[Engine] = None,
) -> Optional[Dict[str, Any]]:
    """
    Lookup the latest active decision for an entity that has not been superseded.
    """
    if engine is None:
        engine = get_engine()

    norm_key = normalize_entity_key(entity_key)

    # Query all decisions for this brand and entity key, ordered by decided_at desc
    query = """
        SELECT d.decision_id, d.decision, d.value, d.reason, d.decided_by, d.decided_at, d.supersedes
        FROM decision_ledger d
        WHERE d.brand_id = :brand_id
          AND d.entity_type = :entity_type
          AND d.entity_key = :entity_key
          AND d.decision_id NOT IN (
              SELECT COALESCE(supersedes, '') FROM decision_ledger WHERE brand_id = :brand_id AND supersedes IS NOT NULL
          )
        ORDER BY d.decided_at DESC
        LIMIT 1
    """

    with engine.connect() as conn:
        row = conn.execute(
            text(query),
            {"brand_id": brand_id, "entity_type": entity_type, "entity_key": norm_key}
        ).fetchone()

        if not row:
            return None

        val = row[2]
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                pass

        return {
            "decision_id": row[0],
            "decision": row[1],
            "value": val,
            "reason": row[3],
            "decided_by": row[4],
            "decided_at": row[5],
            "supersedes": row[6],
        }
