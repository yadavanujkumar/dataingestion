from __future__ import annotations

import pytest
from howlplatform.platform.canonical.schemas import (
    SearchRowV1,
    PaidRowV2,
    OrganicRowV1,
    WebRowV1,
    CRMRowV1,
    PlanRowV1,
    CANONICAL_SCHEMA_MAP,
)


def test_canonical_schema_map_completeness():
    expected_schemas = {"search_v1", "paid_v2", "organic_v1", "web_v1", "crm_v1", "plan_v1"}
    assert set(CANONICAL_SCHEMA_MAP.keys()) == expected_schemas


def test_search_v1_row_creation_and_key():
    row = SearchRowV1(
        brand_id="ampere",
        period="2026-08",
        query="ampere magnus g max price",
        page="/magnus",
        impressions=1500,
        clicks=120,
        ctr=0.08,
        position=2.4,
        is_branded=True,
        product="Magnus G Max",
        tag_source="rule",
    )
    assert row.unique_key == ("ampere", "2026-08", "ampere magnus g max price", "/magnus")
    assert row.clicks == 120
    assert row.is_branded is True


def test_paid_v2_row_creation_and_key():
    row = PaidRowV2(
        brand_id="ampere",
        date="2026-08-15",
        channel="meta_ads",
        campaign="Ampere_Magnus_Awareness",
        spend=4500.50,
        impressions=25000,
        clicks=320,
        engagements=850,
        is_boosted_post=False,
    )
    assert row.unique_key == ("ampere", "2026-08-15", "meta_ads", "Ampere_Magnus_Awareness", "", "")
    assert row.engagements == 850
