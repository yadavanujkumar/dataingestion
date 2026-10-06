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
   │  Lookback revision windows (Meta 28d, GAds 14d, LinkedIn 14d, GSC 3d)  │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                          STAGE 2: NORMALIZE                            │
   │  Adapters (gsc_csv, meta_ads, organic_social)                          │
   │  Canonical Schemas (search_v1, paid_v2, organic_v1, web_v1, etc.)      │
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

## 2. Phased Build Status

| Phase | Focus | Status | Exit Test Criteria |
| :--- | :--- | :---: | :--- |
| **Phase 0** | **Foundations** | **Completed** | `howl validate --brand ampere` passes; all 14 tables verified in database. |
| **Phase 1** | **First Report End-to-End (GSC)** | **Completed** | One command turns GSC CSV into an Ampere Excel report. Re-running produces zero new review items and an identical output file. |
| **Phase 2** | **Live Data & Multi-Channel Reports** | **Completed** | Windsor API puller, Meta Ads adapter, Organic Social adapter, and 2 new deliverables (`paid_social_report` and `engagement_rate_report`) shipped with zero core architecture changes. |
| **Phase 3** | **Shared Review Services** | **Completed** | Two-way Google Sheet / CSV review queue sync, domain impact scoring, decision ledger supersession & audit trail, and rule promotion to brand manifest. |
| **Phase 4** | **Orchestration & Delivery** | *Next* | Scheduled execution, state machine run resumes, Gmail drafts, Slack reviewer DMs, and error alerts. |
| **Phase 5** | **Self-Serve & Media Plans** | *Planned* | Control Sheet execution buttons and media plan naming convention enforcement. |

---

## 3. Implemented Deliverable Reports

### Deliverable 1: Organic Search Performance (`gsc_organic_report`)
- **Input Domain**: `search` (`search_v1`)
- **Format**: Multi-tab Excel (`.xlsx`)
- **Worksheets**:
  1. `Summary`: Overall KPIs (Queries, Impressions, Clicks, CTR, Position) and Branded vs. Non-Branded breakdown.
  2. `Product Breakdown`: Volume and click share by vehicle product (*Magnus G Max*, *Reo Vyb*, *Nexus*, *Magnus Neo*).
  3. `Top Queries`: Detailed query performance with classification tags and audit source (`rule`, `ledger`, `ai`).
  4. `Notes`: Methodology, formula definitions, and audit lineage.

### Deliverable 2: Paid Social Performance (`paid_social_report`)
- **Input Domain**: `paid` (`paid_v2`)
- **Format**: Multi-tab Excel (`.xlsx`)
- **Worksheets**:
  1. `Summary`: Spend (INR), Impressions, Reach, Clicks, Engagements, Conversions, CTR, CPC, CPM.
  2. Campaign Breakdown: Performance by campaign and ad set.
  3. `Notes`: Revision lookback windows (28 days) and currency audit.

### Deliverable 3: Multi-Channel Engagement Rate Report (`engagement_rate_report`)
- **Input Domains**: `paid` (`paid_v2`) and `organic` (`organic_v1`)
- **Format**: Multi-tab Excel (`.xlsx`)
- **Key Fixes & Innovations (Document 06)**:
  - **Ratio of Sums**: Computes $\frac{\sum \text{engagements}}{\sum \text{impressions}}$ across platforms (YouTube denominator: video views). Avoids erroneous legacy averaging of monthly percentages.
  - **Three Canonical Tables**: Paid, Organic, and Total Combined engagement rates across Instagram, Facebook, YouTube, and LinkedIn.
  - **Combined Total Rule**: Combined engagement rate strictly falls between Paid and Organic rates.
  - **Methodology Tab**: Audit documentation of formulas and correction rationale.

---

## 4. Shared Review Services & Decision Ledger

1. **Domain Impact Scoring**:
   - `search`: $\text{clicks} + (\text{impressions} \times 0.05)$
   - `paid`: $\text{spend}$
   - `organic`: $\text{engagements}$
   - Unresolved items are ranked so reviewers address high-volume items first.
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

## 5. CLI Usage Guide

```bash
# 1. Validate Brand Setup & Database Readiness
python cli.py validate --brand ampere

# 2. Run Database Migrations
python cli.py migrate

# 3. Generate Deliverables
python cli.py run --brand ampere --deliverable gsc_organic_report --period 2026-08
python cli.py run --brand ampere --deliverable paid_social_report --period 2026-08
python cli.py run --brand ampere --deliverable engagement_rate_report --period 2026-08

# 4. Review Queue Operations
# Inspect open items
python cli.py review-list --brand ampere

# Export review queue to CSV / Google Sheet format
python cli.py review-export --brand ampere --output review_sheets/ampere_review.csv

# Import reviewed decisions back into decision ledger
python cli.py review-import --file review_sheets/ampere_review.csv --decided-by analyst@howl.internal

# Resolve individual item directly
python cli.py review-resolve \
  --item-id <ITEM-UUID> \
  --action reclassify \
  --val generic_theme=dealership \
  --reason "Dealership intent"

# 5. Ledger Audit & Supersession
python cli.py ledger-audit --brand ampere --entity-key "ampere showroom"

# 6. Discover & Promote Recurring Decisions to Manifest Rules
python cli.py promote-rules --brand ampere --min-count 3
```

---

## 6. Automated Tests

Run the full pytest suite:
```bash
python -m pytest -v
```

**Coverage Summary (41 passing tests)**:
- Manifest schema and semantic validations.
- Database migrations, table inspection, and manifest-to-store syncing.
- Canonical schemas (`search_v1`, `paid_v2`, `organic_v1`, `web_v1`, `crm_v1`, `plan_v1`) and unique key deduplication.
- Windsor API puller with per-channel lookback revision windows (Meta 28d, Google Ads 14d, GSC 3d).
- Legacy sheet importer, percentage parsing, and problem cell flagging.
- GSC CSV, Meta Ads, and Organic Social adapters.
- 3-tier classification hierarchy, real-word context matching (`amber`/`empire`), and ledger lookup overrides.
- Domain impact scoring (`search`, `paid`, `organic`) and reviewer queue impact ranking.
- Review queue gate checks ($\le 2\%$ threshold) and decision ledger append-only persistence.
- Decision ledger supersession, mandatory supersede reasons, and historical audit trail.
- Two-way review queue export and bulk CSV import.
- Recurring decision pattern discovery and automated manifest rule promotion.
- Report generators for all 3 deliverables (`gsc_organic_report`, `paid_social_report`, `engagement_rate_report`).
- Golden deliverable file regression test and end-to-end pipeline execution.

