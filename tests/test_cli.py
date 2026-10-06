from __future__ import annotations

import argparse
from pathlib import Path
import pytest

from cli import (
    cmd_validate,
    cmd_migrate,
    cmd_run,
    cmd_review_list,
    cmd_review_sync,
    cmd_review_resolve,
)

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "gsc_ampere_2026_08.csv"


def test_cli_validate_ampere():
    args = argparse.Namespace(brand="ampere")
    exit_code = cmd_validate(args)
    assert exit_code == 0


def test_cli_validate_missing_brand():
    args = argparse.Namespace(brand="non_existent_brand_123")
    exit_code = cmd_validate(args)
    assert exit_code == 1


def test_cli_migrate():
    args = argparse.Namespace()
    exit_code = cmd_migrate(args)
    assert exit_code == 0


def test_cli_run_and_review_workflow():
    # 1. Run pipeline
    run_args = argparse.Namespace(
        brand="ampere",
        deliverable="gsc_organic_report",
        period="2026-08",
        input=str(SAMPLE_CSV),
    )
    exit_code = cmd_run(run_args)
    assert exit_code == 0

    # 2. List review queue
    review_args = argparse.Namespace(brand="ampere")
    assert cmd_review_list(review_args) == 0
    assert cmd_review_sync(review_args) == 0
