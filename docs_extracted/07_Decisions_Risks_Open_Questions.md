# 07_Decisions_Risks_Open_Questions.docx

HOWL PLATFORM · DOCUMENT 07

Decisions, Risks and Open Questions

What to agree before building, what could go wrong, and what is still unknown.

Version 0.1 (draft)  ·  28 September 2026  ·  Prepared for the HOWL tech team  ·  First brand: Ampere

The choices that need agreeing before Phase 0, the main risks and how they are handled, and the questions still open.

1. Decision log

Status &quot;Proposed&quot; means recommended here and awaiting agreement.

#

Decision

Recommendation

Why

Status

D1

Canonical store

Postgres on Supabase from day one

Ledger and ranked queue need real queries; Sheets outgrown quickly

Proposed

D2

Windsor access

REST API (or Windsor sync into Postgres), not MCP

A scheduled pipeline needs a plain, testable API

Proposed

D3

PowerPoint library

python-pptx

pptxgenjs is JavaScript and would add a Node service

Proposed

D4

Review surface

Google Sheet per brand with two-way sync

No UI to build; same tool as Phase 5

Proposed

D5

AI results

Cache every answer; apply above 0.85 confidence, queue the rest

Repeatable builds, near-zero repeat cost

Proposed

D6

Late data

Re-pull windows per source (Meta 28 days, GSC 3 days)

Platforms revise recent numbers

Proposed

D7

Slack delivery

DM the reviewer; never post to a client channel

Matches &quot;never auto-sent&quot;

Proposed

D8

Generator contract

Generators declare inputs, required columns, outputs

Platform can check readiness before running

Proposed

D9

Narrative model

Claude Opus 5 by default; test Sonnet 5 as a cheaper option

Low volume; quality matters

Proposed

D10

Metric definitions

One metric dictionary; averages as ratio of sums

Fixes the averaging errors in the current sheet

Proposed

D11

Manifest store field

Remove canonical_store Drive path; store is keyed by brand_id

Store is Postgres, not Drive

Proposed

2. Risk register

Risk

Likelihood

Impact

Mitigation

Search Console history lost beyond 16 months

High if not acted on

No year-on-year comparisons

Start monthly exports now

Windsor does not cover a needed field or channel

Medium

Report gap

CSV fallback per source; direct connector for Meta as the spec allows

Metric definitions disputed after reports ship

Medium

Rework, client confusion

Agree the metric dictionary before Phase 2; notes tab in every report

Review queue neglected

Medium

Runs blocked or wrong tags

Impact ranking, blocking thresholds, daily summary of stale items

Campaign names not following the convention

High

Plan-versus-actual joins fail

Generated names only; unmatched campaigns go to review

OAuth connections expire

Medium

Missing data

Monitor auth_status; alert on change

Personal data from CRM leaks into AI calls or reports

Low

High

Hash lead IDs; never send CRM rows to Claude

Core accumulates report-specific logic

Medium

Platform becomes hard to extend

Review rule: no report names in platform/; checked in Phase 2 exit test

3. Open questions

#

Question

Owner

Needed by

Q1

Exact formula for &quot;Total&quot; engagement rate in the current sheet

Sheet owner

Phase 2

Q2

Engagement definition per platform; does YouTube count views?

Account lead

Phase 2

Q3

Reporting period and average window (12 complete months or including current)

Account lead

Phase 1

Q4

Are boosted posts paid or organic?

Account lead

Phase 2

Q5

Which brands follow Ampere, and which sources do they use?

Founder

Phase 5

Q6

Windsor plan: number of accounts and connectors needed

Tech

Phase 2

Q7

Naming convention and plan taxonomy for media plans

Media team

Phase 5

Q8

Output format per client: xlsx, pptx or Google Sheet?

Account lead

Phase 1

Q9

Blocking threshold for review (starting proposal: 2% of the key metric)

Analyst

Phase 1