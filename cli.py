#!/usr/bin/env python3
"""
HOWL Platform CLI (`howl`)
Commands:
  howl validate --brand <brand_id>
  howl migrate
  howl run --brand <brand_id> --deliverable <deliverable> --period <YYYY-MM> [--input <file_path>]
  howl review-list --brand <brand_id>
  howl review-resolve --brand <brand_id> --item-id <id> --action <action> --val <key=val>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

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
from howlplatform.platform.orchestrator.pipeline import PipelineRun
from howlplatform.platform.review.queue import get_open_review_items, resolve_review_item
from howlplatform.deliverables.contract import list_generators, get_generator


def cmd_migrate(args: argparse.Namespace) -> int:
    """Run database migrations and verify schema."""
    print("=" * 60)
    print("HOWL Platform - Database Migration")
    print("=" * 60)
    engine = get_engine()
    print(f"Target Database Engine: {engine.dialect.name.upper()}")

    try:
        applied = run_migrations(engine)
        if applied:
            print(f"Applied migrations: {', '.join(applied)}")
        else:
            print("No new migrations to apply.")

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
    missing_gens = [d for d in declared_deliverables if get_generator(d) is None]

    if missing_gens:
        print(f"[FAIL] Unregistered deliverable generators: {', '.join(missing_gens)}")
        print(f"       Registered generators: {', '.join(list_generators())}")
        return 1
    print(f"[PASS] Deliverable generators verified: {', '.join(declared_deliverables)}")

    # 4. Validate sources against Canonical Schema registry
    sources = manifest.get("sources", [])
    invalid_schemas = [
        f"{s.get('source_id')}: {s.get('schema_ref')}"
        for s in sources if s.get("schema_ref") not in CANONICAL_SCHEMA_MAP
    ]

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
    """Run end-to-end reporting pipeline."""
    brand_id = args.brand
    deliverable = args.deliverable
    period = args.period
    input_file = getattr(args, "input", None)

    print("=" * 60)
    print(f"HOWL Pipeline Run: {brand_id} | {deliverable} | {period}")
    print("=" * 60)

    try:
        pipeline = PipelineRun(
            brand_id=brand_id,
            deliverable=deliverable,
            period=period,
            input_file=input_file,
        )
        result = pipeline.execute()

        print(f"Run ID: {result['run_id']}")
        print(f"Final Status: {result['status'].upper()}")

        if result['status'] == "awaiting_review":
            print("\n[WARNING] RUN PAUSED AT REVIEW GATE")
            print(result['message'])
            print(f"Open review items: {result['gate_status']['items_count']}")
            print("Use 'python cli.py review-list --brand " + brand_id + "' to review and resolve items.")
            return 2

        if result['status'] == "delivered":
            print(f"\n[SUCCESS] Deliverable generated and delivered:")
            for d in result.get('delivered_files', []):
                print(f"  - File: {d['file_name']}")
                print(f"    Location: {d['delivered_to']}")
            return 0

        return 0
    except Exception as e:
        print(f"\n[FAIL] Pipeline run failed: {e}")
        return 1


def cmd_review_list(args: argparse.Namespace) -> int:
    """List open review items for a brand ranked by impact."""
    brand_id = args.brand
    engine = get_engine()
    items = get_open_review_items(brand_id, engine)

    print("=" * 70)
    print(f"HOWL Review Queue: Brand '{brand_id}' ({len(items)} open items)")
    print("=" * 70)

    if not items:
        print("No open review items found. Everything is resolved!")
        return 0

    print(f"{'Item ID':<38} {'Impact':<8} {'Entity Key':<25} {'Reason'}")
    print("-" * 70)
    for it in items:
        print(f"{it['item_id']:<38} {it['impact']:<8.1f} {it['entity_key'][:23]:<25} {it['reason']}")
    return 0


def cmd_review_resolve(args: argparse.Namespace) -> int:
    """Resolve an open review item and write decision to the ledger."""
    item_id = args.item_id
    action = args.action
    val_str = args.val or "{}"
    decided_by = getattr(args, "by", "analyst@howl.internal")
    reason = getattr(args, "reason", "Analyst review")

    try:
        if "=" in val_str and not val_str.startswith("{"):
            k, v = val_str.split("=", 1)
            v_clean = True if v.lower() == "true" else (False if v.lower() == "false" else v)
            val = {k: v_clean}
        else:
            val = json.loads(val_str)
    except Exception as e:
        print(f"Invalid value JSON or format: {e}")
        return 1

    engine = get_engine()
    decision_id = resolve_review_item(
        item_id=item_id,
        action=action,
        value=val,
        decided_by=decided_by,
        reason=reason,
        engine=engine,
    )

    if decision_id:
        print(f"[SUCCESS] Item {item_id} resolved! Recorded decision_id: {decision_id}")
        return 0
    else:
        print(f"[FAIL] Review item {item_id} not found.")
        return 1


def cmd_review_sync(args: argparse.Namespace) -> int:
    """Alias for syncing/listing review queue."""
    return cmd_review_list(args)


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
    subparsers.add_parser("migrate", help="Run database migrations")

    # run
    run_parser = subparsers.add_parser("run", help="Run a report pipeline")
    run_parser.add_argument("--brand", required=True, help="Brand ID")
    run_parser.add_argument("--deliverable", required=True, help="Deliverable name (e.g. gsc_organic_report)")
    run_parser.add_argument("--period", required=True, help="Period (e.g. 2026-08)")
    run_parser.add_argument("--input", required=False, help="Path to input source file")

    # review-list
    review_list_parser = subparsers.add_parser("review-list", help="List open review items")
    review_list_parser.add_argument("--brand", required=True, help="Brand ID")

    # review-sync
    review_sync_parser = subparsers.add_parser("review-sync", help="Synchronize and list review queue")
    review_sync_parser.add_argument("--brand", required=True, help="Brand ID")

    # review-resolve
    resolve_parser = subparsers.add_parser("review-resolve", help="Resolve a review item")
    resolve_parser.add_argument("--item-id", required=True, help="Review item ID")
    resolve_parser.add_argument("--action", required=True, choices=["reclassify", "fix", "exclude", "ignore"])
    resolve_parser.add_argument("--val", default="{}", help="Decision value JSON or key=value")
    resolve_parser.add_argument("--by", default="analyst@howl.internal", help="Reviewer identity")
    resolve_parser.add_argument("--reason", default="", help="Reason for decision")

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
    elif args.command == "review-list":
        return cmd_review_list(args)
    elif args.command == "review-sync":
        return cmd_review_sync(args)
    elif args.command == "review-resolve":
        return cmd_review_resolve(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
