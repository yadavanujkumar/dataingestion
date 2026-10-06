from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine

from howlplatform.platform.ingest.drive import (
    compute_file_sha256,
    is_file_already_ingested,
    record_raw_file,
)
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "gsc_ampere_2026_08.csv"


def test_compute_sha256():
    sha = compute_file_sha256(SAMPLE_CSV)
    assert len(sha) == 64
    assert isinstance(sha, str)


def test_record_and_deduplicate_raw_file():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    sha = compute_file_sha256(SAMPLE_CSV)
    assert not is_file_already_ingested(sha, engine)

    record = record_raw_file("ampere-gsc", "test_run_1", SAMPLE_CSV, engine)
    assert record["sha256"] == sha
    assert is_file_already_ingested(sha, engine)
