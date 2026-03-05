-- LinkedIn integration: platform learnings, post drafts, and profile metrics.
--
-- Run against an existing database:
--   psql $DATABASE_URL -f migrations/003_linkedin.sql

-- ---------------------------------------------------------------------------
-- platform_learnings
-- Dynamic knowledge accumulated from platform interactions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS platform_learnings (
    id          INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    platform    TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    confidence  REAL DEFAULT 0.5,
    learned_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(platform, key)
);

-- ---------------------------------------------------------------------------
-- post_drafts
-- Saved drafts for various post types (text, article, carousel, poll)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS post_drafts (
    id          SERIAL PRIMARY KEY,
    account_id  INTEGER REFERENCES marketing_accounts(id) ON DELETE CASCADE,
    post_type   TEXT NOT NULL DEFAULT 'text',
    title       TEXT,
    content     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS post_drafts_account_idx ON post_drafts(account_id);

-- ---------------------------------------------------------------------------
-- linkedin_profile_metrics
-- Time-series profile-level metrics (views, SSI, followers, connections)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS linkedin_profile_metrics (
    id               SERIAL PRIMARY KEY,
    account_id       INTEGER REFERENCES marketing_accounts(id) ON DELETE CASCADE,
    profile_views    INTEGER,
    ssi_score        INTEGER,
    follower_count   INTEGER,
    connection_count INTEGER,
    recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS linkedin_profile_metrics_account_idx ON linkedin_profile_metrics(account_id);
