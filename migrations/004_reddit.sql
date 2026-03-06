-- Reddit integration: time-series karma tracking.
--
-- Run against an existing database:
--   psql $DATABASE_URL -f migrations/004_reddit.sql

-- ---------------------------------------------------------------------------
-- reddit_profile_metrics
-- Time-series profile-level metrics (karma tracking)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reddit_profile_metrics (
    id               SERIAL PRIMARY KEY,
    account_id       INTEGER REFERENCES marketing_accounts(id) ON DELETE CASCADE,
    post_karma       INTEGER,
    comment_karma    INTEGER,
    total_karma      INTEGER,
    account_age_days INTEGER,
    recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS reddit_profile_metrics_account_idx ON reddit_profile_metrics(account_id);
