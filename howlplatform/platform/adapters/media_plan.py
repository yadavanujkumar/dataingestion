from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..canonical.schemas import PlanRowV1
from ..review.queue import create_review_item
from ..store.db import get_engine
from .gsc_csv import parse_numeric, parse_float


# Default standard naming convention regex: Brand_Channel_Objective_Campaign_Audience
# e.g., AMPERE_META_CONV_MAGNUS_PANINDIA
DEFAULT_NAMING_REGEX = r"^[A-Za-z0-9]+_[A-Za-z0-9]+_[A-Za-z0-9]+_[A-Za-z0-9]+_[A-Za-z0-9_-]+$"


class MediaPlanAdapter:
    """
    Adapter to ingest and validate Media Plans into canonical_plan (plan_v1).
    Enforces campaign naming conventions and flags violations in review_items.
    """

    def __init__(
        self,
        brand_manifest: Dict[str, Any],
        source_id: str = "ampere-media-plan",
        engine: Optional[Engine] = None,
    ):
        self.brand_manifest = brand_manifest
        self.brand_id = brand_manifest["brand_id"]
        self.source_id = source_id
        self.engine = engine or get_engine()

        # Load naming convention regex from manifest if defined, otherwise default
        plan_config = brand_manifest.get("media_plan", {})
        self.naming_regex = re.compile(
            plan_config.get("naming_convention_regex", DEFAULT_NAMING_REGEX),
            re.IGNORECASE,
        )

    def validate_naming_convention(self, campaign_name: str) -> Tuple[bool, Optional[str]]:
        """Validate whether a campaign name conforms to the naming standard."""
        if not campaign_name:
            return False, "Campaign name is empty"
        if not self.naming_regex.match(campaign_name.strip()):
            return False, f"Name '{campaign_name}' does not match convention pattern"
        return True, None

    def process_file(
        self,
        file_path: Path | str,
        plan_id: str,
        run_id: str,
    ) -> Tuple[List[PlanRowV1], Dict[str, Any]]:
        """
        Parses media plan CSV, validates naming conventions, flags violations to review queue,
        and upserts rows into canonical_plan.
        """
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Media plan file not found: {p}")

        canonical_rows: List[PlanRowV1] = []
        violations_count = 0
        total_planned_spend = 0.0
        total_planned_impressions = 0

        with open(p, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                campaign = row.get("campaign", "").strip()
                adset = row.get("adset", "").strip()
                ad = row.get("ad", "").strip()
                utm_source = row.get("utm_source", "").strip() or None
                utm_medium = row.get("utm_medium", "").strip() or None
                utm_campaign = row.get("utm_campaign", "").strip() or None
                utm_content = row.get("utm_content", "").strip() or None

                planned_spend = parse_float(row.get("planned_spend", 0.0))
                planned_impressions = parse_numeric(row.get("planned_impressions", 0)) or None
                start_date = row.get("start_date", "").strip() or None
                end_date = row.get("end_date", "").strip() or None

                total_planned_spend += planned_spend
                if planned_impressions:
                    total_planned_impressions += planned_impressions

                # Check naming convention
                is_valid, reason = self.validate_naming_convention(campaign)
                if not is_valid:
                    violations_count += 1
                    create_review_item(
                        brand_id=self.brand_id,
                        run_id=run_id,
                        entity_type="naming_convention",
                        entity_key=campaign,
                        impact=planned_spend or 10.0,
                        reason=reason or "Naming convention violation",
                        suggestion={
                            "action": "rename_campaign",
                            "expected_pattern": self.naming_regex.pattern,
                        },
                        engine=self.engine,
                    )

                plan_row = PlanRowV1(
                    brand_id=self.brand_id,
                    plan_id=plan_id,
                    campaign=campaign,
                    adset=adset,
                    ad=ad,
                    utm_source=utm_source,
                    utm_medium=utm_medium,
                    utm_campaign=utm_campaign,
                    utm_content=utm_content,
                    planned_spend=planned_spend,
                    planned_impressions=planned_impressions,
                    start_date=start_date,
                    end_date=end_date,
                    source_id=self.source_id,
                    run_id=run_id,
                )
                canonical_rows.append(plan_row)

        self._upsert_rows(canonical_rows)

        stats = {
            "total_rows": len(canonical_rows),
            "naming_violations": violations_count,
            "total_planned_spend": total_planned_spend,
            "total_planned_impressions": total_planned_impressions,
        }
        return canonical_rows, stats

    def _upsert_rows(self, rows: List[PlanRowV1]):
        """Upsert media plan rows into canonical_plan."""
        if not rows:
            return

        with self.engine.begin() as conn:
            for r in rows:
                conn.execute(
                    text("""
                        INSERT INTO canonical_plan (
                            brand_id, plan_id, campaign, adset, ad,
                            utm_source, utm_medium, utm_campaign, utm_content,
                            planned_spend, planned_impressions, start_date, end_date,
                            source_id, run_id, ingested_at
                        ) VALUES (
                            :brand_id, :plan_id, :campaign, :adset, :ad,
                            :utm_source, :utm_medium, :utm_campaign, :utm_content,
                            :planned_spend, :planned_impressions, :start_date, :end_date,
                            :source_id, :run_id, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (brand_id, plan_id, campaign, adset, ad) DO UPDATE SET
                            planned_spend = excluded.planned_spend,
                            planned_impressions = excluded.planned_impressions,
                            start_date = excluded.start_date,
                            end_date = excluded.end_date,
                            source_id = excluded.source_id,
                            run_id = excluded.run_id,
                            ingested_at = CURRENT_TIMESTAMP
                    """),
                    {
                        "brand_id": r.brand_id,
                        "plan_id": r.plan_id,
                        "campaign": r.campaign,
                        "adset": r.adset,
                        "ad": r.ad,
                        "utm_source": r.utm_source,
                        "utm_medium": r.utm_medium,
                        "utm_campaign": r.utm_campaign,
                        "utm_content": r.utm_content,
                        "planned_spend": r.planned_spend,
                        "planned_impressions": r.planned_impressions,
                        "start_date": r.start_date,
                        "end_date": r.end_date,
                        "source_id": r.source_id,
                        "run_id": r.run_id,
                    },
                )


def calculate_planned_vs_actual(
    brand_id: str,
    period: str,
    plan_id: Optional[str] = None,
    engine: Optional[Engine] = None,
) -> Dict[str, Any]:
    """
    Computes planned vs actual spend and impressions for a brand and period.
    Matches canonical_plan with canonical_paid by campaign name.
    """
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        # Planned metrics
        plan_q = """
            SELECT campaign,
                   SUM(planned_spend) as total_planned_spend,
                   SUM(planned_impressions) as total_planned_impressions
            FROM canonical_plan
            WHERE brand_id = :brand_id
        """
        p_params: Dict[str, Any] = {"brand_id": brand_id}
        if plan_id:
            plan_q += " AND plan_id = :plan_id"
            p_params["plan_id"] = plan_id
        plan_q += " GROUP BY campaign"
        plan_records = conn.execute(text(plan_q), p_params).mappings().fetchall()

        # Actual paid metrics
        paid_q = """
            SELECT campaign,
                   SUM(spend) as total_actual_spend,
                   SUM(impressions) as total_actual_impressions
            FROM canonical_paid
            WHERE brand_id = :brand_id AND date LIKE :period_prefix
            GROUP BY campaign
        """
        paid_records = conn.execute(
            text(paid_q),
            {"brand_id": brand_id, "period_prefix": f"{period}%"},
        ).mappings().fetchall()

    planned_by_camp = {r["campaign"]: r for r in plan_records}
    actual_by_camp = {r["campaign"]: r for r in paid_records}

    all_campaigns = sorted(set(list(planned_by_camp.keys()) + list(actual_by_camp.keys())))

    campaign_comparisons = []
    tot_plan_spend = 0.0
    tot_act_spend = 0.0
    tot_plan_imp = 0
    tot_act_imp = 0

    for camp in all_campaigns:
        p_row = planned_by_camp.get(camp, {})
        a_row = actual_by_camp.get(camp, {})

        p_spend = float(p_row.get("total_planned_spend") or 0.0)
        a_spend = float(a_row.get("total_actual_spend") or 0.0)
        p_imp = int(p_row.get("total_planned_impressions") or 0)
        a_imp = int(a_row.get("total_actual_impressions") or 0)

        spend_variance = a_spend - p_spend
        spend_pacing_pct = (a_spend / p_spend * 100) if p_spend > 0 else 0.0

        tot_plan_spend += p_spend
        tot_act_spend += a_spend
        tot_plan_imp += p_imp
        tot_act_imp += a_imp

        campaign_comparisons.append({
            "campaign": camp,
            "planned_spend": p_spend,
            "actual_spend": a_spend,
            "spend_variance": spend_variance,
            "spend_pacing_pct": spend_pacing_pct,
            "planned_impressions": p_imp,
            "actual_impressions": a_imp,
        })

    total_spend_variance = tot_act_spend - tot_plan_spend
    overall_pacing_pct = (tot_act_spend / tot_plan_spend * 100) if tot_plan_spend > 0 else 0.0

    return {
        "brand_id": brand_id,
        "period": period,
        "plan_id": plan_id or "all",
        "total_planned_spend": tot_plan_spend,
        "total_actual_spend": tot_act_spend,
        "spend_variance": total_spend_variance,
        "overall_pacing_pct": overall_pacing_pct,
        "total_planned_impressions": tot_plan_imp,
        "total_actual_impressions": tot_act_imp,
        "campaigns": campaign_comparisons,
    }
