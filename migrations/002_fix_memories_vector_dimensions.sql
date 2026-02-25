-- Fix memories table: reduce vector dimensions 3072 → 1536.
--
-- pgvector's HNSW index supports a maximum of 2000 dimensions.
-- text-embedding-3-large natively supports 1536 via the dimensions= API param,
-- which keeps quality high while staying within the index limit.
--
-- Run this if you already ran 001_initial.sql:
--   psql $DATABASE_URL -f migrations/002_fix_memories_vector_dimensions.sql

-- Drop the table (no data yet since the app hasn't run with the old schema)
DROP TABLE IF EXISTS memories;

-- Recreate with 1536 dimensions
CREATE TABLE memories (
    id          SERIAL PRIMARY KEY,
    content     TEXT    NOT NULL,
    embedding   vector(1536) NOT NULL,
    tags        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', content || ' ' || tags)
    ) STORED
);

CREATE INDEX memories_embedding_idx
    ON memories USING hnsw (embedding vector_cosine_ops);

CREATE INDEX memories_search_idx
    ON memories USING GIN (search_vector);
