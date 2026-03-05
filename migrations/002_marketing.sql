-- Marketing tables: accounts, posts, and engagement metrics.
--
-- Run against an existing database:
--   psql $DATABASE_URL -f migrations/002_marketing.sql

-- ---------------------------------------------------------------------------
-- marketing_accounts
-- Platform login credentials and configuration
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS marketing_accounts (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    platform    TEXT NOT NULL,
    credentials JSONB NOT NULL DEFAULT '{}',
    config      JSONB NOT NULL DEFAULT '{}',
    added_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- marketing_posts
-- Every post ever made across all platforms
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS marketing_posts (
    id               SERIAL PRIMARY KEY,
    account_name     TEXT NOT NULL,
    platform         TEXT NOT NULL,
    campaign         TEXT,
    title            TEXT,
    content          TEXT NOT NULL,
    url              TEXT,
    image_path       TEXT,
    platform_post_id TEXT,
    subreddit        TEXT,
    status           TEXT NOT NULL DEFAULT 'draft',
    error_message    TEXT,
    posted_at        TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS marketing_posts_account_idx ON marketing_posts(account_name);
CREATE INDEX IF NOT EXISTS marketing_posts_platform_idx ON marketing_posts(platform);
CREATE INDEX IF NOT EXISTS marketing_posts_campaign_idx ON marketing_posts(campaign);

-- ---------------------------------------------------------------------------
-- marketing_metrics
-- Engagement snapshots (time-series)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS marketing_metrics (
    id          SERIAL PRIMARY KEY,
    post_id     INTEGER NOT NULL REFERENCES marketing_posts(id) ON DELETE CASCADE,
    likes       INTEGER DEFAULT 0,
    comments    INTEGER DEFAULT 0,
    shares      INTEGER DEFAULT 0,
    views       INTEGER DEFAULT 0,
    extra       JSONB DEFAULT '{}',
    fetched_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS marketing_metrics_post_idx ON marketing_metrics(post_id);
