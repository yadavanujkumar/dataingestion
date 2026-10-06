#!/usr/bin/env python3
"""
HOWL Platform CLI (`howl`)
Commands:
  howl validate --brand <brand_id>
  howl migrate
  howl run --brand <brand_id> --deliverable <deliverable> --period <YYYY-MM>
  howl review-sync --brand <brand_id>
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure howlplatform is in path
CURRENT_DIR = Path(__file__).parent.resolve()
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from howlplatform.platform.manifest.loader import load_manifest, ManifestValidationError
from howlplatform.platform.canonical.schemas import CANONICAL_SCHEMA_MAP
from howlplatform.platform.store.db import (
    get_engine,
    run_migrations,
    check_tables_exist,
    all_required_tables_exist,
    REQUIRED_TABLES,
)
from howlplatform.platform.store.sync import sync_brand_manifest
from howlplatform.deliverables.contract import list_generators, get_generator


def cmd_migrate(args: argparse.Namespace) -> int:
    """Run database migrations and verify schema."""
    print("=" * 60)
    print("HOWL Platform - Database Migration")
    print("=" * 60)
    engine = get_engine()
    db_type = engine.dialect.name
    print(f"Target Database Engine: {db_type.upper()}")

    try:
        applied = run_migrations(engine)
        if applied:
            print(f"Applied migrations: {', '.join(applied)}")
        else:
            print("No new migrations to apply.")

        # Check required tables
        table_status = check_tables_exist(engine)
        missing = [tbl for tbl, exists in table_status.items() if not exists]
        if missing:
            print(f"Error: Missing required tables: {', '.join(missing)}")
            return 1
        
        print(f"All {len(REQUIRED_TABLES)} required platform tables verified successfully.")
        return 0
    except Exception as e:
        print(f"Migration failed: {e}")
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a brand manifest and ensure platform readiness."""
    brand_id = args.brand
    print("=" * 60)
    print(f"HOWL Platform - Brand Validation: '{brand_id}'")
    print("=" * 60)

    # 1. Check manifest file existence
    manifest_path = CURRENT_DIR / "manifests" / f"{brand_id}.json"
    if not manifest_path.is_file():
        print(f"[FAIL] Manifest file not found: {manifest_path}")
        return 1
    print(f"[PASS] Found manifest file at {manifest_path.name}")

    # 2. Validate against Manifest JSON Schema
    try:
        manifest = load_manifest(manifest_path)
        print(f"[PASS] JSON Schema validation passed (version {manifest.get('manifest_version')})")
    except ManifestValidationError as e:
        print(f"[FAIL] Manifest validation error:\n{e}")
        return 1
    except Exception as e:
        print(f"[FAIL] Unexpected error reading manifest: {e}")
        return 1

    # 3. Validate deliverables against Generator Registry
    declared_deliverables = manifest.get("deliverables", [])
    registered = list_generators()
    missing_gens = []
    for d in declared_deliverables:
        if get_generator(d) is None:
            missing_gens.append(d)

    if missing_gens:
        print(f"[FAIL] Unregistered deliverable generators: {', '.join(missing_gens)}")
        print(f"       Registered generators: {', '.join(registered)}")
        return 1
    print(f"[PASS] Deliverable generators verified: {', '.join(declared_deliverables)}")

    # 4. Validate sources against Canonical Schema registry
    sources = manifest.get("sources", [])
    invalid_schemas = []
    for s in sources:
        schema_ref = s.get("schema_ref")
        if schema_ref not in CANONICAL_SCHEMA_MAP:
            invalid_schemas.append(f"{s.get('source_id')}: {schema_ref}")

    if invalid_schemas:
        print(f"[FAIL] Unknown schema_ref in sources: {', '.join(invalid_schemas)}")
        print(f"       Available canonical schemas: {', '.join(CANONICAL_SCHEMA_MAP.keys())}")
        return 1
    print(f"[PASS] All {len(sources)} sources map to valid canonical schemas")

    # 5. Check and initialize Database Store
    engine = get_engine()
    print(f"[INFO] Checking database connection ({engine.dialect.name})...")
    try:
        if not all_required_tables_exist(engine):
            print("[INFO] Missing tables detected. Running initial migrations...")
            run_migrations(engine)

        table_status = check_tables_exist(engine)
        missing_tables = [tbl for tbl, exists in table_status.items() if not exists]
        if missing_tables:
            print(f"[FAIL] Required database tables missing: {', '.join(missing_tables)}")
            return 1
        print(f"[PASS] Database verified ({len(REQUIRED_TABLES)} required tables present)")

        # Sync manifest to database
        sync_brand_manifest(manifest, engine)
        print(f"[PASS] Manifest synchronized into 'brands' and 'sources' tables")
    except Exception as e:
        print(f"[FAIL] Database verification/sync error: {e}")
        return 1

    print("=" * 60)
    print(f"SUCCESS: Brand '{brand_id}' is valid and ready on the HOWL Platform.")
    print("=" * 60)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Trigger a report run (stubbed state machine for Phase 0)."""
    brand_id = args.brand
    deliverable = args.deliverable
    period = args.period
    print(f"Initiating run for brand='{brand_id}', deliverable='{deliverable}', period='{period}'...")
    print("Status: pending -> ingesting")
    print(f"[INFO] Run registered for {brand_id} - {deliverable} ({period}). (Stage: Phase 0 foundation ready).")
    return 0


def cmd_review_sync(args: argparse.Namespace) -> int:
    """Sync review queue with Google Sheet (Phase 1/3 feature)."""
    brand_id = args.brand
    print(f"[INFO] Review sync triggered for brand='{brand_id}'.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="howl",
        description="HOWL Platform - Automated Multi-Source Ingestion & Reporting Engine"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # validate
    validate_parser = subparsers.add_parser("validate", help="Validate a brand manifest and store readiness")
    validate_parser.add_argument("--brand", required=True, help="Brand ID (e.g. ampere)")

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")

    # run
    run_parser = subparsers.add_parser("run", help="Run a report pipeline")
    run_parser.add_argument("--brand", required=True, help="Brand ID")
    run_parser.add_argument("--deliverable", required=True, help="Deliverable name (e.g. gsc_organic_report)")
    run_parser.add_argument("--period", required=True, help="Period (e.g. 2026-08)")

    # review-sync
    review_parser = subparsers.add_parser("review-sync", help="Synchronize review queue")
    review_parser.add_argument("--brand", required=True, help="Brand ID")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "validate":
        return cmd_validate(args)
    elif args.command == "migrate":
        return cmd_migrate(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "review-sync":
        return cmd_review_sync(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
