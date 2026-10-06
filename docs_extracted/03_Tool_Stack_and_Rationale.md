# 03_Tool_Stack_and_Rationale.docx

HOWL PLATFORM · DOCUMENT 03

Tool Stack and Rationale

Each tool, why it was chosen, and the alternatives considered.

Version 0.1 (draft)  ·  28 September 2026  ·  Prepared for the HOWL tech team  ·  First brand: Ampere

Every tool in the stack, why it was chosen, and what was considered instead. The guiding rule: pick the simplest tool that satisfies the design principles, and defer anything that is only needed at a scale HOWL has not reached yet.

1. The stack at a glance

Layer

Choice

Phase

Language

Python 3.12 with pandas

P0

Canonical store

Postgres on Supabase

P0

API data

Windsor.ai (REST API)

P2

CSV intake

Watched Google Drive folder (Drive API)

P1

Classification AI

Claude Haiku 4.5 (claude-haiku-4-5)

P1

Narrative AI

Claude Opus 5 (claude-opus-5), optional

P1

Review queue and self-serve

Google Sheets + Apps Script

P1, P5

Report files

openpyxl (xlsx), python-pptx (pptx), Google Sheets API

P1

Delivery

Google Drive, Gmail API (drafts), Slack API (DMs)

P1, P4

Orchestration

Python CLI, then cron or self-hosted n8n

P1, P4

Hosting

One small container (Cloud Run job or a small VM)

P1

Code and CI

GitHub, pytest, GitHub Actions

P0

2. Choices and alternatives

Language: Python 3.12

Choice: Python, with pandas for tabular work.

pandas handles the core job (reshaping, joining, aggregating tables) better than anything else in common use.

The best-maintained libraries for every output format (openpyxl, python-pptx, Google APIs) and the official Anthropic SDK are all Python.

One language for adapters, classifier, generators and CLI keeps the codebase small.

Alternative

Why not (for now)

Node.js / TypeScript

Weaker tabular data tooling. The spec mentions pptxgenjs, but using it would add a second language and runtime for one output format.

Mixed Python + Node

Two runtimes, two dependency trees, two deploy targets, for no real gain.

Canonical store: Postgres on Supabase

Choice: Managed Postgres on Supabase, from day one.

The decision ledger, review queue and run log need small transactional writes and real queries (&quot;open items for Ampere ranked by clicks&quot;), which is exactly what Postgres is for.

Upserts on a unique key make re-runs safe without extra code.

Row-level security gives per-brand access control; Supabase adds a secrets vault, backups and a table viewer.

Expected data volume (a few brands, daily rows per channel, monthly query-level search data) is small for Postgres.

Alternative

Why not (for now)

Google Sheets as the store

Hard cell limits, no transactions, no unique keys, slow to query. Query-level Search Console data outgrows it quickly. Fine for the review queue&apos;s interface, not for storage.

BigQuery

Excellent for large analytical workloads, but awkward for small frequent writes like ledger decisions, and costs are per query. A good later addition if volume grows: Postgres can be replicated into it.

Neon (serverless Postgres)

A valid alternative with the same SQL. Supabase is preferred for its built-in vault, row-level security tooling and table editor. Switching later is a connection-string change.

Files in Drive (CSV/Parquet)

No keys, no concurrency control, no queries. Makes lineage and dedupe hard.

API data: Windsor.ai through its REST API

Choice: Windsor.ai as the single aggregator for ad and analytics platforms, called through its REST API.

One integration covers Meta Ads, Google Ads, LinkedIn Ads, YouTube, GA4, Search Console, SEMrush and organic insights, with one authentication model.

Windsor maintains the connectors when platforms change their APIs, which is the most expensive part of doing this yourself.

The spec suggests reading through Windsor&apos;s MCP endpoint. MCP is designed for an AI model calling tools during a conversation. A scheduled, rule-based pipeline needs a plain API: predictable, testable and not dependent on a model. Windsor can also sync directly into a database, which is an option to evaluate.

Alternative

Why not (for now)

Direct platform APIs

Five or more separate integrations, each with its own auth, rate limits, pagination and breaking changes. Reserve for gaps Windsor does not cover (the spec already allows a direct Meta connector).

Supermetrics

Similar coverage, strongest when the destination is Sheets or Looker Studio. Either is workable; Windsor is already named in the spec and its API suits a code pipeline.

Fivetran / Airbyte

General-purpose data movers built for warehouses. More setup and cost than needed at this scale; Airbyte self-hosted adds operations work.

CSV intake: watched Google Drive folder

Choice: A Drive folder per brand and channel, watched by the platform.

The team already works in Google Drive; dropping a file there needs no training.

Files are hashed on arrival, so the same export dropped twice is processed once.

Outputs go back to Drive, so inputs and outputs sit side by side per brand.

Alternative

Why not (for now)

Email attachments

Harder to parse reliably, easy to lose, no folder structure.

Cloud storage upload (S3/GCS)

Works technically, but the team does not live there.

Upload page in a custom UI

A UI is deliberately deferred until the workflow is proven.

AI: Claude Haiku 4.5 for classification, Claude Opus 5 for narrative

Choice: The Claude API, called as a component from Python with the official Anthropic SDK.

Classification is short, high-volume and simple: &quot;is &apos;ampaire price&apos; branded? which product?&quot;. Claude Haiku 4.5 (claude-haiku-4-5) is the fastest and cheapest current Claude model, at about a fifth of Opus&apos;s per-token price. Structured outputs return a fixed JSON shape (label, confidence) that code can validate.

Narrative is one call per report on already-computed metrics, where writing quality matters and volume is tiny. Claude Opus 5 (claude-opus-5) is the recommended default. Claude Sonnet 5 (claude-sonnet-5) is a cheaper option if the team finds the quality sufficient; measure on a few real reports before choosing.

Cost stays bounded: only unknowns are sent, answers are cached in ai_labels, the rules and ruleset prompt are cached with prompt caching, and the one-off onboarding pass can use the Message Batches API at half price.

Keeping the model behind one small ai/ module means the model can be changed by configuration.

Alternative

Why not (for now)

An LLM for everything (chat-driven reports)

Rejected by the design principles: unpredictable output, per-run cost, no audit trail, and the model becomes the system&apos;s memory.

No AI at all

Workable, but every unknown goes to the review queue, so onboarding a brand takes much longer.

The strongest model for classification too

Several times the cost for a task that does not need it.

Review queue and self-serve: Google Sheets + Apps Script

Choice: A Google Sheet per brand for the review queue, and a control Sheet with buttons for self-serve (Phase 5).

Analysts and account managers already use Sheets daily: no training, no login system, sharing handled by Google.

Apps Script can add buttons and call the platform, which is enough for &quot;run this report&quot; and &quot;upload this plan&quot;.

Building a UI before the workflow is stable usually means rebuilding it.

Alternative

Why not (for now)

Retool / Appsmith

Good internal-tool builders and a sensible next step if Sheets becomes limiting. Adds a paid tool and a new place to work.

Custom web app (React)

Most flexible, most work. Justified only once the workflow is proven and the team outgrows Sheets.

Report files: openpyxl, python-pptx, Google Sheets API

Choice: Native Python libraries for each output format.

openpyxl writes styled xlsx files with formulas, charts and brand colours.

python-pptx builds decks from a branded template with placeholders, so layout stays with designers and data stays with code.

The Google Sheets API covers clients who want a live Sheet instead of a file.

Alternative

Why not (for now)

pptxgenjs

A good library, but JavaScript. It would require a Node service in a Python stack.

Google Slides API

Viable for clients who want Slides; slower and more verbose than python-pptx. Add per client if needed.

Looker Studio

For live dashboards, not finished branded deliverables. Can be added later on top of Postgres.

Orchestration: Python CLI first, then cron or n8n

Choice: A howl run command that runs the stages in order, recording each in the run log. Scheduling and notifications are added in Phase 4.

Early on, the hard part is making each stage correct, not scheduling. A CLI is the fastest thing to test and debug.

The run log gives resumability without a workflow engine.

In Phase 4, cron (or a Cloud Scheduler job) handles &quot;run monthly&quot;; self-hosted n8n is a good choice if the team wants visual flows that glue together Drive, Slack and Gmail events.

Alternative

Why not (for now)

Airflow

Powerful, but heavy to operate for a handful of runs a day.

Prefect / Dagster

Well-designed Python orchestrators and the natural upgrade if run counts grow a lot. Premature today.

n8n as the engine

Keeping business logic in n8n flows makes it hard to test and version. Use n8n to trigger and notify; keep logic in Python.

Hosting, secrets, code

Choice: One container image, run as a scheduled job (Cloud Run job) or on a small VM; secrets in Supabase Vault or Google Secret Manager; code on GitHub with pytest and GitHub Actions.

One image containing the CLI covers every stage; there are no long-running services to keep alive until n8n is added.

Tests run on every pull request: adapter tests against saved sample files, generator tests against &quot;golden&quot; expected outputs.

Alternative

Why not (for now)

Kubernetes

Far more than a few scheduled jobs need.

Secrets in .env files or the manifest

Easy to leak. Never commit credentials.

3. Cost principles

Deterministic code (rules, calculations, templates) costs nothing per run.

AI cost scales with the number of new unknowns, not with the number of runs, because answers are cached.

Windsor.ai pricing depends on the number of connected accounts and data sources; confirm the plan against the brands to be onboarded.

Supabase and a small container run comfortably on entry-level paid tiers at this scale.