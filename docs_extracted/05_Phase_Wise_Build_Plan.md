# 05_Phase_Wise_Build_Plan.docx

HOWL PLATFORM · DOCUMENT 05

Phase-Wise Build Plan

Phase 0 to Phase 5 and scheduling: goals, tasks, outputs, exit tests and risks.

Version 0.1 (draft)  ·  28 September 2026  ·  Prepared for the HOWL tech team  ·  First brand: Ampere

How to build the platform in phases, from the foundations to self-serve. Each phase ends with something you can run and check, not a list of finished parts.

1. How the phases are cut

Build one report end to end before building the second. The first report proves every stage; the second proves reuse.

Each phase has an exit test. A phase is done when its test passes, not when its parts exist.

The platform core must not change to add a report. If Phase 2 needs a core change to ship the second report, the core was designed wrong and is fixed as a general capability.

Scheduling comes last. It wraps a chain that already works reliably by hand.

2. Before Phase 0 (this week)

Agree the decisions in document 07, section 1.

Start archiving Ampere&apos;s Search Console data now. Search Console keeps only 16 months of history. Export it monthly from today, or year-on-year comparisons will have nothing to compare against.

Collect three months of real sample files for each source Ampere uses; they become test fixtures.

Get answers to the open questions about the engagement-rate sheet (document 06, section 6).

3. Phases

Phase 0 · Foundations

Goal: Agree the shapes everything plugs into, for one brand (Ampere).

Indicative duration: 1 week for one developer.

Build

Repo skeleton, Python project, pytest, GitHub Actions.

Supabase project; SQL migrations for every table in document 04.

Manifest JSON Schema and loader; manifests/ampere.json written and validated.

Canonical schemas v1 (and paid_v2) as SQL and as Python definitions.

Generator contract (GeneratorSpec, Generator) and a registry.

Secrets set up (Supabase Vault or Secret Manager).

Outputs

Migrations that create an empty, correct database.

A validated Ampere manifest.

The generator contract module.

Exit test: howl validate --brand ampere passes, and every table exists in Supabase.

Risks to watch

Over-designing schemas before real data is seen. Keep v1 minimal; versioning allows growth.

Phase 1 · First report end to end

Goal: Produce Ampere&apos;s organic search report from a CSV drop with one command.

Indicative duration: 2 to 3 weeks for one developer.

Build

Drive watcher for inbox/google_search_console/ with hashing.

gsc_csv adapter → canonical_search, with upsert and unplaceable-row flagging.

Classifier: ledger lookup, manifest rules (variants, roster), Haiku top-up with caching and a cost cap.

Review queue as a Google Sheet with two-way sync into the ledger.

gsc_organic_report generator (xlsx first) with brand styling and data checks.

Basic orchestrator and CLI: howl run, run log, resume from a failed stage.

Delivery to Drive.

Outputs

A branded August 2026 organic search report for Ampere in Drive.

A review Sheet with real decisions in the ledger.

Exit test: One command turns an August CSV into a report draft. Running it again produces zero new review items and an identical file.

Risks to watch

Misspelling rules that catch real words (see the &quot;amber&quot;/&quot;empire&quot; note in document 04).

Search Console CSV exports differ by export type; save each variant as a test fixture.

Phase 2 · Live data and the second report

Goal: Add Windsor as a live source, and ship reports that reuse the core without changing it.

Indicative duration: 3 weeks for one developer.

Build

Windsor puller with per-source re-pull windows.

Adapters: meta_ads, google_ads, ga4, then linkedin_ads, ig_fb_organic, yt_organic.

paid_v2 schema; metric dictionary in the manifest.

paid_social_report generator.

Legacy importer and engagement_rate_report generator (document 06).

Outputs

Paid social and engagement-rate reports for Ampere from live data.

Historical engagement rates loaded and flagged as legacy.

Exit test: The second and third reports ship with zero changes to the platform layer (checked by reviewing the diff).

Risks to watch

Windsor field names differ from platform UI names; map them against the connector documentation.

Platform-specific definitions of &quot;engagement&quot;. Settle them in the metric dictionary first.

Phase 3 · Shared review services

Goal: Make the review queue and ledger robust enough for every brand and report.

Indicative duration: 1 to 2 weeks for one developer.

Build

Impact scoring per domain; blocking thresholds per deliverable.

Ledger supersession, reasons, audit view.

Promotion of recurring decisions into manifest rules.

Review Sheet improvements: filters, AI suggestion column, bulk actions.

Outputs

A review workflow an analyst can run without a developer.

Exit test: A rerun of any past period resurfaces zero resolved items, and review time on the second month is measurably lower than the first.

Risks to watch

Two people editing the review Sheet at once. Sync must be idempotent.

Phase 4 · Orchestration

Goal: Run the whole chain from one trigger, reliably, with notifications.

Indicative duration: 1 to 2 weeks for one developer.

Build

Full run state machine with resume.

Gmail draft and Slack DM delivery.

Daily summary: failed runs, expired sources, stale review items.

Container image; deploy as a scheduled job; optional n8n for triggers and notifications.

Outputs

Drafts arriving in the reviewer&apos;s inbox or Slack.

Exit test: Trigger to draft with no manual steps in between, for every Ampere deliverable.

Risks to watch

Expired OAuth connections in Windsor. Alert on auth_status changes.

Phase 5 · Self-serve

Goal: Let account managers run reports and submit media plans without a developer.

Indicative duration: 2 to 3 weeks for one developer.

Build

Control Sheet with Apps Script buttons: pick brand, deliverable, period, run.

Media plan upload; naming convention; generated names and UTMs; canonical_plan.

media_plan_report generator (plan versus actual).

Onboarding checklist for a second brand.

Outputs

A working self-serve Sheet.

A second brand onboarded using only a manifest and adapters that already exist.

Exit test: An account manager produces a report for a brand without asking a developer.

Risks to watch

Naming conventions not followed at campaign setup. The generated names must be copied, never retyped.

After Phase 5 · Scheduling

Add scheduled runs (monthly reports on the 3rd, after Search Console data settles) once a month of on-demand runs has gone through without manual fixes.

4. Timeline overview

Phase

Focus

Indicative

Cumulative

0

Foundations

1 week

Week 1

1

First report end to end (GSC)

2 to 3 weeks

Weeks 2 to 4

2

Windsor, paid social, engagement rate

3 weeks

Weeks 5 to 7

3

Shared review services

1 to 2 weeks

Weeks 8 to 9

4

Orchestration and delivery

1 to 2 weeks

Weeks 10 to 11

5

Self-serve and media plans

2 to 3 weeks

Weeks 12 to 14

Durations assume one developer familiar with Python and are estimates to revise after Phase 1.

5. Repo layout

howlplatform/

  platform/                  # core, no report logic

    manifest/                # JSON Schema, loader, validation

    store/                   # SQL migrations, db helpers

    ingest/                  # windsor.py, drive.py, legacy.py

    adapters/                # gsc_csv.py, meta_ads.py, ... one per source type

    classifier/              # ledger lookup, rules, ai.py (Claude calls)

    review/                  # queue, Sheet sync, impact scoring

    ledger/

    orchestrator/            # run state machine, run log

    delivery/                # drive.py, gmail.py, slack.py

  deliverables/

    contract.py              # GeneratorSpec, Generator, registry

    gsc_organic_report/

    paid_social_report/

    engagement_rate_report/

  manifests/

    ampere.json

  tests/

    fixtures/                # real sample files per source

    golden/                  # expected outputs per generator

  cli.py                     # howl run | validate | review-sync

6. Definition of done for any component

Has tests against real sample data.

Writes to the run log.

Fails with a message that says what went wrong and how to fix it.

Contains no report-specific logic if it lives in platform/.

Documented in one short README in its folder.