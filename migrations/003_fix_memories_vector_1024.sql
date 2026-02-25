-- Migration 003: Fix memories vector dimensions (1536 → 1024)
--
-- Run this if you already ran migration 001 or 002.
-- Supported dimensions for the configured embedding model: 256, 1024, 3072.
-- 1024 is the largest that fits within the pgvector HNSW limit (max 2000).

-- Fix memories vector dimension
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'memories'
      AND column_name = 'embedding'
  ) THEN
    RAISE NOTICE 'Dropping and recreating memories table with vector(1024)...';

    DROP TABLE IF EXISTS memories;

    CREATE TABLE memories (
      id          SERIAL PRIMARY KEY,
      content     TEXT NOT NULL,
      embedding   vector(1024) NOT NULL,
      metadata    JSONB DEFAULT '{}',
      created_at  TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX memories_embedding_hnsw_idx
      ON memories USING hnsw (embedding vector_cosine_ops);

    CREATE INDEX memories_content_fts_idx
      ON memories USING gin (to_tsvector('english', content));

    RAISE NOTICE 'memories table recreated with vector(1024).';
  ELSE
    RAISE NOTICE 'memories table not found, skipping dimension fix.';
  END IF;
END
$$;