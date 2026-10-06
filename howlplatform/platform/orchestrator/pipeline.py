from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..adapters.gsc_csv import GSCCSVAdapter
from ..adapters.meta_ads import MetaAdsAdapter
from ..adapters.organic_social import OrganicSocialAdapter
from ..canonical.schemas import SearchRowV1, PaidRowV2, OrganicRowV1
from ..delivery.drive import deliver_report_files
from ..delivery.notifications import (
    notify_review_gate_blocked,
    notify_run_completed,
    notify_run_failed,
)
from ..ingest.drive import is_file_already_ingested, record_raw_file
from ..manifest.loader import load_manifest
from ..review.queue import evaluate_review_gate
from ..store.db import get_engine, run_migrations, all_required_tables_exist
from ..store.sync import sync_brand_manifest
from ...deliverables.contract import get_generator


def load_canonical_data_from_db(
    brand_id: str,
    period: str,
    req_domains: List[str],
    engine: Engine,
) -> Dict[str, List[Any]]:
    """Loads canonical dataclasses from the database for the given brand, period, and domains."""
    data: Dict[str, List[Any]] = {}

    with engine.connect() as conn:
        if "search" in req_domains:
            search_rows = conn.execute(
                text("""
                    SELECT brand_id, period, query, page, impressions, clicks, ctr, position,
                           is_branded, brand_form, product, generic_theme, needs_review, tag_source,
                           source_id, run_id, ingested_at
                    FROM canonical_search
                    WHERE brand_id = :brand_id AND period = :period
                """),
                {"brand_id": brand_id, "period": period},
            ).mappings().fetchall()

            data["search"] = [
                SearchRowV1(
                    brand_id=r["brand_id"],
                    period=r["period"],
                    query=r["query"],
                    page=r["page"],
                    impressions=int(r["impressions"]),
                    clicks=int(r["clicks"]),
                    ctr=float(r["ctr"]),
                    position=float(r["position"]),
                    is_branded=bool(r["is_branded"]),
                    brand_form=r["brand_form"],
                    product=r["product"],
                    generic_theme=r["generic_theme"],
                    needs_review=bool(r["needs_review"]),
                    tag_source=r["tag_source"],
                    source_id=r["source_id"],
                    run_id=r["run_id"],
                    ingested_at=r["ingested_at"],
                )
                for r in search_rows
            ]

        if "paid" in req_domains:
            paid_rows = conn.execute(
                text("""
                    SELECT brand_id, date, channel, campaign, adset, ad, spend, currency,
                           impressions, reach, clicks, engagements, video_views, conversions,
                           revenue, utm_source, utm_medium, utm_campaign, utm_content,
                           is_boosted_post, source_id, run_id, ingested_at
                    FROM canonical_paid
                    WHERE brand_id = :brand_id AND date LIKE :period_prefix
                """),
                {"brand_id": brand_id, "period_prefix": f"{period}%"},
            ).mappings().fetchall()

            data["paid"] = [
                PaidRowV2(
                    brand_id=r["brand_id"],
                    date=r["date"],
                    channel=r["channel"],
                    campaign=r["campaign"],
                    adset=r["adset"],
                    ad=r["ad"],
                    spend=float(r["spend"]),
                    currency=r["currency"],
                    impressions=int(r["impressions"]),
                    reach=r["reach"],
                    clicks=int(r["clicks"]),
                    engagements=r["engagements"],
                    video_views=r["video_views"],
                    conversions=r["conversions"],
                    revenue=r["revenue"],
                    utm_source=r["utm_source"],
                    utm_medium=r["utm_medium"],
                    utm_campaign=r["utm_campaign"],
                    utm_content=r["utm_content"],
                    is_boosted_post=bool(r["is_boosted_post"]),
                    source_id=r["source_id"],
                    run_id=r["run_id"],
                    ingested_at=r["ingested_at"],
                )
                for r in paid_rows
            ]

        if "organic" in req_domains:
            org_rows = conn.execute(
                text("""
                    SELECT brand_id, date, channel, post_id, post_type, published_at,
                           reach, impressions, engagements, video_views, followers,
                           source_id, run_id, ingested_at
                    FROM canonical_organic
                    WHERE brand_id = :brand_id AND date LIKE :period_prefix
                """),
                {"brand_id": brand_id, "period_prefix": f"{period}%"},
            ).mappings().fetchall()

            data["organic"] = [
                OrganicRowV1(
                    brand_id=r["brand_id"],
                    date=r["date"],
                    channel=r["channel"],
                    post_id=r["post_id"],
                    post_type=r["post_type"],
                    published_at=r["published_at"],
                    reach=r["reach"],
                    impressions=int(r["impressions"]),
                    engagements=int(r["engagements"]),
                    video_views=r["video_views"],
                    followers=r["followers"],
                    source_id=r["source_id"],
                    run_id=r["run_id"],
                    ingested_at=r["ingested_at"],
                )
                for r in org_rows
            ]

    return data


class PipelineRun:
    """Manages the full end-to-end report generation pipeline state machine."""

    def __init__(
        self,
        brand_id: str,
        deliverable: str,
        period: str,
        input_file: Optional[Path | str] = None,
        run_id: Optional[str] = None,
        engine: Optional[Engine] = None,
    ):
        self.brand_id = brand_id
        self.deliverable = deliverable
        self.period = period
        self.input_file = Path(input_file) if input_file else None
        self.run_id = run_id or f"run_{uuid.uuid4().hex[:10]}"
        self.engine = engine or get_engine()

        if not all_required_tables_exist(self.engine):
            run_migrations(self.engine)

        manifest_path = Path.cwd() / "manifests" / f"{brand_id}.json"
        self.manifest = load_manifest(manifest_path)
        sync_brand_manifest(self.manifest, self.engine)

    def _update_run_status(
        self,
        status: str,
        stage: str,
        row_counts: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ):
        with self.engine.begin() as conn:
            counts_json = json.dumps(row_counts or {})
            conn.execute(
                text("""
                    INSERT INTO runs (run_id, brand_id, deliverable, period, status, stage, started_at, row_counts, error_message)
                    VALUES (:run_id, :brand_id, :deliverable, :period, :status, :stage, CURRENT_TIMESTAMP, :row_counts, :error_message)
                    ON CONFLICT(run_id) DO UPDATE SET
                        status = excluded.status,
                        stage = excluded.stage,
                        row_counts = excluded.row_counts,
                        error_message = excluded.error_message,
                        completed_at = CASE WHEN excluded.status IN ('delivered', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END
                """),
                {
                    "run_id": self.run_id,
                    "brand_id": self.brand_id,
                    "deliverable": self.deliverable,
                    "period": self.period,
                    "status": status,
                    "stage": stage,
                    "row_counts": counts_json,
                    "error_message": error_message,
                },
            )

    def execute(self) -> Dict[str, Any]:
        """
        Execute the pipeline stages in order:
        trigger -> ingest -> normalize -> classify -> review -> generate -> deliver
        """
        try:
            # Stage 0: Trigger
            self._update_run_status("pending", "trigger")

            gen_cls = get_generator(self.deliverable)
            if not gen_cls:
                err = f"Generator for '{self.deliverable}' is not registered."
                self._update_run_status("failed", "trigger", error_message=err)
                notify_run_failed(self.brand_id, self.run_id, self.deliverable, self.period, err)
                raise ValueError(err)

            generator = gen_cls()
            req_domains = [req.domain for req in generator.spec.requires]

            # Stage 1 & 2: Ingest & Normalize for required domains
            self._update_run_status("ingesting", "ingest")
            canonical_data: Dict[str, List[Any]] = {}
            combined_stats: Dict[str, Any] = {}
            total_impact = 0.0

            fixtures_dir = Path.cwd() / "tests" / "fixtures"

            # Search domain
            if "search" in req_domains:
                file_to_use = self.input_file
                if not file_to_use or not file_to_use.is_file():
                    file_to_use = fixtures_dir / f"gsc_{self.brand_id}_{self.period.replace('-', '_')}.csv"
                if file_to_use.is_file():
                    record_raw_file(f"{self.brand_id}-gsc", self.run_id, file_to_use, self.engine)
                    adapter = GSCCSVAdapter(self.manifest, source_id=f"{self.brand_id}-gsc", engine=self.engine)
                    rows, stats = adapter.process_file(file_to_use, self.period, self.run_id)
                    canonical_data["search"] = rows
                    combined_stats["search"] = stats
                    total_impact += float(stats.get("total_clicks", 0))

            # Paid domain
            if "paid" in req_domains:
                file_to_use = self.input_file if (self.input_file and "meta" in self.input_file.name.lower()) else None
                if not file_to_use or not file_to_use.is_file():
                    file_to_use = fixtures_dir / f"meta_ads_{self.brand_id}_{self.period.replace('-', '_')}.csv"
                if file_to_use.is_file():
                    record_raw_file(f"{self.brand_id}-meta-ads", self.run_id, file_to_use, self.engine)
                    adapter = MetaAdsAdapter(self.manifest, source_id=f"{self.brand_id}-meta-ads", engine=self.engine)
                    rows, stats = adapter.process_file(file_to_use, self.period, self.run_id)
                    canonical_data["paid"] = rows
                    combined_stats["paid"] = stats
                    total_impact += float(stats.get("total_spend", 0.0))

            # Organic domain
            if "organic" in req_domains:
                file_to_use = self.input_file if (self.input_file and "organic" in self.input_file.name.lower()) else None
                if not file_to_use or not file_to_use.is_file():
                    file_to_use = fixtures_dir / f"organic_social_{self.brand_id}_{self.period.replace('-', '_')}.csv"
                if file_to_use.is_file():
                    record_raw_file(f"{self.brand_id}-organic-social", self.run_id, file_to_use, self.engine)
                    adapter = OrganicSocialAdapter(self.manifest, source_id=f"{self.brand_id}-organic-social", engine=self.engine)
                    rows, stats = adapter.process_file(file_to_use, self.period, self.run_id)
                    canonical_data["organic"] = rows
                    combined_stats["organic"] = stats
                    total_impact += float(stats.get("total_impressions", 0))

            combined_stats["total_impact"] = total_impact

            # Stage 4: Review Gate
            self._update_run_status("classifying", "review_gate", row_counts=combined_stats)
            review_block = self.manifest.get("review", {})
            blocking_share = review_block.get("blocking_share", 0.02)

            gate_status = evaluate_review_gate(
                brand_id=self.brand_id,
                total_impact=total_impact,
                blocking_share=blocking_share,
                engine=self.engine,
            )

            if gate_status["blocked"]:
                msg = (
                    f"Run paused: Review gate blocked. "
                    f"Unresolved items account for {gate_status['unresolved_share']*100:.2f}% of impact "
                    f"(threshold: {blocking_share*100:.2f}%)."
                )
                self._update_run_status("awaiting_review", "review_gate", row_counts=combined_stats, error_message=msg)
                notify_review_gate_blocked(self.brand_id, self.run_id, self.deliverable, self.period, gate_status)
                return {
                    "run_id": self.run_id,
                    "status": "awaiting_review",
                    "stage": "review_gate",
                    "message": msg,
                    "gate_status": gate_status,
                    "stats": combined_stats,
                }

            # Stage 5: Generate
            self._update_run_status("generating", "generate", row_counts=combined_stats)
            temp_out = Path.cwd() / "outputs" / "temp"
            generated_files = generator.build(
                brand=self.manifest,
                period=self.period,
                data=canonical_data,
                out_dir=temp_out,
            )

            # Stage 6: Deliver
            self._update_run_status("delivering", "deliver", row_counts=combined_stats)
            delivered = deliver_report_files(
                run_id=self.run_id,
                brand_id=self.brand_id,
                deliverable=self.deliverable,
                period=self.period,
                generator_version=generator.spec.version,
                generated_files=generated_files,
                engine=self.engine,
            )

            self._update_run_status("delivered", "delivered", row_counts=combined_stats)
            notify_res = notify_run_completed(self.brand_id, self.run_id, self.deliverable, self.period, delivered)

            return {
                "run_id": self.run_id,
                "status": "delivered",
                "stage": "completed",
                "stats": combined_stats,
                "delivered_files": delivered,
                "gate_status": gate_status,
                "notifications": notify_res,
            }

        except Exception as e:
            err_msg = str(e)
            self._update_run_status("failed", "failed", error_message=err_msg)
            notify_run_failed(self.brand_id, self.run_id, self.deliverable, self.period, err_msg)
            raise


def resume_run(run_id: str, engine: Optional[Engine] = None) -> Dict[str, Any]:
    """
    Resumes a pipeline run that was paused at 'awaiting_review'.
    Re-evaluates the review gate. If unblocked, loads existing canonical data from DB,
    generates deliverables, delivers outputs, and dispatches completion notifications.
    """
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        run_record = conn.execute(
            text("SELECT run_id, brand_id, deliverable, period, status, stage, row_counts FROM runs WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).mappings().fetchone()

    if not run_record:
        raise ValueError(f"Run '{run_id}' not found.")

    if run_record["status"] != "awaiting_review":
        raise ValueError(
            f"Run '{run_id}' is in status '{run_record['status']}'. "
            f"Only runs in 'awaiting_review' status can be resumed."
        )

    brand_id = run_record["brand_id"]
    deliverable = run_record["deliverable"]
    period = run_record["period"]
    row_counts_str = run_record["row_counts"]
    if isinstance(row_counts_str, str):
        row_counts = json.loads(row_counts_str)
    elif isinstance(row_counts_str, dict):
        row_counts = row_counts_str
    else:
        row_counts = {}

    total_impact = float(row_counts.get("total_impact", 0.0))

    manifest_path = Path.cwd() / "manifests" / f"{brand_id}.json"
    manifest = load_manifest(manifest_path)

    gen_cls = get_generator(deliverable)
    if not gen_cls:
        raise ValueError(f"Generator for '{deliverable}' is not registered.")
    generator = gen_cls()
    req_domains = [req.domain for req in generator.spec.requires]

    # Re-evaluate review gate
    review_block = manifest.get("review", {})
    blocking_share = review_block.get("blocking_share", 0.02)
    gate_status = evaluate_review_gate(
        brand_id=brand_id,
        total_impact=total_impact,
        blocking_share=blocking_share,
        engine=engine,
    )

    if gate_status["blocked"]:
        msg = (
            f"Run resume halted: Review gate still blocked. "
            f"Unresolved items: {gate_status.get('items_count', 0)} "
            f"({gate_status.get('unresolved_share', 0.0)*100:.2f}% impact)."
        )
        return {
            "run_id": run_id,
            "status": "awaiting_review",
            "stage": "review_gate",
            "message": msg,
            "gate_status": gate_status,
        }

    # Unblocked! Load canonical data directly from the DB
    canonical_data = load_canonical_data_from_db(brand_id, period, req_domains, engine)

    # Generate
    temp_out = Path.cwd() / "outputs" / "temp"
    generated_files = generator.build(
        brand=manifest,
        period=period,
        data=canonical_data,
        out_dir=temp_out,
    )

    # Deliver
    delivered = deliver_report_files(
        run_id=run_id,
        brand_id=brand_id,
        deliverable=deliverable,
        period=period,
        generator_version=generator.spec.version,
        generated_files=generated_files,
        engine=engine,
    )

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE runs
                SET status = 'delivered',
                    stage = 'delivered',
                    error_message = NULL,
                    completed_at = CURRENT_TIMESTAMP
                WHERE run_id = :run_id
            """),
            {"run_id": run_id},
        )

    notify_res = notify_run_completed(brand_id, run_id, deliverable, period, delivered)

    return {
        "run_id": run_id,
        "status": "delivered",
        "stage": "completed",
        "delivered_files": delivered,
        "gate_status": gate_status,
        "notifications": notify_res,
    }


def list_runs(
    brand_id: Optional[str] = None,
    limit: int = 10,
    engine: Optional[Engine] = None,
) -> List[Dict[str, Any]]:
    """List recent pipeline execution runs."""
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        q = "SELECT run_id, brand_id, deliverable, period, status, stage, started_at, completed_at, error_message, row_counts FROM runs"
        p: Dict[str, Any] = {"limit": limit}
        if brand_id:
            q += " WHERE brand_id = :brand_id"
            p["brand_id"] = brand_id
        q += " ORDER BY started_at DESC LIMIT :limit"

        rows = conn.execute(text(q), p).mappings().fetchall()
        return [dict(r) for r in rows]
