"""Semantic memory store with Postgres/pgvector persistence."""

import json
from datetime import datetime, timezone
from typing import Any

from src.db import Database
from src.embeddings import EmbeddingClient


class MemoryStore:
    """Persistent semantic memory using Postgres + pgvector.

    Stores text content with embedding vectors and optional tags.
    Supports hybrid search: pgvector cosine similarity + tsvector keyword bonus.
    """

    def __init__(self, db: Database, embedding_client: EmbeddingClient, dimensions: int = 3072) -> None:
        self._embedding_client = embedding_client
        self._db = db
        self._dimensions = dimensions
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS memories (
                        id SERIAL PRIMARY KEY,
                        content TEXT NOT NULL,
                        embedding vector({self._dimensions}) NOT NULL,
                        tags TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        search_vector tsvector GENERATED ALWAYS AS (
                            to_tsvector('english', content || ' ' || tags)
                        ) STORED
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS memories_embedding_idx
                        ON memories USING hnsw (embedding vector_cosine_ops)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS memories_search_idx
                        ON memories USING GIN (search_vector)
                """)
            conn.commit()
        finally:
            self._db.put_connection(conn)

    def add(self, content: str, tags: list[str] | None = None) -> int:
        """Store a memory with its embedding.

        Args:
            content: The text content to remember.
            tags: Optional list of tags for categorization.

        Returns:
            The ID of the stored memory.
        """
        vectors = self._embedding_client.embed([content])
        embedding_str = json.dumps(vectors[0])
        tags_str = ",".join(tags) if tags else ""
        now = datetime.now(timezone.utc).isoformat()

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO memories (content, embedding, tags, created_at) VALUES (%s, %s::vector, %s, %s) RETURNING id",
                    (content, embedding_str, tags_str, now),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Hybrid search: pgvector cosine similarity + tsvector keyword matching.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results to return.

        Returns:
            List of memory dicts sorted by relevance, each with keys:
            id, content, tags, created_at, score.
        """
        query_vector = self._embedding_client.embed([query])[0]
        query_embedding_str = json.dumps(query_vector)

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, content, tags, created_at,
                              1 - (embedding <=> %s::vector) AS semantic_score,
                              CASE WHEN search_vector @@ plainto_tsquery('english', %s)
                                   THEN 0.1 ELSE 0.0 END AS fts_bonus
                       FROM memories
                       ORDER BY semantic_score + fts_bonus DESC
                       LIMIT %s""",
                    (query_embedding_str, query, top_k),
                )
                rows = cur.fetchall()
            return [
                {
                    "id": row["id"],
                    "content": row["content"],
                    "tags": [t for t in row["tags"].split(",") if t],
                    "created_at": row["created_at"],
                    "score": round(float(row["semantic_score"]) + float(row["fts_bonus"]), 4),
                }
                for row in rows
            ]
        finally:
            self._db.put_connection(conn)

    def delete(self, memory_id: int) -> bool:
        """Delete a memory by ID.

        Returns:
            True if a memory was deleted, False if ID not found.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM memories WHERE id = %s", (memory_id,)
                )
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self._db.put_connection(conn)

    def count(self) -> int:
        """Return the total number of stored memories."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM memories")
                row = cur.fetchone()
            return row["cnt"]
        finally:
            self._db.put_connection(conn)

    def close(self) -> None:
        """No-op — connection pool is managed by Database."""
