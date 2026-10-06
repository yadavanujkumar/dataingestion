from __future__ import annotations

import pytest
from howlplatform.platform.review.impact import compute_entity_impact, rank_items_by_impact


def test_domain_impact_scoring():
    # Search: clicks
    assert compute_entity_impact("search", {"clicks": 150, "impressions": 2000}) == 150.0
    # Search: 0 clicks -> fallback to impressions * 0.01
    assert compute_entity_impact("search", {"clicks": 0, "impressions": 5000}) == 50.0

    # Paid: spend
    assert compute_entity_impact("paid", {"spend": 12500.50}) == 12500.50

    # Organic: impressions
    assert compute_entity_impact("organic", {"impressions": 45000}) == 45000.0

    # Web: sessions
    assert compute_entity_impact("web", {"sessions": 3200}) == 3200.0

    # CRM: deal value
    assert compute_entity_impact("crm", {"value": 85000.0}) == 85000.0


def test_rank_items_by_impact():
    items = [
        {"item_id": "1", "impact": 10.0},
        {"item_id": "2", "impact": 500.0},
        {"item_id": "3", "impact": 50.0},
    ]
    ranked = rank_items_by_impact(items)
    assert [x["item_id"] for x in ranked] == ["2", "3", "1"]
