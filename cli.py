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
from howlplatform.platform.orchestrator.pipeline import PipelineRun, resume_run, list_runs
from howlplatform.platform.orchestrator.ops_summary import generate_ops_summary, format_ops_summary_text
from howlplatform.platform.delivery.notifications import send_slack_message, create_email_draft
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
    """Run or resume end-to-end reporting pipeline."""
    resume_id = getattr(args, "resume", None)

    if resume_id:
        print("=" * 60)
        print(f"HOWL Pipeline Resume: Run ID '{resume_id}'")
        print("=" * 60)
        try:
            result = resume_run(resume_id)
            if result["status"] == "awaiting_review":
                print("\n[WARNING] RESUME HALTED: REVIEW GATE STILL BLOCKED")
                print(result["message"])
                return 2

            print(f"\n[SUCCESS] Pipeline successfully resumed and delivered:")
            for d in result.get("delivered_files", []):
                print(f"  - File: {d['file_name']}")
                print(f"    Location: {d['delivered_to']}")
            return 0
        except Exception as e:
            print(f"\n[FAIL] Resume failed: {e}")
            return 1

    brand_id = args.brand
    deliverable = args.deliverable
    period = args.period
    input_file = getattr(args, "input", None)

    if not brand_id or not deliverable or not period:
        print("Error: --brand, --deliverable, and --period are required unless using --resume <run_id>.")
        return 1

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
            print(f"After resolving items, resume this run with: python cli.py run --resume {result['run_id']}")
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


def cmd_runs_list(args: argparse.Namespace) -> int:
    """List recent pipeline execution runs."""
    brand_id = getattr(args, "brand", None)
    limit = getattr(args, "limit", 10)
    runs = list_runs(brand_id=brand_id, limit=limit)

    print("=" * 75)
    print(f"HOWL Pipeline Runs History (Recent {len(runs)})")
    print("=" * 75)
    if not runs:
        print("No recorded runs found.")
        return 0

    print(f"{'Run ID':<18} {'Brand':<10} {'Deliverable':<24} {'Period':<8} {'Status':<12}")
    print("-" * 75)
    for r in runs:
        print(f"{r['run_id']:<18} {r['brand_id']:<10} {r['deliverable'][:22]:<24} {r['period']:<8} {r['status']:<12}")
    return 0


def cmd_ops_summary(args: argparse.Namespace) -> int:
    """Display daily operational summary."""
    brand_id = getattr(args, "brand", None)
    hours = getattr(args, "hours", 24)
    summary = generate_ops_summary(brand_id=brand_id, hours=hours)
    print(format_ops_summary_text(summary))
    return 0


def cmd_notify_test(args: argparse.Namespace) -> int:
    """Test notification channels (Slack, Email)."""
    channel = getattr(args, "channel", "slack").lower()
    print("=" * 60)
    print(f"HOWL Notification Channel Test: [{channel.upper()}]")
    print("=" * 60)

    if channel == "slack":
        res = send_slack_message(text="HOWL Platform automated test alert: Notification system active.", channel="#ops-test")
        print(f"[PASS] Slack message dispatched. Mock mode: {res['mock']}, ID: {res['id']}")
        return 0
    elif channel == "email":
        res = create_email_draft(
            brand_id="system",
            subject="HOWL Test Operational Alert",
            body_text="Test notification dispatch from HOWL CLI.",
        )
        print(f"[PASS] Email draft created successfully: {res['eml_path']}")
        return 0
    else:
        print(f"Unknown notification channel: {channel}. Choose 'slack' or 'email'.")
        return 1


def cmd_plan_ingest(args: argparse.Namespace) -> int:
    """Ingest and validate a media plan against naming conventions."""
    brand_id = args.brand
    file_path = args.file
    plan_id = getattr(args, "plan_id", "q3_plan") or "q3_plan"

    print("=" * 65)
    print(f"HOWL Media Plan Ingestion: '{brand_id}' (Plan: {plan_id})")
    print("=" * 65)

    manifest_path = CURRENT_DIR / "manifests" / f"{brand_id}.json"
    manifest = load_manifest(manifest_path)
    engine = get_engine()

    from howlplatform.platform.adapters.media_plan import MediaPlanAdapter
    adapter = MediaPlanAdapter(manifest, engine=engine)
    run_id = f"plan_ingest_{brand_id}"

    try:
        rows, stats = adapter.process_file(file_path, plan_id=plan_id, run_id=run_id)
        print(f"[SUCCESS] Media Plan Ingested:")
        print(f"  - Total Rows:           {stats['total_rows']}")
        print(f"  - Planned Spend (INR):  {stats['total_planned_spend']:,.2f}")
        print(f"  - Planned Impressions:  {stats['total_planned_impressions']:,}")
        print(f"  - Naming Violations:    {stats['naming_violations']}")
        if stats['naming_violations'] > 0:
            print(f"  [NOTE] Naming violations flagged in review queue. Run 'python cli.py review-list --brand {brand_id}' to inspect.")
        return 0
    except Exception as e:
        print(f"[FAIL] Ingestion failed: {e}")
        return 1


def cmd_plan_variance(args: argparse.Namespace) -> int:
    """Calculate and display Planned vs Actual media spend pacing."""
    brand_id = args.brand
    period = args.period
    plan_id = getattr(args, "plan_id", None)

    from howlplatform.platform.adapters.media_plan import calculate_planned_vs_actual
    res = calculate_planned_vs_actual(brand_id, period, plan_id=plan_id, engine=get_engine())

    print("=" * 80)
    print(f"HOWL Media Plan Variance & Pacing: '{brand_id}' ({period})")
    print("=" * 80)
    print(f"Planned Spend: INR {res['total_planned_spend']:,.2f} | Actual Spend: INR {res['total_actual_spend']:,.2f}")
    print(f"Variance:      INR {res['spend_variance']:,.2f} | Overall Pacing: {res['overall_pacing_pct']:.1f}%")
    print("-" * 80)
    print(f"{'Campaign':<36} {'Planned':<12} {'Actual':<12} {'Variance':<12} {'Pacing %'}")
    print("-" * 80)
    for c in res["campaigns"]:
        print(
            f"{c['campaign'][:34]:<36} "
            f"{c['planned_spend']:<12,.0f} "
            f"{c['actual_spend']:<12,.0f} "
            f"{c['spend_variance']:<12,.0f} "
            f"{c['spend_pacing_pct']:<6.1f}%"
        )
    return 0


def cmd_control_run(args: argparse.Namespace) -> int:
    """Execute triggered runs from a control sheet."""
    sheet_path = args.sheet
    print("=" * 65)
    print(f"HOWL Control Sheet Processor: {sheet_path}")
    print("=" * 65)

    from howlplatform.platform.orchestrator.control_sheet import run_control_sheet
    try:
        res = run_control_sheet(sheet_path, engine=get_engine())
        print(f"Total Rows:     {res['total_rows']}")
        print(f"Triggered Runs: {res['triggered_count']}")
        if res["runs"]:
            print("\nExecution Results:")
            for r in res["runs"]:
                err = f" (Error: {r['error']})" if r.get("error") else ""
                print(f"  * [{r['status']}] {r['brand_id']} - {r['deliverable']} ({r['period']}) ID: {r.get('run_id', 'N/A')}{err}")
        return 0
    except Exception as e:
        print(f"[FAIL] Control sheet run failed: {e}")
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


def cmd_review_export(args: argparse.Namespace) -> int:
    """Export review queue to CSV for Google Sheets sync."""
    brand_id = args.brand
    out_path = getattr(args, "out", None)
    from howlplatform.platform.review.sheet_sync import export_review_sheet
    saved_file = export_review_sheet(brand_id, out_path)
    print(f"[SUCCESS] Exported open review queue to: {saved_file}")
    return 0


def cmd_review_import(args: argparse.Namespace) -> int:
    """Import analyst decisions from CSV back into decision ledger."""
    brand_id = args.brand
    in_path = args.file
    decided_by = getattr(args, "by", "analyst@howl.internal")
    from howlplatform.platform.review.sheet_sync import import_review_sheet
    res = import_review_sheet(brand_id, in_path, decided_by=decided_by)
    print(f"[SUCCESS] Review sheet sync complete for '{brand_id}':")
    print(f"  - Resolved items: {res['resolved_count']}")
    print(f"  - Skipped items: {res['skipped_count']}")
    if res['errors']:
        print(f"  - Errors: {res['errors']}")
    return 0


def cmd_ledger_audit(args: argparse.Namespace) -> int:
    """View audit trail of decisions recorded in the decision ledger."""
    brand_id = args.brand
    key = getattr(args, "key", None)
    from howlplatform.platform.ledger.audit import get_brand_audit_trail, get_decision_history

    print("=" * 70)
    print(f"HOWL Decision Ledger Audit Trail: '{brand_id}'")
    print("=" * 70)

    if key:
        history = get_decision_history(brand_id, "query", key)
        if not history:
            print(f"No decisions recorded for key: '{key}'")
            return 0
        print(f"History for '{key}':")
        for h in history:
            print(f"  [{h['decided_at']}] Action: {h['decision']} | Value: {h['value']} | By: {h['decided_by']} | Reason: {h['reason']}")
    else:
        trail = get_brand_audit_trail(brand_id, limit=20)
        if not trail:
            print("No decisions recorded in ledger.")
            return 0
        for t in trail:
            print(f"  [{t['decided_at']}] {t['entity_key'][:25]:<26} -> {t['decision']:<10} | {t['value']} ({t['decided_by']})")
    return 0


def cmd_promote_rules(args: argparse.Namespace) -> int:
    """Promote recurring decisions into brand manifest rules."""
    brand_id = args.brand
    min_count = getattr(args, "min_count", 2)
    from howlplatform.platform.ledger.promotion import promote_decisions_to_manifest
    res = promote_decisions_to_manifest(brand_id, min_count=min_count)
    print("=" * 60)
    print(f"HOWL Rule Promotion: '{brand_id}' (Manifest v{res['new_version']})")
    print("=" * 60)
    print(f"Promoted regex rules: {len(res['promoted_rules'])}")
    for r in res['promoted_rules']:
        print(f"  - Pattern: {r['pattern']} -> {r['tag']}")
    print(f"Promoted misspellings: {len(res['promoted_misspellings'])}")
    for m in res['promoted_misspellings']:
        print(f"  - {m}")
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
    subparsers.add_parser("migrate", help="Run database migrations")

    # run
    run_parser = subparsers.add_parser("run", help="Run or resume a report pipeline")
    run_parser.add_argument("--brand", required=False, help="Brand ID")
    run_parser.add_argument("--deliverable", required=False, help="Deliverable name (e.g. gsc_organic_report)")
    run_parser.add_argument("--period", required=False, help="Period (e.g. 2026-08)")
    run_parser.add_argument("--input", required=False, help="Path to input source file")
    run_parser.add_argument("--resume", required=False, help="Run ID to resume from review gate")

    # runs-list
    runs_parser = subparsers.add_parser("runs-list", help="List recent pipeline execution runs")
    runs_parser.add_argument("--brand", required=False, help="Brand ID")
    runs_parser.add_argument("--limit", type=int, default=10, help="Max runs to display")

    # ops-summary
    ops_parser = subparsers.add_parser("ops-summary", help="Display daily operational summary")
    ops_parser.add_argument("--brand", required=False, help="Brand ID")
    ops_parser.add_argument("--hours", type=int, default=24, help="Window in hours")

    # notify-test
    notify_parser = subparsers.add_parser("notify-test", help="Test notification dispatch")
    notify_parser.add_argument("--channel", default="slack", choices=["slack", "email"], help="Channel to test")

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

    # review-export
    export_parser = subparsers.add_parser("review-export", help="Export review queue to CSV for Google Sheets")
    export_parser.add_argument("--brand", required=True, help="Brand ID")
    export_parser.add_argument("--out", required=False, help="Target export path")

    # review-import
    import_parser = subparsers.add_parser("review-import", help="Import analyst decisions from CSV/Sheet")
    import_parser.add_argument("--brand", required=True, help="Brand ID")
    import_parser.add_argument("--file", required=True, help="Path to completed review CSV")
    import_parser.add_argument("--by", default="analyst@howl.internal", help="Reviewer email")

    # ledger-audit
    audit_parser = subparsers.add_parser("ledger-audit", help="View decision ledger audit trail")
    audit_parser.add_argument("--brand", required=True, help="Brand ID")
    audit_parser.add_argument("--key", required=False, help="Specific entity key to inspect")

    # promote-rules
    promote_parser = subparsers.add_parser("promote-rules", help="Promote recurring decisions to manifest rules")
    promote_parser.add_argument("--brand", required=True, help="Brand ID")
    promote_parser.add_argument("--min-count", type=int, default=2, help="Minimum occurrences to promote")

    # plan-ingest
    plan_ingest_parser = subparsers.add_parser("plan-ingest", help="Ingest media plan and validate naming conventions")
    plan_ingest_parser.add_argument("--brand", required=True, help="Brand ID")
    plan_ingest_parser.add_argument("--file", required=True, help="Path to media plan CSV")
    plan_ingest_parser.add_argument("--plan-id", default="q3_plan", help="Media plan identifier")

    # plan-variance
    plan_var_parser = subparsers.add_parser("plan-variance", help="Calculate Planned vs Actual spend variance")
    plan_var_parser.add_argument("--brand", required=True, help="Brand ID")
    plan_var_parser.add_argument("--period", required=True, help="Period (e.g. 2026-08)")
    plan_var_parser.add_argument("--plan-id", required=False, help="Filter by plan ID")

    # control-run
    control_parser = subparsers.add_parser("control-run", help="Execute triggered runs from a control sheet")
    control_parser.add_argument("--sheet", required=True, help="Path to control sheet CSV")

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
    elif args.command == "runs-list":
        return cmd_runs_list(args)
    elif args.command == "ops-summary":
        return cmd_ops_summary(args)
    elif args.command == "notify-test":
        return cmd_notify_test(args)
    elif args.command == "review-list":
        return cmd_review_list(args)
    elif args.command == "review-sync":
        return cmd_review_sync(args)
    elif args.command == "review-resolve":
        return cmd_review_resolve(args)
    elif args.command == "review-export":
        return cmd_review_export(args)
    elif args.command == "review-import":
        return cmd_review_import(args)
    elif args.command == "ledger-audit":
        return cmd_ledger_audit(args)
    elif args.command == "promote-rules":
        return cmd_promote_rules(args)
    elif args.command == "plan-ingest":
        return cmd_plan_ingest(args)
    elif args.command == "plan-variance":
        return cmd_plan_variance(args)
    elif args.command == "control-run":
        return cmd_control_run(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
