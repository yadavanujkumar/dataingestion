-- HOWL Platform - Initial Schema Migration (001_initial_schema.sql)
-- Target: PostgreSQL / Supabase
-- Covers Document 04 Sections 2, 3, 4

-- 1. Brands Table
CREATE TABLE IF NOT EXISTS brands (
    brand_id TEXT PRIMARY KEY,
    manifest JSONB NOT NULL,
    learned JSONB NOT NULL DEFAULT '{}'::jsonb,
    manifest_version INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Sources Table
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    domain TEXT NOT NULL,
    mode TEXT NOT NULL,
    schema_ref TEXT NOT NULL,
    auth_status TEXT NOT NULL DEFAULT 'active',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sources_brand ON sources(brand_id);

-- 3. Runs Table
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    deliverable TEXT NOT NULL,
    period TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    stage TEXT NOT NULL DEFAULT 'trigger',
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    row_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_brand_period ON runs(brand_id, period);

-- 4. Raw Files Table
CREATE TABLE IF NOT EXISTS raw_files (
    file_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    run_id TEXT,
    sha256 TEXT NOT NULL,
    storage_ref TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_raw_files_sha256 ON raw_files(sha256);

-- 5. Canonical Search Table (search_v1)
CREATE TABLE IF NOT EXISTS canonical_search (
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    query TEXT NOT NULL,
    page TEXT NOT NULL DEFAULT '',
    impressions BIGINT NOT NULL DEFAULT 0,
    clicks BIGINT NOT NULL DEFAULT 0,
    ctr DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    position DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    is_branded BOOLEAN NOT NULL DEFAULT FALSE,
    brand_form TEXT,
    product TEXT,
    generic_theme TEXT,
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    tag_source TEXT NOT NULL DEFAULT 'unclassified',
    source_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (brand_id, period, query, page)
);
CREATE INDEX IF NOT EXISTS idx_canonical_search_period ON canonical_search(brand_id, period);
CREATE INDEX IF NOT EXISTS idx_canonical_search_review ON canonical_search(brand_id, needs_review);

-- 6. Canonical Paid Table (paid_v2)
CREATE TABLE IF NOT EXISTS canonical_paid (
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    channel TEXT NOT NULL,
    campaign TEXT NOT NULL,
    adset TEXT NOT NULL DEFAULT '',
    ad TEXT NOT NULL DEFAULT '',
    spend DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    currency TEXT NOT NULL DEFAULT 'INR',
    impressions BIGINT NOT NULL DEFAULT 0,
    reach BIGINT,
    clicks BIGINT NOT NULL DEFAULT 0,
    engagements BIGINT,
    video_views BIGINT,
    conversions DOUBLE PRECISION,
    revenue DOUBLE PRECISION,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    utm_content TEXT,
    is_boosted_post BOOLEAN NOT NULL DEFAULT FALSE,
    source_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (brand_id, date, channel, campaign, adset, ad)
);
CREATE INDEX IF NOT EXISTS idx_canonical_paid_date ON canonical_paid(brand_id, date);

-- 7. Canonical Organic Table (organic_v1)
CREATE TABLE IF NOT EXISTS canonical_organic (
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    channel TEXT NOT NULL,
    post_id TEXT NOT NULL,
    post_type TEXT,
    published_at TIMESTAMPTZ,
    reach BIGINT,
    impressions BIGINT NOT NULL DEFAULT 0,
    engagements BIGINT NOT NULL DEFAULT 0,
    video_views BIGINT,
    followers BIGINT,
    source_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (brand_id, date, channel, post_id)
);
CREATE INDEX IF NOT EXISTS idx_canonical_organic_date ON canonical_organic(brand_id, date);

-- 8. Canonical Web Table (web_v1)
CREATE TABLE IF NOT EXISTS canonical_web (
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    source TEXT NOT NULL,
    medium TEXT NOT NULL,
    campaign TEXT NOT NULL,
    landing_page TEXT NOT NULL,
    sessions BIGINT NOT NULL DEFAULT 0,
    engaged_sessions BIGINT,
    users BIGINT,
    conversions DOUBLE PRECISION,
    source_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (brand_id, date, source, medium, campaign, landing_page)
);

-- 9. Canonical CRM Table (crm_v1)
CREATE TABLE IF NOT EXISTS canonical_crm (
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    lead_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    source TEXT,
    campaign TEXT,
    value DOUBLE PRECISION,
    currency TEXT,
    status TEXT,
    source_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (brand_id, lead_id, stage)
);

-- 10. Canonical Plan Table (plan_v1)
CREATE TABLE IF NOT EXISTS canonical_plan (
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL,
    campaign TEXT NOT NULL,
    adset TEXT NOT NULL DEFAULT '',
    ad TEXT NOT NULL DEFAULT '',
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    utm_content TEXT,
    planned_spend DOUBLE PRECISION,
    planned_impressions BIGINT,
    start_date DATE,
    end_date DATE,
    source_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (brand_id, plan_id, campaign, adset, ad)
);

-- 11. Review Items Table
CREATE TABLE IF NOT EXISTS review_items (
    item_id TEXT PRIMARY KEY,
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    run_id TEXT,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    impact DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    reason TEXT NOT NULL,
    suggestion JSONB,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_review_items_brand_status ON review_items(brand_id, status);
CREATE INDEX IF NOT EXISTS idx_review_items_impact ON review_items(impact DESC);

-- 12. Decision Ledger Table
CREATE TABLE IF NOT EXISTS decision_ledger (
    decision_id TEXT PRIMARY KEY,
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    decision TEXT NOT NULL,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT,
    supersedes TEXT REFERENCES decision_ledger(decision_id),
    decided_by TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_decision_ledger_lookup ON decision_ledger(brand_id, entity_type, entity_key);

-- 13. AI Labels Table
CREATE TABLE IF NOT EXISTS ai_labels (
    label_id TEXT PRIMARY KEY,
    brand_id TEXT NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    label JSONB NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_labels_unique ON ai_labels(brand_id, entity_type, entity_key, prompt_version);

-- 14. Outputs Table
CREATE TABLE IF NOT EXISTS outputs (
    output_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    generator TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    file_ref TEXT NOT NULL,
    delivered_to TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_outputs_run ON outputs(run_id);
