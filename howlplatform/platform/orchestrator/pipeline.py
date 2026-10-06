from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..adapters.gsc_csv import GSCCSVAdapter
from ..canonical.schemas import SearchRowV1
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

        # Ensure database tables exist
        if not all_required_tables_exist(self.engine):
            run_migrations(self.engine)

        # Load brand manifest
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

        # Stage 1: Ingest
        self._update_run_status("ingesting", "ingest")
        if not self.input_file or not self.input_file.is_file():
            # Check default inbox fixture
            default_fixture = Path.cwd() / "tests" / "fixtures" / f"gsc_{self.brand_id}_{self.period.replace('-', '_')}.csv"
            if default_fixture.is_file():
                self.input_file = default_fixture
            else:
                err = f"No input file provided or found for brand '{self.brand_id}'"
                self._update_run_status("failed", "ingest", error_message=err)
                raise FileNotFoundError(err)

        file_meta = record_raw_file(
            source_id=f"{self.brand_id}-gsc",
            run_id=self.run_id,
            file_path=self.input_file,
            engine=self.engine,
        )

        # Stage 2 & 3: Normalize & Classify
        self._update_run_status("normalizing", "normalize")
        adapter = GSCCSVAdapter(
            brand_manifest=self.manifest,
            source_id=f"{self.brand_id}-gsc",
            engine=self.engine,
        )
        canonical_rows, stats = adapter.process_file(
            file_path=self.input_file,
            period=self.period,
            run_id=self.run_id,
        )

        # Stage 4: Review Gate
        self._update_run_status("classifying", "review_gate")
        review_block = self.manifest.get("review", {})
        blocking_share = review_block.get("blocking_share", 0.02)
        total_impact = float(stats.get("total_clicks", 0))

        gate_status = evaluate_review_gate(
            brand_id=self.brand_id,
            total_impact=total_impact,
            blocking_share=blocking_share,
            engine=self.engine,
        )

        if gate_status["blocked"]:
            msg = (
                f"Run paused: Review gate blocked. "
                f"Unresolved items account for {gate_status['unresolved_share']*100:.2f}% of clicks "
                f"(threshold: {blocking_share*100:.2f}%)."
            )
            self._update_run_status("awaiting_review", "review_gate", row_counts=stats, error_message=msg)
            return {
                "run_id": self.run_id,
                "status": "awaiting_review",
                "stage": "review_gate",
                "message": msg,
                "gate_status": gate_status,
                "stats": stats,
            }

        # Stage 5: Generate
        self._update_run_status("generating", "generate")
        gen_cls = get_generator(self.deliverable)
        if not gen_cls:
            err = f"Generator for '{self.deliverable}' is not registered."
            self._update_run_status("failed", "generate", error_message=err)
            raise ValueError(err)

        generator = gen_cls()
        temp_out = Path.cwd() / "outputs" / "temp"
        generated_files = generator.build(
            brand=self.manifest,
            period=self.period,
            data={"search": canonical_rows},
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

        self._update_run_status("delivered", "delivered", row_counts=stats)

        return {
            "run_id": self.run_id,
            "status": "delivered",
            "stage": "completed",
            "stats": stats,
            "delivered_files": delivered,
            "gate_status": gate_status,
        }
