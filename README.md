# HOWL Platform

Automated Multi-Source Marketing Data Ingestion & Reporting Engine.

> **Core Principle**: *A report is not built, it is projected.*  
> All of a brand's data is collected, cleaned, and stored once in a standard canonical shape. Each report is a specific view of that store, rendered in the brand's style. Adding a new report means registering one new generator without re-collecting or re-cleaning data.

---

## 1. System Architecture

The platform enforces a strict separation between the **Platform Core** (which knows nothing about specific reports) and the **Deliverable Layer** (which knows everything about one specific report).

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │                            DATA SOURCES                                │
   │   Windsor.ai REST API  │  Drive CSV Drop  │  CRM Feeds  │  Legacy CSV  │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                           STAGE 1: INGEST                              │
   │  drive.py / windsor.py  │  SHA-256 Hashing  │  raw_files deduplication │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                          STAGE 2: NORMALIZE                            │
   │  Adapters (gsc_csv, etc.) ──> Canonical Schemas (search_v1, paid_v2)   │
   │  Composite Key Upserts  ──> Unplaceable rows flagged for review        │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                          STAGE 3: CLASSIFY                             │
   │  Precedence 1: Decision Ledger Lookup (exact, remembered decisions)    │
   │  Precedence 2: Brand Manifest Rules (variants, misspellings, roster)   │
   │  Precedence 3: Claude AI Top-Up / Review Queue Fallback                │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                        STAGE 4: REVIEW GATE                            │
   │  Impact-ranked review queue (by clicks/spend). If unresolved items     │
   │  exceed brand blocking threshold (e.g. > 2%), pipeline pauses.         │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                         STAGE 5: GENERATE                              │
   │  Report Generators (openpyxl / python-pptx) reading canonical rows.    │
   │  Data Quality Checks (CTR <= 100%, vs medians) & Brand Styling.        │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                         STAGE 6: DELIVER                               │
   │  outputs/<Brand>/<deliverable>/<period>/  │  Lineage Audit in `outputs`│
   │  Draft creation only — never auto-sent to clients without human review │
   └────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Phased Build Status

| Phase | Focus | Status | Exit Test Criteria |
| :--- | :--- | :---: | :--- |
| **Phase 0** | **Foundations** | **Completed** | `howl validate --brand ampere` passes; all 14 tables verified in database. |
| **Phase 1** | **First Report End-to-End** | **Completed** | One command turns GSC CSV into an Ampere Excel report. Re-running produces zero new review items and an identical output file. |
| **Phase 2** | **Live Data & Second Report** | *Next* | Windsor API puller, paid social & engagement rate reports with zero core changes. |
| **Phase 3** | **Shared Review Services** | *Planned* | Two-way Google Sheet review queue sync and automatic promotion to manifest rules. |
| **Phase 4** | **Orchestration & Delivery** | *Planned* | Scheduled execution, Gmail drafts, Slack reviewer DMs, and error alerts. |
| **Phase 5** | **Self-Serve & Media Plans** | *Planned* | Control Sheet execution buttons and media plan naming convention enforcement. |

---

## 3. Repository Structure

```
dataingestion/
├── howlplatform/
│   ├── platform/                       # Core platform layer (no report logic)
│   │   ├── manifest/                   # JSON Schema, loader, semantic validator
│   │   │   ├── manifest.schema.json
│   │   │   └── loader.py
│   │   ├── store/                      # Database engine & SQL migrations
│   │   │   ├── migrations/
│   │   │   │   └── 001_initial_schema.sql
│   │   │   ├── db.py                   # SQLAlchemy (PostgreSQL / SQLite fallback)
│   │   │   └── sync.py                 # Manifest-to-database synchronization
│   │   ├── canonical/                  # Canonical schema dataclasses & keys
│   │   │   └── schemas.py              # search_v1, paid_v2, organic_v1, web_v1, crm_v1, plan_v1
│   │   ├── ingest/                     # File ingestion & SHA-256 deduplication
│   │   │   └── drive.py
│   │   ├── adapters/                   # Raw-to-canonical adapters
│   │   │   └── gsc_csv.py              # GSC CSV adapter with composite upserts
│   │   ├── classifier/                 # 3-tier classification engine
│   │   │   └── classifier.py           # Ledger -> Manifest Rules -> AI/Review
│   │   ├── ledger/                     # Append-only permanent decision ledger
│   │   │   └── ledger.py
│   │   ├── review/                     # Impact-scored review queue & gate check
│   │   │   └── queue.py
│   │   ├── orchestrator/               # Pipeline execution state machine
│   │   │   └── pipeline.py
│   │   └── delivery/                   # File delivery and output lineage
│   │       └── drive.py
│   └── deliverables/                   # Deliverable report layer (generators)
│       ├── contract.py                 # GeneratorSpec, Requirement, Registry
│       ├── gsc_organic_report/         # GSC Organic Search Report (xlsx)
│       │   └── generator.py
│       ├── paid_social_report/         # Paid Social Report generator
│       │   └── generator.py
│       └── engagement_rate_report/     # Multi-channel Engagement Rate generator
│           └── generator.py
├── manifests/
│   └── ampere.json                     # Validated Ampere Brand Manifest
├── outputs/                            # Delivered client-ready reports
│   └── Ampere/
│       └── gsc_organic_report/
│           └── 2026-08/
│               └── ampere_organic_search_report_2026-08.xlsx
├── tests/
│   ├── fixtures/                       # Real test source files (gsc_ampere_2026_08.csv)
│   ├── golden/                         # Expected golden deliverables for regression
│   ├── test_manifest.py
│   ├── test_store.py
│   ├── test_canonical.py
│   ├── test_generator_contract.py
│   ├── test_ingest.py
│   ├── test_classifier.py
│   ├── test_adapter_gsc.py
│   ├── test_review_queue.py
│   ├── test_golden.py
│   ├── test_pipeline_e2e.py
│   └── test_cli.py
├── cli.py                              # Unified CLI interface (`howl`)
├── pyproject.toml                      # Project metadata and dependencies
└── README.md
```

---

## 4. CLI Usage Guide

The unified CLI provides commands for validation, migrations, running report pipelines, and resolving review items.

### 1. Validate Brand Setup
Validates manifest schema, deliverable registries, canonical mapping, and database tables:
```bash
python cli.py validate --brand ampere
```

### 2. Run Database Migrations
Applies SQL migrations creating all 14 required platform and canonical tables:
```bash
python cli.py migrate
```

### 3. Run Report Pipeline (End-to-End)
Runs the complete 7-stage pipeline for a brand, deliverable, and period:
```bash
python cli.py run --brand ampere --deliverable gsc_organic_report --period 2026-08 --input tests/fixtures/gsc_ampere_2026_08.csv
```

### 4. Review Queue Operations
List open review items ranked by impact (e.g. clicks):
```bash
python cli.py review-list --brand ampere
```

Resolve an open review item and commit the decision to the decision ledger:
```bash
python cli.py review-resolve \
  --item-id <ITEM-UUID> \
  --action reclassify \
  --val generic_theme=dealership \
  --reason "Near me search signifies dealership intent"
```
*Note: Any item resolved in the ledger is immediately and permanently remembered on future runs.*

---

## 5. Report Deliverable: GSC Organic Search (`.xlsx`)

The generated workbook for Ampere includes 4 custom-styled worksheets adhering to the brand palette (`#1C2321`, `#4E8C2B`, Arial):
1. **Summary**: Overall KPIs (Total Queries, Impressions, Clicks, Overall CTR, Avg Position) and Branded vs. Non-Branded performance breakdown.
2. **Product Breakdown**: Volume, clicks, CTR, and click share grouped by product roster (e.g., *Magnus G Max*, *Reo Vyb*, *Nexus*, *Magnus Neo*).
3. **Top Queries**: Query-level detail with rank, metrics, branded flag, product attribution, theme, and classification lineage source (`rule`, `ledger`, `ai`).
4. **Notes**: Methodological notes, calculation lineage, generator version, and audit metadata.

---

## 6. Running Tests

The test suite runs with `pytest` and validates every component without external credentials:
```bash
python -m pytest -v
```

**Test Coverage Summary (27 passing tests)**:
- Manifest syntax and semantic validation.
- Database schema migration, table verification, and manifest synchronization.
- Canonical schema definitions and composite deduplication keys.
- Generator contract requirements and dynamic auto-registration.
- File hashing and SHA-256 deduplication.
- 3-tier classification hierarchy, sensitive word context matching, and ledger overrides.
- GSC CSV parsing, validation, and database upsert idempotency.
- Review queue impact scoring, gate evaluation, and resolution recording.
- End-to-end pipeline execution and golden file structure verification.
