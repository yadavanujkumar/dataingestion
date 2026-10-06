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
from ..ingest.drive import is_file_already_ingested, record_raw_file
from ..manifest.loader import load_manifest
from ..review.queue import evaluate_review_gate
from ..store.db import get_engine, run_migrations, all_required_tables_exist
from ..store.sync import sync_brand_manifest
from ...deliverables.contract import get_generator


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

    def _update_run_status(self, status: str, stage: str, row_counts: Optional[Dict[str, Any]] = None, error_message: Optional[str] = None):
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
                }
            )

    def execute(self) -> Dict[str, Any]:
        """
        Execute the pipeline stages in order:
        trigger -> ingest -> normalize -> classify -> review -> generate -> deliver
        """
        # Stage 0: Trigger
        self._update_run_status("pending", "trigger")

        gen_cls = get_generator(self.deliverable)
        if not gen_cls:
            err = f"Generator for '{self.deliverable}' is not registered."
            self._update_run_status("failed", "trigger", error_message=err)
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

        # Stage 4: Review Gate
        self._update_run_status("classifying", "review_gate")
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
            return {
                "run_id": self.run_id,
                "status": "awaiting_review",
                "stage": "review_gate",
                "message": msg,
                "gate_status": gate_status,
                "stats": combined_stats,
            }

        # Stage 5: Generate
        self._update_run_status("generating", "generate")
        temp_out = Path.cwd() / "outputs" / "temp"
        generated_files = generator.build(
            brand=self.manifest,
            period=self.period,
            data=canonical_data,
            out_dir=temp_out,
        )

        # Stage 6: Deliver
        self._update_run_status("delivering", "deliver")
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

        return {
            "run_id": self.run_id,
            "status": "delivered",
            "stage": "completed",
            "stats": combined_stats,
            "delivered_files": delivered,
            "gate_status": gate_status,
        }
