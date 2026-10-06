from __future__ import annotations

import argparse
from pathlib import Path
import pytest

from cli import cmd_validate, cmd_migrate, cmd_run, cmd_review_sync

REPO_ROOT = Path(__file__).parent.parent


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


def test_cli_run_stub():
    args = argparse.Namespace(brand="ampere", deliverable="gsc_organic_report", period="2026-08")
    exit_code = cmd_run(args)
    assert exit_code == 0
