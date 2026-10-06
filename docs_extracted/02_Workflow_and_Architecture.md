# 02_Workflow_and_Architecture.docx

HOWL PLATFORM · DOCUMENT 02

Workflow and Architecture

The system&apos;s structure, every component, and how a report moves from raw data to a reviewed draft.

Version 0.1 (draft)  ·  28 September 2026  ·  Prepared for the HOWL tech team  ·  First brand: Ampere

How the platform is put together and how a report moves through it, from raw platform data to a draft in a reviewer&apos;s inbox.

1. Architecture at a glance

The next page shows the whole system on one diagram. Read it left to right:

Sources (Windsor.ai, a Drive CSV folder, CRM, legacy sheets) supply raw data.

Ingestion services fetch that raw data. They are the only part of the system that touches it.

Platform core turns raw data into the standard shape, stores it, and classifies it. People resolve uncertain items in the review queue; their decisions go into the decision ledger.

Deliverables are generators that read the store and produce report files.

Delivery puts the draft in Drive, Gmail or Slack for a reviewer, who sends it to the client.

Across the top, the orchestrator runs the six stages in order. Along the bottom, the media-plan branch generates campaign names that later match results back to the plan.

Box colours: blue outline is code you write, violet is a call to Claude, amber is a person, shaded is stored data, plain grey is an external system. The P badges show the build phase that adds each part.

Figure 1. HOWL system map. Full resolution: diagrams/system_map.png

2. The two layers

The single most important boundary is between the platform layer and the deliverable layer.

Figure 2. The platform layer knows nothing about any particular report.

Platform layer (core)

Deliverable layer (generators)

Knows four things only: brands, sources, canonical data, deliverables

Knows exactly what one report looks like

Fetching, normalizing, storing, classifying, reviewing

Reading canonical data, calculating report metrics, laying out the file

Changes rarely

Grows by one generator per new report

Example: &quot;store this Meta Ads row in paid_v2&quot;

Example: &quot;engagement rate = engagements ÷ impressions, shown by month&quot;

Test for any new code: if it mentions a specific report, it belongs in a generator. If a generator needs something the core does not provide, the core gains a general capability (a new column, a new check), never a report-specific branch.

3. Components

Component

Responsibility

Reads

Writes

Phase

Triggers

Start a run: CLI command, Sheet button, schedule

User input

Run request

P1, P5, later

Orchestrator

Run the six stages in order; record progress; resume failed runs

Run request, run log

Run log

P1 basic, P4 full

Windsor puller

Fetch API data on a schedule; re-pull recent days that platforms revise

Windsor REST API

Raw files

P2

Drive watcher

Detect new CSVs in the brand&apos;s folder and start a run

Google Drive

Raw files + hash

P1

Legacy importer

Read old report sheets for history

Old Google Sheets

Raw files

P2

Adapters

Map raw columns to the canonical schema; dedupe; flag unplaceable rows

Raw files, manifest source config

Canonical rows, review items

P1 onward

Brand manifest

Hold identity, sources, rules, variants, metric dictionary

—

—

P0

Canonical store

Per-brand tables per domain with lineage

—

—

P0

Classifier

Tag rows: ledger first, then rules, then AI for high-volume unknowns

Canonical rows, ledger, manifest, AI cache

Tags, review items

P1

Claude Haiku

Suggest labels for unknown entities

Unknown entities

Cached labels

P1

Review queue

Show flagged items by impact; capture decisions

Review items

Decisions

P1, hardened P3

Decision ledger

Permanent record of decisions; read before classifying

Decisions

—

P1, hardened P3

Generator contract

Define what every generator declares: inputs, required columns, outputs

—

—

P0

Generators

Build one report each from canonical data + manifest identity

Canonical store, manifest

Output file

P1 onward

Claude narrative

Optionally draft the written commentary once per run

Computed metrics

Draft text

P1 (optional)

Delivery

Save to Drive; create Gmail draft or Slack DM to the reviewer

Output file

Draft

P1 Drive, P4 Gmail/Slack

4. The end-to-end workflow

Every run follows the same stages, whatever the report. The example throughout is Ampere&apos;s August 2026 organic search report.

Stage 0. Trigger

A person runs howl run --brand ampere --deliverable gsc_organic_report --period 2026-08 (Phase 1), or clicks a button in the control Sheet (Phase 5), or a schedule fires (after Phase 5). The orchestrator creates a run record with status pending and reads the manifest to learn which sources the deliverable needs.

Stage 1. Ingest

For each required source, the orchestrator asks the right ingestion service for data covering the period.

API sources: the Windsor puller requests the period plus a re-pull window (28 days for Meta, 3 days for Search Console), because platforms revise recent numbers.

CSV sources: the Drive watcher finds the newest file in HOWL/&lt;Brand&gt;/inbox/&lt;channel&gt;/, computes its SHA-256 hash, and skips it if that hash was already processed.

Raw files are saved unchanged to raw_files with the run ID. Nothing downstream ever reads a platform directly.

Stage 2. Normalize

The adapter for each source type reads the raw file and the source&apos;s schema_ref from the manifest.

It renames and converts columns into the canonical shape: dates to ISO dates, percentages to decimals, &quot;-&quot; to empty, currency and timezone recorded.

It upserts on the row&apos;s unique key, so re-running a period replaces rows instead of duplicating them.

Rows it cannot place (unknown columns, impossible values, missing keys) become review items. They are never guessed or silently dropped.

Stage 3. Classify

The classifier tags each new or changed row. Section 5 describes the order it follows.

Stage 4. Review gate

If there are open review items above the deliverable&apos;s blocking threshold (for example, unresolved items that together account for more than 2% of clicks), the run pauses with status awaiting_review.

The analyst works the queue. When the blocking items are resolved, the run resumes from this stage.

Items below the threshold do not block; they are listed in the draft&apos;s notes for the reviewer.

Stage 5. Generate

The generator first checks that every column it declares as required is present and filled for the period. If not, it fails with a clear message rather than producing a wrong report.

It runs data checks: rates over 100%, values more than three times the platform&apos;s median, totals that do not match the platform&apos;s own reported totals.

It computes the report metrics using the metric dictionary, lays out the file (xlsx, pptx or Google Sheet) with the brand&apos;s palette and fonts, and records the generator version.

Optionally it sends the computed metrics (never raw rows) to Claude once to draft the commentary, which is inserted into the file clearly marked as a draft.

Stage 6. Deliver draft

The file is saved to HOWL/&lt;Brand&gt;/outputs/&lt;deliverable&gt;/&lt;period&gt;/. In Phase 4 the platform also creates a Gmail draft addressed to the client, or sends a Slack DM to the reviewer. Nothing goes to a client automatically.

Stage 7. Send (a person)

The reviewer opens the draft, checks it, and sends it. The run is marked sent when they confirm.

Run states

pending → ingesting → normalizing → classifying → awaiting_review → generating → delivered → sent

                 \____________ any stage can move to  failed  (resumable from that stage) ___/

5. Classification and the learning loop

Figure 3. Each decision becomes a lookup the next run does first.

For every entity (a search query, a campaign, a post) the classifier tries three steps in order and stops at the first that answers:

Ledger lookup. Has a person already decided this entity for this brand? Keys are normalized (lower-cased, trimmed, repeated spaces collapsed) before matching. If there is a decision, apply it.

Rules. Match against the manifest: brand-name variants and misspellings (for Ampere: &quot;amper&quot;, &quot;ampaire&quot;, &quot;ampair&quot;), the product roster (&quot;Magnus G Max&quot;, &quot;Reo Vyb&quot;), and regular-expression rules per domain. Fast, free and exact.

AI top-up. Only for unknowns that matter: above a volume threshold (for example the top 200 unknown queries by clicks) and within a per-run cost cap. Claude Haiku returns a label and a confidence. Answers are saved in ai_labels and never requested again for the same entity and prompt version.

AI answers above the confidence threshold (start at 0.85) are applied and marked ai. The rest go to the review queue with the AI&apos;s suggestion shown. At onboarding, a one-off full AI pass over the brand&apos;s history discovers variants and products to seed the manifest&apos;s learned half; this pass can use the Message Batches API, which costs half the normal rate.

When the same kind of decision keeps recurring, it is promoted from the ledger into the manifest as a rule, so it is resolved at step 2 without a ledger lookup.

6. The review queue

Ranking by impact

Items are sorted so the analyst always works on what most affects the report first. Impact is defined per domain: clicks for search, spend for paid, impressions for organic, sessions for web, deal value for CRM.

The four actions

Action

Meaning

Example

Reclassify

The row is fine but its tag is wrong or missing. Set the tag.

&quot;ampaire scooter&quot; is branded, product = none

Fix

The row&apos;s data is wrong. Correct a value or mapping.

A campaign&apos;s currency is INR, not USD

Exclude

The row should not count in any report.

A test campaign with ₹10 spend

Ignore

Leave the row as it is and stop flagging it.

A low-volume query that is genuinely ambiguous

Each decision is written to the ledger with who decided, when, a reason, and, if it replaces an earlier decision, which one. Ledger entries are never edited or deleted; a change is a new entry that supersedes the old one.

Where the queue lives

In the MVP the queue is a Google Sheet per brand, synced both ways by the platform: new items are appended, and decisions typed into the Sheet are read back into the ledger. This avoids building a user interface until the workflow is proven.

7. Media-plan branch

Figure 4. The plan generates the names that later join results back to it.

Some deliverables compare actual results against a media plan. For these, the plan is submitted before any data comes in (Phase 5: through a Google Sheet). The platform applies the brand&apos;s naming convention to generate every campaign, ad set and ad name, plus UTM strings. People use those generated names when they set up campaigns on the ad platforms.

When actuals come back through Windsor, their campaign names match plan rows exactly, so plan-versus-actual needs no manual cleanup. Note that ad platforms report campaign names, not UTM values: the join to paid actuals uses the generated names, while the UTMs join GA4 and CRM rows back to the plan.

8. Mixed-mode sources

Mode belongs to the brand&apos;s source entry, not the channel. Ampere might send Search Console as a monthly CSV while another brand connects it by API. Both arrive at the same adapter family and produce identical canonical rows, so generators never know or care how data arrived.

9. Error handling and data quality

Check

Where

On failure

Source authorisation expired

Windsor puller

Run fails at ingest; auth_status set to expired; reviewer notified

CSV already processed (same hash)

Drive watcher

Skipped, logged

Unknown or missing columns

Adapter

Row or file goes to review queue

Duplicate rows

Adapter (upsert on key)

Replaced, never duplicated

Row count drops more than 30% versus last period

Adapter

Warning on the run; flagged in draft notes

Rate above 100% or above 3× median

Generator checks

Review item; blocks if above threshold

Totals differ from the platform&apos;s own totals by more than 1%

Generator checks

Review item

Required column missing for the period

Generator contract

Run fails with a message naming the column

AI call fails or exceeds cost cap

Classifier

Remaining unknowns go straight to review; run continues

10. Security and access

API keys and OAuth tokens are stored in a secrets manager (Supabase Vault or Google Secret Manager), never in the repo or the manifest.

Each brand&apos;s data is isolated by brand_id; Postgres row-level security limits which staff can read which brand.

CRM data can contain personal data. Store only the fields the deliverables need, hash lead identifiers where possible, and keep CRM out of AI calls.

Only computed metrics, never raw rows or personal data, are sent to Claude for narrative drafts.

Delivery creates drafts only; the platform has no permission to send email on its own.

11. Observability

Every stage writes to the run log: start and end time, status, row counts in and out, number of review items created.

A simple daily summary (Slack DM in Phase 4) lists failed runs, expired sources and review items older than three days.

Every output records the run ID and generator version, so any report can be regenerated exactly.