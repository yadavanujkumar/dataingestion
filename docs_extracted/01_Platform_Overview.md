# 01_Platform_Overview.docx

HOWL PLATFORM · DOCUMENT 01

Platform Overview

What the HOWL Platform is, the problem it solves, who uses it, and the ideas everything else rests on.

Version 0.1 (draft)  ·  28 September 2026  ·  Prepared for the HOWL tech team  ·  First brand: Ampere

The basics: what the HOWL Platform is, why it is being built, who uses it, and the handful of ideas everything else depends on.

1. What the platform is

The HOWL Platform is an internal reporting engine. A brand is set up on it once. After that, any report the team produces for that brand (a monthly organic search report, a paid social report, an engagement-rate summary, a media-plan performance tracker) is generated on demand from the same underlying data.

The central idea: a report is not built, it is projected. All of a brand&apos;s data is collected, cleaned and stored once in a standard shape. Each report is just a particular view of that store, rendered in the brand&apos;s style. Adding a new report means writing one new generator. It does not mean re-collecting or re-cleaning data.

One-line summary: onboard a brand once, then generate any deliverable for it on demand from one clean, shared store of its data.

2. The problem it solves

Today, each report is typically produced by hand, one at a time:

This causes four recurring problems:

Problem

What it looks like in practice

Repeated work

The same data is pulled and cleaned many times a month, once per report, per brand.

Inconsistent numbers

Two reports for the same brand can show different figures for the same metric because each sheet defines it differently.

Silent errors

Formula mistakes reach clients. In the existing engagement-rate sheet, the &quot;AVG Total&quot; column actually points at the October 2025 column, and some &quot;total&quot; rates exceed 100%. See document 06.

Knowledge in people&apos;s heads

Decisions like &quot;&apos;ampaire&apos; is a misspelling of Ampere&quot; or &quot;this campaign belongs to Magnus G Max&quot; live in individual sheets and are re-made every month.

3. What changes with the platform

Today

With the platform

Data is exported and cleaned for each report

Data is collected and cleaned once, into a shared canonical store

Each sheet has its own formulas

Each metric has one definition, written once in a metric dictionary

Cleanup decisions are re-made monthly

Every decision is recorded in a decision ledger and applied automatically next time

A new report means a new manual process

A new report means registering one generator

Reports take hours

Reports take a command and a short review

Errors are found by clients

Outliers and unplaceable rows stop at a review queue before a report is built

4. Who uses it

Person

What they do on the platform

Account manager

Requests a report for a brand and period, checks the draft, sends it to the client. In Phase 5 they can trigger runs and upload media plans from a Google Sheet without a developer.

Analyst

Works the review queue: resolves the items the system could not classify with confidence. Each decision is remembered.

Developer

Onboards new sources by writing adapters, adds new reports by writing generators, maintains the core.

Client

Receives the finished report. Never interacts with the platform directly.

5. Core concepts

These terms are used throughout the other documents.

Term

Meaning

Brand

A client brand, for example Ampere. The primary key of the whole system: every piece of data belongs to exactly one brand.

Brand manifest

One JSON file per brand. The static half is written at onboarding (identity, sources, deliverables). The learned half grows from reviews (brand-name variants, product roster, launch calendar).

Source

One feed of data for a brand, for example &quot;Ampere&apos;s Meta Ads account&quot;. Each source has a channel, a domain and a mode.

Channel

The platform the data comes from: Meta Ads, Google Ads, GA4, Search Console, LinkedIn, YouTube, HubSpot and so on.

Domain

The kind of data a source feeds: paid media, organic social, web analytics, search/SEO or CRM. Each domain has one standard shape.

Mode

How a source arrives: by API (through Windsor.ai) or by CSV (dropped into a Drive folder). Mode is set per brand, so the same channel can be API for one brand and CSV for another.

Adapter

Code that turns one type of raw source data into the standard shape for its domain. Nothing else reads raw data.

Canonical store

The database where normalized data lives, one set of tables per brand per domain. Every report reads from here.

Classification

Tagging rows with meaning: is this search query branded or generic, which product is this campaign for, is this post paid or organic.

Review queue

The list of items the system could not classify confidently, ranked by impact, for a person to resolve.

Decision ledger

A permanent record of every review decision. The classifier checks it first, so a resolved item never comes back.

Generator

Code that reads the canonical store and the manifest, and produces one kind of report file. One generator per deliverable.

Deliverable

A kind of report, for example gsc_organic_report. A brand&apos;s manifest lists which deliverables it receives.

Run

One execution of the pipeline for one brand, one deliverable and one period.

Metric dictionary

The single written definition of each metric per platform, for example what counts as an &quot;engagement&quot; on LinkedIn.

6. Design principles

These rules come from the build specification. Every design choice in the other documents is checked against them.

7. What the platform is not

8. Benefits

Benefit

Why it follows from the design

Time

Data is cleaned once. Review effort shrinks every month because decisions are remembered.

Consistency

Every report for a brand reads the same numbers with the same metric definitions.

Traceability

Every row records which source file and which run it came from, so any number in a report can be traced back.

Low running cost

Rule-based code has no per-run cost. AI calls are limited to unknowns and cached, so repeated runs cost close to nothing.

Easy growth

A new brand is a new manifest. A new report is a new generator. A new source is a new adapter. None requires changing the core.