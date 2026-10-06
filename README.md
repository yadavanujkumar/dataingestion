# HOWL Platform

Automated Multi-Source Marketing Data Ingestion & Reporting Engine.

> **Principle**: A report is not built, it is projected. All of a brand's data is collected, cleaned, and stored once in a standard canonical shape. Each report is a specific view of that store, rendered in the brand's style. Adding a new report means registering one new generator without re-collecting or re-cleaning data.

---

## Architecture Overview

```
Sources (Windsor API, Drive CSV, etc.)
               │
               ▼
   [ Ingestion & Adapters ]  --> Raw files + Checksum deduplication
               │
               ▼
     [ Canonical Store ]     --> search_v1, paid_v2, organic_v1, web_v1, crm_v1, plan_v1
               │
               ▼
        [ Classifier ]       --> Ledger lookup -> Manifest Rules -> AI Top-up
               │
               ▼
      [ Review Queue ]       --> Human-in-the-loop decision ledger
               │
               ▼
     [ Report Generators ]   --> Deterministic reporting (xlsx, pptx, gsheet)
               │
               ▼
        [ Delivery ]         --> Drive, Gmail drafts, Slack reviewer DMs
```

---

## Phase 0 (Foundations) Deliverables

1. **Brand Manifest & Schema Validation**:
   - `howlplatform/platform/manifest/manifest.schema.json`: JSON Schema draft 2020-12 defining static and learned brand configurations.
   - `howlplatform/platform/manifest/loader.py`: Validates manifest and raises informative errors on syntax or semantic violations.
   - `manifests/ampere.json`: Validated onboarding manifest for Ampere (sources, identity, learned lists, rules, metric dictionary).

2. **Database Store & SQL Migrations**:
   - `howlplatform/platform/store/migrations/001_initial_schema.sql`: Full PostgreSQL DDL creating 14 platform and canonical tables (`brands`, `sources`, `runs`, `raw_files`, `canonical_search`, `canonical_paid`, `canonical_organic`, `canonical_web`, `canonical_crm`, `canonical_plan`, `review_items`, `decision_ledger`, `ai_labels`, `outputs`).
   - `howlplatform/platform/store/db.py`: Database engine manager supporting PostgreSQL/Supabase and local SQLite fallback for offline development.
   - `howlplatform/platform/store/sync.py`: Synchronizes validated manifests and sources into database records.

3. **Canonical Schemas**:
   - `howlplatform/platform/canonical/schemas.py`: Dataclass models for `search_v1`, `paid_v2`, `organic_v1`, `web_v1`, `crm_v1`, `plan_v1` with composite unique keys for deduplication and upserts.

4. **Deliverable Contract & Registry**:
   - `howlplatform/deliverables/contract.py`: `Requirement`, `GeneratorSpec`, abstract `Generator`, and generator registry with initial built-ins (`gsc_organic_report`, `paid_social_report`, `engagement_rate_report`).

5. **CLI & Tooling**:
   - `cli.py`: Command-line tool `howl validate`, `howl migrate`, `howl run`, `howl review-sync`.
   - `.github/workflows/ci.yml`: Continuous integration pipeline.
   - Comprehensive test suite in `tests/`.

---

## Quickstart

### 1. Validate Brand Setup (Phase 0 Exit Test)
```bash
python cli.py validate --brand ampere
```

### 2. Run Database Migrations
```bash
python cli.py migrate
```

### 3. Run Automated Tests
```bash
python -m pytest -v
```
