from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from howlplatform.platform.ledger.ledger import get_active_decision
from howlplatform.platform.review.queue import (
    create_review_item,
    get_open_review_items,
    resolve_review_item,
    evaluate_review_gate,
)
from howlplatform.platform.store.db import run_migrations


def test_review_queue_and_gate_evaluation():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    # 1. Create review item
    item_id = create_review_item(
        brand_id="ampere",
        run_id="run_1",
        entity_type="query",
        entity_key="unclear ev scooter",
        impact=50.0,
        reason="Unknown brand attribution",
        engine=engine,
    )
    assert item_id is not None

    # 2. Gate evaluation with blocking threshold
    # Total clicks = 1000. 50 clicks = 5% > 2% threshold -> should block
    gate_block = evaluate_review_gate("ampere", total_impact=1000.0, blocking_share=0.02, engine=engine)
    assert gate_block["blocked"] is True

    # Total clicks = 10000. 50 clicks = 0.5% < 2% threshold -> should NOT block
    gate_ok = evaluate_review_gate("ampere", total_impact=10000.0, blocking_share=0.02, engine=engine)
    assert gate_ok["blocked"] is False

    # 3. Resolve review item
    decision_id = resolve_review_item(
        item_id=item_id,
        action="reclassify",
        value={"is_branded": True, "product": "Reo"},
        decided_by="analyst@howl.internal",
        engine=engine,
    )
    assert decision_id is not None

    # Verify ledger has it
    dec = get_active_decision("ampere", "query", "unclear ev scooter", engine)
    assert dec is not None
    assert dec["decision"] == "reclassify"

    # Verify queue has 0 open items now
    open_items = get_open_review_items("ampere", engine)
    assert len(open_items) == 0
