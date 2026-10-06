from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
from ..store.db import get_engine


def compute_file_sha256(file_path: Path | str) -> str:
    """Compute SHA-256 hash of a file."""
    p = Path(file_path)
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_file_already_ingested(sha256: str, engine: Optional[Engine] = None) -> bool:
    """Check if this file SHA-256 hash was previously ingested in raw_files."""
    if engine is None:
        engine = get_engine()
    with engine.connect() as conn:
        res = conn.execute(
            text("SELECT file_id FROM raw_files WHERE sha256 = :sha256"),
            {"sha256": sha256}
        ).fetchone()
        return res is not None


def record_raw_file(
    source_id: str,
    run_id: str,
    file_path: Path | str,
    engine: Optional[Engine] = None
) -> Dict[str, str]:
    """
    Compute hash and record file in raw_files table.
    Returns file metadata dict.
    """
    if engine is None:
        engine = get_engine()

    p = Path(file_path)
    sha256 = compute_file_sha256(p)
    file_id = f"file_{uuid.uuid4().hex[:12]}"
    storage_ref = str(p.resolve())

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO raw_files (file_id, source_id, run_id, sha256, storage_ref, received_at)
                VALUES (:file_id, :source_id, :run_id, :sha256, :storage_ref, CURRENT_TIMESTAMP)
            """),
            {
                "file_id": file_id,
                "source_id": source_id,
                "run_id": run_id,
                "sha256": sha256,
                "storage_ref": storage_ref,
            }
        )

    return {
        "file_id": file_id,
        "source_id": source_id,
        "run_id": run_id,
        "sha256": sha256,
        "storage_ref": storage_ref,
    }


def find_inbox_files(base_dir: Path | str, brand_id: str, channel: str) -> List[Path]:
    """Locate incoming CSV files in the watched brand inbox folder."""
    inbox_dir = Path(base_dir) / brand_id / "inbox" / channel
    if not inbox_dir.exists():
        # Fallback to local simplified path inbox/<channel>/
        alt_dir = Path(base_dir) / "inbox" / channel
        if alt_dir.exists():
            inbox_dir = alt_dir
        else:
            return []
    return sorted(list(inbox_dir.glob("*.csv")), key=lambda p: p.stat().st_mtime, reverse=True)
