from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..canonical.schemas import PaidRowV2
from ..store.db import get_engine
from .gsc_csv import parse_numeric, parse_float


class MetaAdsAdapter:
    """Adapter to ingest, normalize and store Meta Ads data into canonical_paid (paid_v2)."""

    def __init__(
        self,
        brand_manifest: Dict[str, Any],
        source_id: str = "ampere-meta-ads",
        engine: Optional[Engine] = None,
    ):
        self.brand_manifest = brand_manifest
        self.brand_id = brand_manifest["brand_id"]
        self.source_id = source_id
        self.engine = engine or get_engine()

    def process_file(
        self,
        file_path: Path | str,
        period: str,
        run_id: str,
    ) -> Tuple[List[PaidRowV2], Dict[str, Any]]:
        """Parse raw Meta Ads file (CSV or JSON) into PaidRowV2 and upsert to database."""
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Meta Ads file not found: {p}")

        canonical_rows: List[PaidRowV2] = []
        total_spend = 0.0
        total_impressions = 0
        total_clicks = 0
        total_engagements = 0

        with open(p, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                dt = raw.get("date", "").strip()
                camp = raw.get("campaign", "").strip() or "Unnamed_Campaign"
                adset = raw.get("adset", "").strip()
                ad = raw.get("ad", "").strip()

                spend = parse_float(raw.get("spend", 0.0))
                currency = raw.get("currency", "INR").strip() or "INR"
                impressions = parse_numeric(raw.get("impressions", 0))
                reach = parse_numeric(raw.get("reach", 0)) or None
                clicks = parse_numeric(raw.get("clicks", 0))

                # Post engagements mapping per manifest metric dictionary
                engagements = parse_numeric(raw.get("post_engagements", raw.get("engagements", 0)))
                video_views = parse_numeric(raw.get("video_views", 0))
                conversions = parse_float(raw.get("conversions", 0.0))
                revenue = parse_float(raw.get("revenue", 0.0))

                # UTM tags
                utm_src = raw.get("utm_source")
                utm_med = raw.get("utm_medium")
                utm_camp = raw.get("utm_campaign")
                utm_cnt = raw.get("utm_content")

                is_boosted = str(raw.get("is_boosted_post", "")).lower() in ("true", "1", "yes")
                if not is_boosted and "boost" in camp.lower():
                    is_boosted = True

                row = PaidRowV2(
                    brand_id=self.brand_id,
                    date=dt,
                    channel="meta_ads",
                    campaign=camp,
                    adset=adset,
                    ad=ad,
                    spend=spend,
                    currency=currency,
                    impressions=impressions,
                    reach=reach,
                    clicks=clicks,
                    engagements=engagements,
                    video_views=video_views,
                    conversions=conversions,
                    revenue=revenue,
                    utm_source=utm_src,
                    utm_medium=utm_med,
                    utm_campaign=utm_camp,
                    utm_content=utm_cnt,
                    is_boosted_post=is_boosted,
                    source_id=self.source_id,
                    run_id=run_id,
                )
                canonical_rows.append(row)
                total_spend += spend
                total_impressions += impressions
                total_clicks += clicks
                total_engagements += engagements

        self._upsert_rows(canonical_rows)

        summary = {
            "total_rows": len(canonical_rows),
            "total_spend": round(total_spend, 2),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_engagements": total_engagements,
            "boosted_posts_count": sum(1 for r in canonical_rows if r.is_boosted_post),
        }
        return canonical_rows, summary

    def _upsert_rows(self, rows: List[PaidRowV2]) -> None:
        """Upsert canonical paid rows on unique key."""
        if not rows:
            return

        is_sqlite = self.engine.dialect.name == "sqlite"
        sql = """
            INSERT INTO canonical_paid (
                brand_id, date, channel, campaign, adset, ad,
                spend, currency, impressions, reach, clicks, engagements, video_views,
                conversions, revenue, utm_source, utm_medium, utm_campaign, utm_content,
                is_boosted_post, source_id, run_id, ingested_at
            ) VALUES (
                :brand_id, :date, :channel, :campaign, :adset, :ad,
                :spend, :currency, :impressions, :reach, :clicks, :engagements, :video_views,
                :conversions, :revenue, :utm_source, :utm_medium, :utm_campaign, :utm_content,
                :is_boosted_post, :source_id, :run_id, CURRENT_TIMESTAMP
            )
            ON CONFLICT(brand_id, date, channel, campaign, adset, ad) DO UPDATE SET
                spend = excluded.spend,
                currency = excluded.currency,
                impressions = excluded.impressions,
                reach = excluded.reach,
                clicks = excluded.clicks,
                engagements = excluded.engagements,
                video_views = excluded.video_views,
                conversions = excluded.conversions,
                revenue = excluded.revenue,
                utm_source = excluded.utm_source,
                utm_medium = excluded.utm_medium,
                utm_campaign = excluded.utm_campaign,
                utm_content = excluded.utm_content,
                is_boosted_post = excluded.is_boosted_post,
                source_id = excluded.source_id,
                run_id = excluded.run_id,
                ingested_at = CURRENT_TIMESTAMP
        """

        with self.engine.begin() as conn:
            for r in rows:
                conn.execute(
                    text(sql),
                    {
                        "brand_id": r.brand_id,
                        "date": r.date,
                        "channel": r.channel,
                        "campaign": r.campaign,
                        "adset": r.adset,
                        "ad": r.ad,
                        "spend": r.spend,
                        "currency": r.currency,
                        "impressions": r.impressions,
                        "reach": r.reach,
                        "clicks": r.clicks,
                        "engagements": r.engagements,
                        "video_views": r.video_views,
                        "conversions": r.conversions,
                        "revenue": r.revenue,
                        "utm_source": r.utm_source,
                        "utm_medium": r.utm_medium,
                        "utm_campaign": r.utm_campaign,
                        "utm_content": r.utm_content,
                        "is_boosted_post": 1 if (is_sqlite and r.is_boosted_post) else r.is_boosted_post,
                        "source_id": r.source_id,
                        "run_id": r.run_id,
                    }
                )
