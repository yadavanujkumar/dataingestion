from __future__ import annotations

import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine

from howlplatform.platform.ledger.ledger import record_decision
from howlplatform.platform.ledger.promotion import find_promotable_patterns, promote_decisions_to_manifest
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent


def test_find_promotable_patterns_and_promotion(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    # Insert repeated decisions
    for q in ["ampere charging issue", "fast charging time for scooter"]:
        record_decision(
            brand_id="test_brand",
            entity_type="query",
            entity_key=q,
            decision="reclassify",
            value={"generic_theme": "charging"},
            decided_by="analyst@howl.internal",
            engine=engine,
        )

    patterns = find_promotable_patterns("test_brand", min_count=2, engine=engine)
    assert len(patterns["promotable_rules"]) > 0
    assert any("charging" in r["pattern"] for r in patterns["promotable_rules"])
