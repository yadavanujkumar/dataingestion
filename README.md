# HOWL Platform

Automated Multi-Source Marketing Data Ingestion & Reporting Engine.

> **Core Principle**: *A report is not built, it is projected.*  
> All of a brand's data is collected, cleaned, and stored once in a standard canonical shape. Each report is a specific view of that store, rendered in the brand's style. Adding a new report means registering one new generator without re-collecting or re-cleaning data.

---

## Table of Contents
1. [System Architecture](#1-system-architecture)
2. [Codebase & Folder Structure](#2-codebase--folder-structure)
3. [Transitioning from Fixtures to Live Production Data](#3-transitioning-from-fixtures-to-live-production-data)
4. [Step-by-Step Execution Guide](#4-step-by-step-execution-guide)
5. [Deliverable Reports & Methodology](#5-deliverable-reports--methodology)
6. [Shared Review Services & Decision Ledger](#6-shared-review-services--decision-ledger)
7. [Self-Serve Control Sheets & Media Planning](#7-self-serve-control-sheets--media-planning)
8. [CLI Reference](#8-cli-reference)
9. [Automated Test Suite](#9-automated-test-suite)

---

## 1. System Architecture

The platform enforces strict two-layer decoupling:
- **Platform Core**: Ingests, normalizes, deduplicates, classifies, and stores canonical data. The core knows nothing about report designs, layout, or client presentation.
- **Deliverable Layer**: Reads canonical rows on demand, applies deliverable business logic, and renders client-ready styled assets (`.xlsx`, `.pptx`).

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
   │  Lookback revision windows (Meta 28d, GAds 14d, LinkedIn 14d, GSC 3d)  │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                          STAGE 2: NORMALIZE                            │
   │  Adapters (gsc_csv, meta_ads, organic_social, media_plan)              │
   │  Canonical Schemas (search_v1, paid_v2, organic_v1, plan_v1, etc.)     │
   │  Composite Key Upserts  ──> Unplaceable rows flagged for review        │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                          STAGE 3: CLASSIFY                             │
   │  Precedence 1: Decision Ledger Lookup (exact, remembered decisions)    │
   │  Precedence 2: Brand Manifest Rules (variants, misspellings, roster)   │
   │  Precedence 3: Claude AI Top-Up / Review Queue Fallback                │
   │  Sensitive variant filtering (real words 'amber'/'empire' need EV term)│
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                        STAGE 4: REVIEW GATE                            │
   │  Impact-ranked review queue (by clicks/spend/engagements). If          │
   │  unresolved items exceed blocking threshold (e.g. > 2%), run pauses.   │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                         STAGE 5: GENERATE                              │
   │  Report Generators (openpyxl / python-pptx) reading canonical store.   │
   │  Data Quality Checks & Brand Styling (Ampere: #1C2321, #4E8C2B, Arial) │
   │  Enforces ratio-of-sums (sum of engagements / sum of impressions)      │
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

## 2. Codebase & Folder Structure

```
dataingestion/
├── manifests/
│   └── ampere.json                     # Brand manifest (identity, roster, regex rules, thresholds)
├── manifests/schema/
│   └── manifest.schema.json            # JSON Schema Draft 2020-12 validating all manifests
│
├── howlplatform/
│   ├── deliverables/                   # DELIVERABLE LAYER (Isolated from platform core)
│   │   ├── __init__.py
│   │   ├── contract.py                 # GeneratorSpec, Requirement, registry decorator
│   │   ├── gsc_organic_report/         # GSC Organic Search Excel generator
│   │   │   ├── __init__.py
│   │   │   └── generator.py
│   │   ├── paid_social_report/         # Paid Social Excel generator
│   │   │   ├── __init__.py
│   │   │   └── generator.py
│   │   └── engagement_rate_report/     # Multi-Channel Engagement Rate generator (Doc 06)
│   │       ├── __init__.py
│   │       └── generator.py
│   │
│   └── platform/                       # PLATFORM CORE (Namespaced under howlplatform)
│       ├── manifest/
│       │   ├── __init__.py
│       │   └── loader.py               # Manifest loader and semantic validator
│       ├── store/
│       │   ├── __init__.py
│       │   ├── db.py                   # SQLAlchemy engine manager (Postgres + SQLite fallback)
│       │   ├── sync.py                 # Brand manifest store synchronizer
│       │   └── migrations/
│       │       └── 001_initial_schema.sql # DDL for all 14 platform tables
│       ├── canonical/
│       │   ├── __init__.py
│       │   └── schemas.py              # Canonical dataclasses (search_v1, paid_v2, organic_v1, plan_v1)
│       ├── ingest/
│       │   ├── __init__.py
│       │   ├── drive.py                # File hashing (SHA-256) & deduplication
│       │   ├── windsor.py              # Windsor.ai puller with lookback revision windows
│       │   └── legacy.py               # Historical report importer & outlier cell flagging
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── gsc_csv.py              # GSC CSV -> canonical_search
│       │   ├── meta_ads.py             # Meta Ads -> canonical_paid
│       │   ├── organic_social.py       # Instagram/FB/YouTube/LinkedIn -> canonical_organic
│       │   └── media_plan.py           # Media Plan -> canonical_plan & naming convention checker
│       ├── classifier/
│       │   ├── __init__.py
│       │   └── classifier.py           # 3-tier hierarchy & sensitive word disambiguation
│       ├── ledger/
│       │   ├── __init__.py
│       │   ├── ledger.py               # Append-only decision ledger writer & resolver
│       │   ├── audit.py                # Supersession history & audit trails
│       │   └── promotion.py            # Recurring decision pattern discovery & rule promotion
│       ├── review/
│       │   ├── __init__.py
│       │   ├── queue.py                # Review queue item creator & review gate evaluator
│       │   ├── impact.py               # Domain impact scoring engine (clicks, spend, engagements)
│       │   └── sheet_sync.py           # Bidirectional Google Sheet / CSV review sync
│       ├── orchestrator/
│       │   ├── __init__.py
│       │   ├── pipeline.py             # 7-stage run state machine, pause, and resume_run
│       │   ├── ops_summary.py          # Daily operational dashboard & health status generator
│       │   └── control_sheet.py        # Self-serve control sheet batch executor
│       └── delivery/
│           ├── __init__.py
│           ├── drive.py                # Output directory management & DB lineage tracking
│           └── notifications.py        # Slack alerts & RFC 822 email draft generator
│
├── tests/                              # AUTOMATED TEST SUITE (51 passing tests)
│   ├── fixtures/                       # Test CSVs and fixtures
│   ├── golden/                         # Golden master Excel workbooks for regression testing
│   ├── test_manifest.py
│   ├── test_store.py
│   ├── test_canonical.py
│   ├── test_ingest.py
│   ├── test_windsor.py
│   ├── test_classifier.py
│   ├── test_review_queue.py
│   ├── test_impact.py
│   ├── test_audit.py
│   ├── test_promotion.py
│   ├── test_sheet_sync.py
│   ├── test_resume_run.py
│   ├── test_notifications.py
│   ├── test_ops_summary.py
│   ├── test_media_plan.py
│   ├── test_control_sheet.py
│   ├── test_adapter_gsc.py
│   ├── test_adapter_meta.py
│   ├── test_adapter_organic.py
│   ├── test_generator_contract.py
│   ├── test_paid_social_report.py
│   ├── test_engagement_rate_report.py
│   ├── test_pipeline_e2e.py
│   └── test_cli.py
│
├── cli.py                              # Unified CLI (`howl`)
├── pyproject.toml                      # Package metadata and dependencies
└── README.md                           # Documentation
```

---

## 3. Transitioning from Fixtures to Live Production Data

In development and CI, the platform operates offline with SQLite (`howl.db`) and fallback fixtures (`tests/fixtures/`). To switch to **live production data**, the following configuration changes and integrations are required:

### 1. Database Backend (`DATABASE_URL`)
- **Current Development Default**: Local SQLite database file (`howl.db`) created automatically.
- **Production Requirement**: A managed PostgreSQL database (Supabase, AWS RDS, GCP Cloud SQL).
- **Configuration**:
  ```bash
  # In .env or production environment
  DATABASE_URL=postgresql://postgres:[PASSWORD]@[HOST]:[PORT]/[DATABASE_NAME]?sslmode=require
  ```
- **Apply migrations**: Run `python cli.py migrate` once connected. All 14 PostgreSQL tables with indexes and JSONB constraints will be created.

### 2. Windsor.ai API Key & Connectors (`WINDSOR_API_KEY`)
- **Current Development Default**: Falls back to fixture files when Windsor API credentials are not set.
- **Production Requirement**: 
  1. Obtain a Windsor.ai API Key from the Windsor.ai console.
  2. Set the environment variable:
     ```bash
     WINDSOR_API_KEY=your_production_windsor_api_key_here
     ```
  3. Authorize the live connectors in Windsor.ai:
     - Google Search Console (GSC)
     - Meta Ads (Facebook & Instagram Ads)
     - Google Ads
     - LinkedIn Campaign Manager
     - Organic Social (Instagram Graph API, YouTube Analytics)
  4. In `manifests/<brand>.json`, verify that the `sources` array entries correspond to your connected accounts:
     ```json
     {
       "source_id": "ampere-meta-ads",
       "channel": "meta_ads",
       "domain": "paid",
       "mode": "api",
       "schema_ref": "paid_v2"
     }
     ```

### 3. Windsor Revision Lookback Automation
Data from platforms like Meta Ads and Google Ads changes retroactively due to conversion attribution windows. In production, configure an automated daily runner with the platform's standard lookback windows:
- **Meta Ads**: 28-day lookback window (`howlplatform/platform/ingest/windsor.py`)
- **Google Ads**: 14-day lookback window
- **LinkedIn**: 14-day lookback window
- **Google Search Console**: 3-day lookback window

### 4. Google Drive Automatic Ingestion
- **Current Development Default**: Local file paths provided via `--input <path>`.
- **Production Requirement**:
  1. Create a Google Cloud Service Account with Google Drive API enabled.
  2. Download the JSON key file and set:
     ```bash
     GOOGLE_APPLICATION_CREDENTIALS=/path/to/service_account.json
     ```
  3. Share the client input folders with the service account email.
  4. Specify the folder ID in the brand manifest under `sources[].config.folder_id`.
  5. The platform will automatically calculate SHA-256 checksums, skip duplicate uploads, and track new files in `raw_files`.

### 5. Automated Notifications (Slack & Email)
- **Slack Alerting**:
  - Set the webhook URL in environment variables:
    ```bash
    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/XXXXX
    ```
  - Alerts are routed to:
    - `#data-reviewers`: When a run pauses at the Review Gate.
    - `#ops-alerts`: When a run fails with an unhandled error.
    - `#marketing-reports`: When deliverables are successfully generated.
- **Email Drafts**:
  - In production, email delivery generates `.eml` draft files in `outputs/email_drafts/<Brand>/`.
  - In Google Workspace environments, integrate the Gmail API to create drafts in the account manager's inbox rather than sending directly to clients.

### 6. Claude AI Query Categorization Top-Up
- **Production Requirement**:
  - For unclassified search queries that do not match the Brand Manifest rules, the platform can invoke Claude AI for preliminary tagging before routing to human reviewers:
    ```bash
    ANTHROPIC_API_KEY=sk-ant-api03-...
    ```

---

## 4. Step-by-Step Execution Guide

### Prerequisites
- Python 3.9+ (tested on Python 3.9.16)
- Git

### 1. Installation & Environment Setup
```bash
# Clone repository
git clone <repo-url>
cd dataingestion

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -e .
```

### 2. Initialize Database & Validate Brand Readiness
```bash
# Apply database migrations (creates all 14 platform tables)
python cli.py migrate

# Validate Ampere brand manifest against JSON schema and registry
python cli.py validate --brand ampere
```

### 3. Generate Deliverables

#### Organic Search Performance Report (`gsc_organic_report`)
```bash
# Generate report for August 2026
python cli.py run --brand ampere --deliverable gsc_organic_report --period 2026-08

# With a specific input CSV:
python cli.py run --brand ampere --deliverable gsc_organic_report --period 2026-08 --input path/to/gsc_data.csv
```

#### Paid Social Performance Report (`paid_social_report`)
```bash
python cli.py run --brand ampere --deliverable paid_social_report --period 2026-08
```

#### Multi-Channel Engagement Rate Report (`engagement_rate_report`)
```bash
python cli.py run --brand ampere --deliverable engagement_rate_report --period 2026-08
```

### 4. Review Queue Operations & Human-in-the-Loop Workflow

If unresolved items exceed the brand's blocking threshold ($\le 2\%$ of total volume/spend), the pipeline pauses with `AWAITING_REVIEW`.

```bash
# 1. Inspect open items ranked by impact
python cli.py review-list --brand ampere

# 2. Export queue to CSV for review by non-technical analysts
python cli.py review-export --brand ampere --out review_sheets/ampere_review.csv

# 3. Resolve an item directly via CLI
python cli.py review-resolve \
  --item-id <ITEM-UUID> \
  --action reclassify \
  --val generic_theme=dealership \
  --reason "Dealership showroom query"

# 4. Or re-import reviewed CSV edited in Google Sheets / Excel
python cli.py review-import --brand ampere --file review_sheets/ampere_review.csv --by analyst@howl.internal

# 5. Resume the paused run (rehydrates canonical data directly from DB without re-running ingest)
python cli.py run --resume <RUN-ID>
```

### 5. Audit Trail & Rule Promotion
```bash
# View audit history of decisions in the decision ledger
python cli.py ledger-audit --brand ampere

# Discover recurring decisions (frequency >= 3) and promote them to brand manifest rules
python cli.py promote-rules --brand ampere --min-count 3
```

### 6. Media Planning Governance & Control Sheets
```bash
# Ingest media plan and validate naming conventions
python cli.py plan-ingest --brand ampere --file tests/fixtures/media_plan_ampere_2026.csv --plan-id q3_plan

# Track Planned vs Actual media spend variance and pacing
python cli.py plan-variance --brand ampere --period 2026-08

# Process batch triggers from a self-serve control sheet
python cli.py control-run --sheet tests/fixtures/control_sheet_sample.csv
```

### 7. Operational Dashboard & Health Status
```bash
# List recent pipeline execution runs
python cli.py runs-list --brand ampere --limit 10

# Generate consolidated daily operational summary
python cli.py ops-summary --brand ampere --hours 24

# Verify notification channels
python cli.py notify-test --channel slack
python cli.py notify-test --channel email
```

---

## 5. Deliverable Reports & Methodology

### Deliverable 1: Organic Search Performance (`gsc_organic_report`)
- **Domain**: `search` (`search_v1`)
- **Worksheets**:
  1. `Summary`: Overall KPIs (Queries, Impressions, Clicks, CTR, Average Position) with Branded vs. Non-Branded split.
  2. `Product Breakdown`: Volume and click share by vehicle product (*Magnus G Max*, *Reo Vyb*, *Nexus*, *Magnus Neo*).
  3. `Top Queries`: Detailed query metrics with classification tags and audit source (`rule`, `ledger`, `ai`).
  4. `Notes`: Methodology, formula definitions, and audit lineage.

### Deliverable 2: Paid Social Performance (`paid_social_report`)
- **Domain**: `paid` (`paid_v2`)
- **Worksheets**:
  1. `Summary`: Spend (INR), Impressions, Reach, Clicks, Engagements, Conversions, CTR, CPC, CPM.
  2. Campaign Breakdown: Performance by campaign and ad set.
  3. `Notes`: Revision lookback windows (28 days) and currency audit.

### Deliverable 3: Multi-Channel Engagement Rate Report (`engagement_rate_report`)
- **Domains**: `paid` (`paid_v2`) and `organic` (`organic_v1`)
- **Methodology (Document 06)**:
  - **Ratio of Sums**: Computes $\frac{\sum \text{engagements}}{\sum \text{impressions}}$ across platforms (YouTube denominator: video views). Never calculates period averages by taking the average of monthly percentages.
  - **Three Canonical Tables**: Paid, Organic, and Total Combined engagement rates across Instagram, Facebook, YouTube, and LinkedIn.
  - **Combined Total Rule**: Combined engagement rate strictly falls between Paid and Organic rates.
  - **Methodology Tab**: Audit documentation of formulas and correction rationale.

---

## 6. Shared Review Services & Decision Ledger

1. **Domain Impact Scoring**:
   - `search`: $\text{clicks} + (\text{impressions} \times 0.05)$
   - `paid`: $\text{spend}$
   - `organic`: $\text{engagements}$
   - High-volume and high-spend items are surfaced to reviewers first.
2. **Review Gate**:
   - Evaluates unresolved impact ratio against brand manifest threshold ($\le 2\%$). Blocks generation when threshold is exceeded.
3. **Decision Ledger & Audit Supersession**:
   - Immutable append-only ledger (`decision_ledger`).
   - Supersessions require a mandatory `supersede_reason`.
   - Full history queryable with timestamps, authors, and rationale.
4. **Two-Way Sheet / CSV Sync**:
   - Export review queue to Google Sheets / CSV for non-technical analysts.
   - Import reviewer edits (`status=resolved`, `action`, `val`, `reason`), automatically updating the ledger and unblocking runs.
5. **Rule Promotion Engine**:
   - Discovers recurring manual classifications (frequency $\ge 3$).
   - Automatically promotes high-frequency patterns into regex rules in the Brand Manifest, versioning the manifest file.

---

## 7. Self-Serve Control Sheets & Media Planning

1. **Media Plan Governance**:
   - Validates planned campaigns against standard naming conventions (`Brand_Channel_Objective_Campaign_Audience`).
   - Non-compliant campaigns are routed directly to `review_items`.
   - Tracks Planned vs Actual media spend and impressions pacing (`python cli.py plan-variance`).
2. **Control Sheet Execution**:
   - Watches control sheet triggers (`RUN` / `TRUE`), executes pipeline batches, and writes back execution statuses (`COMPLETED`, `PAUSED`, `FAILED`).

---

## 8. CLI Reference

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `validate` | `--brand <id>` | Validate manifest against schema & test store readiness |
| `migrate` | *(none)* | Apply and verify all 14 database tables |
| `run` | `--brand <id> --deliverable <name> --period <YYYY-MM> [--input <file>]` | Run reporting pipeline |
| `run` | `--resume <run_id>` | Resume paused run from review gate |
| `runs-list` | `[--brand <id>] [--limit <N>]` | Display historical pipeline execution runs |
| `ops-summary` | `[--brand <id>] [--hours <N>]` | Display daily operational health summary |
| `notify-test` | `[--channel slack\|email]` | Test notification dispatching |
| `review-list` | `--brand <id>` | List open review items ranked by impact |
| `review-export`| `--brand <id> [--out <file>]` | Export review queue to CSV for Google Sheets |
| `review-import`| `--brand <id> --file <file> [--by <email>]` | Import reviewer decisions into decision ledger |
| `review-resolve`| `--item-id <id> --action <action> --val <k=v> [--reason <text>]` | Resolve an open review item directly |
| `ledger-audit`| `--brand <id> [--key <key>]` | Inspect audit trail of decision ledger |
| `promote-rules`| `--brand <id> [--min-count <N>]` | Promote recurring decisions to manifest regex rules |
| `plan-ingest` | `--brand <id> --file <file> [--plan-id <id>]` | Ingest media plan and validate naming conventions |
| `plan-variance`| `--brand <id> --period <YYYY-MM> [--plan-id <id>]` | Display Planned vs Actual media spend pacing |
| `control-run` | `--sheet <file>` | Execute batch runs from a control sheet |

---

## 9. Automated Test Suite

Run the full pytest suite:
```bash
python -m pytest -v
```

**Coverage Summary (51 passing tests)**:
- Manifest schema Draft 2020-12 and semantic validations.
- Database migrations, table inspection, and manifest-to-store syncing.
- Canonical schemas (`search_v1`, `paid_v2`, `organic_v1`, `web_v1`, `crm_v1`, `plan_v1`) and unique key deduplication.
- Windsor API puller with per-channel lookback revision windows (Meta 28d, Google Ads 14d, GSC 3d).
- Legacy sheet importer, percentage parsing, and problem cell flagging.
- GSC CSV, Meta Ads, Organic Social, and Media Plan adapters.
- 3-tier classification hierarchy, real-word context matching (`amber`/`empire`), and ledger lookup overrides.
- Domain impact scoring (`search`, `paid`, `organic`) and reviewer queue impact ranking.
- Review queue gate checks ($\le 2\%$ threshold) and decision ledger append-only persistence.
- Decision ledger supersession, mandatory supersede reasons, and historical audit trail.
- Two-way review queue export and bulk CSV import.
- Recurring decision pattern discovery and automated manifest rule promotion.
- Run state machine pause/resume and canonical DB rehydration.
- Notification dispatching (Slack payload audit & Email draft creation).
- Daily operational summary reporter & platform health indicators.
- Media plan adapter, naming convention validator, and Planned vs Actual variance analyzer.
- Control sheet self-serve batch trigger executor.
- Report generators for all 3 deliverables (`gsc_organic_report`, `paid_social_report`, `engagement_rate_report`).
- Golden deliverable file regression test and end-to-end pipeline execution.
