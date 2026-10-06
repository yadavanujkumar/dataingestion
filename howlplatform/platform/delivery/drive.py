from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
from ..store.db import get_engine


def deliver_report_files(
    run_id: str,
    brand_id: str,
    deliverable: str,
    period: str,
    generator_version: str,
    generated_files: List[str],
    base_output_dir: Optional[str | Path] = None,
    engine: Optional[Engine] = None,
) -> List[Dict[str, str]]:
    """
    Deliver generated report files to target directory:
    outputs/<Brand>/<deliverable>/<period>/
    and record them in the 'outputs' platform table.
    """
    if engine is None:
        engine = get_engine()

    base_dir = Path(base_output_dir or Path.cwd() / "outputs")
    target_dir = base_dir / brand_id.capitalize() / deliverable / period
    target_dir.mkdir(parents=True, exist_ok=True)

    delivered_records = []

    for src_file in generated_files:
        src_path = Path(src_file)
        dest_path = target_dir / src_path.name

        if src_path.resolve() != dest_path.resolve():
            shutil.copy2(src_path, dest_path)

        output_id = str(uuid.uuid4())
        delivered_to = str(dest_path.resolve())

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO outputs (
                        output_id, run_id, generator, generator_version, file_ref, delivered_to, created_at
                    ) VALUES (
                        :output_id, :run_id, :generator, :generator_version, :file_ref, :delivered_to, CURRENT_TIMESTAMP
                    )
                """),
                {
                    "output_id": output_id,
                    "run_id": run_id,
                    "generator": deliverable,
                    "generator_version": generator_version,
                    "file_ref": str(src_path.resolve()),
                    "delivered_to": delivered_to,
                }
            )

        delivered_records.append({
            "output_id": output_id,
            "file_name": dest_path.name,
            "delivered_to": delivered_to,
        })

    return delivered_records
