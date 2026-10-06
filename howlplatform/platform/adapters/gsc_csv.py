from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..canonical.schemas import SearchRowV1
from ..classifier.classifier import QueryClassifier
from ..review.queue import create_review_item
from ..store.db import get_engine


def parse_ctr_value(val: Any) -> float:
    """Parse CTR which might be '8.12%', 0.0812, or '0.0812'."""
    if val is None or val == "":
        return 0.0
    val_str = str(val).strip()
    if val_str.endswith("%"):
        try:
            return round(float(val_str[:-1]) / 100.0, 6)
        except ValueError:
            return 0.0
    try:
        f = float(val_str)
        # If > 1.0, might be percentage without percent sign e.g. 8.12
        return round(f / 100.0, 6) if f > 1.0 else round(f, 6)
    except ValueError:
        return 0.0


def parse_numeric(val: Any, default: int = 0) -> int:
    """Parse integer value handling commas or formatted strings."""
    if val is None or val == "":
        return default
    try:
        val_clean = str(val).replace(",", "").strip()
        return int(float(val_clean))
    except ValueError:
        return default


def parse_float(val: Any, default: float = 0.0) -> float:
    """Parse float position value."""
    if val is None or val == "":
        return default
    try:
        return round(float(str(val).replace(",", "").strip()), 2)
    except ValueError:
        return default


class GSCCSVAdapter:
    """Adapter to ingest, normalize and store Google Search Console CSV exports."""

    def __init__(
        self,
        brand_manifest: Dict[str, Any],
        source_id: str = "ampere-gsc",
        engine: Optional[Engine] = None
    ):
        self.brand_manifest = brand_manifest
        self.brand_id = brand_manifest["brand_id"]
        self.source_id = source_id
        self.engine = engine or get_engine()
        self.classifier = QueryClassifier(brand_manifest, engine=self.engine)

    def process_file(
        self,
        file_path: Path | str,
        period: str,
        run_id: str
    ) -> Tuple[List[SearchRowV1], Dict[str, Any]]:
        """
        Normalize GSC CSV into canonical_search rows, classify queries,
        and upsert into database.
        """
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"GSC CSV file not found: {p}")

        canonical_rows: List[SearchRowV1] = []
        unplaceable_count = 0
        total_clicks = 0
        total_impressions = 0

        with open(p, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Find column names case-insensitively
            fieldnames = reader.fieldnames or []
            field_map = {name.strip().lower(): name for name in fieldnames}

            query_col = (
                field_map.get("top queries")
                or field_map.get("query")
                or field_map.get("top query")
            )
            clicks_col = field_map.get("clicks")
            impressions_col = field_map.get("impressions")
            ctr_col = field_map.get("ctr")
            position_col = field_map.get("position")
            page_col = field_map.get("landing page") or field_map.get("page")

            if not query_col:
                create_review_item(
                    brand_id=self.brand_id,
                    run_id=run_id,
                    entity_type="file",
                    entity_key=p.name,
                    impact=100.0,
                    reason=f"GSC CSV missing required query column. Header found: {fieldnames}",
                    engine=self.engine,
                )
                raise ValueError(f"Missing required query column in GSC CSV: {fieldnames}")

            for row_idx, raw_row in enumerate(reader, start=2):
                query = raw_row.get(query_col, "").strip() if query_col else ""
                if not query:
                    unplaceable_count += 1
                    create_review_item(
                        brand_id=self.brand_id,
                        run_id=run_id,
                        entity_type="record",
                        entity_key=f"{p.name}:row_{row_idx}",
                        impact=0.0,
                        reason="GSC CSV row has empty query string",
                        engine=self.engine,
                    )
                    continue

                clicks = parse_numeric(raw_row.get(clicks_col, 0) if clicks_col else 0)
                impressions = parse_numeric(raw_row.get(impressions_col, 0) if impressions_col else 0)
                ctr = parse_ctr_value(raw_row.get(ctr_col, 0.0) if ctr_col else 0.0)
                position = parse_float(raw_row.get(position_col, 0.0) if position_col else 0.0)
                page = raw_row.get(page_col, "").strip() if page_col else ""

                if clicks < 0 or impressions < 0:
                    unplaceable_count += 1
                    create_review_item(
                        brand_id=self.brand_id,
                        run_id=run_id,
                        entity_type="query",
                        entity_key=query,
                        impact=abs(clicks),
                        reason=f"Negative clicks ({clicks}) or impressions ({impressions}) found in GSC data",
                        engine=self.engine,
                    )
                    continue

                # Run query classification
                tag_info = self.classifier.classify_query(
                    query=query,
                    clicks=clicks,
                    impressions=impressions,
                    run_id=run_id,
                )

                canonical_row = SearchRowV1(
                    brand_id=self.brand_id,
                    period=period,
                    query=query,
                    page=page,
                    impressions=impressions,
                    clicks=clicks,
                    ctr=ctr,
                    position=position,
                    is_branded=tag_info["is_branded"],
                    brand_form=tag_info["brand_form"],
                    product=tag_info["product"],
                    generic_theme=tag_info["generic_theme"],
                    needs_review=tag_info["needs_review"],
                    tag_source=tag_info["tag_source"],
                    source_id=self.source_id,
                    run_id=run_id,
                )
                canonical_rows.append(canonical_row)
                total_clicks += clicks
                total_impressions += impressions

        # Upsert canonical rows to database
        self._upsert_rows(canonical_rows)

        summary = {
            "total_rows": len(canonical_rows),
            "unplaceable_rows": unplaceable_count,
            "total_clicks": total_clicks,
            "total_impressions": total_impressions,
            "branded_count": sum(1 for r in canonical_rows if r.is_branded),
            "unclassified_count": sum(1 for r in canonical_rows if r.needs_review),
        }
        return canonical_rows, summary

    def _upsert_rows(self, rows: List[SearchRowV1]) -> None:
        """Upsert canonical search rows on composite primary key."""
        if not rows:
            return

        is_sqlite = self.engine.dialect.name == "sqlite"
        sql = """
            INSERT INTO canonical_search (
                brand_id, period, query, page, impressions, clicks, ctr, position,
                is_branded, brand_form, product, generic_theme, needs_review, tag_source,
                source_id, run_id, ingested_at
            ) VALUES (
                :brand_id, :period, :query, :page, :impressions, :clicks, :ctr, :position,
                :is_branded, :brand_form, :product, :generic_theme, :needs_review, :tag_source,
                :source_id, :run_id, CURRENT_TIMESTAMP
            )
            ON CONFLICT(brand_id, period, query, page) DO UPDATE SET
                impressions = excluded.impressions,
                clicks = excluded.clicks,
                ctr = excluded.ctr,
                position = excluded.position,
                is_branded = excluded.is_branded,
                brand_form = excluded.brand_form,
                product = excluded.product,
                generic_theme = excluded.generic_theme,
                needs_review = excluded.needs_review,
                tag_source = excluded.tag_source,
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
                        "period": r.period,
                        "query": r.query,
                        "page": r.page,
                        "impressions": r.impressions,
                        "clicks": r.clicks,
                        "ctr": r.ctr,
                        "position": r.position,
                        "is_branded": 1 if (is_sqlite and r.is_branded) else r.is_branded,
                        "brand_form": r.brand_form,
                        "product": r.product,
                        "generic_theme": r.generic_theme,
                        "needs_review": 1 if (is_sqlite and r.needs_review) else r.needs_review,
                        "tag_source": r.tag_source,
                        "source_id": r.source_id,
                        "run_id": r.run_id,
                    }
                )
