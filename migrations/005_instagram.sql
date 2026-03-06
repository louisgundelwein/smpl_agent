-- Instagram integration: time-series profile tracking.
--
-- Run against an existing database:
--   psql $DATABASE_URL -f migrations/005_instagram.sql

-- ---------------------------------------------------------------------------
-- instagram_profile_metrics
-- Time-series profile-level metrics (followers, engagement tracking)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS instagram_profile_metrics (
    id               SERIAL PRIMARY KEY,
    account_id       INTEGER REFERENCES marketing_accounts(id) ON DELETE CASCADE,
    followers        INTEGER,
    following        INTEGER,
    posts_count      INTEGER,
    engagement_rate  REAL,
    recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS instagram_profile_metrics_account_idx
    ON instagram_profile_metrics(account_id);
