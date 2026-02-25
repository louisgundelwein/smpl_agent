-- Initial Postgres schema for smpl_agent
-- Migrates all stores from SQLite to Postgres + pgvector.
--
-- Run once against a fresh Postgres database:
--   psql $DATABASE_URL -f migrations/001_initial.sql

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- memories
-- Semantic memory store (pgvector + full-text search)
-- Default embedding dimensions match text-embedding-3-large (3072).
-- Override EMBEDDING_DIMENSIONS in .env if using a different model.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS memories (
    id          SERIAL PRIMARY KEY,
    content     TEXT    NOT NULL,
    embedding   vector(3072) NOT NULL,
    tags        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', content || ' ' || tags)
    ) STORED
);

CREATE INDEX IF NOT EXISTS memories_embedding_idx
    ON memories USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS memories_search_idx
    ON memories USING GIN (search_vector);

-- ---------------------------------------------------------------------------
-- schedules
-- Recurring task engine (cron-based scheduler)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS schedules (
    id                SERIAL PRIMARY KEY,
    name              TEXT    NOT NULL UNIQUE,
    prompt            TEXT    NOT NULL,
    cron_expression   TEXT    NOT NULL,
    enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    deliver_to        TEXT    NOT NULL DEFAULT 'memory',
    telegram_chat_id  BIGINT,
    last_run_at       TEXT,
    next_run_at       TEXT    NOT NULL,
    created_at        TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- connections
-- CalDAV connection registry
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS connections (
    id          SERIAL PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    url         TEXT    NOT NULL,
    username    TEXT    NOT NULL,
    password    TEXT    NOT NULL,
    provider    TEXT    NOT NULL DEFAULT 'caldav',
    added_at    TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- accounts
-- Email account registry (IMAP / SMTP)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS accounts (
    id              SERIAL PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    email_address   TEXT    NOT NULL,
    password        TEXT    NOT NULL,
    imap_host       TEXT    NOT NULL,
    imap_port       INTEGER NOT NULL DEFAULT 993,
    smtp_host       TEXT    NOT NULL,
    smtp_port       INTEGER NOT NULL DEFAULT 587,
    provider        TEXT    NOT NULL DEFAULT 'generic',
    added_at        TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- repos
-- Repository registry
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS repos (
    id              SERIAL PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    owner           TEXT    NOT NULL,
    repo            TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    default_branch  TEXT    NOT NULL DEFAULT 'main',
    description     TEXT    NOT NULL DEFAULT '',
    tags            TEXT    NOT NULL DEFAULT '',
    added_at        TEXT    NOT NULL
);
