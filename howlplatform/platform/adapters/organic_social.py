from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..canonical.schemas import OrganicRowV1
from ..store.db import get_engine
from .gsc_csv import parse_numeric


class OrganicSocialAdapter:
    """Adapter to ingest and normalize organic social posts across Instagram, Facebook, YouTube, and LinkedIn."""

    def __init__(
        self,
        brand_manifest: Dict[str, Any],
        source_id: str = "ampere-organic-social",
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
    ) -> Tuple[List[OrganicRowV1], Dict[str, Any]]:
        """Parse organic social CSV into OrganicRowV1 and upsert to database."""
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Organic social file not found: {p}")

        canonical_rows: List[OrganicRowV1] = []
        total_impressions = 0
        total_engagements = 0

        with open(p, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                dt = raw.get("date", "").strip()
                channel = raw.get("channel", "").strip().lower()
                post_id = raw.get("post_id", "").strip() or f"post_{len(canonical_rows)}"
                post_type = raw.get("post_type", "").strip() or None
                published_at = raw.get("published_at", "").strip() or None

                reach = parse_numeric(raw.get("reach", 0)) or None
                impressions = parse_numeric(raw.get("impressions", 0))
                engagements = parse_numeric(raw.get("engagements", 0))
                video_views = parse_numeric(raw.get("video_views", 0)) or None
                followers = parse_numeric(raw.get("followers", 0)) or None

                row = OrganicRowV1(
                    brand_id=self.brand_id,
                    date=dt,
                    channel=channel,
                    post_id=post_id,
                    post_type=post_type,
                    published_at=None,
                    reach=reach,
                    impressions=impressions,
                    engagements=engagements,
                    video_views=video_views,
                    followers=followers,
                    source_id=self.source_id,
                    run_id=run_id,
                )
                canonical_rows.append(row)
                total_impressions += impressions
                total_engagements += engagements

        self._upsert_rows(canonical_rows)

        summary = {
            "total_rows": len(canonical_rows),
            "total_impressions": total_impressions,
            "total_engagements": total_engagements,
            "channels": list(set(r.channel for r in canonical_rows)),
        }
        return canonical_rows, summary

    def _upsert_rows(self, rows: List[OrganicRowV1]) -> None:
        """Upsert canonical organic rows on composite unique key."""
        if not rows:
            return

        is_sqlite = self.engine.dialect.name == "sqlite"
        sql = """
            INSERT INTO canonical_organic (
                brand_id, date, channel, post_id, post_type, published_at,
                reach, impressions, engagements, video_views, followers,
                source_id, run_id, ingested_at
            ) VALUES (
                :brand_id, :date, :channel, :post_id, :post_type, :published_at,
                :reach, :impressions, :engagements, :video_views, :followers,
                :source_id, :run_id, CURRENT_TIMESTAMP
            )
            ON CONFLICT(brand_id, date, channel, post_id) DO UPDATE SET
                post_type = excluded.post_type,
                reach = excluded.reach,
                impressions = excluded.impressions,
                engagements = excluded.engagements,
                video_views = excluded.video_views,
                followers = excluded.followers,
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
                        "post_id": r.post_id,
                        "post_type": r.post_type,
                        "published_at": None,
                        "reach": r.reach,
                        "impressions": r.impressions,
                        "engagements": r.engagements,
                        "video_views": r.video_views,
                        "followers": r.followers,
                        "source_id": r.source_id,
                        "run_id": r.run_id,
                    }
                )
