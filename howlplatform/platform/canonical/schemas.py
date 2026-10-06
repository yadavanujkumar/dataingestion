"""
Canonical schema definitions as Python dataclasses and Pydantic models.
Matches HOWL Document 04 Section 2.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class SearchRowV1:
    """Canonical schema: search_v1"""
    brand_id: str
    period: str  # YYYY-MM
    query: str
    page: str = ""
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    position: float = 0.0
    is_branded: bool = False
    brand_form: Optional[str] = None
    product: Optional[str] = None
    generic_theme: Optional[str] = None
    needs_review: bool = False
    tag_source: str = "unclassified"
    source_id: str = ""
    run_id: str = ""
    ingested_at: Optional[datetime] = None

    @property
    def unique_key(self) -> tuple:
        return (self.brand_id, self.period, self.query.lower().strip(), self.page.strip())


@dataclass(frozen=True)
class PaidRowV2:
    """Canonical schema: paid_v2"""
    brand_id: str
    date: str  # YYYY-MM-DD
    channel: str
    campaign: str
    adset: str = ""
    ad: str = ""
    spend: float = 0.0
    currency: str = "INR"
    impressions: int = 0
    reach: Optional[int] = None
    clicks: int = 0
    engagements: Optional[int] = None
    video_views: Optional[int] = None
    conversions: Optional[float] = None
    revenue: Optional[float] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    is_boosted_post: bool = False
    source_id: str = ""
    run_id: str = ""
    ingested_at: Optional[datetime] = None

    @property
    def unique_key(self) -> tuple:
        return (self.brand_id, self.date, self.channel, self.campaign, self.adset, self.ad)


@dataclass(frozen=True)
class OrganicRowV1:
    """Canonical schema: organic_v1"""
    brand_id: str
    date: str  # YYYY-MM-DD
    channel: str
    post_id: str
    post_type: Optional[str] = None
    published_at: Optional[datetime] = None
    reach: Optional[int] = None
    impressions: int = 0
    engagements: int = 0
    video_views: Optional[int] = None
    followers: Optional[int] = None
    source_id: str = ""
    run_id: str = ""
    ingested_at: Optional[datetime] = None

    @property
    def unique_key(self) -> tuple:
        return (self.brand_id, self.date, self.channel, self.post_id)


@dataclass(frozen=True)
class WebRowV1:
    """Canonical schema: web_v1"""
    brand_id: str
    date: str  # YYYY-MM-DD
    source: str
    medium: str
    campaign: str
    landing_page: str
    sessions: int = 0
    engaged_sessions: Optional[int] = None
    users: Optional[int] = None
    conversions: Optional[float] = None
    source_id: str = ""
    run_id: str = ""
    ingested_at: Optional[datetime] = None

    @property
    def unique_key(self) -> tuple:
        return (self.brand_id, self.date, self.source, self.medium, self.campaign, self.landing_page)


@dataclass(frozen=True)
class CRMRowV1:
    """Canonical schema: crm_v1"""
    brand_id: str
    date: str  # YYYY-MM-DD
    lead_id: str  # Hashed
    stage: str
    source: Optional[str] = None
    campaign: Optional[str] = None
    value: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    source_id: str = ""
    run_id: str = ""
    ingested_at: Optional[datetime] = None

    @property
    def unique_key(self) -> tuple:
        return (self.brand_id, self.lead_id, self.stage)


@dataclass(frozen=True)
class PlanRowV1:
    """Canonical schema: plan_v1"""
    brand_id: str
    plan_id: str
    campaign: str
    adset: str = ""
    ad: str = ""
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    planned_spend: Optional[float] = None
    planned_impressions: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    source_id: str = ""
    run_id: str = ""
    ingested_at: Optional[datetime] = None

    @property
    def unique_key(self) -> tuple:
        return (self.brand_id, self.plan_id, self.campaign, self.adset, self.ad)


# Map of schema_ref strings to their respective canonical row classes
CANONICAL_SCHEMA_MAP: Dict[str, Any] = {
    "search_v1": SearchRowV1,
    "paid_v2": PaidRowV2,
    "organic_v1": OrganicRowV1,
    "web_v1": WebRowV1,
    "crm_v1": CRMRowV1,
    "plan_v1": PlanRowV1,
}
