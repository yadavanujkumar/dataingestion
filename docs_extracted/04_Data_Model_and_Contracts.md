# 04_Data_Model_and_Contracts.docx

HOWL PLATFORM · DOCUMENT 04

Data Model and Contracts

Manifest, canonical schemas, tables, ledger, generator contract and metric dictionary.

Version 0.1 (draft)  ·  28 September 2026  ·  Prepared for the HOWL tech team  ·  First brand: Ampere

The shapes every part of the platform agrees on: the brand manifest, the canonical schemas, the database tables, the decision ledger, the generator contract and the metric dictionary. Write these first (Phase 0); everything else plugs into them.

1. Brand manifest

One JSON document per brand, stored in the repo (manifests/ampere.json) and loaded into the brands table. It is validated against a JSON Schema on every load, so a typo fails loudly instead of silently changing a report.

Static half (written at onboarding)

{

  &quot;brand_id&quot;: &quot;ampere&quot;,

  &quot;manifest_version&quot;: 1,

  &quot;identity&quot;: {

    &quot;display_name&quot;: &quot;Ampere&quot;,

    &quot;palette&quot;: [&quot;1C2321&quot;, &quot;4E8C2B&quot;],

    &quot;fonts&quot;: { &quot;heading&quot;: &quot;Arial&quot;, &quot;body&quot;: &quot;Arial&quot; },

    &quot;logo_ref&quot;: &quot;drive://HOWL/Ampere/brand/logo.png&quot;,

    &quot;templates&quot;: { &quot;pptx&quot;: &quot;drive://HOWL/Ampere/brand/template.pptx&quot; },

    &quot;voice&quot;: &quot;concise, declarative&quot;

  },

  &quot;sources&quot;: [

    { &quot;source_id&quot;: &quot;ampere-gsc&quot;,

      &quot;channel&quot;: &quot;google_search_console&quot;, &quot;domain&quot;: &quot;search&quot;,

      &quot;mode&quot;: &quot;csv&quot;, &quot;account_ref&quot;: &quot;ampere-electric.com&quot;,

      &quot;schema_ref&quot;: &quot;search_v1&quot;, &quot;cadence&quot;: &quot;monthly&quot;,

      &quot;currency&quot;: null, &quot;timezone&quot;: &quot;Asia/Kolkata&quot;, &quot;auth_status&quot;: &quot;n/a&quot; },

    { &quot;source_id&quot;: &quot;ampere-meta-ads&quot;,

      &quot;channel&quot;: &quot;meta_ads&quot;, &quot;domain&quot;: &quot;paid&quot;,

      &quot;mode&quot;: &quot;windsor_api&quot;, &quot;account_ref&quot;: &quot;act_XXXX&quot;,

      &quot;schema_ref&quot;: &quot;paid_v2&quot;, &quot;cadence&quot;: &quot;daily&quot;,

      &quot;currency&quot;: &quot;INR&quot;, &quot;timezone&quot;: &quot;Asia/Kolkata&quot;, &quot;auth_status&quot;: &quot;active&quot; }

  ],

  &quot;deliverables&quot;: [&quot;gsc_organic_report&quot;, &quot;paid_social_report&quot;,

                   &quot;engagement_rate_report&quot;],

  &quot;review&quot;: { &quot;sheet_ref&quot;: &quot;gsheet://&lt;id&gt;&quot;, &quot;blocking_share&quot;: 0.02 }

}

Changes from the spec: canonical_store is removed (the store is Postgres, keyed by brand_id); source_id, currency, timezone, logo_ref, templates and a review block are added.

Learned half (grown from reviews)

{

  &quot;variant_lists&quot;: { &quot;misspellings&quot;: [&quot;amper&quot;, &quot;ampaire&quot;, &quot;ampair&quot;, &quot;amber&quot;, &quot;empire&quot;] },

  &quot;product_roster&quot;: {

    &quot;tagged&quot;: [&quot;Magnus&quot;, &quot;Magnus G Max&quot;, &quot;Magnus Neo&quot;, &quot;Nexus&quot;, &quot;Reo&quot;, &quot;Reo Vyb&quot;],

    &quot;branded_untagged&quot;: [&quot;Primus&quot;, &quot;Zeal&quot;]

  },

  &quot;launch_calendar&quot;: [

    { &quot;date&quot;: &quot;2026-08-01&quot;, &quot;product&quot;: &quot;Magnus G Max&quot;, &quot;activity&quot;: &quot;awareness&quot; },

    { &quot;date&quot;: &quot;2026-08-01&quot;, &quot;product&quot;: &quot;Reo Vyb&quot;, &quot;activity&quot;: &quot;lead_gen&quot; }

  ],

  &quot;rules&quot;: [

    { &quot;domain&quot;: &quot;search&quot;, &quot;match&quot;: &quot;regex&quot;, &quot;pattern&quot;: &quot;\\b(price|cost)\\b&quot;, &quot;tag&quot;: &quot;generic_theme=pricing&quot; }

  ]

}

Note: &quot;amber&quot; and &quot;empire&quot; are real words. Treat them as misspellings only when they appear together with a product or category term, or they will mis-tag unrelated queries. This is exactly the kind of case the review queue should settle once.

2. Canonical schemas

One shape per domain. Every canonical table also carries the lineage columns brand_id, source_id, run_id and ingested_at. The unique key decides what counts as &quot;the same row&quot; for upserts.

Domain / version

Columns

Unique key

search_v1

period, query, page (optional), impressions, clicks, ctr, position, is_branded, brand_form, product, generic_theme, needs_review, tag_source

brand_id, period, query, page

paid_v2

date, channel, campaign, adset, ad, spend, currency, impressions, reach, clicks, engagements, video_views, conversions, revenue, utm_source, utm_medium, utm_campaign, utm_content, is_boosted_post

brand_id, date, channel, campaign, adset, ad

organic_v1

date, channel, post_id, post_type, published_at, reach, impressions, engagements, video_views, followers

brand_id, date, channel, post_id

web_v1

date, source, medium, campaign, landing_page, sessions, engaged_sessions, users, conversions

brand_id, date, source, medium, campaign, landing_page

crm_v1

date, lead_id (hashed), stage, source, campaign, value, currency, status

brand_id, lead_id, stage

plan_v1

plan_id, campaign, adset, ad, utm_*, planned_spend, planned_impressions, start_date, end_date

brand_id, plan_id, campaign, adset, ad

Versioning rules

Adding a column creates a new version (paid_v1 → paid_v2). New columns are nullable, so older adapters keep working.

Columns are never renamed or removed within a major version.

A source&apos;s schema_ref says which version its adapter writes.

paid_v2 exists because the engagement-rate report needed engagements, reach, video_views and is_boosted_post, which the spec&apos;s paid schema lacked.

Late-arriving data

Platforms revise recent numbers. Each source re-pulls a window on every run and upserts over it: Meta Ads 28 days, Google Ads 14 days, LinkedIn Ads 14 days, Search Console 3 days, GA4 3 days. Tune these once real revision patterns are observed.

3. Database tables

Table

Purpose

Key columns

brands

The manifest (static and learned halves) per brand

brand_id, manifest jsonb, learned jsonb, manifest_version

sources

One row per brand source, mirrored from the manifest

source_id, brand_id, channel, domain, mode, schema_ref, auth_status

runs

One row per run with its current stage and status

run_id, brand_id, deliverable, period, status, stage, started_at, row_counts jsonb

raw_files

Every raw file received, unchanged

file_id, source_id, run_id, sha256, storage_ref, received_at

canonical_&lt;domain&gt;

Normalized rows per domain (search, paid, organic, web, crm, plan)

See section 2

review_items

Items waiting for a person

item_id, brand_id, run_id, entity_type, entity_key, impact, reason, suggestion, status

decision_ledger

Every decision, append-only

See section 4

ai_labels

Cache of AI answers

brand_id, entity_type, entity_key, prompt_version, model, label, confidence, created_at

outputs

Every draft produced and where it went

output_id, run_id, generator, generator_version, file_ref, delivered_to

4. Decision ledger

Field

Type

Notes

decision_id

uuid

Primary key

brand_id

text

entity_type

text

query, campaign, post, record, file

entity_key

text

Normalized: lower-case, trimmed, single spaces

decision

text

reclassify, fix, exclude, ignore

value

jsonb

The tag or correction, e.g. {&quot;is_branded&quot;: true, &quot;product&quot;: &quot;Reo Vyb&quot;}

reason

text

Short free text; required for exclude

supersedes

uuid

Earlier decision this replaces, if any

decided_by

text

Person&apos;s email

decided_at

timestamptz

The ledger is shared across brands but always queried by brand_id. The current decision for an entity is the latest one not superseded by another.

5. Generator contract

Every generator declares what it needs and what it makes. The platform reads the declaration to check a brand is ready before running, and to build the right ingestion plan.

from dataclasses import dataclass

 

@dataclass(frozen=True)

class Requirement:

    domain: str                # &quot;paid&quot;

    min_version: str           # &quot;paid_v2&quot;

    columns: tuple[str, ...]   # (&quot;impressions&quot;, &quot;engagements&quot;)

 

@dataclass(frozen=True)

class GeneratorSpec:

    name: str                  # &quot;engagement_rate_report&quot;

    version: str               # &quot;1.0.0&quot;

    requires: tuple[Requirement, ...]

    outputs: tuple[str, ...]   # (&quot;xlsx&quot;,)

    blocking_checks: tuple[str, ...]   # (&quot;rate_over_100&quot;, &quot;vs_platform_totals&quot;)

    uses_narrative: bool = False

 

class Generator:

    spec: GeneratorSpec

    def build(self, brand, period, data, out_dir) -&gt; list[str]:

        &quot;&quot;&quot;Read only from `data` (canonical rows) and `brand` (manifest).

        Return the paths of the files written. Must be deterministic.&quot;&quot;&quot;

Rules: a generator never reads a raw source, never writes to canonical tables, and produces the same output for the same inputs and version. Each generator has a golden-file test.

6. Metric dictionary

Each metric is defined once per platform in the manifest (or a shared default), so every report computes it the same way.

&quot;metrics&quot;: {

  &quot;engagement_rate&quot;: {

    &quot;formula&quot;: &quot;sum(engagements) / sum(impressions)&quot;,

    &quot;engagements&quot;: {

      &quot;meta_ads&quot;:       &quot;post_engagement&quot;,

      &quot;instagram&quot;:      &quot;likes + comments + shares + saves&quot;,

      &quot;facebook&quot;:       &quot;reactions + comments + shares&quot;,

      &quot;youtube_ads&quot;:    &quot;engagements&quot;,

      &quot;youtube&quot;:        &quot;likes + comments + shares&quot;,

      &quot;linkedin_ads&quot;:   &quot;total_engagements&quot;,

      &quot;linkedin&quot;:       &quot;clicks + reactions + comments + shares&quot;

    },

    &quot;denominator&quot;: { &quot;default&quot;: &quot;impressions&quot;, &quot;youtube&quot;: &quot;views&quot; },

    &quot;aggregate&quot;: &quot;ratio_of_sums&quot;,

    &quot;flag_if_above&quot;: 1.0

  }

}

ratio_of_sums means averages across months are computed as total engagements divided by total impressions, never as an average of monthly percentages. Confirm the exact field names against the Windsor connector field lists before building.

7. Drive folder layout

HOWL/

  Ampere/

    brand/            logo, templates

    inbox/

      google_search_console/   drop CSV exports here

      meta_business_suite/

    outputs/

      gsc_organic_report/2026-08/

    review/           the brand&apos;s review Sheet