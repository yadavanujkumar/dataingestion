from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from howlplatform.platform.ledger.ledger import record_decision, get_active_decision
from howlplatform.platform.ledger.audit import (
    supersede_decision,
    get_decision_history,
    get_brand_audit_trail,
)
from howlplatform.platform.store.db import run_migrations


def test_decision_supersession_and_history():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    # 1. First decision
    d1_id = record_decision(
        brand_id="ampere",
        entity_type="query",
        entity_key="ampere battery warranty",
        decision="reclassify",
        value={"generic_theme": "warranty"},
        decided_by="analyst1@howl.internal",
        reason="Initial review",
        engine=engine,
    )

    active1 = get_active_decision("ampere", "query", "ampere battery warranty", engine)
    assert active1["decision_id"] == d1_id
    assert active1["value"]["generic_theme"] == "warranty"

    # 2. Supersede with new decision
    d2_id = supersede_decision(
        old_decision_id=d1_id,
        brand_id="ampere",
        decision="reclassify",
        value={"generic_theme": "support_warranty"},
        decided_by="lead@howl.internal",
        reason="Updated taxonomy",
        engine=engine,
    )
    assert d2_id != d1_id

    # Active decision must now be d2
    active2 = get_active_decision("ampere", "query", "ampere battery warranty", engine)
    assert active2["decision_id"] == d2_id
    assert active2["value"]["generic_theme"] == "support_warranty"

    # 3. History inspection
    history = get_decision_history("ampere", "query", "ampere battery warranty", engine)
    assert len(history) == 2
    assert history[0]["decision_id"] == d1_id
    assert history[1]["decision_id"] == d2_id
    assert history[1]["supersedes"] == d1_id

    # 4. Brand audit trail
    trail = get_brand_audit_trail("ampere", limit=10, engine=engine)
    assert len(trail) == 2


def test_supersede_without_reason_raises_error():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    d1 = record_decision("ampere", "query", "test", "ignore", {}, "a@b.com", engine=engine)
    with pytest.raises(ValueError):
        supersede_decision(d1, "ampere", "reclassify", {}, "a@b.com", reason="", engine=engine)
